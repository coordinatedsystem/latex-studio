"""Local editing contracts and PDF sanity checks, not a claim of factual accuracy."""
import hashlib,re
from decimal import Decimal

POLICY=('先识别用户要求的修改类型，严格保持范围。排版请求只改排版，不改写事实；润色改善表达，不增加结论强度；翻译保持语义与限定条件。'
 '保留数值的统计角色：当前观测值、基线、目标和提升幅度不能互换，不能把 is 94% 改成 improve to/by 94%。'
 '翻译按完整自然段给出修改，覆盖句末量词、章节后缀和标点；不要拆成紧邻小片段。检查英文句间、单词与公式和引用两侧需要的空格，不能遗留未翻译的正文。'
 '翻译时，如果 source 是单个自然段且不包含文档环境，使用覆盖整个自然段的一条 edits，连同锁定标记一起完整输出。'
 'source 中的 ⟦KEEP_…⟧ 是锁定片段，必须逐字保留，可从 lockedContent 理解含义。不要改写、删除或新建锁定标记。'
 '每项修改须有对应用户目标与具体理由；先自检事实、数值、公式、引用、否定和不确定性措辞。确定无需修改时明确说明；有明确问题时给出实际 edits，不只提建议。')

def lock_source(text):
    from studio_ai import PROTECTED
    values={};prefix=hashlib.sha256(text.encode()).hexdigest()[:8]
    def replace(match):
        if match[0].startswith('\\includegraphics'):return match[0]
        token=f'⟦KEEP_{prefix}_{len(values):04d}⟧';values[token]=match[0];return token
    return PROTECTED.sub(replace,text),values

def unlock_result(result,locked,masked=None):
    if not isinstance(result,dict):raise ValueError('AI 响应不是对象')
    for edit in result.get('edits',[]) if isinstance(result.get('edits',[]),list) else []:
        if not isinstance(edit,dict):continue
        if masked and isinstance(edit.get('line'),int) and not isinstance(edit['line'],bool):
            prefix=''.join(masked.splitlines(keepends=True)[:max(0,edit['line']-1)])
            for token,value in locked.items():prefix=prefix.replace(token,value)
            edit['line']=prefix.count('\n')+1
        for name in ['before','after']:
            if not isinstance(edit.get(name),str):continue
            for token,value in locked.items():edit[name]=edit[name].replace(token,value)
            if re.search(r'⟦KEEP_[^⟧]*⟧',edit[name]):raise ValueError('AI 返回了无法识别的锁定标记，未应用修改')
    return result

def _prose(text):
    from studio_ai import PROTECTED
    text=PROTECTED.sub('',text)
    text=re.sub(r'\\(?:setlength|fontsize)\s*\{[^{}]*\}\s*\{[^{}]*\}','',text)
    text=re.sub(r'\\(?:vspace|hspace|linespread)\*?\s*\{[^{}]*\}','',text)
    text=re.sub(r'\\[A-Za-z@]+\*?(?:\[[^\]]*\])?','',text)
    return re.sub(r'[\s{}$]','',text)

def edit_problem(before,after,task='polish',instruction=''):
    if re.search(r'翻译|translat',instruction,re.I):task='translate'
    if re.search(r'\\(?:write18|endinput|catcode|scrollmode|batchmode|nonstopmode)\b',after) and after!=before:return '修改引入额外执行或隐藏错误指令'
    if len(before)>80 and len(after.strip())<len(before.strip())*.35:return '修改删除内容过多'
    if re.search(r'可能|初步|提示|\b(?:may|might|suggests?|possibly)\b',before,re.I) and not re.search(r'可能|初步|提示|\b(?:may|might|suggests?|possibly|could)\b',after,re.I):return '建议去除了原文的不确定性限定'
    if re.search(r'没有|并未|未能|不能|不显著|无显著|\b(?:not|never|without)\b|no evidence',before,re.I) and not re.search(r'没有|并未|未能|不能|不显著|无显著|\b(?:not|never|without|no)\b',after,re.I):return '建议去除了原文的否定含义'
    layout=bool(re.search(r'排版|版面|字号|行距|间距|layout|spacing',instruction,re.I)) and not re.search(r'润色|翻译|措辞|改写|polish|translat',instruction,re.I)
    if layout and _prose(before)!=_prose(after):return '仅请求排版，但建议改写了正文'
    if task not in {'translate','repair','correct'}:
        if re.findall(r'\b(?:to|by|from)\s+\d',after,re.I)!=re.findall(r'\b(?:to|by|from)\s+\d',before,re.I):return '建议改变了数值的当前值、目标或变化量关系'
        for strong,soft in [('证明','表明'),('显著',''),('首次',''),('最优',''),('必然',''),('完全消除',''),('guarantees',''),('prove',''),('significantly',''),('state-of-the-art','')]:
            contains=lambda text:bool(re.search(r'\b'+re.escape(strong)+r'(?:s|d)?\b',text,re.I)) if strong.isascii() else strong in text
            if contains(after) and not contains(before):return '建议新增了原文没有的结论强度：'+strong
    return None

def measurements(text):
    text=re.sub(r'\\(?:setlength|fontsize)\s*\{[^{}]*\}\s*\{[^{}]*\}|\\(?:vspace|hspace|linespread)\*?\s*\{[^{}]*\}|(?:width|height|scale)\s*=\s*[\d.]+(?:pt|mm|cm|em|ex|in|\\linewidth|\\textwidth)?','',text)
    text=text.replace(r'\%','%');units={'milliseconds':('time','0.001'),'millisecond':('time','0.001'),'seconds':('time','1'),'second':('time','1'),'ms':('time','0.001'),'毫秒':('time','0.001'),'s':('time','1'),'秒':('time','1'),'kg':('mass','1'),'千克':('mass','1'),'g':('mass','0.001'),'克':('mass','0.001'),'%':('ratio','0.01')};found=[]
    for m in re.finditer(r'(?<![A-Za-z\d.])([+-]?\d+(?:\.\d+)?)\s*(milliseconds?\b|seconds?\b|毫秒|千克|秒|克|ms\b|kg\b|s\b|g\b|%)',text):
        group,factor=units[m[2]];found.append((group,Decimal(m[1])*Decimal(factor)))
    return found

def report(before,after,task='edit',target=''):
    warnings=[]
    if before!=after and _prose(before)==_prose(after) and task in {'polish','translate'}:warnings.append('未检测到可读正文变化，请确认修改目标是否已满足')
    if len(_prose(before))>100 and len(_prose(after))<len(_prose(before))*.7:warnings.append('正文缩短较多，请核对是否遗漏信息')
    if task=='translate' and target=='en' and re.search(r'[\u4e00-\u9fff]',_prose(after)):warnings.append('译文仍有中文正文或尾词，请检查是否漏译')
    if re.search(r'[.!?](?=[A-Z][a-z])|[A-Za-z](?=\$|\\(?:cite|ref)\b)',after):warnings.append('英文句子、公式或引用附近可能缺少空格')
    return {'status':'review' if warnings else 'checked','warnings':warnings,'checks':['数值与引用保护','修改范围检查'],'note':'自动检查不替代对原意、术语与版面的人工审阅'}

def pdf_report(before,after):
    try:
        from pypdf import PdfReader
        a,b=PdfReader(before),PdfReader(after);old=[(p.extract_text() or '').strip() for p in a.pages];new=[(p.extract_text() or '').strip() for p in b.pages];warnings=[]
        if len(new)>len(old)+1:warnings.append('修改后页数增加，请检查分页与留白')
        if sum(len(t)<8 for t in new)>sum(len(t)<8 for t in old):warnings.append('新增空白或文字很少的页面，请检查')
        if sum(map(len,old))>100 and sum(map(len,new))<sum(map(len,old))*.75:warnings.append('PDF 可提取正文减少，请检查内容是否完整')
        return {'status':'review' if warnings else 'checked','warnings':warnings,'beforePages':len(old),'afterPages':len(new)}
    except Exception:return {'status':'unavailable','warnings':['未能完成 PDF 内容检查，请直接查看预览']}
