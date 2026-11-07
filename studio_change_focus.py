"""Locate literal text changes in real PDF pages; fall back to actual pixel differences."""
import hashlib
from pathlib import Path
import re

def edit_key(edit,path='',offset=0):
    value='\0'.join((edit.get('path',path),str(edit.get('fileStart',offset+edit['start'])),edit['before'],edit['after']))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]

def text_box(page,text):
    if not text or '\\' in text or len(text)>4000:return None
    needle=re.sub(r'[\s\u200b]+','',text)
    if len(needle)<2:return None
    letters=[];positions=[]
    for char in page.chars:
        for letter in re.sub(r'[\s\u200b]+','',char.get('text','')):letters.append(letter);positions.append(char)
    value=''.join(letters);start=value.find(needle)
    if start<0 or value.find(needle,start+1)>=0:return None
    chars=positions[start:start+len(needle)]
    return [max(0,min(c['x0'] for c in chars)/page.width),max(0,min(c['top'] for c in chars)/page.height),
            min(1,max(c['x1'] for c in chars)/page.width),min(1,max(c['bottom'] for c in chars)/page.height)]

def locate(pdf,preferred,text,search=False):
    import pdfplumber
    if not text or '\\' in text:return None
    with pdfplumber.open(pdf) as document:
        if 1<=preferred<=len(document.pages):
            box=text_box(document.pages[preferred-1],text)
            if box:return {'page':preferred,'box':box}
        if search:
            found=[]
            for i,page in enumerate(document.pages[:200],1):
                if i==preferred:continue
                box=text_box(page,text)
                if box:found.append({'page':i,'box':box})
                if len(found)>1:return None
            if found:return found[0]
    return None

def focus(manager,ident,root,index=None,key=None,preview_id=None):
    with manager.lock:
        s=manager._session(ident,root);edits=s.get('edits') or []
        if key is not None:index=next((i for i,e in enumerate(edits) if e.get('key')==key),-1)
        if not isinstance(index,int) or not 0<=index<len(edits):raise ValueError('该条建议已更新，请重新选择')
        edit=dict(edits[index]);page=edit.get('page',s['page']);before_pdf=Path(s['folder'])/'before.pdf';preview=dict(s['preview']);candidate=s.get('candidatePdf')
        cache_key=(edit.get('key',str(index)),preview_id)
        cached=s.setdefault('focusCache',{}).get(str(cache_key))
        if cached:return cached
    before=locate(before_pdf,page,edit['before']);after=None
    valid=bool(preview.get('success') and preview.get('id')==preview_id and index in preview.get('selected',[]) and candidate and Path(candidate).exists())
    if valid:after=locate(candidate,page,edit['after'],True)
    bounds=next((p.get('bounds') for p in preview.get('pages',[]) if p['page']==page),None) if valid else None
    kind='text' if before or after else 'pixels' if bounds else 'source'
    result={'index':index,'page':page,'kind':kind,'before':before or ({'page':page,'box':bounds} if bounds else None),
            'after':after or ({'page':min(page,preview.get('totalPages',page)),'box':bounds} if bounds else None),
            'previewId':preview_id if valid else None,'label':'文字改动' if kind=='text' else '本页改动区域' if kind=='pixels' else '源码设置'}
    with manager.lock:s.setdefault('focusCache',{})[str(cache_key)]=result
    return result

def image(manager,ident,root,which,index=None,key=None,preview_id=None):
    from studio_review import page_image
    result=focus(manager,ident,root,index,key,preview_id)
    with manager.lock:
        s=manager._session(ident,root)
        if which=='before':pdf=Path(s['folder'])/'before.pdf';page=(result['before'] or {}).get('page',result['page'])
        elif which=='after' and result['previewId'] and result['after']:pdf=Path(s['candidatePdf']);page=result['after']['page']
        else:raise ValueError('该建议尚未生成可用的效果预览')
        return page_image(pdf,manager.storage.data,s['projectId'],page,pdf.stat().st_mtime_ns)
