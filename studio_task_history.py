"""Local writing-task snapshots. Credentials and request headers never enter this store."""
import base64
import copy
import json
from pathlib import Path
import re
import shutil
import time

from studio_storage import project_id,write_json

def encode(value):
    if isinstance(value,bytes):return {'$bytes':base64.b64encode(value).decode('ascii')}
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [encode(v) for v in value]
    return value

def decode(value):
    if isinstance(value,dict):
        if set(value)=={'$bytes'}:return base64.b64decode(value['$bytes'],validate=True)
        return {k:decode(v) for k,v in value.items()}
    if isinstance(value,list):return [decode(v) for v in value]
    return value

def folder_for(storage,root,ident):
    if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('任务标识无效')
    return storage.data/'page-edits'/project_id(root)/ident

def save(storage,session):
    session.setdefault('created',time.time());session['updated']=time.time()
    # Session dictionaries contain source snapshots, accepted edits and local file paths only.
    target=folder_for(storage,session['root'],session['id'])/'session.json'
    value=encode(session)
    if len(json.dumps(value,ensure_ascii=False).encode('utf-8'))>32*1024*1024:raise ValueError('任务源码超过本地历史容量，请拆分文件后处理')
    write_json(target,value)

def load(storage,root,ident):
    folder=folder_for(storage,root,ident);target=folder/'session.json'
    if not target.is_file() or target.stat().st_size>32*1024*1024:return None
    try:s=decode(json.loads(target.read_text(encoding='utf-8')))
    except (ValueError,TypeError,KeyError):return None
    root=Path(root).resolve()
    if s.get('id')!=ident or s.get('projectId')!=project_id(root) or Path(s.get('root','')).resolve()!=root:return None
    names=[s.get('path','')]+list(s.get('files',{}))+list(s.get('sourceHashes',{}))
    for name in names:
        if not name or Path(name).is_absolute() or not (root/name).resolve().is_relative_to(root):return None
    s['folder']=str(folder);s['root']=str(root)
    image_root=(storage.data/'review-previews'/project_id(root)).resolve()
    for pair in s.get('imagePages',{}).values():
        if any(not Path(p).resolve().is_relative_to(image_root) or Path(p).suffix!='.png' for p in pair.values()):return None
    if s.get('candidatePdf') and not Path(s['candidatePdf']).resolve().is_relative_to(folder.resolve()):return None
    if s.get('preview',{}).get('running'):s['preview'].update(running=False,success=False,stage='上次预览已中断，请重新预览')
    return s

def identifiers(storage,root):
    base=storage.data/'page-edits'/project_id(root)
    if not base.exists():return []
    return [p.name for p in sorted(base.iterdir(),key=lambda p:p.stat().st_mtime_ns,reverse=True) if p.is_dir() and not p.is_symlink() and re.fullmatch(r'[a-f0-9]{32}',p.name) and (p/'session.json').exists()]

def prune(manager,root):
    base=(manager.storage.data/'page-edits'/project_id(root)).resolve()
    for ident in identifiers(manager.storage,root)[20:]:
        session=manager.sessions.get(ident)
        if session and (session.get('job',{}).get('running') or session.get('preview',{}).get('running')):continue
        folder=folder_for(manager.storage,root,ident)
        if folder.resolve().is_relative_to(base) and not folder.is_symlink():shutil.rmtree(folder,ignore_errors=True)
        manager.sessions.pop(ident,None)

def public_job(job):
    fields=('id','task','provider','started','running','success','stage','duration','error','progress','requestCount','persistenceError')
    return {k:copy.deepcopy(job[k]) for k in fields if k in job}
