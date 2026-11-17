"""Authoritative local facts for the pinned Tectonic bundle and this machine.

The assistant must not guess whether a package, class or font exists. Everything here
is read from the installed index of the pinned public bundle and the Windows font
registry, so an answer can name its source instead of relying on model memory.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ENGINE = {
    'name': 'Tectonic',
    'tex': 'XeTeX / XeLaTeX',
    'shellEscape': False,
    'features': [
        'fontspec 选择本机已安装的系统字体；中文字体可用 xeCJK 或 ctex',
        'TikZ、graphicx、geometry、booktabs、amsmath、hyperref 等常见宏包可用',
        '不执行外部命令：minted、pythontex、svg、shellesc、\\write18 不可用',
        'pdfTeX 专用原语（\\pdfpagewidth、\\pdfoutput 等）不可用',
        '编译失败时先看是否是固定 bundle 缺少的官方资源，再判断源码问题',
    ],
}

_INDEX = {}
_FONTS = None

# Rules that do not depend on the bundle index. Each line is matched independently.
RULES = [
    (r'\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{inputenc\}', 'info',
     'XeTeX 默认按 UTF-8 读取源码，inputenc 通常不需要；保留一般也不影响，可以删除。'),
    (r'\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{fontenc\}', 'warning',
     'fontenc 是 pdfTeX 的字体编码机制，与 fontspec 同用可能冲突；用 fontspec 选择系统字体时不要加载 fontenc。'),
    (r'\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{(?:times|mathptmx|helvet|courier|newtxtext|newtxmath|mathpazo|txfonts|pxfonts|kpfonts|anttor)\}', 'warning',
     '这是 pdfTeX 时代的 Type1 字体宏包，与 XeTeX + fontspec 冲突；请改用 \\setmainfont 选择已安装字体。'),
    (r'\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{(?:minted|pythontex|sagetex|gnuplottex|shellesc|svg|auto-pst-pdf)\}', 'error',
     '该宏包需要 shell-escape 或外部程序；Tectonic 的安全模式不执行外部命令，会编译失败。请改用 listings、graphicx 或预生成的图片。'),
    (r'\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{(?:pstricks|pst-[a-z0-9-]+|multido)\}', 'warning',
     'PSTricks 在 XeTeX 下需要额外支持，Tectonic 常无法完成转换；优先改用 TikZ。'),
    (r'\\(?:write18|ShellEscape|immediate\s*\\write18)\b', 'error',
     'Tectonic 在 untrusted 模式下禁用 shell-escape，\\write18 不会执行。'),
    (r'\\(?:pdfoutput|pdfpagewidth|pdfpageheight|pdfcompresslevel|pdfobjcompresslevel|pdfinfo|pdfcatalog|pdfximage|pdfrefximage|pdfglyphtounicode)\b', 'error',
     '这是 pdfTeX 专用原语，XeTeX 不支持，会出现 Undefined control sequence；请删除或改用 geometry、hyperref 等宏包。'),
    (r'\\usepackage\s*(?:\[[^\]]*\])?\s*\{epsfig\}', 'warning',
     'epsfig 是旧接口；改用 graphicx 的 \\includegraphics，并优先提供 PDF/PNG 图片。'),
    (r'\\includegraphics\s*(?:\[[^\]]*\])?\s*\{[^}]*\.eps\}', 'warning',
     'EPS 需要转换；Tectonic 只能处理部分 EPS，建议提供 PDF/PNG，保证离线也能编译。'),
    (r'\\setmathfont\b', 'error',
     '\\setmathfont 需要先加载 unicode-math；缺少该宏包时报 Undefined control sequence。'),
]


def _bundle_index(cache):
    """Return (path, names) for the single pinned bundle index, cached by mtime."""
    indices = list((Path(cache) / 'bundles' / 'data').glob('*.index')) if cache else []
    if len(indices) != 1:
        return None, set()
    path = indices[0]
    stamp = path.stat().st_mtime_ns
    cached = _INDEX.get(str(path))
    if cached and cached[0] == stamp:
        return path, cached[1]
    names = set()
    try:
        for line in path.read_text('utf8').splitlines():
            parts = line.rsplit(' ', 2)
            if len(parts) == 3:
                names.add(parts[0])
    except (OSError, UnicodeError):
        return None, set()
    _INDEX[str(path)] = (stamp, names)
    return path, names


def installed_font_families():
    """Families from the Windows font registry, not a guessed list."""
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    names = set()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
            index = 0
            while True:
                try:
                    value, data, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                family = re.sub(r'\s*\((?:TrueType|OpenType|Type 1|All res|PostScript)[^)]*\)\s*$', '', value).strip()
                if family:
                    names.add(family)
                    names.add(Path(str(data)).stem)
    except (ImportError, OSError):
        pass
    fonts_dir = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    try:
        for path in fonts_dir.iterdir():
            if path.suffix.lower() in {'.ttf', '.otf', '.ttc'}:
                names.add(path.stem)
    except OSError:
        pass
    _FONTS = sorted(names, key=lambda name: (name.casefold(), name))
    return _FONTS


def _font_known(requested, fonts):
    target = requested.strip().strip('"').casefold()
    if not target:
        return None
    if target.endswith(('.otf', '.ttf', '.ttc')):
        return any(Path(name).stem.casefold() == Path(target).stem.casefold() for name in fonts)
    for name in fonts:
        folded = name.casefold()
        if folded == target or target in folded:
            return True
    return False


def search_bundle(cache, query, limit=40):
    path, names = _bundle_index(cache)
    if not names:
        return {'available': False, 'reason': '本机没有固定的 Tectonic bundle 索引，无法确认宏包是否存在'}
    needle = str(query or '').casefold().strip()
    if not needle:
        return {'available': True, 'index': path.name, 'count': len(names)}
    hits = sorted(name for name in names if needle in name.casefold())[:limit]
    return {'available': True, 'index': path.name, 'query': query, 'hits': hits,
            'truncated': len(hits) >= limit}


def package_exists(cache, name):
    _, names = _bundle_index(cache)
    if not names:
        return None
    name = str(name or '').strip()
    return name in names or name + '.sty' in names or name + '.cls' in names


def font_matches(query, limit=40):
    fonts = installed_font_families()
    needle = str(query or '').casefold().strip()
    if not fonts:
        return {'available': False, 'reason': '未能读取本机字体列表'}
    hits = [name for name in fonts if needle in name.casefold()] if needle else fonts
    return {'available': True, 'fonts': hits[:limit], 'count': len(hits), 'truncated': len(hits) > limit}


def _strip_comments(text):
    out = []
    for line in text.splitlines():
        escaped = re.match(r'^(?:[^\\%]|\\.)*%', line)
        out.append(line[:escaped.end() - 1] if escaped else line)
    return '\n'.join(out)


def local_resources(root):
    """Style/class files shipped with the project itself, which are not in the bundle."""
    names = set()
    if not root:
        return names
    try:
        for path in Path(root).rglob('*'):
            if path.suffix.lower() in {'.sty', '.cls', '.bbx', '.cbx', '.def'} and path.is_file():
                names.add(path.name)
    except OSError:
        pass
    return names


def compatibility(source, cache, main='main.tex', local=None):
    """Check one source against the pinned bundle and the real installed fonts."""
    text = _strip_comments(source)
    issues = []
    local = set(local or ())
    def add(line, severity, message, rule):
        issues.append({'line': line, 'severity': severity, 'message': message, 'rule': rule})
    for pattern, severity, message in RULES:
        for match in re.finditer(pattern, text, re.M):
            add(text.count('\n', 0, match.start()) + 1, severity, message, pattern[:60])
    font_guard = '\\IfFontExistsTF' in text
    _, names = _bundle_index(cache)
    for match in re.finditer(r'\\(documentclass|usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}', text):
        kind = match[1]
        for name in (part.strip() for part in match[2].split(',')):
            if not name:
                continue
            wanted = name if name.endswith(('.sty', '.cls')) else name + ('.cls' if kind == 'documentclass' else '.sty')
            if names and wanted not in names and wanted not in local:
                add(text.count('\n', 0, match.start()) + 1, 'error',
                    '固定 Tectonic bundle 中没有 ' + wanted + '，编译会报 File not found；请换用存在的宏包，或让用户提供该文件。',
                    'bundle:' + wanted)
    if not font_guard:
        fonts = installed_font_families()
        for match in re.finditer(r'\\(setmainfont|setsansfont|setmonofont|setCJKmainfont|setCJKsansfont|setCJKmonofont)\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}', text):
            requested = match[2].split(',')[0].strip()
            known = _font_known(requested, fonts)
            if known is False:
                add(text.count('\n', 0, match.start()) + 1, 'warning',
                    '本机字体列表中没有 ' + requested + '，XeTeX 会报字体找不到；可用 environment 查看已安装字体，或使用 \\IfFontExistsTF 做回退。',
                    'font:' + requested)
    unique = []
    seen = set()
    for issue in issues:
        key = (issue['line'], issue['message'])
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    unique.sort(key=lambda item: (item['line'], item['severity'] != 'error'))
    return {'engine': 'Tectonic/XeTeX', 'source': main, 'issues': unique[:40],
            'basis': '固定 bundle 索引 + Windows 字体注册表', 'fontGuard': font_guard}


def reference(cache, query='', source=None, main='main.tex'):
    result = {'engine': ENGINE, 'bundle': search_bundle(cache, query), 'fontQuery': query,
              'fonts': font_matches(query, 20)}
    if isinstance(source, str):
        result['compatibility'] = compatibility(source, cache, main)
    return result


def diagnose_missing(log, cache):
    """Name the missing files from a compiler log and say whether the bundle has them."""
    names = set()
    for a, b in re.findall(r"(?:File\s+[`'\"]([^`'\"\s]+)[`'\"]\s+not found|I can't find file\s+[`'\"]([^`'\"\s]+)[`'\"])", log or '', re.I):
        names.add(a or b)
    names.update(re.findall(r"=\[([\w.+-]+)\]", log or ''))
    names.update(re.findall(r'\bfont\s+[`\'"]([\w.+-]+)[`\'"]\s+(?:cannot be found|not found)', log or '', re.I))
    _, available = _bundle_index(cache)
    result = []
    for name in sorted(names):
        if not name or '/' in name or '\\' in name:
            continue
        in_bundle = (name in available) if available else None
        result.append({'name': name, 'inPinnedBundle': in_bundle,
                       'suggestion': ('属于固定公共 bundle，可用 resources 补齐后重试' if in_bundle else
                                      '固定 bundle 中没有这个文件；改用存在的宏包/字体，不要反复重试同一资源' if in_bundle is False else
                                      '无法读取固定 bundle 索引，先确认资源名称是否正确')})
    return result[:12]


def engine_error_notes(log):
    """Recognise engine-level failures that source edits cannot fix by guessing."""
    text = log or ''
    notes = []
    if re.search(r'Undefined control sequence.*\\(?:pdf[a-z]+|pdfoutput)', text, re.I) or re.search(r'\\pdf(?:pagewidth|pageheight|output|info)\b', text):
        notes.append('错误来自 pdfTeX 专用原语；XeTeX 不支持，改用 geometry/hyperref 或删除这些命令。')
    if re.search(r"(?:fontspec|font)\s*(?:error|Error).*(?:cannot be found|not found|not loadable)", text, re.I) or re.search(r'Package fontspec Error', text, re.I):
        notes.append('错误来自字体不可用；先用 environment 查看本机字体，或用 \\IfFontExistsTF 回退，不要重复尝试同一字体名。')
    if re.search(r'shell-escape|shell escape|write18|restricted \\write18', text, re.I):
        notes.append('Tectonic 不允许 shell-escape；依赖外部程序的宏包不能使用。')
    return notes[:5]
