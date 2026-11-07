"""Selected PDF pages share one preview and one reversible file transaction."""
from pathlib import Path
import os
import shutil
import threading
import uuid

MAX_PAGES=12

def original_encoding(text,original):
    if b'\r\n' in original:text=text.replace('\n','\r\n')
    return (b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'')+text.encode('utf-8')

def atomic_write_set(changes):
    staged=[];written=[];originals={p:p.read_bytes() for p,_ in changes}
    try:
        for target,content in changes:
            temp=target.with_name(target.name+'.studio-tmp-'+uuid.uuid4().hex)
            staged.append((target,temp));temp.write_bytes(content)
        for target,temp in staged:
            os.replace(temp,target);written.append(target)
    except Exception:
        for target in reversed(written):
            temp=target.with_name(target.name+'.studio-rollback-'+uuid.uuid4().hex)
            try:temp.write_bytes(originals[target]);os.replace(temp,target)
            finally:temp.unlink(missing_ok=True)
        raise
    finally:
        for _,temp in staged:temp.unlink(missing_ok=True)

class BatchEditsMixin:
    def prepare_pages(self,root,main,pdf,pages):
        if not isinstance(pages,list) or not pages or len(pages)>MAX_PAGES or any(isinstance(p,bool) or not isinstance(p,int) for p in pages):
            raise ValueError('请选择 1～12 个有效 PDF 页面')
        pages=sorted(set(pages));parts=[];internal=[]
        self._batch_preparing=True
        try:
            for page in pages:
                context=self.prepare(root,main,pdf,page)
                with self.lock:
                    part=dict(self._session(context['id'],root));parts.append(part);internal.append((part['id'],Path(part['folder'])))
        except Exception:
            for ident,folder in internal:
                self.sessions.pop(ident,None)
                expected=(self.storage.data/'page-edits').resolve()
                if folder.resolve().is_relative_to(expected) and not folder.is_symlink():shutil.rmtree(folder,ignore_errors=True)
            raise
        finally:self._batch_preparing=False
        first=parts[0]
        context=self._store(Path(root),main,Path(pdf),pages[0],first['path'],first['startLine'],first['endLine'],first['start'],first['end'],first['source'],first['full'],Path(root)/first['path'],first['sourceHashes'],first['candidates'],'pages')
        with self.lock:
            s=self._session(context['id'],root);combined='';files={}
            for number,part in enumerate(parts):
                combined+=f"% PDF 第 {part['page']} 页 · {part['path']}\n"
                part['part']=number;part['displayStart']=len(combined);combined+=part['source']+'\n\n'
                files[part['path']]={'full':part['full'],'originalBytes':part['originalBytes']}
            if len(combined)>300000:raise ValueError('所选页面的源码过长，请分批处理')
            slim=[{k:p[k] for k in ('part','page','path','start','end','startLine','endLine','source','displayStart')} for p in parts]
            s.update(source=combined,parts=slim,files=files,pages=pages,appliedHashes={})
            for ident,folder in internal:
                self.sessions.pop(ident,None)
                if folder.resolve().is_relative_to(Path(s['folder']).parent.resolve()) and not folder.is_symlink():shutil.rmtree(folder,ignore_errors=True)
            self.remember(s)
        return self.context(context['id'],root)

    def batch_input(self,ident,root,pdf,retry_pages=None):
        import base64
        from studio_review import page_image
        with self.lock:
            s=self._session(ident,root);self._fresh(s,root,pdf)
            if s['mode']!='pages':raise ValueError('多页选择已失效，请重新选择')
            original=Path(s['folder'])/'before.pdf';images=[];parts=[]
            if retry_pages is not None:
                allowed=set((s.get('result') or {}).get('failedPages',[])+(s.get('result') or {}).get('pendingPages',[]))
                if not isinstance(retry_pages,list) or not retry_pages or any(isinstance(p,bool) or not isinstance(p,int) or p not in allowed for p in retry_pages):raise ValueError('只能重试失败或未完成的页面')
            for p in s['parts']:
                if retry_pages is not None and p['page'] not in retry_pages:continue
                image=page_image(original,self.storage.data,s['projectId'],p['page'],original.stat().st_mtime_ns)
                images.append({'page':p['page'],'image':'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode()})
                parts.append({k:p[k] for k in ('part','page','path','source','displayStart')})
            return parts,images

    def attach_batch(self,ident,root,result):
        from studio_ai import validate_edits
        from studio_change_focus import edit_key
        with self.lock:
            s=self._session(ident,root);kept=[];rejected=list(result.get('rejected',[]));seen=set()
            for edit in result.get('edits',[]):
                try:
                    index=edit['part']
                    if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(s['parts']):raise ValueError('无效的页面来源')
                    part=s['parts'][index];relative=edit['start']-part['displayStart']
                    line=part['source'][:relative].count('\n')+1
                    checked=validate_edits(part['source'],[{'before':edit['before'],'after':edit['after'],'reason':edit['reason'],'line':line}])[0][0]
                    if checked['start']!=relative:raise ValueError('修改超出已选页面的源码范围')
                    start=part['start']+checked['start'];end=part['start']+checked['end'];key=(part['path'],start,end,checked['after'])
                    if key in seen:continue
                    if any(e['path']==part['path'] and start<e['fileEnd'] and end>e['fileStart'] for e in kept):raise ValueError('与其他页面的修改冲突，请单独审阅')
                    seen.add(key);kept.append({**checked,'start':part['displayStart']+checked['start'],'end':part['displayStart']+checked['end'],
                                             'fileStart':start,'fileEnd':end,'path':part['path'],'page':part['page'],'part':index})
                except (ValueError,KeyError,IndexError,TypeError) as exc:
                    rejected.append({'reason':str(exc) if isinstance(exc,ValueError) else '无法定位页面修改'})
            for edit in kept:edit['key']=edit_key(edit)
            result.update(edits=kept,rejected=rejected,pageContext=ident,pages=s['pages'])
            s.update(edits=kept,result=result,preview={})
            s.pop('focusCache',None)
            self.remember(s)

    def preview_batch(self,ident,root,pdf,selected):
        with self.lock:
            s=self._session(ident,root);self._fresh(s,root,pdf)
            if self.busy():raise ValueError('请等待当前预览编译完成')
            if not isinstance(selected,list) or not selected or any(isinstance(i,bool) or not isinstance(i,int) or not 0<=i<len(s['edits'] or []) for i in selected):raise ValueError('请选择有效修改')
            chosen=sorted(set(selected));candidate={name:info['full'] for name,info in s['files'].items()}
            for index in sorted(chosen,key=lambda i:s['edits'][i]['fileStart'],reverse=True):
                edit=s['edits'][index];name=edit['path'];text=candidate[name];candidate[name]=text[:edit['fileStart']]+edit['after']+text[edit['fileEnd']:]
            preview_id=uuid.uuid4().hex;s['preview']={'id':preview_id,'running':True,'stage':'编译所选页面的修改','success':None,'selected':chosen}
            self.remember(s)
            threading.Thread(target=self._compile,args=(s,candidate,preview_id),daemon=True).start()
            return dict(s['preview'])

    def apply_files(self,ident,root,pdf,preview_id,undo=False,selected=None):
        from studio_page_edits import sha
        with self.lock:
            s=self._session(ident,root)
            if s['mode']!='pages':
                target,content,s=self.apply_data(ident,root,pdf,preview_id,undo,selected)
                return [(target,content)],s
            if undo:
                if not s['appliedHashes'] or any(sha(Path(root)/n)!=v for n,v in s['appliedHashes'].items()):raise ValueError('应用后源码已变化，请使用文件历史撤销')
                return [(Path(root)/n,s['files'][n]['originalBytes']) for n in s['appliedHashes']],s
            self._fresh(s,root,pdf);preview=s['preview']
            if preview.get('id')!=preview_id or preview.get('running') or not preview.get('success'):raise ValueError('请先生成所选修改的效果预览')
            if not isinstance(selected,list) or sorted(set(selected))!=preview['selected']:raise ValueError('修改选择已变化，请重新预览')
            changes=[(Path(root)/n,original_encoding(text,s['files'][n]['originalBytes'])) for n,text in s['candidate'].items() if text!=s['files'][n]['full']]
            if not changes:raise ValueError('没有实际源码变化')
            return changes,s
