"""Explicitly linked project copies; hash-based two-way sync with no automatic deletion."""
import hashlib, threading, os
from pathlib import Path
from studio_storage import read_json, write_json, project_id, safe_relative
from studio_page_edits import project_files, sha

LOCK=threading.RLock()
_hashes={}

def metadata(store,root):return store.data/'project-links'/(project_id(root)+'.json')

def files(root):
    root=Path(root).resolve()
    # Reject directory links too: resolving only the final file misses parent junctions.
    for folder,dirs,names in os.walk(root,followlinks=False):
        from studio_page_edits import SKIP
        dirs[:]=[d for d in dirs if not d.startswith('.') and d not in SKIP]
        for name in dirs+names:
            p=Path(folder)/name
            if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('同步目录不能包含符号链接或目录连接')
    result={};memo=_hashes.setdefault(str(root),{})
    for p in project_files(root):
        stat=p.stat();stamp=(stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns);name=p.relative_to(root).as_posix()
        if name not in memo or memo[name][0]!=stamp:memo[name]=(stamp,sha(p))
        result[name]=memo[name][1]
    for name in list(memo):
        if name not in result:memo.pop(name)
    return result

def connect(store,root,source):
    root=Path(root).resolve();source=Path(source).expanduser().resolve()
    if source.is_file():source=source.parent
    if not source.is_dir() or source==root or source.is_relative_to(root) or root.is_relative_to(source):
        raise ValueError('请选择独立的原始项目文件夹，不能与当前项目相互包含')
    from studio_storage import detect_main
    detect_main(source)
    local=files(root);remote=files(source)
    # Initial unequal files have no common ancestor: deliberately report a conflict.
    baseline={name:local.get(name) if local.get(name)==remote.get(name) else 'unresolved' for name in local.keys()|remote.keys()}
    with LOCK:
        write_json(metadata(store,root),{'root':str(root),'source':str(source),'baseline':baseline})
    return synchronize(store,root)

def transfer(store,root,name,destination,source,expected,expected_dest):
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('同步期间文件再次变化，稍后重试')
    if (sha(destination) if destination.exists() else None)!=expected_dest:raise ValueError('目标文件再次变化，未覆盖；请重新同步')
    if destination.exists():
        backup=store.data/'sync-history'/project_id(root)/__import__('uuid').uuid4().hex/safe_relative(name)
        backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(destination.read_bytes())
    destination.parent.mkdir(parents=True,exist_ok=True)
    if expected_dest is None:
        temporary=destination.with_name('.sync-'+__import__('uuid').uuid4().hex)
        try:
            temporary.write_bytes(raw)
            # Windows rename is atomic and fails if another process creates the destination.
            if os.name=='nt':os.rename(temporary,destination)
            else:os.link(temporary,destination)
        finally:
            if temporary.exists():temporary.unlink()
    else:
        from studio_batch_edits import atomic_write_set
        atomic_write_set([(destination,raw)])

def synchronize(store,root,resolution=None):
    root=Path(root).resolve()
    with LOCK:
        path=metadata(store,root);meta=read_json(path,{})
        if not meta:return {'linked':False,'conflicts':[],'updated':[]}
        source=Path(meta['source']).resolve()
        if not source.is_dir():return {'linked':True,'source':str(source),'conflicts':[],'updated':[],'error':'原文件夹暂不可用'}
        local=files(root);remote=files(source);baseline=meta['baseline'];conflicts=[];updated=[]
        for name in sorted(local.keys()|remote.keys()|baseline.keys()):
            a,b,prior=local.get(name),remote.get(name),baseline.get(name)
            if a==b:baseline[name]=a;continue
            # Missing existing files need a choice, never propagate a deletion silently.
            conflict=prior=='unresolved' or (a!=prior and b!=prior) or (prior is not None and (a is None or b is None))
            choice=None
            if resolution and resolution.get('path')==name:
                if resolution.get('localHash')!=a or resolution.get('sourceHash')!=b:raise ValueError('文件再次变化，请刷新冲突后再选择')
                choice=resolution.get('choice')
                if choice not in {'local','source'}:raise ValueError('同步选择无效')
                if (a if choice=='local' else b) is None:raise ValueError('选择的版本已不存在；请恢复文件，自动同步不会删除另一份')
            if conflict and choice is None:
                conflicts.append({'path':name,'localHash':a,'sourceHash':b});continue
            direction=choice or ('local' if a!=prior else 'source')
            if direction=='source':
                if local.get(name)!=a or sha(source/safe_relative(name))!=b:raise ValueError('同步期间文件变化')
                transfer(store,root,name,root/safe_relative(name),source/safe_relative(name),b,a);baseline[name]=b
            else:
                if remote.get(name)!=b or sha(root/safe_relative(name))!=a:raise ValueError('同步期间文件变化')
                transfer(store,root,name,source/safe_relative(name),root/safe_relative(name),a,b);baseline[name]=a
            updated.append({'path':name,'direction':direction})
        write_json(path,meta)
        return {'linked':True,'source':str(source),'conflicts':conflicts,'updated':updated}

def disconnect(store,root):
    with LOCK:
        path=metadata(store,root)
        if path.exists():path.unlink()
    return {'linked':False,'conflicts':[],'updated':[]}
