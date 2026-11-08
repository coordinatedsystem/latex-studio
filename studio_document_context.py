"""Bounded project context for connected page review; no network or source writes."""
from pathlib import Path
import json,re
from pypdf import PdfReader
from studio_page_edits import project_files

MAX_REVIEW_PAGES=80
def reading_context(root,main,pdf,pages,whole=False):
    root=Path(root).resolve();document=PdfReader(pdf)
    if len(document.pages)>MAX_REVIEW_PAGES and whole:raise ValueError('全文审核最多支持 80 页，请按章节选择')
    if any(p<1 or p>len(document.pages) for p in pages):raise ValueError('页次超出当前 PDF 范围')
    if whole and pages!=list(range(1,len(document.pages)+1)):raise ValueError('全文审核需要选择所有页面')
    texts=[];outline=[]
    for file in project_files(root):
        if file.suffix.lower() not in {'.tex','.bib'}:continue
        text=file.read_text('utf-8-sig');name=file.relative_to(root).as_posix()
        outline.extend({'file':name,'title':m[1]} for m in re.finditer(r'\\(?:chapter|section|subsection)\*?\{([^}]+)\}',text))
        if whole:
            texts.append('% '+name+'\n'+text)
            if sum(map(len,texts))>60000:raise ValueError('全文上下文超过 60000 字符，请按章节审核；尚未调用 AI')
    result={'main':main,'totalPages':len(document.pages),'selectedPages':pages,'outline':outline[:160],'pageSummaries':[],'wholeDocument':bool(whole)}
    neighbors={n for p in pages for n in (p-1,p,p+1) if 1<=n<=len(document.pages)}
    adjacent={}
    for n,page in enumerate(document.pages,1):
        text=(page.extract_text() or '')
        if n in neighbors:adjacent[str(n)]=text[:3000]
        if whole or n in neighbors or len(result['pageSummaries'])<160:result['pageSummaries'].append({'page':n,'text':text[:160]})
    if whole:result['documentSource']='\n\n'.join(texts)
    if whole and len(json.dumps(result,ensure_ascii=False))>60000:raise ValueError('全文上下文超过 60000 字符，请按章节审核；尚未调用 AI')
    return result,adjacent
