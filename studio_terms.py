"""Evidence-anchored terminology review. All replacements require a reviewed plan."""
from pathlib import Path
import hashlib,json,re,uuid
from studio_storage import project_id,read_json,write_json
from studio_review import analyze_references,masked,group
from studio_batch_edits import atomic_write_set

def digest(raw):return hashlib.sha256(raw).hexdigest()

def prose_mask(text):
    """Keep offsets; exclude mathematics, command names and structural arguments."""
    view=list(masked(text))
    def hide(a,b):
        for i in range(a,b):
            if view[i]!='\n':view[i]=' '
    source=''.join(view)
    pattern=r'\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|tikzpicture|thebibliography)\}.*?\\end\{\1\}|\\\[.*?\\\]|\\\(.*?\\\)|(?<!\\)\$\$.*?(?<!\\)\$\$|(?<!\\)\$[^$\n]*?(?<!\\)\$'
    for m in re.finditer(pattern,source,re.S):hide(m.start(),m.end())
    source=''.join(view)
    for m in re.finditer(r'\\([A-Za-z@]+)\*?',source):
        name=m[1];end=m.end();hide(m.start(),end)
        # Only these commands have prose arguments that may be edited.
        if name in {'section','subsection','subsubsection','paragraph','chapter','title','caption','emph','textbf','textit','textrm','textsf','textnormal','underline','mbox','footnote'}:continue
        while True:
            parsed=group(source,end,'[',']') or group(source,end)
            if not parsed:break
            hide(end,parsed[1]);end=parsed[1]
    body=re.search(r'\\begin\{document\}',text)
    if body:hide(0,body.end())
    return ''.join(view)

def occurrences(text,term,view=None):
    left=r'(?<![A-Za-z0-9_])' if re.match(r'[A-Za-z0-9_]',term) else ''
    right=r'(?![A-Za-z0-9_])' if re.search(r'[A-Za-z0-9_]$',term) else ''
    return list(re.finditer(left+re.escape(term)+right,prose_mask(text) if view is None else view))

def valid_term(value):
    return isinstance(value,str) and bool(re.search(r'[A-Za-z\u4e00-\u9fff]',value)) and 1<len(value.strip())<=120 and not re.search(r'[\\{}$%\n\r\x00-\x1f]',value)

def selected_terms(value):
    if value is None:return []
    if not isinstance(value,list) or not 1<=len(value)<=100:raise ValueError('请选择 1～100 个术语')
    result=[];seen=set()
    for item in value:
        if not isinstance(item,dict) or not valid_term(item.get('source')):raise ValueError('所选术语原词无效')
        source=item['source'].strip()
        if source.casefold() in seen:continue
        seen.add(source.casefold());result.append({'source':source,'target':str(item.get('target',''))[:160],'note':str(item.get('note',''))[:300]})
    return result

class Terms:
    def __init__(self,data):self.data=Path(data)
    def folder(self,root):return self.data/'terminology'/project_id(root)
    def path(self,root,ident):
        if not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{32}',ident):raise ValueError('术语任务无效')
        return self.folder(root)/(ident+'.json')
    def load(self,root,ident):
        value=read_json(self.path(root,ident),{})
        if not value:raise ValueError('术语任务不存在，请重新提取')
        return value
    def save(self,root,s):write_json(self.path(root,s['id']),s)
    def prepare(self,root,sources,main,targets=None):
        targets=selected_terms(targets)
        reachable=analyze_references(sources,main)['files'];files={}
        for name in reachable:
            if not name.endswith('.tex'):continue
            raw=(Path(root)/name).read_bytes();text=raw.decode('utf-8-sig');files[name]={'text':text,'hash':digest(raw),'bom':raw.startswith(b'\xef\xbb\xbf')}
        document='\n\n'.join('FILE '+name+'\n'+prose_mask(f['text']) for name,f in files.items())
        if not document.strip() or len(document)>180000:raise ValueError('全文提取支持 18 万字符以内的正文项目，请拆分过长项目')
        ident=uuid.uuid4().hex;s={'id':ident,'files':files,'groups':[],'main':main,'applied':False,'targets':targets}
        self.save(root,s);return ident,document
    def attach(self,root,ident,result):
        s=self.load(root,ident);groups=[];seen=set();views={n:prose_mask(f['text']) for n,f in s['files'].items()}
        proposed=result.get('groups',[])
        targets={t['source'].casefold():t for t in s.get('targets',[])}
        if not isinstance(proposed,list):raise ValueError('术语响应格式无效')
        for item in proposed[:100]:
            if not isinstance(item,dict):continue
            preferred=item.get('preferred','').strip() if isinstance(item.get('preferred'),str) else ''
            if not valid_term(preferred) or preferred.casefold() in seen:continue
            values=item.get('variants',[])
            if not isinstance(values,list):continue
            target=targets.get(preferred.casefold())
            if targets and not target:
                target=next((targets[v.casefold()] for v in values if isinstance(v,str) and v.casefold() in targets),None)
            if targets and not target:continue
            if target:preferred=target['source']
            if preferred.casefold() in seen:continue
            variants=[]
            for term in dict.fromkeys([preferred]+[v for v in values if isinstance(v,str)]):
                if not valid_term(term):continue
                locs=[]
                for name,f in s['files'].items():
                    for m in occurrences(f['text'],term,views[name]):
                        line=f['text'].count('\n',0,m.start())+1
                        locs.append({'file':name,'line':line,'start':m.start(),'end':m.end(),'context':f['text'][max(0,m.start()-45):m.end()+60]})
                if locs:variants.append({'text':term,'count':len(locs),'locations':locs[:300]})
            if not variants:continue
            # Proposed spellings must already be found in the paper.
            if not target and preferred not in [v['text'] for v in variants]:preferred=variants[0]['text']
            relation=item.get('relation','related')
            relation=relation if relation in {'same','abbreviation','related'} else 'related'
            if relation=='same' and len({tuple(re.findall(r'\d+(?:\.\d+)?',value)) for value in [preferred]+[v['text'] for v in variants]})>1:relation='related'
            translation=str(target['target'] if target else item.get('target',''))[:160].strip()
            if re.search(r'[\x00-\x1f]',translation):translation=''
            groups.append({'id':len(groups),'preferred':preferred,'target':translation,'note':str(item.get('note',''))[:300], 'relation':relation,'variants':variants})
            seen.add(preferred.casefold())
        for key,target in targets.items():
            if key not in seen:groups.append({'id':len(groups),'preferred':target['source'],'target':target['target'],'note':'未找到可核对的正文位置，请检查术语或重新检索。','relation':'related','variants':[]})
        s['groups']=groups;self.save(root,s)
        result.clear();result.update({'termContext':ident,'groups':groups,'summary':f'已找到 {len(groups)} 组术语','files':list(s['files'])})
    def check(self,root,s,applied=False):
        for name,f in s['files'].items():
            p=(Path(root)/name).resolve()
            if not p.is_relative_to(Path(root).resolve()) or p.is_symlink():raise ValueError('术语文件路径无效')
            expected=f.get('appliedHash') if applied else f['hash']
            if not p.is_file() or digest(p.read_bytes())!=expected:raise ValueError('文档已变化，请重新提取术语；未覆盖任何文件')
    def plan(self,root,ident,choices):
        s=self.load(root,ident);self.check(root,s)
        if not isinstance(choices,list) or len(choices)>100:raise ValueError('请选择术语')
        edits={};selected=set();skipped=[];views={n:prose_mask(f['text']) for n,f in s['files'].items()}
        for choice in choices:
            if not isinstance(choice,dict):raise ValueError('术语选择无效')
            n=choice.get('id')
            if not isinstance(n,int) or isinstance(n,bool) or n<0 or n>=len(s['groups']) or n in selected:raise ValueError('术语选择无效')
            selected.add(n);g=s['groups'][n]
            if g['relation']!='same':raise ValueError('缩写及相关概念不自动合并，请只选择同义写法')
            preferred=choice.get('preferred',g['preferred'])
            if not valid_term(preferred):raise ValueError('首选术语无效')
            for v in g['variants']:
                if v['text']==preferred:continue
                for name,f in s['files'].items():
                    for m in occurrences(f['text'],v['text'],views[name]):
                        a=max(f['text'].rfind(c,0,m.start()) for c in '。；;\n')+1
                        ends=[i for c in '。；;\n' if (i:=f['text'].find(c,m.end()))>=0];b=min(ends) if ends else len(f['text'])
                        clause=f['text'][a:b]
                        others=[t['text'] for t in g['variants'] if t['text']!=v['text'] and t['text'] in clause]
                        defining=bool(others and (re.search(r'又称|亦称|称为|简称|也称|即为|also (?:called|known)|referred to|[（(].*[）)]',clause,re.I) or any(re.search(re.escape(t)+r'\s*(?:与|和|及|或|and|or|/|、)\s*'+re.escape(v['text'])+'|'+re.escape(v['text'])+r'\s*(?:与|和|及|或|and|or|/|、)\s*'+re.escape(t),clause,re.I) for t in others)))
                        if defining:
                            skipped.append({'file':name,'line':f['text'].count('\n',0,m.start())+1,'before':m[0],'reason':'定义、别名说明或并列概念，保留原文以免造成重复或改变含义'});continue
                        edits.setdefault(name,[]).append({'start':m.start(),'end':m.end(),'before':m[0],'after':preferred,'group':n})
        for name,items in edits.items():
            items.sort(key=lambda e:e['start'])
            if any(a['end']>b['start'] for a,b in zip(items,items[1:])):raise ValueError('所选术语有重叠，请分批统一')
        plan={'id':uuid.uuid4().hex,'changes':[], 'count':0,'skipped':skipped}
        for name,items in edits.items():
            text=s['files'][name]['text'];after=text
            for e in reversed(items):after=after[:e['start']]+e['after']+after[e['end']:]
            plan['changes'].append({'path':name,'before':text,'after':after,'edits':items});plan['count']+=len(items)
        s['plan']=plan;self.save(root,s);return plan
    def apply(self,root,ident,plan_id,snapshot,undo=False):
        s=self.load(root,ident);plan=s.get('plan',{})
        if plan.get('id')!=plan_id or not plan.get('count'):raise ValueError('请先预览术语修改')
        if s['applied']==(not undo):raise ValueError('任务状态已变化，请重新打开结果')
        self.check(root,s,applied=undo);changes=[]
        for c in plan['changes']:
            f=s['files'][c['path']];text=c['before' if undo else 'after'];raw=text.encode('utf-8-sig' if f['bom'] else 'utf-8');changes.append((Path(root)/c['path'],raw))
        for p,_ in changes:snapshot(p,'术语撤销前' if undo else '术语统一前')
        atomic_write_set(changes)
        for p,raw in changes:
            s['files'][p.relative_to(root).as_posix()]['appliedHash']=digest(raw)

        # Unmodified dependencies must also be checked before undo.
        for f in s['files'].values():f.setdefault('appliedHash',f['hash'])
        s['applied']=not undo;self.save(root,s)
        warnings=[]
        for p,_ in changes:
            try:snapshot(p,'术语撤销' if undo else '术语统一')
            except OSError:warnings.append('文件已保存，但版本历史未能写入')
        return {'ok':True,'files':[c['path'] for c in plan['changes']],'warnings':warnings}
