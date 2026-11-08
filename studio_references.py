"""Inspectable, project-scoped reference entries. Never fetches remote metadata."""
from collections import defaultdict
import hashlib
import posixpath
import re

LIMIT=2000

def plain(text):
    text=re.sub(r'\\(?:url|href|textit|textbf|emph|textrm|textnormal)\s*\{([^{}]*)\}',r'\1',str(text))
    return re.sub(r'\s+',' ',re.sub(r'[{}]','',text)).strip()

def bib_fields(raw):
    from studio_review import group
    result={};cursor=raw.find(',')+1
    while cursor>0 and cursor<len(raw):
        match=re.search(r'([\w-]+)\s*=\s*',raw[cursor:])
        if not match:break
        name=match[1].lower();start=cursor+match.end();value='';end=start
        if start<len(raw) and raw[start]=='{':
            parsed=group(raw,start)
            if parsed:value,end=parsed
        elif start<len(raw) and raw[start]=='"':
            end=start+1
            while end<len(raw) and (raw[end]!='"' or raw[end-1]=='\\'):end+=1
            value=raw[start+1:end];end+=1
        else:
            end=raw.find(',',start)
            if end<0:end=len(raw)-1
            value=raw[start:end]
        result[name]=plain(value)[:1200];cursor=max(start+1,end)
    return result

def _raw_location(sources,loc,key,kind,occurrence=0):
    from studio_review import group,masked
    text=sources[loc['file']];lines=text.splitlines(keepends=True);line=max(1,min(loc['line'],len(lines) or 1));start=sum(map(len,lines[:line-1]));stop=start+len(lines[line-1] if lines else '')
    patterns={'labels':r'\\label\s*\{[^}]*\}', 'references':r'\\(?:eqref|ref|autoref|pageref|nameref|cref|Cref|vref)\*?\s*\{[^}]*\}',
              'citations':r'\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{[^}]*\}', 'bibliography':r'\\bibitem\s*(?:\[[^\]]*\])?\{[^}]*\}|@[A-Za-z]+\s*[{(]\s*[^,\s]+\s*,'}
    def has_key(value):
        if value.startswith('@'):
            found=re.search(r'@[A-Za-z]+\s*[{(]\s*([^,\s]+)',value);return bool(found and found[1]==key)
        groups=re.findall(r'\{([^{}]*)\}',value);return bool(groups and key in [part.strip() for part in groups[-1].split(',')])
    candidates=[m for m in re.finditer(patterns[kind],masked(text[start:stop])) if has_key(m[0])]
    match=candidates[min(occurrence,len(candidates)-1)] if candidates else None
    a=start+(match.start() if match else 0);b=start+(match.end() if match else len(text[start:stop].rstrip()))
    command=text[a:b]
    if kind=='bibliography':
        if command.startswith('@'):
            opening=re.search(r'[{(]',text[a:b]);parsed=group(text,a+opening.start(),opening[0],'}' if opening[0]=='{' else ')') if opening else None
            if parsed:b=parsed[1]
        else:
            following=re.search(r'\\bibitem\b|\\end\s*\{thebibliography\}',masked(text[b:]));b=b+following.start() if following else min(len(text),b+12000)
    raw=text[a:b].strip()[:12000];endline=text[:b].count('\n')+1
    column=len(text[start:a].encode('utf-16-le'))//2+1
    return {'file':loc['file'],'line':line,'column':column,'endLine':endline,'raw':raw,'match':command,'context':''.join(lines[max(0,line-3):min(len(lines),endline+2)])[:2200],
            'key':key,'kind':kind}

def catalog(sources,files,labels,refs,cites,bibs):
    from studio_review import masked
    seen=defaultdict(int)
    def location(loc,key,kind):
        identity=(loc['file'],loc['line'],key,kind);n=seen[identity];seen[identity]+=1
        return _raw_location(sources,loc,key,kind,n)
    label_defs={key:[location(loc,key,'labels') for loc in locs] for key,locs in list(labels.items())[:LIMIT]}
    bib_defs={key:[location(loc,key,'bibliography') for loc in locs] for key,locs in list(bibs.items())[:LIMIT]}
    references=[{**location(loc,key,'references'),'resolved':key in labels} for key,loc in refs[:LIMIT]]
    citations=[{**location(loc,key,'citations'),'resolved':key in bibs or key=='*'} for key,loc in cites[:LIMIT]]
    result={'files':[],'labels':[],'references':[],'bibliography':[],'citations':citations,'edges':[], 'truncated':any(n>LIMIT for n in [len(labels),len(refs),len(cites),len(bibs)])}
    for file in files:
        text=sources[file];result['files'].append({'file':file,'line':1,'kind':'files','key':file,'title':file,'raw':text[:2200],'lines':text.count('\n')+1,
            'labels':sum(sum(loc['file']==file for loc in locs) for locs in labels.values()),'references':sum(loc['file']==file for _,loc in refs),'citations':sum(loc['file']==file for _,loc in cites)})
        for match in re.finditer(r'\\(input|include|subfile|bibliography|addbibresource)\s*(?:\[[^\]]*\])?\{([^}]+)\}',masked(text)):
            for name in match[2].split(','):
                target=posixpath.normpath(posixpath.join(posixpath.dirname(file),name.strip()))
                if not posixpath.splitext(target)[1]:target+='.bib' if match[1] in {'bibliography','addbibresource'} else '.tex'
                if target in files:result['edges'].append({'from':file,'to':target,'line':text[:match.start()].count('\n')+1})
    for key,definitions in label_defs.items():
        loc=definitions[0];context=loc['context'];kind=next((v for p,v in [('fig','图'),('tab','表'),('eq','公式'),('sec','章节')] if key.lower().startswith(p)),'标签')
        result['labels'].append({**loc,'title':key,'objectType':kind,'definitions':definitions,'usages':[r for r in references if r['key']==key],'duplicate':len(definitions)>1})
    for loc in references:result['references'].append({**loc,'title':loc['key'],'definitions':label_defs.get(loc['key'],[])})
    for key,definitions in bib_defs.items():
        loc=definitions[0];fields=bib_fields(loc['raw']) if loc['raw'].startswith('@') else {}
        result['bibliography'].append({**loc,'title':fields.get('title') or plain(re.sub(r'^\\bibitem\s*(?:\[[^\]]*\])?\{[^}]+\}','',loc['raw']))[:200] or key,
            'fields':fields,'definitions':definitions,'usages':[c for c in citations if c['key'] in {key,'*'}],'duplicate':len(definitions)>1})
    for kind in ['files','labels','references','bibliography','citations']:
        for index,item in enumerate(result[kind]):item['id']=hashlib.sha256(f"{kind}:{item['key']}:{item['file']}:{item['line']}:{index}".encode()).hexdigest()[:16]
    return result
