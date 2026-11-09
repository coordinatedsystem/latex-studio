"""Durable, deduplicated before/after file versions; compatible with existing IDs."""
from pathlib import Path
import hashlib,re,threading,time
from studio_storage import read_json,write_json,project_id

LOCK=threading.RLock()
VALID=re.compile(r'\d{8}-\d{6}-\d+')
def _folder(storage,root,relative):
    return storage.data/'history'/project_id(root)/relative

def capture(storage,root,path,reason='保存版本'):
    root=Path(root).resolve();path=Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file():return None
    with LOCK:
        folder=_folder(storage,root,path.relative_to(root));folder.mkdir(parents=True,exist_ok=True)
        content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
        entries=versions(storage,root,path)
        if entries and hashlib.sha256((folder/entries[0]['id']).read_bytes()).hexdigest()==digest:return entries[0]['id']
        now=time.time_ns();stamp=time.strftime('%Y%m%d-%H%M%S',time.localtime(now//1000000000))+f'-{now%1000000000:09d}'
        while (folder/stamp).exists():
            now+=1;stamp=time.strftime('%Y%m%d-%H%M%S',time.localtime(now//1000000000))+f'-{now%1000000000:09d}'
        target=folder/stamp;temp=folder/(stamp+'.tmp');temp.write_bytes(content);temp.replace(target)
        metadata=read_json(folder/'metadata.json',{});metadata[stamp]={'reason':str(reason)[:80],'created':time.time(),'size':len(content),'sha256':digest}
        records=sorted([p for p in folder.iterdir() if p.is_file() and VALID.fullmatch(p.name)],key=lambda p:_sort(p.name),reverse=True)
        for old in records[30:]:old.unlink();metadata.pop(old.name,None)
        write_json(folder/'metadata.json',metadata);return stamp

def _sort(name):
    date,clock,fraction=name.split('-');return date,clock,int(fraction)

def versions(storage,root,path):
    root=Path(root).resolve();path=Path(path).resolve()
    if not path.is_relative_to(root):raise ValueError('历史路径无效')
    folder=_folder(storage,root,path.relative_to(root))
    if not folder.is_dir():return []
    metadata=read_json(folder/'metadata.json',{});result=[]
    for p in sorted((p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and VALID.fullmatch(p.name)),key=lambda p:_sort(p.name),reverse=True):
        result.append({'id':p.name,'reason':metadata.get(p.name,{}).get('reason','历史保存'),'size':p.stat().st_size,'created':metadata.get(p.name,{}).get('created',p.stat().st_mtime)})
    return result[:30]
