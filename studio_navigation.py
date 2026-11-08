"""Local semantic PDF locations layered over SyncTeX; no network operations."""
from functools import lru_cache
from pathlib import Path
import json,math,re
from pypdf import PdfReader

def read_sources(root):
    from studio_page_edits import project_files
    result={};total=0
    for p in project_files(root):
        if p.suffix.lower() not in {'.tex','.bib'}:continue
        if p.stat().st_size>2_000_000:raise ValueError('源码文件超过定位分析上限')
        text=p.read_text('utf-8-sig',errors='replace');total+=len(text)
        if total>8_000_000:raise ValueError('项目文本超过定位分析上限')
        result[p.relative_to(root).as_posix()]=text
    return result

def read_aux_anchors(folder):
    from studio_review import group
    result={};total=0
    for file in list(Path(folder).rglob('*.aux'))[:200]:
        if file.is_symlink() or file.stat().st_size>2_000_000:continue
        text=file.read_text('utf8',errors='replace');total+=len(text)
        if total>8_000_000:break
        for match in re.finditer(r'\\newlabel\s*',text):
            key=group(text,match.end())
            if not key:continue
            body=group(text,key[1])
            if not body:continue
            parts=[];cursor=0
            while (item:=group(body[0],cursor)) is not None:
                parts.append(item[0]);cursor=item[1]
            if len(parts)>=4 and parts[3]:result[key[0]]={'number':parts[0],'pageLabel':parts[1],'title':parts[2],'anchor':parts[3]}
    return result

def _norm(page,rect):
    box=page.cropbox;w=float(box.width);h=float(box.height);l,b,r,t=map(float,rect)
    points=[((x-float(box.left))/w,(float(box.top)-y)/h) for x,y in [(l,b),(l,t),(r,b),(r,t)]]
    rotation=int(page.rotation or 0)%360
    if rotation==90:points=[(1-y,x) for x,y in points]
    elif rotation==180:points=[(1-x,1-y) for x,y in points]
    elif rotation==270:points=[(y,1-x) for x,y in points]
    return [max(0,min(1,min(x for x,y in points))),max(0,min(1,min(y for x,y in points))),max(0,min(1,max(x for x,y in points))),max(0,min(1,max(y for x,y in points)))]

def _point_for(points,loc):
    choices=[p for p in points if p['path']==loc['file']]
    return min(choices,key=lambda p:(abs(p['line']-loc['line']),p['page'],p['y'])) if choices else None

@lru_cache(maxsize=3)
def _index(root_name,pdf_name,version,main,anchors_json,sources_key):
    from studio_review import analyze_references
    root=Path(root_name);sources=read_sources(root);report=analyze_references(sources,main);entries=report['catalog'];reader=PdfReader(pdf_name)
    destinations={};named=reader.named_destinations
    for name,dest in named.items():
        try:
            n=reader.get_destination_page_number(dest);page=reader.pages[n];left=dest.left;top=dest.top
            if not isinstance(left,(float,int)):left=float(page.cropbox.left)+float(page.cropbox.width)*.07
            if not isinstance(top,(float,int)):top=float(page.cropbox.top)
            bbox=_norm(page,[left,top-14,float(page.cropbox.right)-25,top+3]);destinations[name]={'page':n+1,'bbox':bbox,'x':bbox[0],'y':bbox[1]}
        except (TypeError,ValueError,AttributeError,IndexError):continue
    anchors=json.loads(anchors_json);anchor_keys={};regions=[]
    for kind in ['labels','bibliography']:
        for entry in entries[kind]:
            key=entry['key'];name=anchors.get(key,{}).get('anchor') if kind=='labels' else next((name for name in destinations if name=='cite.'+key or name.endswith('@'+key)),None)
            if not name and key in destinations:name=key
            if name not in destinations:continue
            point=destinations[name];anchor_keys[name]=(kind,key)
            bbox=list(point['bbox'])
            if kind=='bibliography':
                below=[p['bbox'][1] for name2,p in destinations.items() if name2!=name and name2.startswith(('cite.','bib.')) and p['page']==point['page'] and p['bbox'][1]>bbox[1]+.005]
                bbox[0]=.05;bbox[2]=.96;bbox[3]=min(1,min(below)-.004 if below else bbox[1]+.09)
            regions.append({**point,'bbox':bbox,'path':entry['file'],'line':entry['line'],'column':entry.get('column',1),'match':entry.get('match',''),'raw':entry.get('raw',''),
                'key':key,'kind':kind,'method':'destination','approximate':False,'anchor':name})
    links=[]
    for n,page in enumerate(reader.pages,1):
        for raw in page.get('/Annots',[]):
            try:
                annotation=raw.get_object()
                if annotation.get('/Subtype')!='/Link':continue
                action=annotation.get('/A',{});action=action.get_object() if hasattr(action,'get_object') else action;target=annotation.get('/Dest') or action.get('/D')
                if not isinstance(target,str) or target not in anchor_keys:continue
                kind,key=anchor_keys[target];bbox=_norm(page,annotation['/Rect']);links.append({'page':n,'bbox':bbox,'x':bbox[0],'y':bbox[1],'key':key,'targetKind':kind,'target':target})
            except (TypeError,ValueError,KeyError,AttributeError):continue
    return {'catalog':entries,'sources':sources,'destinations':destinations,'regions':regions,'links':links}

def _data(root,pdf,meta):
    return _index(str(root),str(pdf),str(Path(pdf).stat().st_mtime_ns),meta.get('main') or 'main.tex',json.dumps(meta.get('anchors',{}),sort_keys=True),tuple(sorted(meta['sources'].items())))

def _line_box(point,points,sizes):
    same=[p for p in points if p['path']==point['path'] and p['line']==point['line'] and p['page']==point['page'] and abs(p['y']-point['y'])<.012]
    return [max(0,min(p['x'] for p in same)-.005),max(0,point['y']-12/sizes[point['page']-1][1]),min(1,max(max(p['x'] for p in same)+.015,point['x']+.03)),min(1,point['y']+.006)]

def _lookup_entry(data,query):
    kind=query.get('kind');key=query.get('key');path=query.get('path');line=int(query.get('line',1))
    if kind not in {'labels','bibliography','references','citations'} or not key:return None
    matches=[e for e in data['catalog'][kind] if e['key']==key and (not path or e['file']==path)]
    return min(matches,key=lambda e:(abs(e['line']-line),abs(e.get('column',1)-int(query.get('column',1))))) if matches else None

def _entry_at_source(data,path,line,column):
    for kind in ['references','citations','labels','bibliography']:
        choices=[]
        for entry in data['catalog'][kind]:
            if entry['file']!=path:continue
            if kind=='bibliography' and entry['line']<=line<=entry.get('endLine',entry['line']):choices.append(entry);continue
            length=len(entry.get('match','').encode('utf-16-le'))//2
            if entry['line']==line and entry.get('column',1)<=column<=entry.get('column',1)+length:choices.append(entry)
        if choices:return min(choices,key=lambda e:abs(e.get('column',1)-column))
    return None

def _text_box(pdf,needle,page_numbers):
    if len(needle)<4:return None
    import pypdfium2 as pdfium
    document=pdfium.PdfDocument(str(pdf));matches=[]
    try:
        for n in page_numbers:
            page=document[n-1];text=page.get_textpage();search=text.search(needle)
            try:
                while (found:=search.get_next()) is not None:
                    start,count=found;boxes=[text.get_charbox(i) for i in range(start,start+count)]
                    l=min(b[0] for b in boxes);b=min(b[1] for b in boxes);r=max(b[2] for b in boxes);t=max(b[3] for b in boxes);w,h=page.get_size();bbox=[max(0,l/w),max(0,1-t/h),min(1,r/w),min(1,1-b/h)]
                    matches.append({'page':n,'x':bbox[0],'y':bbox[1],'bbox':bbox})
                    if len(matches)>1:return None
            finally:search.close();text.close();page.close()
    finally:document.close()
    return matches[0] if len(matches)==1 else None

def _usage_for_link(data,points,link,kind):
    usages=[]
    for loc in data['catalog'][kind]:
        if loc['key']!=link['key']:continue
        point=_point_for(points,loc)
        if point and point['page']==link['page']:usages.append(loc)
    links=sorted([r for r in data['links'] if r['key']==link['key'] and r['targetKind']==link['targetKind'] and r['page']==link['page']],key=lambda r:(round(r['y'],2),r['x']))
    usages.sort(key=lambda r:(r['file'],r['line'],r.get('column',1)))
    if len(links)==len(usages) and usages:return usages[links.index(link)]
    return min(usages,key=lambda loc:abs(_point_for(points,loc)['y']-link['y'])) if usages else None

def locate_precise(root,pdf,meta,sizes,points,query):
    from studio_storage import project_id
    direction=query.get('direction','inverse');data=_data(root,pdf,meta)
    if direction not in {'forward','inverse'}:raise ValueError('定位方向无效')
    if direction=='forward':
        path=str(query.get('path',''));line=int(query.get('line',1));entry=_lookup_entry(data,query)
        if not query.get('key'):entry=_entry_at_source(data,path,line,int(query.get('column',1)))
        if query.get('key') and not entry:raise ValueError('该条目已变化，请重新检查引用')
        if entry:
            if entry.get('duplicate'):raise ValueError('此键存在重复定义，请先确认定义再定位 PDF')
            if entry['kind'] in {'labels','bibliography'}:
                region=next((r for r in data['regions'] if r['kind']==entry['kind'] and r['key']==entry['key']),None)
                if region:return {**region,'projectId':project_id(root)}
            else:
                links=[r for r in data['links'] if r['key']==entry['key'] and r['targetKind']==('labels' if entry['kind']=='references' else 'bibliography')]
                hint=_point_for(points,entry)
                if links and hint:
                    region=next((r for r in links if (_usage_for_link(data,points,r,entry['kind']) or {}).get('id')==entry.get('id')),None) or min(links,key=lambda r:(abs(r['page']-hint['page']),abs(r['y']-hint['y'])))
                    return {**region,'path':entry['file'],'line':entry['line'],'column':entry.get('column',1),'match':entry.get('match',''),'kind':entry['kind'],'method':'pdf-link','approximate':False,'projectId':project_id(root)}
        choices=[p for p in points if p['path']==path]
        point=min(choices,key=lambda p:(abs(p['line']-line),p['page'],p['y'])) if choices else None
        if entry and entry['kind']=='bibliography':
            from studio_references import plain
            needle=entry.get('fields',{}).get('title') or plain(re.sub(r'^\\bibitem\s*(?:\[[^\]]*\])?\{[^}]+\}','',entry['raw']))
            found=_text_box(pdf,needle[:30],range(1,len(sizes)+1))
            if found:return {**found,'path':path,'line':line,'column':entry.get('column',1),'key':entry['key'],'kind':entry['kind'],'match':entry.get('match',''),'method':'text','approximate':False,'projectId':project_id(root)}
            raise ValueError('当前 PDF 中未找到此文献条目；请确认已编译且该条目确实输出')
        if not point:raise ValueError('此文件没有可用的 PDF 定位信息')
        needle=str(query.get('text',''))[:160].strip()
        if needle:
            found=_text_box(pdf,needle,[point['page']])
            if found:return {**found,'path':path,'line':line,'column':int(query.get('column',1)),'method':'text','approximate':False,'projectId':project_id(root)}
        return {**point,'bbox':_line_box(point,points,sizes),'column':int(query.get('column',1)),'method':'synctex','approximate':True,'projectId':project_id(root)}
    n=int(query.get('page',0));x=float(query.get('x',0));y=float(query.get('y',0))
    if not 1<=n<=len(sizes) or not math.isfinite(x+y) or not 0<=x<=1 or not 0<=y<=1:raise ValueError('页面坐标无效')
    hits=[r for r in data['links']+data['regions'] if r['page']==n and r['bbox'][0]-.003<=x<=r['bbox'][2]+.003 and r['bbox'][1]-.003<=y<=r['bbox'][3]+.003]
    if hits:
        hit=min(hits,key=lambda r:(r['bbox'][2]-r['bbox'][0])*(r['bbox'][3]-r['bbox'][1]))
        if 'path' in hit:return {**hit,'projectId':project_id(root)}
        kind='references' if hit['targetKind']=='labels' else 'citations';usages=[e for e in data['catalog'][kind] if e['key']==hit['key']]
        loc=_usage_for_link(data,points,hit,kind) or next((r for r in data['regions'] if r['key']==hit['key'] and r['kind']==hit['targetKind']),None)
        if loc:
            return {**hit,'path':loc.get('file',loc.get('path')),'line':loc['line'],'column':loc.get('column',1),'match':loc.get('match',''),'raw':loc.get('raw',''),'kind':kind,'method':'pdf-link','approximate':False,'projectId':project_id(root)}
    choices=[p for p in points if p['page']==n]
    if not choices:raise ValueError('这一页没有可定位的源码')
    point=min(choices,key=lambda p:(p['y']-y)**2*4+(p['x']-x)**2)
    return {**point,'bbox':_line_box(point,points,sizes),'column':1,'method':'synctex','approximate':True,'projectId':project_id(root)}
