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
           function('tex_reference','查询固定 Tectonic bundle 中真实存在的宏包/文件、本机已安装字体，并按当前引擎检查源码兼容性；用于替代凭记忆猜测。',{'query':S,'check':B,'path':S}),
           function('layout_check','检查 PDF 版面几何和页次，默认关联页或代表页，不重读全文。',{'pages':{'type':'array','items':I,'maxItems':12}}),
           function('read_page','读取 PDF 页面；需要视觉判断时 visual=true，最多按需查看代表页。',{'page':I,'visual':B},('page',)),
           function('read_attachment','读取明确关联的附件，PDF 可指定 page 和 visual',{'id':S,'start':I,'lines':I,'page':I,'visual':B},('id',))]
    if mode=='agent':tools.extend([function('edit','先读取文件，再按准确原文替换副本；配套代码/数据文件需要用户授权，不执行代码',{'path':S,'before':S,'after':S,'replace_all':B},('path','before','after')),function('compile','编译候选并验证 PDF；源码未变则复用结果'),function('resources','恢复编译器已知缺少的公共资源'),function('browser','经用户授权读取公开 HTTPS 网页；action=read 只读正文，open 在系统浏览器打开。不能登录、提交表单或访问内网。',{'url':S,'action':{'type':'string','enum':['read','open']}},('url',))])
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
            name=schema['function']['name'];mutating=name in {'edit','compile','resources','browser'}
            handler=getattr(self,'compile_candidate' if name in {'compile','resources'} else name)
            self.registry.register(ToolSpec(schema,handler,('agent',) if mutating else ('chat','agent'),mutating))
    def execute(self,s,clone,name,args,read):
        self.owner.checkpoint()
        from studio_assistant_policy import allowed
        if not allowed(s,name):raise ValueError('该工具已在本轮上下文设置中禁用，请使用其他已启用工具')
        return self.registry.resolve(name,s['chatMode']).handler(s,clone,args,read,name)

    def browser(self,s,clone,args,read,name):
        from studio_assistant_browser import browse,public_target
        from studio_assistant_policy import approve
        url=args.get('url');action=args.get('action','read')
        public_target(url,resolve=False)
        if action not in {'read','open'}:raise ValueError('网页操作无效')
        approve(self.owner,s,'browser',action+' '+url)
        return browse(url,action,self.owner.checkpoint)

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
        from studio_tex_reference import ENGINE,font_matches
        common=['Times New Roman','Arial','Cambria','Calibri','SimSun','SimHei','Microsoft YaHei','KaiTi','FangSong','Consolas','Courier New','Cambria Math','Noto Serif CJK SC','Noto Sans CJK SC']
        installed=font_matches('',500).get('fonts',[]);folded={f.casefold():f for f in installed}
        fonts=[folded[name.casefold()] for name in common if name.casefold() in folded]
        return {'engine':ENGINE,'installedFonts':fonts,'fontQuery':font_matches('',40).get('fonts',[])[:40],
                'fontHint':'用 fontspec 的 setmainfont 选择已安装字体；不支持 shell-escape 或更换引擎。需要确认宏包是否存在时调用 tex_reference。'}

    def tex_reference(self,s,clone,args,read,name):
        from studio_tex_reference import reference,compatibility,local_resources
        query=args.get('query','')
        if not isinstance(query,str) or len(query)>200:raise ValueError('查询词应为 200 字符以内的字符串')
        result=reference(self.owner.storage.tex_cache,query)
        if args.get('check',True) is not False:
            path=self.owner.file(clone,args.get('path') or s['main'])[1]
            result['compatibility']=compatibility(path.read_text('utf-8-sig',errors='replace'),
                self.owner.storage.tex_cache,path.relative_to(clone).as_posix(),local_resources(clone))
        return result

    def diagnostics(self,s,clone,args,read,name):
        if name!='diagnostics':return None
        log=s.get('lastLog') or s.get('errorContext','');result={'compiler':'Tectonic/XeTeX','log':log[-6000:],'compiled':s.get('lastCompiled',False),
            'editRevision':s.get('editRevision',0),'compiledRevision':s.get('compiledRevision'),'stale':s.get('compiledRevision')!=s.get('editRevision',0)}
        if s.get('previewFailure'):result['failingStep']='render';result['next']='本地预览渲染失败，不是源码错误；请重试 compile，仍失败则说明需要重启应用，不要继续改源码。'
        elif not s.get('lastCompiled'):
            from studio_editor_ai import error_target
            try:
                path,line,message=error_target(log,clone,s['main']);result.update(errorPath=path,errorLine=line,errorMessage=message,failingStep='tex')
                result['next']='只修改 '+path+' 第 '+str(line)+' 行附近：'+message[:300]
            except Exception:result['failingStep']='tex'
        return result

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
        s['layoutRevision']=s.get('editRevision',0)
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

    def anchor_hint(self,full,before):
        """A failed anchor is usually an escaping or context mistake; say which one."""
        import difflib
        if '\\\\' in before and '\\\\' not in full:
            return 'before 里的反斜杠被重复转义了（\\\\），源码中只有单反斜杠，请用 read_file 得到的原文逐字复制'
        probe=before.strip().splitlines()[0][:40] if before.strip() else ''
        if not probe:return None
        rows=full.splitlines()
        for index,row in enumerate(rows,1):
            if probe[:12] and probe[:12] in row:return '目标现在在第 '+str(index)+' 行附近，请读取该行后用当前原文作为 before'
        best=difflib.get_close_matches(probe,[row.strip() for row in rows],n=1,cutoff=.6) if probe else []
        if best:
            line=next((i for i,row in enumerate(rows,1) if row.strip()==best[0]),None)
            if line:return '最接近的是第 '+str(line)+' 行：'+best[0][:160]+'；请按该行当前原文修改'
        return '当前文件共 '+str(len(rows))+' 行；请 read_file 读取目标段落，用其中逐字原文作为 before'

    def edit(self,s,clone,args,read,name):
        from studio_assistant_context import ELIDED_MARK
        if s.get('previewFailure'):raise ValueError('上次失败发生在 PDF 渲染而非源码；先重试 compile 或报告渲染问题，不能用修改源码来修复渲染器')
        path,p=self.owner.file(clone,args.get('path',''))
        from studio_assistant_policy import AUXILIARY,approve
        if p.suffix.lower() not in EDITABLE|AUXILIARY or path not in read:raise ValueError('修改前请读取项目中的相应文本文件')
        before=args.get('before');after=args.get('after')
        if any(not isinstance(v,str) for v in (before,after)):raise ValueError('修改参数必须是字符串，当前 before/after 不完整')
        if ELIDED_MARK in before or ELIDED_MARK in after:raise ValueError('before/after 里是历史占位说明，不是源码。请先 read_file 读取目标段落，再用其中的准确原文作为 before。')
        if before==after:raise ValueError('before 与 after 相同，这次调用不会产生任何修改；若要删改，请给出不同的 after，若已完成修改则直接调用 compile。')
        full=p.read_text('utf-8-sig');applied=s.setdefault('appliedEdits',[])
        if [path,before,after] in applied:
            # This exact replacement already ran in this task: report it instead of failing again.
            return {'edits':0,'path':path,'alreadyApplied':True,'revision':s.get('editRevision',0),'next':'这次修改此前已经执行过；直接调用 compile 验证候选，不要重复同一处修改。'}
        if p.suffix.lower() not in EDITABLE:approve(self.owner,s,'auxiliary',path)
        # Revision counters alone cannot spot A→B→A→B oscillations.
        # Compare actual normalized candidate contents, allowing one legitimate rollback.
        import hashlib,studio_ai
        try:_,proposed=studio_ai.validate_edits(full,[args],allow_content_changes=True)
        except ValueError as exc:
            hint=self.anchor_hint(full,before)
            raise ValueError(str(exc)+(('。'+hint) if hint else '')) from None
        fingerprint=lambda value:hashlib.sha256(value.replace('\r\n','\n').encode('utf8')).hexdigest()
        states=s.setdefault('candidateFingerprints',{}).setdefault(path,[fingerprint(full)])
        proposed_hash=fingerprint(proposed)
        if states.count(proposed_hash)>=2:raise ValueError('该修改会再次回到本轮已经出现过的相同源码，已拦截反复改回的循环。请按编译诊断换一种修复，或 compile 验证现有候选')
        try:count=self.owner.accept(s,clone,path,0,len(full),full,{'edits':[args]})
        except ValueError as exc:
            hint=self.anchor_hint(full,before)
            raise ValueError(str(exc)+(('。'+hint) if hint else '')) from None
        applied.append([path,before,after]);del applied[:-40]
        states.append(proposed_hash);del states[:-64]
        s['verified']=False;s['lastCompiled']=False;s['candidateReady']=False;s['editRevision']=s.get('editRevision',0)+1
        return {'edits':count,'path':path,'revision':s['editRevision'],'next':'调用 compile 验证候选'}

    def layout_summary(self,log):
        """Cheap, reliable layout signal from the compiler's own box warnings."""
        from studio_ai_quality import box_warnings
        over,under=box_warnings(log)
        summary={'overfull':len(over),'underfull':len(under),'overfullLines':[item['line'] for item in over if item['line']][:8]}
        if over:summary['warning']='编译日志有 '+str(len(over))+' 处 Overfull 盒子（文字可能超出页边距），涉及行：'+(', '.join(map(str,summary['overfullLines'])) or '未知')
        return summary

    def layout_next(self,s,result):
        if result.get('layout',{}).get('overfull'):
            return '候选已通过编译，但存在 Overfull（文字超出页边距）。请先修复这些位置或调整版面，再给出结论；不要声称版面已检查。'
        if s.get('contextPolicy',{}).get('layout',True) and s.get('layoutTask') and s.get('editRevision',0)>0 and s.get('layoutRevision')!=s.get('editRevision',0):
            return '候选已通过编译。正文改动可能改变分页与版面：请调用 layout_check 复核受影响页/代表页，确认后再给出结论。'
        return '候选已通过验证，可以给出结论'

    def compile_candidate(self,s,clone,args,read,name):
        revision=s.get('editRevision',0)
        if s.get('compiledRevision')==revision and name=='compile':
            reused={'success':s['lastCompiled'],'unchanged':True,'log':s.get('lastLog','')[-4500:]}
            if s.get('previewFailure'):
                reused.update(failingStep='render',previewRendered=False,next='候选源码已编译出 PDF，失败在本地预览渲染；重试无效时说明需要重启应用，不要改源码')
            elif s['lastCompiled'] is False:reused['next']='候选仍未通过编译；调用 diagnostics 读取报错并针对该处修改，不要直接结束'
            else:
                reused['layout']=self.layout_summary(s.get('lastLog',''))
                reused['next']=self.layout_next(s,reused)
            return reused
        recovered=None
        if name=='resources':
            missing=cached_resource_missing(s.get('lastLog',s['errorContext']),self.owner.storage.tex_cache)
            if not missing:raise ValueError('当前没有可自动恢复的官方宏包缺失记录')
            s['allowNetwork']=True
        ok,log=self.owner.compile_copy(s,clone,len(s['events']))
        if not ok and not s.get('previewFailure') and not s.get('allowNetwork'):
            # A pinned public bundle file (e.g. size12.clo) is not a source problem: fetch it once and retry.
            missing=cached_resource_missing(log,self.owner.storage.tex_cache)
            if missing:
                s['allowNetwork']=True;recovered=missing
                ok,log=self.owner.compile_copy(s,clone,len(s['events']))
        # Keep the newest log even when only the preview check failed, so diagnostics never describes an older attempt.
        s.update(lastLog=log,lastCompiled=ok,compiledRevision=revision,verified=ok)
        preview_failed=bool(s.get('previewFailure'))
        result={'success':ok,'previewRendered':ok and not preview_failed,'log':log[-6000:],
                'failingStep':'render' if preview_failed else 'tex'}
        if recovered:result['resourceRecovered']=recovered
        if ok:
            result['layout']=self.layout_summary(log)
            result['next']=self.layout_next(s,result)
        elif preview_failed:
            result['next']='编译本身已生成 PDF，失败发生在本地预览渲染，不是源码问题。重试 compile 一次；仍失败就停下来说明当前环境需要重启应用，不要继续改源码。'
        else:
            from studio_editor_ai import error_target
            from studio_tex_reference import diagnose_missing,engine_error_notes
            missing=diagnose_missing(log,self.owner.storage.tex_cache)
            if missing:result['missingResources']=missing
            notes=engine_error_notes(log)
            if notes:result['engineNotes']=notes
            try:
                path,line,message=error_target(log,clone,s['main'])
                result.update(errorPath=path,errorLine=line,errorMessage=message[:500])
                # Give the model what it needs to fix this exact line without another read.
                try:
                    rows=(clone/path).read_text('utf-8-sig').splitlines()
                    lo=max(0,line-3);hi=min(len(rows),line+2)
                    result['source']='\n'.join(str(i+1)+': '+rows[i][:300] for i in range(lo,hi))
                except (OSError,UnicodeError):pass
                result['next']='这是 TeX 报错：修改 '+path+' 第 '+str(line)+' 行附近（'+message[:200]+'），改完重新 compile'
            except Exception:result['next']='这是 TeX 报错：调用 diagnostics 读取该错误指向的位置，只改那一处后重新 compile'
            if missing and any(item.get('inPinnedBundle') for item in missing):
                result['next']+=' 日志中的缺失文件属于固定公共 bundle，可先调用 resources 补齐，不要改源码绕开。'
        return result
