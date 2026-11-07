"""Move owned project/cache directories with rollback; preserve local task history."""
from pathlib import Path
import json

from studio_storage import project_id,read_json,write_json


def nested(a,b):return a==b or a.is_relative_to(b) or b.is_relative_to(a)


def validate(store,value,current):
    if not isinstance(value,str) or not value.strip():raise ValueError('请输入完整目录路径')
    target=Path(value.strip()).expanduser()
    if not target.is_absolute():raise ValueError('请输入绝对路径')
    target=target.resolve()
    if target==current:return target
    if target==Path(target.anchor) or (store.installed and target.drive.upper()!='D:'):raise ValueError('请选择 D 盘中的一个文件夹，不能使用盘符根目录')
    if any(nested(target,p.resolve()) for p in [store.app,store.data,store.runtime,store.home/'source']):raise ValueError('目录不能覆盖软件、数据或编译器目录')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):raise ValueError('目标目录须为空；已有项目会一并迁移')
    return target


def remap_project_records(store,original,new,cache,rename,save):
    old_id,new_id=project_id(original),project_id(new)
    for name in ['history','page-edits','review-previews','editor-ai']:
        rename(store.data/name/old_id,store.data/name/new_id)
    for name,extensions in [('glossaries',['.json']),('previews',['.pdf','.synctex.gz','.synctex.json'])]:
        for ext in extensions:rename(store.data/name/(old_id+ext),store.data/name/(new_id+ext))
    for path in (store.data/'page-edits'/new_id).glob('*/session.json'):
        value=read_json(path,None)
        if not value:raise ValueError('历史记录无法读取，目录迁移已回滚')
        prior=store.data/'page-edits'/old_id;after=store.data/'page-edits'/new_id
        def rewrite(text,a=prior,b=after):
            p=Path(text)
            return str(b/p.relative_to(a)) if p.is_relative_to(a) else text
        value.update(root=str(new),projectId=new_id,folder=rewrite(value['folder']))
        if value.get('candidatePdf'):value['candidatePdf']=rewrite(value['candidatePdf'])
        for images in list(value.get('imagePages',{}).values())+[value.get('images',{})]:
            for which,text in images.items():images[which]=rewrite(text,store.data/'review-previews'/old_id,store.data/'review-previews'/new_id)
        value.pop('focusCache',None);save(path,value)
    for path in (store.data/'editor-ai'/new_id).glob('*/session.json'):
        value=read_json(path,None)
        if not value:raise ValueError('AI 修复记录无法读取，目录迁移已回滚')
        value.update(root=str(new),projectId=new_id);save(path,value)
    rename(cache/'editor-ai'/old_id,cache/'editor-ai'/new_id)
    rename(cache/'build'/old_id,cache/'build'/new_id)


def configure(store,projects,cache):
    projects=validate(store,projects,store.projects);cache=validate(store,cache,store.cache)
    if nested(projects,cache):raise ValueError('项目与缓存目录不能相互包含')
    for old,new in [(store.projects,projects),(store.cache,cache)]:
        if old!=new and nested(old,new):raise ValueError('新旧目录不能相互包含')
    if nested(projects,store.cache) or nested(cache,store.projects):raise ValueError('项目与缓存目录不能交叉覆盖')
    journal=[];snapshots=[];created=[];old_projects=store.projects;old_cache=store.cache;old_default=store.default_root
    def rename(source,target):
        if not source.exists():return
        if target.exists():raise ValueError('迁移目标已有历史记录，未覆盖任何文件')
        target.parent.mkdir(parents=True,exist_ok=True);source.rename(target);journal.append((target,source))
    def save(path,value):
        snapshots.append((path,path.read_bytes() if path.exists() else None));write_json(path,value)
    def move(source,target):
        if source==target:return
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():target.rmdir()
        if source.exists():rename(source,target)
        else:target.mkdir();created.append(target)
    def remap_root(value):
        path=Path(value).resolve()
        return projects/path.relative_to(old_projects) if path.is_relative_to(old_projects) else path
    try:
        move(old_projects,projects);move(old_cache,cache)
        settings=store.settings();roots={}
        for entry in settings.get('recent',[])+([settings['active']] if settings.get('active') else []):
            old=Path(entry['root']).resolve();new=remap_root(old)
            if old!=new:roots[str(old)]=new
            entry.update(root=str(new),id=project_id(new))
        for original,new in roots.items():remap_project_records(store,original,new,cache,rename,save)
        store.projects=projects;store.cache=cache;store.tex_cache=cache/'tectonic';store.default_root=remap_root(old_default)
        save(store.settings_path,settings)
        save(store.data/'locations.json',{'projects':str(projects),'cache':str(cache),'defaultProject':str(store.default_root)})
    except Exception:
        for path,raw in reversed(snapshots):
            if raw is None:path.unlink(missing_ok=True)
            else:path.write_bytes(raw)
        for target,source in reversed(journal):target.rename(source)
        for path in reversed(created):
            if path.exists() and not any(path.iterdir()):path.rmdir()
        store.projects=old_projects;store.cache=old_cache;store.tex_cache=old_cache/'tectonic';store.default_root=old_default
        raise
    return store.describe()
