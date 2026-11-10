"""Studio capability plugins: schemas, mode admission and domain tool handlers."""
from dataclasses import dataclass
import copy,json,os
from pathlib import Path
from studio_editor_ai import EDITABLE,cached_resource_missing
from studio_page_edits import project_files
from studio_assistant_content import TEXT,window,image_payload,bounded_int

def function(name,description,properties=None,required=()):
    return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties or {},'required':list(required)}}}
S={'type':'string'};I={'type':'integer'};B={'type':'boolean'}
def builtin_schemas(mode):
    tools=[function('list_files','列出项目文件'),function('read_file','读取指定文件行范围；start>=1，每次最多160行。默认80行。',{'path':S,'start':{'type':'integer','minimum':1},'lines':{'type':'integer','minimum':1,'maximum':160}},('path',)),
           function('search','字面检索，优先检索必要片段',{'query':S,'path':S},('query',)),function('diagnostics','读取精简编译报错'),function('environment','查看可用字体与编译环境'),function('references','检查引用'),function('glossary','读取术语表'),
           function('layout_check','检查 PDF 版面几何和页次，默认关联页或代表页，不重读全文。',{'pages':{'type':'array','items':I,'maxItems':12}}),
           function('read_page','读取 PDF 页面；需要视觉判断时 visual=true，最多按需查看代表页。',{'page':I,'visual':B},('page',)),
           function('read_attachment','读取明确关联的附件，PDF 可指定 page 和 visual',{'id':S,'start':I,'lines':I,'page':I,'visual':B},('id',))]
    if mode=='agent':tools.extend([function('edit','先读取文件，再按准确原文替换副本',{'path':S,'before':S,'after':S,'replace_all':B},('path','before','after')),function('compile','编译候选并验证 PDF；源码未变则复用结果'),function('resources','恢复编译器已知缺少的公共资源')])
    return tools

@dataclass(frozen=True)
class ToolSpec:
    schema:dict
    handler:object
    modes:tuple=('chat','agent')
    exclusive:bool=False
    @property
    def name(self):return self.schema['function']['name']

class ToolRegistry:
    def __init__(self):self._tools={}
    def register(self,spec):
        if spec.name in self._tools:raise ValueError('工具重复注册：'+spec.name)
        self._tools[spec.name]=spec
        def dispose():
            if self._tools.get(spec.name) is spec:self._tools.pop(spec.name)
        return dispose
    def resolve(self,name,mode):
        spec=self._tools.get(name)
        if spec is None:raise ValueError('不支持的 Studio 工具')
        if mode not in spec.modes:raise ValueError('Chat 模式只读，请切换 Agent 执行')
        return spec
    def schemas(self,mode):return [copy.deepcopy(s.schema) for s in self._tools.values() if mode in s.modes]

class StudioTools:
    def __init__(self,owner):
        self.owner=owner;self.registry=ToolRegistry()
        for schema in builtin_schemas('agent'):
            name=schema['function']['name'];mutating=name in {'edit','compile','resources'}
            handler=getattr(self,'compile_candidate' if name in {'compile','resources'} else name)
            self.registry.register(ToolSpec(schema,handler,('agent',) if mutating else ('chat','agent'),mutating))
    def execute(self,s,clone,name,args,read):
        self.owner.checkpoint()
        return self.registry.resolve(name,s['chatMode']).handler(s,clone,args,read,name)

    def list_files(self,s,clone,args,read,name):
        if name=='list_files':return {'files':s.get('knownFiles',[p.relative_to(clone).as_posix() for p in project_files(clone)])[:350]}

    def read_file(self,s,clone,args,read,name):
        path,p=self.owner.file(clone,args.get('path',''));read.add(path);return window(p.read_text('utf-8-sig'),args.get('start',1),min(160,max(1,int(args.get('lines',80)))))

    def search(self,s,clone,args,read,name):
        query=args.get('query','')
        if not isinstance(query,str) or not 1<=len(query)<=200:raise ValueError('检索词应为 1～200 字符')
        paths=[self.owner.file(clone,args['path'])[1]] if args.get('path') else [p for p in project_files(clone) if p.suffix.lower() in TEXT and p.stat().st_size<=2*1024*1024]
        hits=[]
        for p in paths:
            for i,line in enumerate(p.read_text('utf-8-sig',errors='replace').splitlines(),1):
                if query.casefold() in line.casefold():hits.append({'path':p.relative_to(clone).as_posix(),'line':i,'text':line[:350]})
                if len(hits)>=40:return {'hits':hits,'truncated':True}
        return {'hits':hits}

    def environment(self,s,clone,args,read,name):
        fonts=[family for filename,family in [('arial.ttf','Arial'),('times.ttf','Times New Roman'),('simsun.ttc','SimSun'),('msyh.ttc','Microsoft YaHei'),('simhei.ttf','SimHei')] if (Path(os.environ.get('WINDIR',r'C:\Windows'))/'Fonts'/filename).is_file()]
        return {'engine':'Tectonic / XeTeX','installedFonts':fonts,'fontHint':'用 fontspec 的 setmainfont 选择已安装字体；不支持 shell-escape 或更换引擎'}

    def diagnostics(self,s,clone,args,read,name):
        if name=='diagnostics':return {'compiler':'Tectonic/XeTeX','log':s.get('lastLog',s['errorContext'])[-6000:],'compiled':s.get('lastCompiled',False)}

    def references(self,s,clone,args,read,name):
        from studio_review import analyze_references
        sources={p.relative_to(clone).as_posix():p.read_text('utf-8-sig',errors='replace') for p in project_files(clone) if p.suffix.lower() in {'.tex','.bib'} and p.stat().st_size<2*1024*1024}
        report=analyze_references(sources,s['main']);return {k:report.get(k) for k in ('issues','labels','references','bibliography')}

    def glossary(self,s,clone,args,read,name):
        from studio_review import glossary_get
        return {'terms':glossary_get(self.owner.storage.data,s['projectId']).get('terms',[])[:100]}

    def layout_check(self,s,clone,args,read,name):
        from pypdf import PdfReader
        from studio_review import inspect_pdf
        pdf=self.owner.folder(s['root'],s['id'],True)/('candidate.pdf' if s.get('verified') else 'before.pdf')
        if not pdf.exists():return {'error':'尚无 PDF，请先 compile 再检查版面'}
        total=len(PdfReader(pdf).pages)
        selected=args.get('pages') or s.get('pages',[])[:12] or sorted({1,min(2,total),max(1,(total+1)//2),total})
        if not isinstance(selected,list) or len(selected)>12:raise ValueError('每次检查 1～12 页')
        selected=sorted(set(bounded_int(n,1,total) for n in selected));report=inspect_pdf(pdf,','.join(map(str,selected)),checkpoint=self.owner.checkpoint)
        report['measurementNotes']='contentBottom 是最后一个对象距页面顶端的比例，包含页脚页码；0.89 表示89%处，不能用来计算正文留白。少量留白、末页和缺少某些论文结构不自动构成错误，小字号也要区分正文、脚注和公式。'
        report['scope']='仅检查列出的页次，未检查的页不能宣称已审核'
        s['layoutEvidence']={'pages':selected,'issues':report['issues'],'totalPages':total}
        return report

    def read_page(self,s,clone,args,read,name):
        from pypdf import PdfReader
        pdf=self.owner.folder(s['root'],s['id'],True)/('candidate.pdf' if s.get('verified') else 'before.pdf')
        if not pdf.is_file():raise ValueError('尚无 PDF，请在 Agent 中编译或先在主页面编译')
        reader=PdfReader(pdf);page=bounded_int(args.get('page',1),1,len(reader.pages))
        if args.get('visual') is True:
            from studio_review import page_image
            image=page_image(pdf,self.owner.folder(s['root'],s['id'],True)/'pages',s['projectId'],page,pdf.stat().st_mtime_ns)
            return {'image':image_payload(image),'name':'PDF 第 '+str(page)+' 页'}
        return {'page':page,'pages':len(reader.pages),**window(reader.pages[page-1].extract_text() or '本页无文字层，可用 visual:true 检查图片。',1,100)}

    def read_attachment(self,s,clone,args,read,name):
        ident=args.get('id')
        if ident not in {m['id'] for m in s['attachments']}:raise ValueError('该附件未关联到当前会话')
        meta,p=self.owner.attachment_meta(s['root'],ident);suffix=meta['suffix']
        if suffix in {'.png','.jpg','.jpeg','.webp'}:
            return {'image':image_payload(p),'name':meta['name']}
        if suffix=='.pdf':
            from pypdf import PdfReader
            reader=PdfReader(p);page=bounded_int(args.get('page',1),1,len(reader.pages))
            if args.get('visual') is True:
                from studio_review import page_image
                image=page_image(p,self.owner.folder(s['root'],s['id'],True)/'attachment-pages',ident,page,p.stat().st_mtime_ns)
                return {'image':image_payload(image),'name':meta['name']+' 第 '+str(page)+' 页'}
            return {'page':page,'pages':len(reader.pages),**window(reader.pages[page-1].extract_text() or '本页无文字层，可用 visual:true 查看扫描页面。',args.get('start',1),args.get('lines',80))}
        if suffix=='.docx':
            import zipfile,xml.etree.ElementTree as ET
            with zipfile.ZipFile(p) as archive:
                entry=archive.getinfo('word/document.xml')
                if entry.file_size>4*1024*1024:raise ValueError('Word 文档内容过大')
                text='\n'.join(''.join(e.itertext()) for e in ET.fromstring(archive.read(entry)).iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'))
        else:text=p.read_text('utf-8-sig')
        return window(text,args.get('start',1),args.get('lines',80))

    def edit(self,s,clone,args,read,name):
        path,p=self.owner.file(clone,args.get('path',''))
        if p.suffix.lower() not in EDITABLE or path not in read:raise ValueError('修改前请读取相应 LaTeX 文件')
        full=p.read_text('utf-8-sig');count=self.owner.accept(s,clone,path,0,len(full),full,{'edits':[args]});s['verified']=False;s['lastCompiled']=False;s['candidateReady']=False;s['editRevision']=s.get('editRevision',0)+1
        return {'edits':count,'path':path,'revision':s['editRevision']}

    def compile_candidate(self,s,clone,args,read,name):
        revision=s.get('editRevision',0)
        if s.get('compiledRevision')==revision and name=='compile':return {'success':s['lastCompiled'],'unchanged':True,'log':s.get('lastLog','')[-4500:]}
        if name=='resources':
            missing=cached_resource_missing(s.get('lastLog',s['errorContext']),self.owner.storage.tex_cache)
            if not missing:raise ValueError('当前没有可自动恢复的官方宏包缺失记录')
            s['allowNetwork']=True
        ok,log=self.owner.compile_copy(s,clone,len(s['events']));s.update(lastLog=log,lastCompiled=ok,compiledRevision=revision,verified=ok)
        return {'success':ok,'previewRendered':ok,'log':log[-6000:]}
