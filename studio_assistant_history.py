"""Project / conversation / turn history, with recoverable deletion."""
import copy,hashlib,json,re,shutil,time,uuid
from pathlib import Path
from studio_storage import project_id,read_json,write_json

def valid(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value):raise ValueError('会话标识无效')
    return value

def records(manager,root):
    base=manager.storage.data/'assistant'/project_id(root);result=[]
    for path in base.glob('*/session.json'):
        if path.parent.is_symlink():continue
        s=read_json(path,{})
        if s.get('root')==str(Path(root).resolve()) and s.get('id')==path.parent.name:result.append(s)
    result.sort(key=lambda s:s.get('created',0));chains={};prefix={}
    for s in result:
        messages=s.get('messages',[]);prior=messages[:-1] if messages and messages[-1]['role']=='user' else messages[:-2]
        key=json.dumps(prior,sort_keys=True,ensure_ascii=False)
        chain=s.get('conversationId') or chains.get(s.get('parentId')) or prefix.get(key) or s['id']
        chains[s['id']]=chain;s['_conversationId']=chain
        prefix[json.dumps(messages[-12:],sort_keys=True,ensure_ascii=False)]=chain
    return result

def groups(manager,root):
    result={}
    for s in records(manager,root):
        key=s['_conversationId'];g=result.setdefault(key,{'id':key,'title':s.get('question','新会话')[:100],'turns':[]})
        g['turns'].append({k:s.get(k) for k in ('id','question','chatMode','stage','created','updated','running')});g.update(latestId=s['id'],updated=s.get('updated',s.get('created',0)))
    return sorted(result.values(),key=lambda g:g['updated'],reverse=True)

def messages(manager,root,session):
    chain=next((s['_conversationId'] for s in records(manager,root) if s['id']==session['id']),session['id']);out=[]
    for s in records(manager,root):
        if s['_conversationId']!=chain or s.get('created',0)>session.get('created',0):continue
        out.append({'role':'user','content':s.get('question',''),'mode':s.get('chatMode','chat')})
        if s.get('messages') and s['messages'][-1]['role']=='assistant':out.append(copy.deepcopy(s['messages'][-1]))
    return out or copy.deepcopy(session.get('messages',[]))

def tree(manager,root):
    recent=manager.storage.settings().get('recent',[]) if hasattr(manager.storage,'settings') else []
    projects=[{'id':project_id(root),'root':str(Path(root).resolve()),'name':Path(root).name}]+recent
    for file in (manager.storage.data/'assistant').glob('*/*/session.json'):
        if file.parent.is_symlink():continue
        saved=read_json(file,{})
        if saved.get('root') and project_id(saved['root'])==file.parent.parent.name:projects.append({'id':file.parent.parent.name,'root':saved['root'],'name':Path(saved['root']).name})
    seen=set();out=[]
    for p in projects:
        if p['id'] in seen:continue
        seen.add(p['id']);conversations=groups(manager,p['root'])
        if conversations or p['id']==project_id(root):out.append({'id':p['id'],'name':p.get('name',Path(p['root']).name),'root':p['root'],'conversations':conversations})
    return out

def delete(manager,root,conversation):
    valid(conversation)
    with manager.lock:
        turns=[s for s in records(manager,root) if s['_conversationId']==conversation]
        if not turns:raise ValueError('会话不存在')
        if any(manager.sessions.get(s['id'],{}).get('running') for s in turns):raise ValueError('请先停止该会话再删除')
        token=uuid.uuid4().hex;trash=manager.storage.data/'assistant-trash'/project_id(root)/token;trash.mkdir(parents=True)
        moved=[]
        try:
            for s in turns:
                folder=manager.folder(root,s['id']);expected=manager.storage.data/'assistant'/project_id(root)
                if folder.is_symlink() or folder.resolve().parent!=expected.resolve():raise ValueError('会话路径无效')
                shutil.move(str(folder),str(trash/s['id']));moved.append(s['id'])
            write_json(trash/'deleted.json',{'ids':moved,'conversation':conversation,'root':str(Path(root).resolve()),'at':time.time()})
        except Exception:
            for ident in moved:shutil.move(str(trash/ident),str(manager.folder(root,ident)))
            raise
        for ident in moved:manager.sessions.pop(ident,None)
        return {'ok':True,'restoreToken':token,'count':len(moved),'ids':moved}

def restore(manager,root,token):
    valid(token);trash=manager.storage.data/'assistant-trash'/project_id(root)/token;meta=read_json(trash/'deleted.json',{})
    if not meta:raise ValueError('找不到已删除会话')
    with manager.lock:
        for ident in meta['ids']:
            valid(ident)
            if manager.folder(root,ident).exists():raise ValueError('会话已恢复')
            if (trash/ident).is_symlink():raise ValueError('会话路径无效')
        moved=[]
        try:
            for ident in meta['ids']:
                manager.folder(root,ident).parent.mkdir(parents=True,exist_ok=True);shutil.move(str(trash/ident),str(manager.folder(root,ident)));moved.append(ident)
        except Exception:
            for ident in moved:shutil.move(str(manager.folder(root,ident)),str(trash/ident))
            raise
    return {'ok':True}


def project_root(manager,current,pid,token=None):
    if not pid or pid==project_id(current):return current
    if not re.fullmatch(r'[a-f0-9]{20}',pid):raise ValueError('项目标识无效')
    for item in tree(manager,current):
        if item['id']==pid:return Path(item['root'])
    if token:
        valid(token);meta=read_json(manager.storage.data/'assistant-trash'/pid/token/'deleted.json',{})
        if meta.get('root') and project_id(meta['root'])==pid:return Path(meta['root'])
    raise ValueError('找不到历史项目')
