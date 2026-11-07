"""Relocate previously reviewed edits against a freshly compiled project; no AI calls."""
import copy
from pathlib import Path

from studio_ai import validate_edits
from studio_storage import project_id,read_json

def rebase(manager,ident,root,main,pdf,selected):
    from studio_page_edits import project_files,sha
    from studio_change_focus import edit_key
    root=Path(root).resolve();pdf=Path(pdf);old=manager._session(ident,root)
    if old.get('appliedHash'):raise ValueError('已应用任务不能重新关联，请先撤销或创建新任务')
    metadata=read_json(manager.storage.data/'previews'/(project_id(root)+'.synctex.json'),{})
    hashes={p.relative_to(root).as_posix():sha(p) for p in project_files(root)}
    if metadata.get('main')!=main or metadata.get('pdfVersion')!=str(pdf.stat().st_mtime_ns) or metadata.get('sources')!=hashes:raise ValueError('请先保存并编译，再重新关联建议')
    edits=old.get('edits') or [];selected=set(range(len(edits))) if selected is None else set(selected)
    if any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(edits) for i in selected):raise ValueError('修改选择无效')
    by_file={};rejected=[]
    for index,e in enumerate(edits):
        name=e.get('path',old['path']);target=(root/name).resolve()
        if not target.is_relative_to(root) or target.suffix!='.tex' or not target.exists():raise ValueError('任务源码文件已不存在')
        full=target.read_text(encoding='utf-8-sig').replace('\r\n','\n')
        try:
            # Unique exact matching is intentional: never guess after an external edit.
            checked=validate_edits(full,[{'before':e['before'],'after':e['after'],'reason':e['reason']}])[0][0]
            if any(checked['start']<prior['end'] and checked['end']>prior['start'] for _,prior in by_file.get(name,{}).get('edits',[])):
                raise ValueError('重新关联后与其他修改重叠')
            by_file.setdefault(name,{'full':full,'raw':target.read_bytes(),'edits':[]})['edits'].append((index,checked))
        except (ValueError,IndexError):rejected.append({'reason':f'{name}：原文已变化或存在多个匹配，原建议仍在历史中'})
    if not by_file:raise ValueError('原建议无法唯一匹配当前源码，请重新选择范围；原结果已保留')
    parts=[];combined='';new_edits=[];new_selected=[];files={};pages=set()
    for part_index,(name,info) in enumerate(by_file.items()):
        lo=max(0,min(e['start'] for _,e in info['edits'])-80);hi=min(len(info['full']),max(e['end'] for _,e in info['edits'])+80)
        start_line=info['full'][:lo].count('\n')+1;end_line=info['full'][:hi].count('\n')+1
        scores={int(p):sum(v for line,v in records.get(name,{}).items() if start_line<=int(line)<=end_line) for p,records in metadata.get('pages',{}).items()}
        page=max(scores,key=scores.get) if scores and max(scores.values()) else min(old['page'],metadata['totalPages'])
        pages.add(page);combined+=f'% {name}\n';display=len(combined);source=info['full'][lo:hi];combined+=source+'\n\n'
        parts.append({'part':part_index,'page':page,'path':name,'start':lo,'end':hi,'startLine':start_line,'endLine':end_line,'source':source,'displayStart':display})
        files[name]={'full':info['full'],'originalBytes':info['raw']}
        for origin,e in info['edits']:
            if origin in selected:new_selected.append(len(new_edits))
            new_edits.append({**e,'start':display+e['start']-lo,'end':display+e['end']-lo,'fileStart':e['start'],'fileEnd':e['end'],'path':name,'page':page,'part':part_index,'originIndex':origin})
    first=parts[0];info=files[first['path']]
    for edit in new_edits:edit['key']=edit_key(edit)
    context=manager._store(root,main,pdf,first['page'],first['path'],first['startLine'],first['endLine'],first['start'],first['end'],first['source'],info['full'],root/first['path'],hashes,[p['path'] for p in parts],'pages')
    s=manager._session(context['id'],root);result=copy.deepcopy(old.get('result') or {})
    result.update(edits=new_edits,rejected=result.get('rejected',[])+rejected,summary=f'已重新关联 {len(new_edits)} 项建议。',pageContext=s['id'],failedPages=[],pendingPages=[],pageStates=[],rebased=True)
    s.update(source=combined,parts=parts,files=files,pages=sorted(pages),edits=new_edits,result=result,appliedHashes={},rebased=True,view={'selected':new_selected},job={'task':'rebased','provider':'local','running':False,'success':True,'stage':'等待预览'})
    manager.remember(s);return manager.describe_task(s['id'],root,pdf)
