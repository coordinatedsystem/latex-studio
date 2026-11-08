"""One-page source context and disposable PDF comparisons; no network calls."""
from __future__ import annotations

from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

from studio_engine import engine_environment
from studio_storage import project_id, read_json, write_json
from studio_review import page_image
from studio_batch_edits import BatchEditsMixin
from studio_change_focus import edit_key
import studio_task_history as task_history

SKIP={'.git','.codex','.agents','latex-studio','latex-portable','build','__pycache__'}
ALLOWED={'.tex','.bib','.sty','.cls','.bst','.bbl','.cfg','.def','.clo','.fd','.tikz','.py','.txt','.csv','.json',
         '.png','.jpg','.jpeg','.webp','.pdf','.eps','.svg','.otf','.ttf','.tfm','.pfb','.map'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_files(root):
    root=Path(root).resolve();result=[]
    for path in root.rglob('*'):
        relative=path.relative_to(root)
        if any(p.startswith('.') or p in SKIP for p in relative.parts) or path.is_symlink():continue
        if path.is_file() and path.suffix.lower() in ALLOWED:result.append(path)
        if len(result)>3000:raise ValueError('项目文件过多，无法生成比较副本')
    if sum(p.stat().st_size for p in result)>200*1024*1024:raise ValueError('比较副本暂支持 200 MB 以内的项目素材')
    return result


def save_source_map(root,main,pdf,synctex,data,source_hashes=None):
    root=Path(root).resolve();pdf=Path(pdf);synctex=Path(synctex)
    if not synctex.exists():return
    target=Path(data)/'previews'/(project_id(root)+'.synctex.gz')
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(synctex,target)
    inputs={};pages=defaultdict(lambda:defaultdict(Counter));current=0;unit=1
    from pypdf import PdfReader
    sizes=[float(p.mediabox.height) for p in PdfReader(pdf).pages]
    for line in gzip.decompress(target.read_bytes()).decode('utf-8',errors='replace').splitlines():
        match=re.match(r'Input:(\d+):(.*)',line)
        if match and match[2]:
            path=Path(match[2]);path=(root/path).resolve() if not path.is_absolute() else path.resolve()
            if path.is_relative_to(root) and path.suffix.lower()=='.tex' and path.exists():inputs[int(match[1])]=path.relative_to(root).as_posix()
        elif line.startswith('Unit:'):unit=float(line.split(':',1)[1])
        elif re.fullmatch(r'\{\d+',line):current=int(line[1:])
        elif line.startswith('}'):current=0
        elif current and current<=len(sizes):
            match=re.match(r'[gxkh](\d+),(\d+)(?:,\d+)?:-?\d+,(-?\d+)',line)
            if match and int(match[1]) in inputs:
                y=int(match[3])*unit/65536
                if 45<y<sizes[current-1]-40:pages[current][inputs[int(match[1])]][int(match[2])]+=1
    sources=source_hashes or {str(p.relative_to(root).as_posix()):sha(p) for p in project_files(root)}
    mapping={'main':main,'pdfVersion':str(pdf.stat().st_mtime_ns),'totalPages':len(sizes),'sources':sources,
             'pages':{str(p):{name:dict(counts) for name,counts in files.items()} for p,files in pages.items()}}
    write_json(target.with_suffix('.json'),mapping)


class PageEdits(BatchEditsMixin):
    def __init__(self,storage):
        self.storage=storage;self.lock=threading.RLock();self.sessions={}

    def busy(self):
        with self.lock:return any(s.get('preview',{}).get('running') for s in self.sessions.values())

    def _session(self,ident,root):
        session=self.sessions.get(ident)
        if session is None:
            session=task_history.load(self.storage,root,ident)
            if session:self.sessions[ident]=session
        if not session or session['projectId']!=project_id(root):raise ValueError('修改任务已失效或属于其他项目，请重新选择内容')
        return session

    def remember(self,session):
        if not getattr(self,'_batch_preparing',False):task_history.save(self.storage,session)

    def readiness(self,root,main,pdf):
        pdf=Path(pdf);metadata=read_json(self.storage.data/'previews'/(project_id(root)+'.synctex.json'),{})
        ready=pdf.is_file() and metadata.get('main')==main and metadata.get('pdfVersion')==str(pdf.stat().st_mtime_ns)
        if ready:ready=metadata.get('sources')=={p.relative_to(Path(root)).as_posix():sha(p) for p in project_files(root)}
        return {'projectId':project_id(root),'needsCompile':not ready,'hasPdf':pdf.is_file()}

    def bind_job(self,ident,root,job,request=None):
        with self.lock:
            s=self._session(ident,root);previous=s.get('job',{})
            if previous.get('id')!=job.get('id') or previous.get('running') or previous.get('success') is None:s['job']=task_history.public_job(job)
            if request:s['request']={k:request[k] for k in ('task','provider','instruction','target') if k in request}
            self.remember(s)

    def finish_job(self,ident,root,job):
        with self.lock:
            s=self._session(ident,root);s['job']=task_history.public_job(job)
            result=s.get('result')
            if result and not job.get('success'):
                for page in result.get('pageStates',[]):
                    if page.get('status')=='running':page['status']='pending'
                result['pendingPages']=[p['page'] for p in result.get('pageStates',[]) if p['status']=='pending']
            self.remember(s)

    def save_view(self,ident,root,view):
        with self.lock:
            s=self._session(ident,root);value={}
            selected=view.get('selected')
            if isinstance(selected,list) and all(isinstance(i,int) and not isinstance(i,bool) and 0<=i<len(s.get('edits') or []) for i in selected):value['selected']=sorted(set(selected))
            if view.get('view') in {'content','comparison','diff'}:value['view']=view['view']
            if isinstance(view.get('comparePage'),int):value['comparePage']=view['comparePage']
            settings=view.get('settings')
            if isinstance(settings,dict):value['settings']={k:str(settings[k])[:1600 if k=='instruction' else 40] for k in ('task','provider','language','instruction') if k in settings}
            if isinstance(settings,dict):value['settings']['wholeDocument']=bool(settings.get('wholeDocument'))
            s['view']={**s.get('view',{}),**value};self.remember(s);return {'ok':True}

    def describe_task(self,ident,root,pdf,live=None):
        with self.lock:
            s=self._session(ident,root)
            if live and s.get('job',{}).get('id')==live.get('id'):s['job']=task_history.public_job(live)
            elif s.get('job',{}).get('running'):
                s['job'].update(running=False,success=False,stage='任务已中断',error='服务已重启，已完成的建议已保留')
                if s.get('result'):
                    for item in s['result'].get('pageStates',[]):
                        if item['status']=='running':item['status']='pending'
                    s['result']['pendingPages']=[p['page'] for p in s['result'].get('pageStates',[]) if p['status']=='pending']
                self.remember(s)
            try:self._fresh(s,root,pdf);stale=False
            except (ValueError,OSError):stale=True
            hashes=s.get('appliedHashes') or ({s['path']:s['appliedHash']} if s.get('appliedHash') else {})
            can_undo=bool(hashes) and all((Path(root)/name).is_file() and sha(Path(root)/name)==value for name,value in hashes.items())
            public=self.context(ident,root);public.update(job=s.get('job',{}),view=s.get('view',{}),request=s.get('request',{}),stale=stale and not bool(s.get('appliedHash')),canUndo=can_undo,created=s.get('created'),updated=s.get('updated'))
            if public['preview'].get('success') and (not s.get('candidatePdf') or not Path(s['candidatePdf']).exists()):public['preview']={}
            return public

    def task_list(self,root,pdf,live=None):
        result=[]
        for ident in task_history.identifiers(self.storage,root)[:20]:
            try:
                s=self._session(ident,root)
                if not s.get('result') and not s.get('job'):continue
                job=s.get('job',{});is_live=bool(live and job.get('id')==live.get('id') and live.get('running'))
                result.append({'id':ident,'mode':s['mode'],'path':s['path'],'pages':s.get('pages',[s['page']]),'startLine':s['startLine'],'endLine':s['endLine'],'count':len(s.get('edits') or []),'created':s.get('created'),'updated':s.get('updated'),'running':is_live,'applied':bool(s.get('appliedHash')),'undone':s.get('undone',False),'failedPages':(s.get('result') or {}).get('failedPages',[])})
            except (ValueError,OSError):continue
        return result

    def rebase(self,ident,root,main,pdf,selected=None):
        from studio_task_rebase import rebase
        with self.lock:return rebase(self,ident,root,main,pdf,selected)

    def _fresh(self,s,root,pdf):
        if str(Path(pdf).stat().st_mtime_ns)!=s['pdfVersion']:raise ValueError('PDF 已更新，请重新关联源码')
        for name,value in s['sourceHashes'].items():
            path=Path(root)/name
            if not path.is_file() or sha(path)!=value:raise ValueError('项目源码或素材已变化，请保存并编译后重新关联')

    def prepare(self,root,main,pdf,page,path=None):
        root=Path(root).resolve();pdf=Path(pdf);page=int(page)
        metadata=read_json(self.storage.data/'previews'/(project_id(root)+'.synctex.json'),{})
        if metadata.get('pdfVersion')!=str(pdf.stat().st_mtime_ns) or metadata.get('main')!=main:
            raise ValueError('当前 PDF 缺少源码映射，请先保存并编译')
        if not 1<=page<=metadata['totalPages']:raise ValueError('PDF 页次超出范围')
        records=metadata.get('pages',{}).get(str(page),{})
        if not records:raise ValueError('这一页无法可靠定位到 .tex 源码；目录或外部素材页可能需要手动编辑')
        candidates=sorted(records,key=lambda n:sum(records[n].values()),reverse=True)
        path=path or candidates[0]
        if path not in candidates:raise ValueError('所选文件没有映射到当前页面')
        target=(root/path).resolve()
        if not target.is_relative_to(root) or target.suffix.lower()!='.tex':raise ValueError('只能修改当前项目的 .tex 文件')
        full=target.read_text(encoding='utf-8-sig').replace('\r\n','\n');rows=full.splitlines(keepends=True)
        counts=Counter({int(k):v for k,v in records[path].items() if 1<=int(k)<=len(rows)})
        begin=next((i+1 for i,line in enumerate(rows) if '\\begin{document}' in line),0)
        body={n:v for n,v in counts.items() if n>=begin} if begin else dict(counts)
        counts=Counter(body or counts)
        clusters=[]
        for number in sorted(counts):
            if not clusters or number-clusters[-1][-1]>35:clusters.append([])
            clusters[-1].append(number)
        selected=max(clusters,key=lambda c:sum(counts[n] for n in c))
        lo=max(1,min(selected)-1);hi=min(len(rows),max(selected)+2)
        if hi-lo>220:raise ValueError('本页源码范围过大或映射不明确，请先拆分长段落再编译')
        text=''.join(rows[lo-1:hi])
        if len(text)>25000:raise ValueError('单页源码片段过长，请先拆分后编译')
        return self._store(root,main,pdf,page,path,lo,hi,sum(map(len,rows[:lo-1])),sum(map(len,rows[:hi])),text,full,target,metadata['sources'],candidates,'pdf')

    def prepare_source(self,root,main,pdf,path,start,end):
        root=Path(root).resolve();pdf=Path(pdf);target=(root/str(path)).resolve()
        if not target.is_relative_to(root) or target.suffix.lower()!='.tex' or not target.is_file():raise ValueError('请选择当前项目的 .tex 源码')
        metadata=read_json(self.storage.data/'previews'/(project_id(root)+'.synctex.json'),{})
        if metadata.get('pdfVersion')!=str(pdf.stat().st_mtime_ns) or metadata.get('main')!=main:
            raise ValueError('请先保存并编译，更新 PDF 与源码映射')
        full=target.read_text(encoding='utf-8-sig').replace('\r\n','\n')
        if any(isinstance(n,bool) or not isinstance(n,int) for n in (start,end)) or not 0<=start<end<=len(full):raise ValueError('源码选区无效，请重新选择')
        text=full[start:end]
        if len(text)>45000:raise ValueError('选区超过 45000 字符，请缩小源码范围')
        name=target.relative_to(root).as_posix();lo=full[:start].count('\n')+1;hi=full[:end].count('\n')+1
        if name not in metadata.get('sources',{}):raise ValueError('该源码文件尚未编译，请先保存并编译')
        scores={int(p):sum(v for n,v in files.get(name,{}).items() if lo<=int(n)<=hi) for p,files in metadata.get('pages',{}).items()}
        page=max(scores,key=scores.get) if scores and max(scores.values()) else 1
        return self._store(root,main,pdf,page,name,lo,hi,start,end,text,full,target,metadata['sources'],[name],'source')

    def _store(self,root,main,pdf,page,path,lo,hi,start,end,text,full,target,source_hashes,candidates,mode):
        ident=uuid.uuid4().hex;folder=self.storage.data/'page-edits'/project_id(root)/ident
        folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(pdf,folder/'before.pdf')
        s={'id':ident,'projectId':project_id(root),'root':str(root),'main':main,'page':page,'path':path,'startLine':lo,'endLine':hi,
           'start':start,'end':end,'source':text,'full':full,'originalBytes':target.read_bytes(),'mode':mode,
           'pdfVersion':str(pdf.stat().st_mtime_ns),'sourceHashes':source_hashes,'folder':str(folder),'edits':None,
           'candidates':candidates,'preview':{},'appliedHash':None}
        self._fresh(s,root,pdf)
        with self.lock:
            self.sessions[ident]=s
            self.remember(s)
            if not getattr(self,'_batch_preparing',False):task_history.prune(self,root)
        return {k:s[k] for k in ('id','projectId','page','path','startLine','endLine','start','end','source','pdfVersion','candidates','mode')}

    def source_input(self,ident,root,pdf):
        with self.lock:
            s=self._session(ident,root);self._fresh(s,root,pdf)
            if s['mode']!='source':raise ValueError('请重新选择源码范围')
            return s['source']

    def ai_input(self,ident,root,pdf):
        with self.lock:
            s=self._session(ident,root);self._fresh(s,root,pdf)
            image=page_image(Path(s['folder'])/'before.pdf',self.storage.data,s['projectId'],s['page'],(Path(s['folder'])/'before.pdf').stat().st_mtime_ns)
            import base64
            return s['source'],[{'page':s['page'],'image':'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()}]

    def attach(self,ident,root,edits,result=None):
        with self.lock:
            s=self._session(ident,root)
            # Revalidate server-origin edits against the original single-page source.
            from studio_ai import validate_edits
            proposed=[]
            for e in edits:
                line=s['source'][:e['start']].count('\n')+1
                proposed.append({'before':e['before'],'after':e['after'],'reason':e['reason'],'line':line})
            s['edits']=validate_edits(s['source'],proposed)[0]
            for e in s['edits']:e['key']=edit_key(e,s['path'],s['start'])
            s['preview']={}
            s.pop('focusCache',None)
            if result is not None:result['edits']=s['edits']
            s['result']=result
            self.remember(s)

    def context(self,ident,root):
        with self.lock:
            s=self._session(ident,root)
            return {**{k:s[k] for k in ('id','projectId','page','path','startLine','endLine','start','end','source','pdfVersion','candidates','mode')},
                    'wholeDocument':s.get('wholeDocument',False),'readOnlyPages':[p['page'] for p in s.get('parts',[]) if p.get('readOnly')],'pages':s.get('pages',[s['page']]),'result':s.get('result'),'preview':dict(s['preview']),'applied':bool(s['appliedHash']),'undone':s.get('undone',False)}

    def preview(self,ident,root,pdf,selected):
        with self.lock:
            s=self._session(ident,root);self._fresh(s,root,pdf)
            if s['mode']=='pages':return self.preview_batch(ident,root,pdf,selected)
            if self.busy():raise ValueError('已有比较预览正在编译，请等待完成')
            if not s['edits']:raise ValueError('没有可生成预览的源码修改')
            if not isinstance(selected,list) or not selected or any(isinstance(i,bool) or not isinstance(i,int) or i<0 or i>=len(s['edits']) for i in selected):raise ValueError('请选择有效修改')
            chosen=sorted(set(selected));snippet=s['source']
            for index in sorted(chosen,key=lambda i:s['edits'][i]['start'],reverse=True):
                e=s['edits'][index];snippet=snippet[:e['start']]+e['after']+snippet[e['end']:]
            candidate=s['full'][:s['start']]+snippet+s['full'][s['end']:]
            preview_id=uuid.uuid4().hex
            s['preview']={'id':preview_id,'running':True,'stage':'在临时副本中编译','success':None,'selected':chosen}
            self.remember(s)
            threading.Thread(target=self._compile,args=(s,candidate,preview_id),daemon=True).start()
            return dict(s['preview'])

    def _compile(self,s,candidate,preview_id):
        folder=Path(s['folder'])/preview_id;clone=folder/'project';clone.mkdir(parents=True,exist_ok=True)
        try:
            root=Path(s['root']);manifest={}
            for p in project_files(root):
                relative=p.relative_to(root);target=clone/relative;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(p,target);manifest[relative.as_posix()]=sha(target)
            if manifest!=s['sourceHashes']:raise ValueError('源码或素材已变化，请重新关联源码')
            for name,text in (candidate.items() if isinstance(candidate,dict) else [(s['path'],candidate)]):
                (clone/name).write_text(text,encoding='utf-8')
            output=folder/'output';output.mkdir()
            command=[str(self.storage.runtime/'bin/tectonic.exe'),'--only-cached','--untrusted','--keep-logs','--outdir',str(output),s['main']]
            result=subprocess.run(command,cwd=clone,env=engine_environment(self.storage.runtime,folder/'engine-data',getattr(self.storage,'tex_cache',None)),capture_output=True,text=True,
                                  encoding='utf-8',errors='replace',timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            pdf=output/(Path(s['main']).stem+'.pdf')
            if result.returncode or not pdf.exists():
                raise ValueError('候选修改编译失败，原文件未改动。\n'+(result.stdout+'\n'+result.stderr)[-3500:])
            from pypdf import PdfReader
            from PIL import Image,ImageChops
            total=len(PdfReader(pdf).pages);comparisons=[];images={}
            for number in s.get('pages',[s['page']]):
                shown=min(number,total)
                before=page_image(Path(s['folder'])/'before.pdf',self.storage.data,s['projectId'],number,(Path(s['folder'])/'before.pdf').stat().st_mtime_ns)
                after=page_image(pdf,self.storage.data,s['projectId'],shown,pdf.stat().st_mtime_ns)
                with Image.open(before) as a,Image.open(after) as b:
                    aa=a.convert('RGB');bb=b.convert('RGB')
                    if aa.size!=bb.size:bb=bb.resize(aa.size)
                    bounds=ImageChops.difference(aa,bb).getbbox();changed=bounds is not None
                    normalized=[bounds[0]/aa.width,bounds[1]/aa.height,bounds[2]/aa.width,bounds[3]/aa.height] if bounds else None
                comparisons.append({'page':number,'shownPage':shown,'changed':changed,'bounds':normalized});images[str(number)]={'before':str(before),'after':str(after)}
            with self.lock:
                s['candidate']=candidate;s['candidatePdf']=str(pdf);s['imagePages']=images;s['images']=images[str(s['page'])]
                s['preview'].update(running=False,success=True,stage='编译通过，等待确认',changed=any(p['changed'] for p in comparisons),totalPages=total,shownPage=comparisons[0]['shownPage'],pages=comparisons)
                self.remember(s)
            cached=sorted((p for p in Path(s['folder']).iterdir() if p.is_dir() and re.fullmatch(r'[a-f0-9]{32}',p.name)),key=lambda p:p.stat().st_mtime_ns,reverse=True)
            for old in cached[2:]:
                if old.name!=preview_id and old.resolve().is_relative_to(Path(s['folder']).resolve()) and not old.is_symlink():shutil.rmtree(old,ignore_errors=True)
        except Exception as exc:
            with self.lock:
                s['preview'].update(running=False,success=False,stage='预览未完成',error=str(exc) if isinstance(exc,ValueError) else '预览生成失败，请检查编译环境');self.remember(s)
        finally:
            if clone.resolve().is_relative_to(folder.resolve()) and not clone.is_symlink():shutil.rmtree(clone,ignore_errors=True)

    def status(self,ident,root):
        with self.lock:return dict(self._session(ident,root)['preview'])

    def image(self,ident,root,which,page=None):
        with self.lock:
            s=self._session(ident,root)
            if which not in {'before','after'} or not s.get('images'):raise ValueError('比较图像尚未生成')
            images=s.get('imagePages',{}).get(str(page or s['page']))
            if images is None:raise ValueError('该页不在当前对比范围内')
            target=Path(images[which])
            if not target.is_file():
                number=page or s['page'];pdf=Path(s['folder'])/'before.pdf'
                if which=='after':
                    pdf=Path(s['candidatePdf']);number=next((p['shownPage'] for p in s['preview'].get('pages',[]) if p['page']==number),number)
                target=page_image(pdf,self.storage.data,s['projectId'],number,pdf.stat().st_mtime_ns)
                images[which]=str(target);self.remember(s)
            return target

    def apply_data(self,ident,root,pdf,preview_id,undo=False,selected=None):
        with self.lock:
            s=self._session(ident,root);target=Path(root)/s['path']
            if undo:
                if not s['appliedHash'] or sha(target)!=s['appliedHash']:raise ValueError('应用后源码已变化，无法直接撤销；请使用文件历史')
                return target,s['originalBytes'],s
            self._fresh(s,root,pdf)
            p=s['preview']
            if p.get('id')!=preview_id or p.get('running') or not p.get('success'):raise ValueError('请先生成并确认所选修改的效果预览')
            if not isinstance(selected,list) or sorted(set(selected))!=p['selected']:raise ValueError('修改选择已变化，请重新生成效果预览')
            text=s['candidate'];original=s['originalBytes']
            if b'\r\n' in original:text=text.replace('\n','\r\n')
            data=text.encode('utf-8')
            if original.startswith(b'\xef\xbb\xbf'):data=b'\xef\xbb\xbf'+data
            return target,data,s


_managers={}
_lock=threading.Lock()
def pages_for(storage):
    key=str(storage.data.resolve())
    with _lock:
        if key not in _managers:_managers[key]=PageEdits(storage)
        return _managers[key]
