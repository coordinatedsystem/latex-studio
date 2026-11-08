"""Local document inspection and project terminology. No remote requests."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import threading
import time

from studio_storage import read_json, write_json

GLOSSARY_LOCK = threading.RLock()
LAST_SELFTEST = None


def glossary_path(data, project):
    if not re.fullmatch(r'[a-f0-9]{20}', project):
        raise ValueError('项目标识无效')
    return Path(data) / 'glossaries' / (project + '.json')


def glossary_get(data, project):
    with GLOSSARY_LOCK:
        return read_json(glossary_path(data, project), {'terms': [], 'revision': ''})


def glossary_save(data, project, payload):
    terms = payload.get('terms')
    if not isinstance(terms, list) or len(terms) > 200:
        raise ValueError('术语表最多保存 200 条')
    cleaned, seen = [], set()
    for item in terms:
        if not isinstance(item, dict):
            raise ValueError('术语格式无效')
        row = {k: str(item.get(k, '')).strip() for k in ('source', 'target', 'note')}
        if not row['source'] or not row['target'] or len(row['source']) > 120 or len(row['target']) > 160 or len(row['note']) > 300:
            raise ValueError('每条需填写原词和译词；长度上限为原词 120、译词 160、备注 300 字')
        if any(re.search(r'[\x00-\x1f]', v) for v in row.values()):
            raise ValueError('术语字段不能包含换行或控制字符')
        if row['source'].casefold() in seen:
            raise ValueError('存在重复原词：' + row['source'])
        seen.add(row['source'].casefold())
        cleaned.append(row)
    with GLOSSARY_LOCK:
        current = glossary_get(data, project)
        if payload.get('revision', '') != current['revision']:
            raise ValueError('术语表已在其他窗口更新，请重新载入后保存')
        revision = hashlib.sha256(json.dumps(cleaned, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        result = {'terms': cleaned, 'revision': revision}
        write_json(glossary_path(data, project), result)
        return result


def relevant_terms(data, project, text):
    folded = text.casefold()
    return [t for t in glossary_get(data, project)['terms'] if t['source'].casefold() in folded][:40]


def masked(text):
    # Preserve offsets and line numbers when skipping comments and literal environments.
    def blank(m):
        return re.sub(r'[^\n]', ' ', m[0])
    text = re.sub(r'\\begin\{(verbatim\*?|lstlisting|minted)\}.*?\\end\{\1\}', blank, text, flags=re.S)
    return re.sub(r'(?<!\\)%[^\n]*', blank, text)


def group(text, start, opening='{', closing='}'):
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != opening:
        return None
    depth, i = 1, start + 1
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if not depth:
                return text[start+1:i], i+1
        i += 1
    return None


def macro_labels(text):
    """Resolve simple newcommand wrappers such as fig[4][width]{...label{#4}}."""
    macros, ranges = {}, []
    for match in re.finditer(r'\\(?:newcommand|renewcommand|providecommand)\*?\s*(?:\{\\([A-Za-z@]+)\}|\\([A-Za-z@]+))', text):
        name = match[1] or match[2]
        count = group(text, match.end(), '[', ']')
        if not count or not count[0].isdigit() or int(count[0]) > 9:
            continue
        default = group(text, count[1], '[', ']')
        body = group(text, default[1] if default else count[1])
        if not body:
            continue
        ranges.append((match.start(), body[1]))
        labels = re.findall(r'\\label\s*\{#([1-9])\}', body[0])
        if labels:
            macros[name] = (int(count[0]), default[0] if default else None, [int(x) for x in labels])
    return macros, ranges


def analyze_references(sources, main):
    """sources is an already authorised relative-path -> source map."""
    if main not in sources:
        raise ValueError('主文档不存在或不属于可检查的文本文件')
    labels, cites, bibs = defaultdict(list), [], defaultdict(list)
    refs, issues, files, visiting, macros, bib_entries = [], [], [], set(), {}, []
    def location(path, pos, content):
        return {'file': path, 'line': content[:pos].count('\n')+1}
    def note(loc, code, message, severity='warning'):
        issues.append({**loc, 'code': code, 'message': message, 'severity': severity})
    def resolve(path, name, ext):
        name = name.strip()
        if not name or '\\' in name or re.search(r'[#:$\x00]', name) or name.startswith('/'):
            return None
        target = posixpath.normpath(posixpath.join(posixpath.dirname(path), name))
        if target.startswith('../') or target == '..':
            return None
        if not PurePosixPath(target).suffix:
            target += ext
        return target
    def walk(path, depth=0):
        if path in visiting:
            note({'file':path,'line':1}, 'include-cycle', '检测到循环包含，已停止重复追踪', 'info')
            return
        if path in files:
            return
        if depth > 30 or len(files) >= 200:
            note({'file':path,'line':1}, 'scan-limit', '包含层级或文件数量超过检查上限，结果不完整')
            return
        visiting.add(path)
        files.append(path)
        text = masked(sources[path])
        defined, spans = macro_labels(text)
        macros.update(defined)
        # Macro definitions are not executed labels, references or includes.
        for a,b in reversed(spans):
            text = text[:a]+re.sub(r'[^\n]', ' ', text[a:b])+text[b:]
        for m in re.finditer(r'\\(input|include|subfile|bibliography|addbibresource)\s*(?:\[[^\]]*\])?\{([^}]+)\}', text):
            is_bib = m[1] in {'bibliography', 'addbibresource'}
            for name in m[2].split(','):
                target = resolve(path, name, '.bib' if is_bib else '.tex')
                loc = location(path, m.start(), text)
                if target is None:
                    note(loc, 'dynamic-input', '无法静态追踪包含路径：' + name, 'info')
                elif target not in sources:
                    note(loc, 'missing-file', '引用的文件不存在或未纳入检查：' + target, 'error')
                elif is_bib:
                    if target not in bib_entries:
                        bib_entries.append(target)
                else:
                    walk(target, depth+1)
        for m in re.finditer(r'\\label\s*\{([^}]+)\}', text):
            if '#' not in m[1]:
                labels[m[1]].append(location(path, m.start(), text))
        for name,(count, default, indexes) in macros.items():
            for m in re.finditer(r'\\'+re.escape(name)+r'(?![A-Za-z@])', text):
                args, pos = [], m.end()
                if default is not None:
                    arg = group(text,pos,'[',']')
                    args.append(arg[0] if arg else default)
                    if arg:
                        pos = arg[1]
                for _ in range(count-len(args)):
                    arg = group(text,pos)
                    if not arg:
                        break
                    args.append(arg[0]); pos = arg[1]
                if len(args) == count:
                    for index in indexes:
                        if 0 < index <= len(args) and re.fullmatch(r'[A-Za-z0-9_:./-]+',args[index-1]):
                            labels[args[index-1]].append(location(path,m.start(),text))
        for m in re.finditer(r'\\(?:eqref|ref|autoref|pageref|nameref|cref|Cref|vref)\*?\s*\{([^}]+)\}',text):
            refs.extend((key.strip(),location(path,m.start(),text)) for key in m[1].split(','))
        for m in re.finditer(r'\\(?:[Cc]ite\w*|nocite)\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]+)\}',text):
            cites.extend((key.strip(),location(path,m.start(),text)) for key in m[1].split(','))
        for m in re.finditer(r'\\bibitem\s*(?:\[[^\]]*\])?\{([^}]+)\}',text):
            bibs[m[1]].append(location(path,m.start(),text))
        visiting.remove(path)
    walk(main)
    for path in bib_entries:
        text = masked(sources[path])
        cursor=0
        while True:
            match=re.search(r'@([A-Za-z]+)\s*([{(])\s*([^,\s]+)\s*,',text[cursor:])
            if not match:
                break
            start=cursor+match.start()
            opening=cursor+match.start(2)
            body=group(text,opening,match[2],'}' if match[2]=='{' else ')')
            cursor=body[1] if body else cursor+match.end()
            if match[1].casefold() not in {'comment','preamble','string'}:
                bibs[match[3]].append(location(path,start,text))
        files.append(path)
    for key,locs in labels.items():
        if len(locs)>1:
            for loc in locs:
                note(loc,'duplicate-label','重复标签：'+key,'error')
    for key,locs in bibs.items():
        if len(locs)>1:
            for loc in locs:
                note(loc,'duplicate-bib','重复文献键：'+key,'error')
    for key,loc in refs:
        if key and key not in labels:
            note(loc,'missing-label','未找到标签：'+key+'；自定义动态命令仍需编译核验')
    for key,loc in cites:
        if key not in {'','*'} and key not in bibs:
            note(loc,'missing-citation','未找到文献条目：'+key,'error')
    used = {key for key,_ in cites}
    if '*' not in used:
        for key,locs in bibs.items():
            if key not in used:
                note(locs[0],'unused-bib','文献未被当前主文档引用：'+key,'info')
    from studio_references import catalog
    entries=catalog(sources,files,labels,refs,cites,bibs)
    return {'catalog':entries,'files':files,'labels':len(labels),'references':len(refs),'citations':len(cites),'bibliography':len(bibs),
            'issues':sorted(issues,key=lambda x:(x['file'],x['line']))[:300],
            'note':'仅追踪主文档可静态解析的包含关系；条件编译、复杂宏和外部文献数据库以编译结果为准。'}


def parse_pages(value, total, limit=200):
    if not value or value == 'all':
        return list(range(1,min(total,limit)+1))
    pages = set()
    for part in str(value).split(','):
        match = re.fullmatch(r'\s*(\d{1,4})(?:\s*-\s*(\d{1,4}))?\s*',part)
        if not match:
            raise ValueError('页码格式无效，例如 1,3-5')
        start, end = int(match[1]), int(match[2] or match[1])
        if start < 1 or end < start or end > total or end-start >= limit:
            raise ValueError(f'页码需在 1～{total} 内，且不超过 {limit} 页')
        pages.update(range(start,end+1))
    if not pages or len(pages)>limit:
        raise ValueError(f'一次最多选择 {limit} 页')
    return sorted(pages)


def inspect_geometry(width, height, chars, images, graphic_count=0, index=1, total=1):
    issues = []
    def add(code,message,severity='info',bbox=None):
        issues.append({'page':index,'code':code,'message':message,'severity':severity,'bbox':bbox})
    visible = [c for c in chars if c.get('text','').strip()]
    outside = [c for c in visible+images if c['x0'] < -1 or c['x1'] > width+1 or c['top'] < -1 or c['bottom'] > height+1]
    if outside:
        first = outside[0]
        add('outside-page',f'{len(outside)} 个文字或图像对象超出页面边界，请检查裁切或溢出。','warning',
            [first['x0']/width,first['top']/height,first['x1']/width,first['bottom']/height])
    small = [c for c in visible if 0 < c.get('size',10)<7]
    if len(small)>12:
        add('small-type',f'{len(small)} 个字符小于 7 pt；公式下标或脚注也可能触发，请人工确认可读性。')
    edges = [c for c in visible if c['x0']<18 or c['x1']>width-18]
    if len(edges)>10:
        add('tight-margin','多处文字距离左右纸边不足约 6 mm，请检查页边距。','warning')
    if not visible and not images and not graphic_count:
        add('blank-page','当前页未检测到文字、图片或绘图，可能是有意插入的空白页。')
    bounds = visible+images
    bottom = max((c['bottom'] for c in bounds), default=0)
    if index not in {1,total} and len(visible)>150 and bottom < height*.48:
        add('large-whitespace','内容主要集中在上半页，可检查强制分页、浮动体或标题分页。')
    return {'page':index,'width':round(width,2),'height':round(height,2),'characters':len(visible),'images':len(images),
            'contentBottom':round(bottom/height,3) if height else 0,'issues':issues}


def inspect_pdf(path, pages='all'):
    import pdfplumber
    path=Path(path)
    if path.stat().st_size>40*1024*1024:
        raise ValueError('版面检查暂支持 40 MB 以内的 PDF')
    with pdfplumber.open(path) as pdf:
        total=len(pdf.pages)
        selected=parse_pages(pages,total)
        results=[]
        for n in selected:
            page=pdf.pages[n-1]
            if page.width>5000 or page.height>5000 or page.width<=0 or page.height<=0:
                raise ValueError('页面尺寸不受支持')
            chars=page.chars
            if len(chars)>100000:
                raise ValueError('单页对象过多，请缩小范围或使用其他 PDF')
            results.append(inspect_geometry(page.width,page.height,chars,page.images,len(page.rects)+len(page.curves)+len(page.lines),n,total))
            page.flush_cache()
    return {'totalPages':total,'scannedPages':len(selected),'truncated':total>len(selected) and pages=='all',
            'pages':results,'issues':[i for p in results for i in p['issues']],
            'note':'本地几何检查提供纸边、小字号、留白等线索；不判断审美或保证没有文字重叠。扫描件建议使用视觉审阅。'}


def poppler_exe():
    path=shutil.which('pdftoppm')
    if path:
        return path
    return None


def page_image(pdf, data, project, page, version):
    from pypdf import PdfReader
    pdf=Path(pdf)
    if not pdf.is_file() or pdf.stat().st_mtime_ns!=int(version):
        raise ValueError('PDF 已更新，请重新进行版面检查')
    total=len(PdfReader(pdf).pages)
    page=int(page)
    if page<1 or page>total or page>1000:
        raise ValueError('页码超出范围')
    tool=poppler_exe()
    if not re.fullmatch(r'[a-f0-9]{20}',project):
        raise ValueError('项目标识无效')
    folder=Path(data)/'review-previews'/project
    folder.mkdir(parents=True,exist_ok=True)
    prefix=folder/(str(version)+'-p'+str(page))
    target=prefix.with_suffix('.png')
    if not target.exists():
        if tool:
            result=subprocess.run([tool,'-f',str(page),'-l',str(page),'-singlefile','-scale-to','1400','-png',str(pdf),str(prefix)],
                                  capture_output=True,timeout=25,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode or not target.exists():raise ValueError('页面渲染失败，请重新编译 PDF 后重试')
        else:
            try:import pypdfium2 as pdfium
            except ImportError:raise ValueError('没有找到 PDF 页面渲染工具，请重新安装运行组件') from None
            document=pdfium.PdfDocument(str(pdf))
            try:
                sheet=document[page-1]
                try:
                    bitmap=sheet.render(scale=1400/max(sheet.get_width(),sheet.get_height()))
                    try:bitmap.to_pil().save(target)
                    finally:bitmap.close()
                finally:sheet.close()
            finally:document.close()
    if pdf.stat().st_mtime_ns!=int(version):
        raise ValueError('渲染期间 PDF 已更新，请重新加载')
    cached=sorted((p for p in folder.glob('*.png') if re.fullmatch(r'\d+-p\d+\.png',p.name)),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    for stale in cached[48:]:
        if stale!=target:
            try:
                stale.unlink()
            except OSError:
                pass
    return target


def selftest():
    """Checks guards and document analysis using independent local examples, never an API."""
    from studio_ai import seal, validate_edits, signature
    checks=[]
    def run(name,check):
        try:
            assert check()
            checks.append({'name':name,'passed':True})
        except Exception:
            checks.append({'name':name,'passed':False,'detail':'本地校验未通过，请查看测试或环境配置'})
    def rejects(source,edits):
        try:
            validate_edits(source,edits)
            return False
        except ValueError:
            return True
    run('唯一原文定位',lambda:validate_edits('An eror.',[{'before':'eror','after':'error'}])[1]=='An error.')
    run('重复片段拦截',lambda:rejects('same same',[{'before':'same','after':'other'}]))
    run('数字修改拦截',lambda:rejects('Result 12',[{'before':'12','after':'13'}]))
    run('公式修改拦截',lambda:rejects('$x+y$',[{'before':'$x+y$','after':'$x-y$'}]))
    run('跨文件标签追踪',lambda:not analyze_references({'main.tex':'\\input{part}\n\\ref{x}','part.tex':'\\label{x}'},'main.tex')['issues'])
    run('缺失文献识别',lambda:any(x['code']=='missing-citation' for x in analyze_references({'main.tex':'\\cite{missing}'},'main.tex')['issues']))
    run('页面溢出识别',lambda:any(x['code']=='outside-page' for x in inspect_geometry(100,100,[{'text':'x','x0':98,'x1':105,'top':10,'bottom':20,'size':10}],[])['issues']))
    run('Windows 密钥加密往返',lambda:seal(seal('studio-local-selftest'),True)=='studio-local-selftest')
    run('有道签名格式',lambda:bool(re.fullmatch(r'[a-f0-9]{64}',signature('hello','test-id','test-secret','test-salt','1'))))
    global LAST_SELFTEST
    LAST_SELFTEST={'kind':'local','time':time.strftime('%Y-%m-%d %H:%M:%S'),'checks':checks,'passed':sum(c['passed'] for c in checks),
                   'total':len(checks),'note':'独立样例的本地逻辑检查；没有调用 AI 模型，也不代表线上服务可用。'}
    return LAST_SELFTEST


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pdf',required=True)
    parser.add_argument('--pages',default='all')
    args=parser.parse_args()
    try:
        print(json.dumps(inspect_pdf(args.pdf,args.pages),ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,ValueError) else 'PDF 解析失败，请重新编译或缩小检查范围'},ensure_ascii=True))
        sys.exit(1)
