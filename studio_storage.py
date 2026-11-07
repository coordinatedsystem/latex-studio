"""Shared installation paths and project library; no framework dependencies."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import threading
import time
import uuid

IMPORT_TYPES = {'.tex', '.bib', '.sty', '.cls', '.bst', '.bbl', '.cfg', '.def', '.fd', '.clo',
                '.tikz', '.py', '.md', '.txt', '.csv', '.json', '.pdf', '.png', '.jpg', '.jpeg',
                '.webp', '.gif', '.svg', '.eps', '.otf', '.ttf', '.tfm', '.pfb', '.map'}
LOCK = threading.RLock()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def project_id(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode('utf-8')).hexdigest()[:20]


def safe_relative(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('文件的相对路径无效')
    parts = PurePosixPath(name)
    if parts.is_absolute() or any(p in {'..', '.'} or p.startswith('.') for p in parts.parts):
        raise ValueError('导入的文件不能越过项目目录')
    if any(re.search(r'[<>"|?*\x00-\x1f]', p) for p in parts.parts):
        raise ValueError('文件名包含 Windows 不支持的字符')
    return Path(*parts.parts)


def detect_main(root, preferred=None):
    root = Path(root)
    if preferred:
        candidate = safe_relative(preferred)
        if (root / candidate).is_file() and candidate.suffix.lower() == '.tex':
            return candidate.as_posix()
    for name in ['main.tex', 'report.tex', 'thesis.tex', 'document.tex']:
        if (root / name).is_file():
            return name
    choices = sorted(p for p in root.rglob('*.tex') if not any(part.startswith('.') for part in p.relative_to(root).parts))[:500]
    for candidate in choices:
        try:
            if '\\documentclass' in candidate.read_text(encoding='utf-8-sig', errors='ignore')[:12000]:
                return candidate.relative_to(root).as_posix()
        except OSError:
            pass
    if choices:
        return choices[0].relative_to(root).as_posix()
    raise ValueError('没有找到 .tex 文件，请选择含有 LaTeX 源文件的项目')


class StudioStorage:
    def __init__(self, app):
        self.app = Path(app).resolve()
        config = read_json(self.app / 'installation.json', {})
        self.installed = bool(config.get('home'))
        self.home = Path(config['home']).resolve() if self.installed else self.app
        self.data = self.home / 'data' if self.installed else self.app / 'storage'
        self.runtime = self.home / 'runtime' if self.installed else self.app.parent / 'latex-portable'
        locations=read_json(self.data/'locations.json',{})
        self.projects = Path(locations.get('projects', self.home/'projects' if self.installed else self.data/'projects')).resolve()
        self.cache = Path(locations.get('cache',self.home/'cache')).resolve()
        self.tex_cache = self.cache/'tectonic'
        self.default_root = Path(locations.get('defaultProject',config.get('defaultProject', self.app.parent))).resolve()
        self.settings_path = self.data / 'settings.json'

    def settings(self):
        return read_json(self.settings_path, {'recent': [], 'active': None})

    def record_project(self, root, main, name=None):
        root = Path(root).resolve()
        entry = {'id': project_id(root), 'root': str(root), 'name': name or root.name,
                 'main': main, 'opened': time.strftime('%Y-%m-%d %H:%M')}
        with LOCK:
            config = self.settings()
            config['recent'] = [entry] + [p for p in config.get('recent', []) if p.get('id') != entry['id']][:11]
            config['active'] = entry
            write_json(self.settings_path, config)
        return entry

    def active_project(self):
        entry = self.settings().get('active')
        if entry and Path(entry['root']).is_dir():
            try:
                entry['main'] = detect_main(entry['root'], entry.get('main'))
                return entry
            except ValueError:
                pass
        if self.default_root.is_dir():
            try:
                return self.record_project(self.default_root, detect_main(self.default_root))
            except ValueError:
                pass
        return self.create_project('我的文档', 'minimal')

    def describe(self):
        settings = self.settings()
        return {'home': str(self.home), 'data': str(self.data), 'runtime': str(self.runtime),
                'cache': str(self.cache), 'projects': str(self.projects),
                'installed': self.installed,
                'recent': [{**p, 'exists': Path(p['root']).is_dir()} for p in settings.get('recent', [])],
                'engineReady': (self.runtime / 'bin' / 'tectonic.exe').is_file(),
                'cacheReady': any((self.tex_cache / 'bundles' / 'data').glob('*.index')),
                'offlineFormatReady': any((self.tex_cache / 'formats').glob('*latex*.fmt'))}

    def configure_locations(self,projects,cache):
        from studio_locations import configure
        return configure(self,projects,cache)

    def build_folder(self,root):
        return self.cache/'build'/project_id(root)

    def history_folder(self, root, relative):
        return self.data / 'history' / project_id(root) / relative

    def preview_path(self, root):
        return self.data / 'previews' / (project_id(root) + '.pdf')

    def open_project(self, name):
        chosen = Path(name).expanduser().resolve()
        if chosen.is_file() and chosen.suffix.lower() == '.tex':
            root, main = chosen.parent, chosen.name
        elif chosen.is_dir():
            root, main = chosen, detect_main(chosen)
        else:
            raise ValueError('请选择存在的 .tex 文件或项目文件夹')
        return self.record_project(root, main)

    def forget_project(self, ident):
        with LOCK:
            config = self.settings()
            config['recent'] = [p for p in config.get('recent', []) if p.get('id') != ident]
            write_json(self.settings_path, config)

    def unique_folder(self, name):
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(name)).strip(' .')[:70] or '新项目'
        if name.upper() in {'CON', 'NUL', 'AUX', 'PRN'}:
            name = '项目-' + name
        self.projects.mkdir(parents=True, exist_ok=True)
        target = self.projects / name
        number = 2
        while target.exists():
            target = self.projects / f'{name}-{number}'
            number += 1
        return target

    def import_project(self, name, files, preferred=None):
        if not isinstance(files, list) or not files or len(files) > 3000:
            raise ValueError('请选择 1 至 3000 个项目文件')
        target = self.unique_folder(name)
        staging = self.projects / ('.import-' + uuid.uuid4().hex)
        staging.mkdir()
        total = 0
        skipped = []
        seen = set()
        try:
            for file in files:
                relative = safe_relative(file['path'])
                if relative.suffix.lower() not in IMPORT_TYPES:
                    skipped.append(relative.as_posix())
                    continue
                key = relative.as_posix().casefold()
                if key in seen:
                    raise ValueError('存在重复文件名：' + relative.as_posix())
                seen.add(key)
                content = base64.b64decode(file['content'], validate=True)
                total += len(content)
                if len(content) > 24 * 1024 * 1024 or total > 90 * 1024 * 1024:
                    raise ValueError('单文件上限 24 MB；一次导入上限 90 MB')
                dest = staging / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
            main = detect_main(staging, preferred)
            staging.rename(target)
            return {**self.record_project(target, main), 'imported': len(seen), 'skipped': skipped}
        finally:
            if staging.exists() and staging.resolve().is_relative_to(self.projects.resolve()):
                shutil.rmtree(staging)

    def create_project(self, name, template='minimal'):
        folder = self.unique_folder(name)
        title = re.sub(r'[\\{}%#$&_~^]', '', str(name)) or '我的文档'
        preamble = r'''% !TeX program = xelatex
\documentclass[11pt,a4paper]{article}
\usepackage[margin=25mm]{geometry}
\usepackage{fontspec,xeCJK}
\setmainfont{Times New Roman}
\setCJKmainfont[BoldFont=SimHei]{SimSun}
\usepackage{amsmath,amssymb,graphicx,booktabs}
\usepackage[unicode,hidelinks]{hyperref}
\linespread{1.25}
'''
        body = ('\\title{' + title + '}\n\\author{}\n\\date{\\today}\n'
                '\\begin{document}\n\\maketitle\n'
                '\\section{开始写作}\n在这里输入正文。\n')
        if template == 'report':
            body += ('\n\\section{方法与结果}\n'
                     '\\begin{equation}\n  y = f(x)\n\\end{equation}\n'
                     '\n\\section{结论}\n在这里总结主要发现。\n')
        body += '\n\\end{document}\n'
        folder.mkdir()
        (folder / 'main.tex').write_text(preamble + body, encoding='utf-8')
        return self.record_project(folder, 'main.tex')


_stores = {}


def storage_for(app):
    app = Path(app).resolve()
    key = (str(app), (app / 'installation.json').stat().st_mtime_ns if (app / 'installation.json').exists() else 0)
    with LOCK:
        if key not in _stores:
            _stores[key] = StudioStorage(app)
        return _stores[key]
