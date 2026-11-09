"""Explainable local impact and numeric consistency checks. Never executes code."""
import ast,csv,hashlib,io,json,math,re
from collections import defaultdict

ALIASES={
 'accuracy':['accuracy','acc','准确率','识别率'], 'learning_rate':['learning_rate','learningrate','learning rate','lr','学习率'],
 'epochs':['epochs','epoch','迭代轮数','训练轮数','迭代次数'], 'batch_size':['batch_size','batchsize','batch size','批大小','批量大小'],
 'hidden_units':['hidden_units','hidden_size','hidden_dim','hidden units','隐层节点数','隐藏层节点数','隐层宽度'],
 'seed':['seed','random_state','random seed','随机种子'], 'loss':['loss','损失值','损失'],
 'time':['elapsed','duration','runtime','training_time','耗时','训练时间','运行时间'],
 'precision':['precision','精确率'], 'recall':['recall','召回率'], 'f1':['f1','f1_score','F1分数'],
 'samples':['n_samples','样本数','样本数量'], 'cities':['n_cities','城市数','城市数量']}
UNITS={'%':('ratio',.01),'s':('time',1),'秒':('time',1),'ms':('time',.001),'毫秒':('time',.001),'min':('time',60),'分钟':('time',60),'h':('time',3600),'小时':('time',3600),
       'mm':('length',.001),'cm':('length',.01),'m':('length',1),'米':('length',1),'毫米':('length',.001),'厘米':('length',.01),
       'kb':('bytes',1000),'mb':('bytes',1e6),'gb':('bytes',1e9),'kib':('bytes',1024),'mib':('bytes',1024**2),'gib':('bytes',1024**3),
       '次':('number',1),'轮':('number',1),'个':('number',1)}
NUMBER=re.compile(r'(?<![A-Za-z0-9_.])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(%|毫秒|秒|分钟|小时|厘米|毫米|米|[kmg]i?b\b|ms\b|min\b|[smh]\b|次|轮|个)?',re.I)

def _clean(text):
    text=str(text).replace(r'\%', '%').replace(r'\,',' ').replace(r'\;',' ')
    text=re.sub(r'\\(?:begin|end|label|ref|cite\w*)\s*\{[^{}]*\}',' ',text)
    text=re.sub(r'\\[A-Za-z@]+\*?(?:\[[^\]]*\])?',' ',text)
    return re.sub(r'[{}$]','',text).strip()

def _key(label):
    label=_clean(label).casefold();normal=re.sub(r'[^\w\u4e00-\u9fff]','',label).replace('_','')
    scope=next((prefix for prefix,words in [('train',['train','训练']),('test',['test','测试']),('val',['valid','验证'])] if any(w in label for w in words)),'')
    for key,words in ALIASES.items():
        if any(re.sub(r'[^\w\u4e00-\u9fff]','',w.casefold()).replace('_','') in normal for w in words if len(w)>2 or normal==w):return key,scope
    return re.sub(r'[^\w\u4e00-\u9fff]','',label),scope

def _numeric(value,key,unit_hint=''):
    if isinstance(value,bool):return None
    raw=_clean(value);match=NUMBER.fullmatch(raw)
    if not match:return None
    number=float(match[1])
    if not math.isfinite(number):return None
    unit=(match[2] or unit_hint).casefold();group,factor=UNITS.get(unit,('number',1))
    if not unit and key in {'accuracy','precision','recall','f1'} and 0<=number<=1:group='ratio'
    mantissa,_,exponent=match[1].casefold().partition('e');decimals=len(mantissa.partition('.')[2]);step=10**(int(exponent or 0)-decimals)*factor
    return {'value':number,'unit':unit,'unitGroup':group,'normalized':number*factor,'step':step,'display':raw}

def _id(*parts):return hashlib.sha256(':'.join(map(str,parts)).encode()).hexdigest()[:16]

def data_values(sources):
    result=[];warnings=[]
    def add(file,line,label,value,scope='',unit=''):
        if len(result)>=1500:return
        key,inferred=_key(label);parsed=_numeric(value,key,unit)
        if parsed and key:result.append({'id':_id(file,line,label,parsed['display']),'file':file,'line':line,'column':1,'label':label,'evidence':'code' if file.lower().endswith('.py') else 'export','key':key,'scope':(_key(scope)[1] or scope.casefold()) if scope else inferred,**parsed})
    def flatten(file,line,label,value,depth=0):
        if depth>5:return
        if isinstance(value,dict):
            if 'value' in value and 'unit' in value:
                add(file,line,label,value['value'],str(value.get('split','')),str(value['unit']));return
            for key,item in list(value.items())[:200]:flatten(file,line,label+'.'+str(key),item,depth+1)
        elif isinstance(value,(int,float,str)) and not isinstance(value,bool):add(file,line,label,value)
    for file,text in sources.items():
        if file.lower().endswith('.json'):
            try:
                value=json.loads(text)
                if isinstance(value,dict):
                    for key,item in value.items():
                        match=re.search(r'"'+re.escape(key)+r'"\s*:',text);flatten(file,text[:match.start()].count('\n')+1 if match else 1,key,item)
                elif isinstance(value,list):
                    for row in value[:200]:
                        if isinstance(row,dict):
                            scope=str(row.get('split',row.get('dataset','')))
                            if 'value' in row and ('metric' in row or 'name' in row):add(file,1,str(row.get('metric',row.get('name'))),row['value'],scope,str(row.get('unit','')))
                            else:
                                for key,item in row.items():add(file,1,key,item,scope)
            except (ValueError,TypeError):warnings.append({'file':file,'message':'JSON 无法解析，未核对该文件'})
        elif file.lower().endswith('.csv'):
            try:
                reader=csv.DictReader(io.StringIO(text))
                for n,row in enumerate(reader,2):
                    if n>502:break
                    scope=next((str(v) for k,v in row.items() if k and k.casefold() in {'split','dataset','phase'}),'')
                    if 'value' in row and ('metric' in row or 'name' in row):add(file,n,str(row.get('metric',row.get('name'))),row['value'],scope,str(row.get('unit','')));continue
                    for key,item in row.items():
                        if not key:continue
                        unit='%' if '%' in key else next((u for u in UNITS if re.search(r'[([]\s*'+re.escape(u)+r'\s*[)\]]',key,re.I)),'')
                        add(file,n,key,item,scope,unit)
            except (csv.Error,TypeError):warnings.append({'file':file,'message':'CSV 无法解析，未核对该文件'})
        elif file.lower().endswith('.py'):
            try:
                tree=ast.parse(text)
                for node in ast.walk(tree):
                    try:
                        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):flatten(file,node.lineno,node.targets[0].id,ast.literal_eval(node.value))
                        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name):flatten(file,node.lineno,node.target.id,ast.literal_eval(node.value))
                        elif isinstance(node,ast.keyword) and node.arg and node.arg in {w for words in ALIASES.values() for w in words}:flatten(file,node.lineno,node.arg,ast.literal_eval(node.value))
                    except (ValueError,TypeError,SyntaxError):continue
            except SyntaxError:warnings.append({'file':file,'message':'Python 语法无法静态解析，未运行该文件'})
    return result,warnings

def check_consistency(sources,bindings=None,data_files=None,main=None):
    from studio_review import masked
    bindings=bindings if isinstance(bindings,dict) else {}
    if data_files is not None and (not isinstance(data_files,list) or len(data_files)>200 or any(not isinstance(p,str) or p not in sources for p in data_files)):raise ValueError('数据文件选择无效')
    data,warnings=data_values({p:v for p,v in sources.items() if data_files is None or p in data_files});claims=[];seen=set()
    reachable=None
    if main:
        from studio_review import analyze_references
        reachable=set(analyze_references(sources,main)['files'])
    terms={term:key for key,words in ALIASES.items() for term in words}
    for item in data:terms[item['label']]=item['key']
    for file,text in sources.items():
        if not file.lower().endswith('.tex') or reachable is not None and file not in reachable:continue
        clean=masked(text)
        # Named prose metrics; no guesses from unlabeled numbers or arbitrary equations.
        for line_no,line in enumerate(clean.splitlines(),1):
            visible=_clean(line)
            for term,key in terms.items():
                if not term or len(term)>70:continue
                pattern=(r'(?<![A-Za-z_])' if term.isascii() else '')+re.escape(term)+(r'(?![A-Za-z_])' if term.isascii() else '')
                for match in re.finditer(pattern,visible,re.I):
                    tail=visible[match.end():match.end()+36];number=NUMBER.search(tail)
                    if not number or number.start()>18:continue
                    before=re.sub(r'^\s*,\s*which\s+(is|was|are)\s*$',r'\1 ',tail[:number.start()],flags=re.I)
                    if re.search(r'[，,；;。&]',before):continue
                    if re.search(r'\d',before) or any(word.casefold() not in {'is','was','are','equals','equal','to','of','set','at','about','approximately'} for word in re.findall(r'[A-Za-z]+',before)):continue
                    parsed=_numeric(number[0],key)
                    if not parsed:continue
                    identity=(file,line_no,key,number.start()+match.end())
                    if identity in seen:continue
                    seen.add(identity);scope=_key(visible[max(0,match.start()-8):match.end()])[1]
                    claims.append({'id':_id(*identity),'file':file,'line':line_no,'column':1,'label':term,'key':key,'scope':scope,'context':line.strip()[:600],'pdfText':visible[match.start():match.end()+number.end()][:160],'kind':'text',**parsed})
        # Metric header -> numeric table cells.
        for table in re.finditer(r'\\begin\{(?:tabular\*?|tabularx|longtable)\}.*?\\end\{(?:tabular\*?|tabularx|longtable)\}',clean,re.S):
            header=None
            for row in re.finditer(r'(.*?)(?:\\\\(?:\[[^\]]*\])?|$)',table[0],re.S):
                if not row[0].strip():continue
                cells=[_clean(c) for c in row[1].split('&')]
                if len(cells)<2:continue
                row_key,row_scope=_key(cells[0])
                if row_key in ALIASES and any(_numeric(c,row_key) for c in cells[1:]):
                    for col,cell in enumerate(cells[1:],1):
                        parsed=_numeric(cell,row_key)
                        if not parsed:continue
                        pos=table.start()+row.start()+len(row[1])-len(row[1].lstrip());line_no=clean[:pos].count('\n')+1;identity=(file,line_no,row_key,col,'table-row')
                        claims.append({'id':_id(*identity),'file':file,'line':line_no,'column':1,'label':cells[0],'key':row_key,'scope':row_scope or (_key(header[col])[1] if header and col<len(header) else ''),'context':row[1].strip()[:600],'pdfText':cell[:160],'kind':'table',**parsed})
                    continue
                if all(not _numeric(c,_key(c)[0]) for c in cells[1:]):header=cells;continue
                if not header:continue
                for col,cell in enumerate(cells[:len(header)]):
                    key,scope=_key(header[col]);unit='%' if '%' in header[col] else next((u for u in UNITS if re.search(r'[([]\s*'+re.escape(u)+r'\s*[)\]]',header[col],re.I)),'');parsed=_numeric(cell,key,unit)
                    if not parsed or key not in ALIASES:continue
                    pos=table.start()+row.start()+len(row[1])-len(row[1].lstrip());line_no=clean[:pos].count('\n')+1;identity=(file,line_no,key,col,'table')
                    claims.append({'id':_id(*identity),'file':file,'line':line_no,'column':1,'label':header[col],'key':key,'scope':scope or _key(cells[0])[1],'row':cells[0],'context':row[1].strip()[:600],'pdfText':cell[:160],'kind':'table',**parsed})
    items=[];counts=defaultdict(int)
    for claim in claims[:1000]:
        candidates=[d for d in data if d['key']==claim['key'] and (not claim['scope'] or d['scope']==claim['scope'])]
        selected=next((d for d in candidates if d['id']==bindings.get(claim['id'])),None)
        signatures={(d['unitGroup'],d['normalized']) for d in candidates}
        explicit=selected is not None
        # Code literals can belong to different experiments or be function defaults.
        exports=[d for d in candidates if d.get('evidence')=='export']
        row_context=claim.get('row','')
        if not selected and exports and len({(d['unitGroup'],d['normalized']) for d in exports})==1 and not row_context:selected=exports[0]
        if not candidates:status='unlinked';message='项目没有该指标的结果数据，尚未核对；这不是论文错误'
        elif not selected:status='ambiguous';message='请选择与这一实验对应的数据。代码常量可能是默认参数，不能直接作为论文依据'
        elif selected['unitGroup']!=claim['unitGroup']:status='unit';message='单位或比例表示不同，需要确认'
        elif abs(selected['normalized']-claim['normalized'])<=claim['step']/2+max(1e-12,abs(selected['normalized'])*1e-9):status='match';message='与数据一致（允许正文显示精度内的舍入）'
        else:status='mismatch';message='与选定数据不一致'
        counts[status]+=1;items.append({'claim':claim,'sources':candidates[:60],'source':selected,'status':status,'message':message,'binding':('manual' if explicit else 'export') if selected else None})
    return {'items':items,'data':data,'counts':dict(counts),'warnings':warnings,'sourceFiles':sorted({i['file'] for i in data}),
        'note':'只核对已关联的指标；不会运行实验。无来源表示尚未核对，不代表有错。建议导入实际实验导出的 CSV 或 JSON。'}

def impact(sources,main,path,start,end,meta=None,assets=None):
    from studio_review import analyze_references
    if path not in sources:raise ValueError('请选择项目中的文本文件')
    if any(isinstance(n,bool) or not isinstance(n,int) for n in (start,end)) or start<1 or end<start or end>sources[path].count('\n')+1:raise ValueError('请选择有效源码行范围')
    report=analyze_references(sources,main);catalog=report['catalog'];selected='\n'.join(sources[path].splitlines()[start-1:end]);locations=[{'file':path,'line':start,'endLine':end,'reason':'所选源码'}]
    # A caption/body change belongs to its surrounding float even when label is on another line.
    a,b=start,end
    for env in re.finditer(r'\\begin\{(figure\*?|table\*?|equation\*?)\}.*?\\end\{\1\}',sources[path],re.S):
        first=sources[path].count('\n',0,env.start())+1;last=sources[path].count('\n',0,env.end())+1
        if first<=end and last>=start:a=min(a,first);b=max(b,last)
    labels=[e for e in catalog['labels'] if any(d['file']==path and d['line']<=b and d.get('endLine',d['line'])>=a for d in e['definitions'])]
    bibliography=[e for e in catalog['bibliography'] if any(d['file']==path and d['line']<=end and d.get('endLine',d['line'])>=start for d in e['definitions'])]
    usages=[]
    for entry in labels+bibliography:
        for loc in entry['usages']:usages.append(loc);locations.append({**loc,'reason':'引用 '+entry['key']})
    direct=[e for e in catalog['references']+catalog['citations'] if e['file']==path and start<=e['line']<=end]
    for entry in direct:
        for definition in (entry.get('definitions') or next((e['definitions'] for e in catalog['bibliography'] if e['key']==entry['key']),[])):locations.append({**definition,'reason':'所选引用的目标 '+entry['key']})
    files={path};changed=True
    while changed:
        changed=False
        for edge in catalog['edges']:
            if edge['to'] in files and edge['from'] not in files:files.add(edge['from']);changed=True
    pages={};page_map=(meta or {}).get('pages',{})
    broad=bool(re.search(r'\\(?:documentclass|usepackage|newcommand|renewcommand|geometry|set(?:main|sans|mono|CJK\w*)font|linespread)\b',selected))
    if broad:
        for p in range(1,int((meta or {}).get('totalPages',0))+1):pages[p]={'page':p,'reasons':['全局命令可能影响排版']}
    else:
        for p,mapping in page_map.items():
            for loc in locations:
                rows=mapping.get(loc['file'],{});a=loc['line'];b=loc.get('endLine',a)
                if any(a<=int(row)<=b for row in rows):pages.setdefault(int(p),{'page':int(p),'reasons':[]})['reasons'].append(loc['reason'])
    touched_assets=[]
    for name in assets or []:
        if name not in files and (name in selected or path==name):touched_assets.append(name)
    return {'selection':{'file':path,'startLine':start,'endLine':end},'labels':labels,'bibliography':bibliography,'references':usages+direct,'files':sorted(files),'assets':touched_assets,
        'pages':[{'page':p,'reasons':sorted(set(value['reasons']))} for p,value in sorted(pages.items())],'global':broad,
        'note':'展示静态可追踪的直接关联；分页重排、动态宏及运行代码生成的数据可能影响更多页面。'}
