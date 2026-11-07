"""A real resource manager for the pinned Tectonic support bundle."""
from __future__ import annotations

from collections import deque
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

from studio_engine import engine_environment
from studio_storage import read_json, write_json

HOSTS = ['https://data1b.fullyjustified.net/tlextras-2022.0r0.tar',
         'https://data1.fullyjustified.net/tlextras-2022.0r0.tar']
CORE = {'article.cls', 'report.cls', 'book.cls', 'minimal.cls', 'fontspec.sty', 'xeCJK.sty',
        'expl3.sty', 'xparse.sty', 'l3keys2e.sty', 'fontspec-xetex.sty', 'fix-cm.sty'}
INFO = {
 'amsmath':('数学公式与多行对齐','数学'), 'amssymb':('常用数学符号','数学'),
 'mathtools':('公式排版扩展，增强 amsmath','数学'), 'mhsetup':('mathtools 支持文件','数学'),
 'geometry':('纸张、页边距与页面尺寸','页面'), 'graphicx':('插入图片与缩放','图片'),
 'xcolor':('文字、图表和页面颜色','颜色'), 'booktabs':('学术三线表','表格'),
 'tabularx':('自动列宽表格','表格'), 'longtable':('跨页长表格','表格'),
 'hyperref':('超链接、PDF 目录与书签','导航'), 'xurl':('长链接自动断行','导航'),
 'caption':('图表标题格式','图片'), 'subcaption':('子图与子表标题','图片'),
 'fancyhdr':('页眉与页脚','页面'), 'enumitem':('列表缩进与编号样式','列表'),
 'fontspec':('系统字体与 OpenType 字体','字体'), 'xeCJK':('中文与中西文混排','中文'),
 'ctex':('中文文档与标题格式','中文'), 'ctexart':('中文文章文档类','中文'),
 'tikz':('矢量绘图与流程图','绘图'), 'pgfplots':('坐标轴与科学绘图','绘图'),
 'listings':('源代码排版','代码'), 'fvextra':('代码换行与逐字文本','代码'),
 'minted':('依赖外部高亮程序，当前编译器不启用外部命令','代码'),
 'siunitx':('物理单位、数字与测量值','科学'), 'physics':('物理与数学公式命令','科学'),
 'cleveref':('智能交叉引用','导航'), 'titlesec':('章节标题格式','页面'),
 'float':('图片、表格位置控制','图片'), 'needspace':('防止标题与正文不当分页','页面'),
 'beamer':('演示文稿文档类','幻灯片'), 'biblatex':('参考文献排版；部分样式需额外工具','参考文献'),
 'natbib':('作者年份与数字式文献引用','参考文献'), 'multirow':('表格跨行单元格','表格'),
 'array':('扩展表格列格式','表格'), 'tcolorbox':('彩色内容框','颜色'),
}
FEATURED = ['mathtools.sty', 'geometry.sty', 'graphicx.sty', 'xcolor.sty', 'booktabs.sty',
            'hyperref.sty', 'fontspec.sty', 'xeCJK.sty', 'siunitx.sty', 'tikz.sty',
            'pgfplots.sty', 'cleveref.sty', 'multirow.sty', 'tcolorbox.sty', 'beamer.cls']


class PackageManager:
    def __init__(self, storage):
        self.storage = storage
        self.runtime = storage.runtime
        self.data = storage.data
        indices = sorted((self.storage.tex_cache / 'bundles' / 'data').glob('*.index'))
        if not indices:
            raise ValueError('尚未找到共享宏包目录中的 Tectonic 资源索引')
        self.index_path = indices[0]
        self.bundle_id = self.index_path.stem
        self.cache = self.index_path.parent / self.bundle_id
        self.entries = {}
        for line in self.index_path.read_text(encoding='utf-8').splitlines():
            values = line.rsplit(' ', 2)
            if len(values) != 3:
                continue
            name, start, length = values
            if '/' in name or '\\' in name or name in {'.', '..'}:
                continue
            try:
                self.entries.setdefault(name, (int(start), int(length)))
            except ValueError:
                continue
        self.packages = sorted(n for n in self.entries if n.endswith(('.sty', '.cls')))
        self.manifest_path = self.data / 'package-manifest.json'
        self.trash_path = self.data / 'package-trash.json'
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.process = None
        self.network_verified = False
        self.job = {'running': False, 'id': '', 'action': '', 'current': '', 'completed': 0,
                    'total': 0, 'success': None, 'lines': [], 'result': None}

    def _manifest(self):
        return read_json(self.manifest_path, {})

    def _cached(self):
        return {p.name: p.stat().st_size for p in self.cache.iterdir() if p.is_file()} if self.cache.exists() else {}

    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.job))

    def catalog(self, query='', filter_by='all', page=0):
        cached, manifest, trash = self._cached(), self._manifest(), read_json(self.trash_path, {})
        query = query.strip().casefold()
        results = []
        installed = sum(n in cached and cached[n] == self.entries[n][1] for n in self.packages)
        for name in self.packages:
            stem = Path(name).stem
            info, category = INFO.get(stem, ('LaTeX 文档类' if name.endswith('.cls') else 'LaTeX 宏包', '通用'))
            if query and query not in (name + ' ' + info + ' ' + category).casefold():
                continue
            exists = name in cached
            valid = exists and cached[name] == self.entries[name][1]
            removed = name in trash and not exists
            if filter_by == 'cached' and not exists or filter_by == 'available' and valid or filter_by == 'removed' and not removed:
                continue
            record = manifest.get(name, {})
            item = {'name': name, 'package': stem, 'kind': 'class' if name.endswith('.cls') else 'package',
                    'description': info, 'category': category, 'size': self.entries[name][1],
                    'cached': valid, 'corrupt': exists and not valid, 'removed': removed,
                    'protected': name in CORE, 'verified': valid and bool(record.get('verified')),
                    'downloadedAt': record.get('time'), 'verification': record.get('verification', ''),
                    'resources': len(record.get('files', []))}
            results.append(item)
        def rank(item):
            if query:
                return (item['package'].casefold() != query.removesuffix('.sty').removesuffix('.cls'), not item['cached'], item['name'].casefold())
            return (FEATURED.index(item['name']) if item['name'] in FEATURED else 1000, not item['cached'], item['name'].casefold())
        results.sort(key=rank)
        page = max(0, min(int(page), max(0, (len(results) - 1) // 48)))
        return {'items': results[page * 48:(page + 1) * 48], 'total': len(results), 'page': page,
                'pages': max(1, (len(results) + 47) // 48), 'catalogCount': len(self.packages),
                'cachedPackages': installed, 'cachedResources': len(cached),
                'cacheBytes': sum(p.stat().st_size for p in (self.storage.tex_cache).rglob('*') if p.is_file()),
                'cachePath': str(self.storage.tex_cache), 'bundle': self.bundle_id,
                'source': 'Tectonic 兼容资源库', 'job': self.status()}

    def _say(self, message):
        with self.lock:
            self.job['lines'].append(str(message))
            self.job['lines'] = self.job['lines'][-250:]

    def start(self, action, names):
        if action not in {'install', 'repair', 'remove', 'restore', 'check'}:
            raise ValueError('不支持此宏包操作')
        names = list(dict.fromkeys(names))
        if not names or len(names) > 30 or any(n not in self.packages for n in names):
            raise ValueError('请选择目录中有效的宏包或文档类（一次最多 30 个）')
        with self.lock:
            if self.job['running']:
                raise ValueError('已有宏包任务正在进行')
            self.cancel_event.clear()
            self.job = {'running': True, 'id': uuid.uuid4().hex, 'action': action, 'current': '',
                        'completed': 0, 'total': len(names), 'success': None, 'lines': [], 'result': None}
            threading.Thread(target=self._run, args=(action, names), daemon=True).start()
        return self.status()

    def cancel(self):
        self.cancel_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self._say('正在停止；当前文件的网络请求结束后生效。')

    def _run(self, action, names):
        results = []
        try:
            for name in names:
                if self.cancel_event.is_set():
                    raise ValueError('任务已停止；已完成的缓存会保留')
                with self.lock:
                    self.job['current'] = name
                result = getattr(self, '_' + action)(name)
                results.append(result)
                with self.lock:
                    self.job['completed'] += 1
            with self.lock:
                self.job['success'] = True
                self.job['result'] = results
        except Exception as exc:
            self._say(str(exc))
            with self.lock:
                self.job['success'] = False
                self.job['result'] = results
        finally:
            self.process = None
            with self.lock:
                self.job['running'] = False

    def _range(self, start, size):
        error = None
        for host in HOSTS:
            try:
                request = urllib.request.Request(host, headers={'Range': f'bytes={start}-{start + size - 1}',
                                                               'User-Agent': 'tectonic/0.17.0', 'Accept-Encoding': 'identity'})
                with urllib.request.urlopen(request, timeout=18) as response:
                    if response.status != 206 or not response.headers.get('Content-Range', '').startswith(f'bytes {start}-'):
                        raise ValueError('宏包镜像没有返回有效的分段响应')
                    value = response.read(size + 1)
                if len(value) != size:
                    raise ValueError('下载数据长度不符，请重试')
                return value
            except (OSError, ValueError) as exc:
                error = exc
        raise ValueError('宏包下载失败，请检查网络后重试：' + str(error))

    def _verify_remote_bundle(self):
        if self.network_verified:
            return
        if 'SHA256SUM' not in self.entries:
            raise ValueError('资源索引缺少身份标识')
        value = self._range(*self.entries['SHA256SUM']).decode('ascii').strip()
        if value != self.bundle_id:
            raise ValueError('镜像资源库版本与本地索引不同，已停止下载')
        self.network_verified = True

    def _sync_prefetch(self):
        names = sorted(self._cached())
        for path in self.index_path.parent.glob('*.prefetch'):
            temp = path.with_name(path.name + '.tmp')
            temp.write_text('\n'.join(names) + '\n', encoding='utf-8')
            temp.replace(path)

    def _download(self, name, force=False):
        if self.cancel_event.is_set():
            raise ValueError('任务已停止')
        if name not in self.entries:
            return False
        dest = self.cache / name
        if not force and dest.exists() and dest.stat().st_size == self.entries[name][1]:
            return False
        self._verify_remote_bundle()
        self._say('下载 ' + name)
        value = self._range(*self.entries[name])
        self.cache.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(dest.name + '.studio-download')
        temp.write_bytes(value)
        temp.replace(dest)
        return True

    def dependencies(self, text):
        text = re.sub(r'(?<!\\)%[^\n]*', '', text)
        found = set()
        for command, names in re.findall(r'\\(RequirePackage(?:WithOptions)?|usepackage|LoadClass(?:WithOptions)?)\s*(?:\[[^\]]*\]\s*)?\{([^}]+)\}', text):
            suffix = '.cls' if command.startswith('LoadClass') else '.sty'
            for name in names.split(','):
                name = name.strip()
                if re.fullmatch(r'[A-Za-z0-9_.+-]+', name):
                    found.add(name if name.endswith(suffix) else name + suffix)
        for name in re.findall(r'\\(?:input|InputIfFileExists)\s*\{([^}]+)\}', text):
            if re.fullmatch(r'[A-Za-z0-9_.+-]+', name):
                if name in self.entries:
                    found.add(name)
                elif name + '.tex' in self.entries:
                    found.add(name + '.tex')
        return found

    def _fill(self, name, touched, force=False):
        queue = deque([name])
        while queue:
            current = queue.popleft()
            if current in touched or current not in self.entries:
                continue
            if len(touched) >= 200:
                raise ValueError('自动依赖超过 200 个资源，请在实际项目中联网编译补全')
            touched.add(current)
            self._download(current, force=force and current == name)
            if current.endswith(('.sty', '.cls', '.tex', '.def', '.cfg')):
                content = (self.cache / current).read_text(encoding='utf-8', errors='ignore')
                queue.extend(sorted(self.dependencies(content) - touched))

    def _probe(self, name, touched):
        probes = self.storage.cache/'package-probes'
        probes.mkdir(parents=True, exist_ok=True)
        engine = self.runtime / 'bin' / 'tectonic.exe'
        if not engine.is_file():
            return False, '未找到编译器；主文件和可解析的依赖已缓存'
        stem = Path(name).stem
        source = ('\\documentclass{' + (stem if name.endswith('.cls') else 'article') + '}\n' +
                  ('\\usepackage{' + stem + '}\n' if name.endswith('.sty') else '') +
                  '\\begin{document}\nPackage validation.\n\\end{document}\n')
        with tempfile.TemporaryDirectory(prefix='probe-', dir=probes) as temporary:
            work = Path(temporary)
            if not work.resolve().is_relative_to(probes.resolve()):
                raise ValueError('验证目录无效')
            (work / 'probe.tex').write_text(source, encoding='utf-8')
            for _ in range(16):
                if self.cancel_event.is_set():
                    raise ValueError('任务已停止')
                self._say('离线验证 ' + name)
                self.process = subprocess.Popen([str(engine), '--only-cached', '--untrusted', '--outdir', str(work), 'probe.tex'],
                    cwd=work, env=engine_environment(self.runtime, self.data,self.storage.tex_cache), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                try:
                    output, _ = self.process.communicate(timeout=45)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.communicate()
                    return False, '验证超时；已下载的缓存保留'
                if self.process.returncode == 0 and (work / 'probe.pdf').exists():
                    return True, '离线验证通过'
                missing = re.findall(r"(?:File\s+[`'\"]([^`'\"]+)[`'\"]\s+not found|I can't find file\s+[`'\"]([^`'\"]+)[`'\"])", output)
                names = {a or b for a, b in missing}
                available = {n for n in names if n in self.entries and n not in touched}
                if not available:
                    lines = [line for line in output.splitlines() if 'error' in line.casefold() or line.startswith('!')]
                    detail = ' / '.join(lines[-3:])[:450]
                    return False, '主文件已缓存；此宏包需结合具体文档验证。' + (' ' + detail if detail else '')
                for dependency in sorted(available):
                    self._fill(dependency, touched)
        return False, '主文件已缓存；更多依赖可在实际项目中联网编译补全'

    def _install(self, name, force=False):
        before = set(self._cached())
        touched = set()
        self._fill(name, touched, force)
        verified, message = self._probe(name, touched)
        self._sync_prefetch()
        with self.lock:
            manifest = self._manifest()
            previous = manifest.get(name, {})
            owned = set(previous.get('owned', [])) | (touched - before)
            manifest[name] = {'files': sorted(touched), 'owned': sorted(owned), 'verified': verified,
                              'verification': message, 'time': time.strftime('%Y-%m-%d %H:%M'),
                              'hashes': {n: hashlib.sha256((self.cache / n).read_bytes()).hexdigest() for n in touched}}
            write_json(self.manifest_path, manifest)
        self._say(name + '：' + message)
        return {'name': name, 'verified': verified, 'message': message, 'resources': len(touched)}

    def _repair(self, name):
        record = self._manifest().get(name, {})
        for resource, expected in record.get('hashes', {}).items():
            path = self.cache / resource
            if resource in self.entries and (not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                self._download(resource, force=True)
        return self._install(name, force=True)

    def _check(self, name):
        record = self._manifest().get(name, {})
        bad, good = [], 0
        for resource in record.get('files', [name]):
            path = self.cache / resource
            if not path.exists() or resource not in self.entries or path.stat().st_size != self.entries[resource][1]:
                bad.append(resource)
                continue
            expected = record.get('hashes', {}).get(resource)
            if expected and hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                bad.append(resource)
            else:
                good += 1
        message = ('发现缺失或损坏资源：' + ', '.join(bad)) if bad else f'{good} 个资源检查通过'
        self._say(name + '：' + message)
        return {'name': name, 'valid': not bad, 'bad': bad, 'message': message}

    def _remove(self, name):
        if name in CORE:
            raise ValueError('核心编译资源不能移除')
        manifest = self._manifest()
        record = manifest.get(name, {})
        # Other documents may use dependencies without having a managed record.
        # Removing only the selected main file keeps those shared resources safe.
        candidates = {name}
        referenced = {f for package, data in manifest.items() if package != name for f in data.get('files', [])}
        if name in referenced:
            raise ValueError('其他已管理宏包依赖此文件，请先移除依赖它的宏包')
        ident = uuid.uuid4().hex
        folder = self.data / 'package-trash' / ident
        folder.mkdir(parents=True)
        moved = []
        for resource in sorted(candidates - referenced - CORE):
            path = self.cache / resource
            if path.exists() and path.resolve().is_relative_to(self.cache.resolve()):
                path.replace(folder / resource)
                moved.append(resource)
        trash = read_json(self.trash_path, {})
        trash[name] = {'id': ident, 'files': moved, 'metadata': record, 'time': time.strftime('%Y-%m-%d %H:%M')}
        write_json(self.trash_path, trash)
        manifest.pop(name, None)
        write_json(self.manifest_path, manifest)
        self._sync_prefetch()
        self._say(f'{name} 主文件已移入回收区，可恢复；共享依赖保留。')
        return {'name': name, 'moved': moved, 'message': '已移除，可恢复'}

    def _restore(self, name):
        trash = read_json(self.trash_path, {})
        record = trash.get(name)
        if not record or not re.fullmatch(r'[a-f0-9]{32}', record['id']):
            raise ValueError('没有可恢复的宏包记录')
        folder = self.data / 'package-trash' / record['id']
        if not folder.resolve().is_relative_to((self.data / 'package-trash').resolve()):
            raise ValueError('回收区路径无效')
        for resource in record['files']:
            if resource not in self.entries:
                raise ValueError('回收记录包含无效文件')
            source, dest = folder / resource, self.cache / resource
            if source.exists() and not dest.exists():
                source.replace(dest)
        manifest = self._manifest()
        if record.get('metadata'):
            metadata = record['metadata']
            complete = all((self.cache / n).is_file() and (self.cache / n).stat().st_size == self.entries.get(n, (0, -1))[1]
                           and (not metadata.get('hashes', {}).get(n) or hashlib.sha256((self.cache / n).read_bytes()).hexdigest() == metadata['hashes'][n])
                           for n in metadata.get('files', []))
            if not complete:
                metadata['verified'] = False
                metadata['verification'] = '主文件已恢复，部分依赖需重新下载验证'
            manifest[name] = metadata
            write_json(self.manifest_path, manifest)
        trash.pop(name, None)
        write_json(self.trash_path, trash)
        self._sync_prefetch()
        self._say(name + ' 已恢复。')
        return {'name': name, 'message': '已恢复'}

    def analyze(self, files):
        used = set()
        for name, content in files:
            text = re.sub(r'(?<!\\)%[^\n]*', '', content)
            used.update(self.dependencies(text))
            used.update(n.strip() + '.cls' for n in re.findall(r'\\documentclass(?:\[[^]]*\])?\s*\{([^}]+)\}', text))
        cached = self._cached()
        return [{'name': n, 'available': n in self.entries, 'cached': n in cached and n in self.entries and cached[n] == self.entries[n][1]}
                for n in sorted(used)]


_managers = {}
_manager_lock = threading.Lock()


def packages_for(storage):
    key = (str(storage.runtime), str(storage.data),str(storage.tex_cache))
    with _manager_lock:
        if key not in _managers:
            _managers[key] = PackageManager(storage)
        return _managers[key]
