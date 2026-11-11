"""Content-aligned PDF changes, independent of pagination; no model calls."""
import difflib,re,unicodedata
from studio_page_edits import sha
from studio_storage import read_json,write_json

def words(path):
    import pdfplumber
    result=[];pages=0
    with pdfplumber.open(path) as pdf:
        pages=len(pdf.pages)
        for n,page in enumerate(pdf.pages,1):
            for word in page.extract_words():
                text=unicodedata.normalize('NFKC',word['text']).strip()
                if not text:continue
                if text.isdigit() and len(text)<=4 and word['top']/page.height>.84 and .4<(word['x0']+word['x1'])/2/page.width<.6:continue
                result.append({'text':text,'page':n,'box':[word['x0']/page.width,word['top']/page.height,word['x1']/page.width,word['bottom']/page.height]})
                if len(result)>40000:raise ValueError('对比内容较多，请使用源码差异查看具体修改')
    return result,pages

def regions(tokens):
    groups={}
    for token in tokens:
        page=token['page'];groups.setdefault(page,[]).append(token)
    result=[]
    for page,items in groups.items():
        boxes=[]
        for item in items:
            box=item['box']
            if boxes and abs(box[1]-boxes[-1][1])<.012:
                old=boxes[-1];boxes[-1]=[min(old[0],box[0]),min(old[1],box[1]),max(old[2],box[2]),max(old[3],box[3])]
            else:boxes.append(list(box))
        result.append({'page':page,'boxes':boxes,'text':' '.join(i['text'] for i in items)[:600]})
    return result

def align(before,after):
    matcher=difflib.SequenceMatcher(None,[w['text'] for w in before],[w['text'] for w in after],autojunk=True)
    changes=[];matches=[]
    for tag,a,b,c,d in matcher.get_opcodes():
        if tag=='equal':
            for old,new in zip(before[a:b],after[c:d]):matches.append((old['page'],new['page']))
            continue
        old=regions(before[a:b]);new=regions(after[c:d])
        # A missing side uses its surviving neighbor as context, not a fabricated changed area.
        old_anchor=before[min(a,len(before)-1)] if before else None
        new_anchor=after[min(c,len(after)-1)] if after else None
        changes.append({'id':len(changes)+1,'kind':tag,'before':old,'after':new,'beforeAnchor':{'page':old_anchor['page'],'box':old_anchor['box']} if old_anchor else None,'afterAnchor':{'page':new_anchor['page'],'box':new_anchor['box']} if new_anchor else None})
        if len(changes)>=150:break
    votes={}
    for old,new in matches:votes.setdefault(old,{}).setdefault(new,0);votes[old][new]+=1
    pairs=[{'beforePage':old,'afterPage':max(counts,key=counts.get)} for old,counts in sorted(votes.items())]
    return {'changes':changes,'pagePairs':pairs,'truncated':len(changes)>=150,'method':'PDF text alignment','note':'红色为删除或替换前内容，绿色为新增或替换后内容；虚线为插入/删除处的上下文定位。图像与字体样式变化请结合源码及整页查看。'}

def comparison(manager,root,ident):
    after=manager.preview(root,ident);before=manager.folder(root,ident,True)/'before.pdf'
    key=['content-v2',sha(before) if before.is_file() else None,sha(after)];cache=manager.folder(root,ident,True)/'content-comparison.json';saved=read_json(cache,{})
    if saved.get('key')==key:return saved['result']
    old,old_pages=words(before) if before.is_file() else ([],0);new,new_pages=words(after)
    result={'id':ident,'beforePages':old_pages,'afterPages':new_pages,**align(old,new)}
    if before.is_file() and not result['changes']:
        result['changes']=visual_changes(before,after,result['pagePairs'],old_pages,new_pages)
    write_json(cache,{'key':key,'result':result});return result


def source_diff(before,after):
    old=before.splitlines();new=after.splitlines();blocks=[]
    for group in difflib.SequenceMatcher(None,old,new,autojunk=len(old)>2000).get_grouped_opcodes(3):
        rows=[]
        for tag,a,b,c,d in group:
            for index in range(max(b-a,d-c)):
                oi=a+index;ni=c+index
                rows.append({'kind':tag,'beforeLine':oi+1 if oi<b else None,'afterLine':ni+1 if ni<d else None,'before':old[oi] if oi<b else '', 'after':new[ni] if ni<d else ''})
        blocks.append({'rows':rows})
    return blocks


def visual_changes(before,after,pairs,old_pages,new_pages):
    import pypdfium2 as pdfium
    from PIL import Image,ImageChops
    old=pdfium.PdfDocument(before);new=pdfium.PdfDocument(after);changes=[]
    try:
        for pair in (pairs or [{'beforePage':n,'afterPage':n} for n in range(1,min(old_pages,new_pages)+1)])[:40]:
            a=old[pair['beforePage']-1];b=new[pair['afterPage']-1];ba=a.render(scale=.8);bb=b.render(scale=.8)
            try:
                ia=ba.to_pil().convert('RGB');ib=bb.to_pil().convert('RGB');size=(max(ia.width,ib.width),max(ia.height,ib.height));left=Image.new('RGB',size,'white');right=Image.new('RGB',size,'white');left.paste(ia);right.paste(ib)
                box=ImageChops.difference(left,right).convert('L').point(lambda n:255 if n>35 else 0).getbbox()
                if box:
                    norm=lambda image:[max(0,min(1,box[0]/image.width)),max(0,min(1,box[1]/image.height)),max(0,min(1,box[2]/image.width)),max(0,min(1,box[3]/image.height))]
                    changes.append({'id':len(changes)+1,'kind':'visual','before':[{'page':pair['beforePage'],'boxes':[norm(ia)],'text':'版面 / 样式变化'}],'after':[{'page':pair['afterPage'],'boxes':[norm(ib)],'text':'版面 / 样式变化'}],'beforeAnchor':None,'afterAnchor':None})
            finally:ba.close();bb.close();a.close();b.close()
    finally:old.close();new.close()
    return changes
