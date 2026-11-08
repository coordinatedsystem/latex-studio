"""Local-only LaTeX workspace. Standard-library server; no pip packages required."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit
import webbrowser

sys.dont_write_bytecode = True

if sys.version_info < (3, 10):
    raise RuntimeError('LaTeX Studio requires Python 3.10 or later. Use the desktop launcher to select a compatible runtime.')

from studio_storage import storage_for, project_id, detect_main
from studio_packages import packages_for
from studio_engine import engine_environment
from studio_ai import assistant_for
from studio_usage import usage_for
from studio_sync import locate
from studio_editor_ai import editor_ai_for
from studio_page_edits import pages_for, project_files, save_source_map, sha
from studio_batch_edits import atomic_write_set
from studio_review import analyze_references, glossary_get, glossary_save, page_image, parse_pages, poppler_exe, selftest

sys.dont_write_bytecode = True
APP = Path(__file__).resolve().parent
ROOT = APP.parent
TEXT = {'.tex', '.bib', '.sty', '.cls', '.py', '.txt', '.md', '.json', '.csv', '.bst'}
MEDIA = {'.pdf', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'}
PROTECTED = {'latex-studio', 'latex-portable', 'build', '.git', '.codex', '.agents', '.history'}
MAX_BODY = 128 * 1024 * 1024
from studio_version import VERSION, BUILD
from studio_updates import updates_for
SERVER_BUILD = BUILD


class StudioHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR permits two live processes to bind the same port.
    # Exclusive binding keeps a launcher's health check attached to its own process.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def storage():
    return storage_for(APP)


def current_preview():
    target = storage().preview_path(ROOT)
    if target.exists():
        return target
    if ROOT.resolve() == storage().default_root and (APP / 'preview.pdf').exists():
        return APP / 'preview.pdf'
    return target


def package_busy():
    try:
        return packages_for(storage()).status()['running']
    except ValueError:
        return False


def require_idle():
    if STATE['running']:
        raise ValueError('正在编译，请等待完成后再操作项目或宏包')
    if package_busy():
        raise ValueError('宏包任务尚未完成，请稍后再操作')
    if assistant_for(storage().data).busy():
        raise ValueError('AI 任务尚未结束，请先等待或停止任务')
    if pages_for(storage()).busy():
        raise ValueError('正在编译修改效果预览，请等待完成')
    if editor_ai_for(storage()).busy():raise ValueError('编辑器 AI 正在处理，请先等待或停止')


def seed_preview():
    target = storage().preview_path(ROOT)
    if not target.exists():
        main = Path(STATE['main']).stem
        candidates = [ROOT / 'build' / (main + '.pdf'), ROOT / (main + '.pdf')]
        if ROOT.resolve() == storage().default_root:
            candidates += [APP / 'preview.pdf', ROOT / '人工神经网络实验报告.pdf']
        for candidate in candidates:
            if candidate.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(candidate, target)
                break
    STATE['pdfVersion'] = target.stat().st_mtime_ns if target.exists() else 0


def select_project(entry):
    global ROOT
    require_idle()
    ROOT = Path(entry['root']).resolve()
    STATE.update(main=entry['main'], success=None, lines=[], diagnostics=[], duration=0)
    seed_preview()
    return {**entry, 'projectId': project_id(ROOT)}


def load_session_token(app):
    """Keep existing local-browser sessions valid when the server is restarted."""
    token_file = app / 'session-token'
    candidates = []
    if token_file.exists():
        candidates.append(token_file.read_text(encoding='utf-8').strip())
    runtime = app / 'runtime.json'
    if runtime.exists():
        try:
            url = urlsplit(json.loads(runtime.read_text(encoding='utf-8'))['url'])
            if url.hostname == '127.0.0.1':
                candidates.extend(parse_qs(url.query).get('token', []))
        except (ValueError, KeyError, OSError):
            pass
    token = next((t for t in candidates if re.fullmatch(r'[A-Za-z0-9_-]{32,128}', t)), None)
    token = token or secrets.token_urlsafe(32)
    if not token_file.exists() or token_file.read_text(encoding='utf-8').strip() != token:
        token_file.write_text(token, encoding='utf-8')
    return token


_session_dir = storage().data
_session_dir.mkdir(parents=True, exist_ok=True)
for _name in ['session-token', 'runtime.json']:
    if not (_session_dir / _name).exists() and (APP / _name).exists():
        shutil.copyfile(APP / _name, _session_dir / _name)
TOKEN = load_session_token(_session_dir)
LOCK = threading.RLock()
STATE = {'running': False, 'job': 0, 'lines': [], 'success': None, 'duration': 0,
         'pdfVersion': 0, 'main': 'report.tex', 'started': None, 'diagnostics': []}
PROCESS = None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def project_path(name, write=False):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name:
        raise ValueError('文件路径无效')
    relative = Path(name)
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or any(p.startswith('.') or p in PROTECTED for p in relative.parts):
        raise ValueError('只能访问当前项目的文档和素材')
    if path.suffix.lower() not in TEXT | MEDIA:
        raise ValueError('不支持此文件类型')
    if write and path.suffix.lower() not in TEXT | MEDIA:
        raise ValueError('此文件不可编辑')
    return path


def tree():
    items = []
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in PROTECTED and not (Path(base) / d).is_symlink())
        for name in sorted(files):
            p = Path(base) / name
            if p.suffix.lower() in TEXT | MEDIA and not p.is_symlink():
                items.append({'path': p.relative_to(ROOT).as_posix(), 'size': p.stat().st_size,
                              'editable': p.suffix.lower() in TEXT})
    return items


def snapshot(path):
    if not path.exists():
        return
    relative = path.relative_to(ROOT)
    folder = storage().history_folder(ROOT, relative)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns() % 1000000000)
    shutil.copy2(path, folder / stamp)
    for old in sorted(folder.iterdir(), reverse=True)[30:]:
        old.unlink()


def detect_diagnostics(lines, main):
    found = []
    for line in lines:
        match = re.search(r'(?:error|warning):\s*(.*?):(\d+):\s*(.*)', line, re.I)
        if match:
            name = match[1].replace('\\', '/')
            if name == Path(main).name:
                name = main
            found.append({'file': name, 'line': int(match[2]), 'message': match[3],
                          'severity': 'error' if 'error:' in line.lower() else 'warning'})
    return found


def compile_job(main, offline, job):
    global PROCESS
    started = time.monotonic()
    work = storage().build_folder(ROOT) / f'studio-{job}-{time.time_ns()}'
    work.mkdir(parents=True, exist_ok=True)
    try:
        engine = storage().runtime / 'bin' / 'tectonic.exe'
        if not engine.exists():
            raise RuntimeError('缺少便携式 Tectonic 编译器')
        env = engine_environment(storage().runtime, storage().data,storage().tex_cache)
        source_hashes={p.relative_to(ROOT).as_posix():sha(p) for p in project_files(ROOT)}
        args = [str(engine), '--keep-logs', '--synctex', '--untrusted', '--outdir', str(work)]
        if offline:
            args.append('--only-cached')
        args.append(main)
        with LOCK:
            STATE['lines'].append('Tectonic · ' + ('离线编译' if offline else '自动下载缺少的宏包') + ' · ' + main)
        PROCESS = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for line in PROCESS.stdout:
            with LOCK:
                STATE['lines'].append(line.rstrip())
                STATE['lines'] = STATE['lines'][-6000:]
        code = PROCESS.wait()
        pdf = work / (Path(main).stem + '.pdf')
        if code != 0 or not pdf.exists():
            raise RuntimeError('编译已停止' if code < 0 else '编译失败，请查看错误信息；右侧保留上次成功预览。')
        # App-private PDF is never held open by an external desktop PDF reader.
        target = storage().preview_path(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix('.tmp')
        shutil.copyfile(pdf, temp)
        os.replace(temp, target)
        try:
            save_source_map(ROOT,main,target,work/(Path(main).stem+'.synctex.gz'),storage().data,source_hashes)
        except Exception:
            STATE['lines'].append('PDF 已生成；源码映射不可用，可重新编译后重试单页修改。')
        with LOCK:
            STATE['pdfVersion'] = target.stat().st_mtime_ns
            STATE['success'] = True
            STATE['lines'].append('编译成功 · PDF 预览已更新')
        # Also keep a familiar output path for use outside the editor.
        try:
            shutil.copyfile(pdf, storage().build_folder(ROOT) / (Path(main).stem + '.pdf'))
        except OSError:
            pass
    except Exception as exc:
        with LOCK:
            STATE['success'] = False
            STATE['lines'].append(str(exc))
    finally:
        with LOCK:
            STATE['duration'] = round(time.monotonic() - started, 1)
            STATE['running'] = False
            STATE['diagnostics'] = detect_diagnostics(STATE['lines'], main)
            PROCESS = None
        storage().data.mkdir(parents=True, exist_ok=True)
        (storage().data / 'last-compile.log').write_text('\n'.join(STATE['lines']), encoding='utf-8')
        if work.resolve().is_relative_to(storage().build_folder(ROOT).resolve()):
            shutil.rmtree(work, ignore_errors=True)


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalLaTeX/1.0'

    def log_message(self, *_):
        pass

    def send(self, data, status=200, mime='application/json; charset=utf-8', extra=None):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        elif isinstance(data, str):
            data = data.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store' if mime.startswith('application/json') else 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorized(self):
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
        except Exception:
            return False
        cookie = cookies.get('studio_token')
        return bool(cookie and secrets.compare_digest(cookie.value, TOKEN))

    def local_request(self):
        host = self.headers.get('Host', '')
        expected = f'127.0.0.1:{self.server.server_port}'
        origin = self.headers.get('Origin')
        return host == expected and (not origin or origin == 'http://' + expected)

    def do_GET(self):
        try:
            if not self.local_request():
                return self.send({'error': 'Invalid local origin'}, 403)
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            path = unquote(parsed.path)
            if path == '/' and 'token' in query:
                if not secrets.compare_digest(query['token'][0], TOKEN):
                    return self.send({'error': 'Invalid session'}, 403)
                return self.send(b'', 302, extra={'Location': '/', 'Set-Cookie': f'studio_token={TOKEN}; HttpOnly; SameSite=Strict; Path=/'})
            if path.startswith('/api/') or path == '/preview.pdf' or path.startswith('/project/'):
                if not self.authorized():
                    return self.send({'error': '请通过启动快捷方式打开编辑器'}, 401)
            context = self.headers.get('X-Studio-Project') or query.get('project', [''])[0]
            if context and context != project_id(ROOT) and (path.startswith(('/api/sync-point', '/api/file', '/api/history', '/project/', '/api/review/','/api/ai/','/api/editor-ai/')) or path == '/preview.pdf'):
                return self.send({'error': '当前项目已在其他窗口切换，请重新打开所需项目'}, 409)
            if path == '/api/state':
                with LOCK:
                    return self.send({**STATE, 'root': str(ROOT), 'projectName': ROOT.name, 'projectId': project_id(ROOT), 'serverBuild': SERVER_BUILD, 'version':VERSION, 'app': str(APP),
                                      'hasPdf': current_preview().exists(), 'files': tree(),
                                      'runtime': str(storage().runtime), 'packageBusy': package_busy(), 'aiBusy': assistant_for(storage().data).busy() or editor_ai_for(storage()).busy(), 'editorAiBusy':editor_ai_for(storage()).busy(),
                                      'pythonVersion': sys.version.split()[0], 'pythonExecutable': sys.executable, 'pid': os.getpid(),'pagePreviewBusy':pages_for(storage()).busy()})
            if path == '/api/editor-ai/job':
                with LOCK:return self.send(editor_ai_for(storage()).status(ROOT,query.get('id',[None])[0]))
            if path == '/api/editor-ai/diff':
                with LOCK:return self.send(editor_ai_for(storage()).changes(ROOT,query.get('id',[''])[0],query.get('path',[''])[0]))
            if path == '/api/editor-ai/preview.pdf':
                with LOCK:return self.file(editor_ai_for(storage()).preview(ROOT,query.get('id',[''])[0]))
            if path == '/api/editor-ai/effects':
                with LOCK:return self.send(editor_ai_for(storage()).effects(ROOT,query.get('id',[''])[0]))
            if path == '/api/editor-ai/effect-image':
                return self.file(editor_ai_for(storage()).effect_image(ROOT,query.get('id',[''])[0],query.get('which',[''])[0],query.get('page',['1'])[0]))
            if path == '/api/ai/config':
                return self.send(assistant_for(storage().data).config())
            if path == '/api/ai/readiness':
                with LOCK:return self.send(pages_for(storage()).readiness(ROOT,STATE['main'],current_preview()))
            if path in {'/api/ai/tasks','/api/ai/task'}:
                with LOCK:
                    live=assistant_for(storage().data).status(project_id(ROOT));manager=pages_for(storage())
                    if path.endswith('/tasks'):return self.send(manager.task_list(ROOT,current_preview(),live))
                    return self.send(manager.describe_task(query.get('id',[''])[0],ROOT,current_preview(),live))
            if path in {'/api/ai/page-focus','/api/ai/focus-image'}:
                from studio_change_focus import focus,image
                manager=pages_for(storage());ident=query.get('id',[''])[0];index=int(query.get('index',['-1'])[0]);key=query.get('key',[None])[0];preview=query.get('preview',[None])[0]
                if path.endswith('page-focus'):return self.send(focus(manager,ident,ROOT,index,key,preview))
                return self.file(image(manager,ident,ROOT,query.get('which',[''])[0],index,key,preview))
            if path in {'/api/ai/page-preview','/api/ai/page-image','/api/ai/page-context'}:
                if context and context!=project_id(ROOT):raise ValueError('项目已切换，请重新关联当前页')
                ident=query.get('id',[''])[0]
                if path.endswith('page-context'):return self.send(pages_for(storage()).context(ident,ROOT))
                if path.endswith('page-preview'):return self.send(pages_for(storage()).status(ident,ROOT))
                return self.file(pages_for(storage()).image(ident,ROOT,query.get('which',[''])[0],query.get('page',[None])[0]))
            if path == '/api/review/glossary':
                return self.send(glossary_get(storage().data, project_id(ROOT)))
            if path == '/api/review/health':
                import importlib.util
                return self.send({'pdfAnalysis':bool(importlib.util.find_spec('pdfplumber')), 'pageRendering':bool(poppler_exe() or importlib.util.find_spec('pypdfium2')),
                                  'providers':assistant_for(storage().data).config(), 'build':SERVER_BUILD})
            if path == '/api/review/page':
                with LOCK:
                    image = page_image(current_preview(), storage().data, project_id(ROOT), query.get('page',['1'])[0], query.get('version',['0'])[0])
                    return self.file(image)
            if path == '/api/review/document':
                from pypdf import PdfReader
                with LOCK:
                    preview=current_preview()
                    return self.send({'projectId':project_id(ROOT),'pdfVersion':str(preview.stat().st_mtime_ns) if preview.exists() else None,
                                      'totalPages':len(PdfReader(preview).pages) if preview.exists() else 0})
            if path == '/api/ai/job':
                if context and context != project_id(ROOT):
                    return self.send({'error': '当前项目已切换，请重新打开所需项目'}, 409)
                return self.send(assistant_for(storage().data).status(project_id(ROOT), query.get('id', [None])[0]))
            if path == '/api/overview':
                return self.send({**storage().describe(), 'current': {'id': project_id(ROOT), 'root': str(ROOT), 'main': STATE['main'], 'name': ROOT.name}})
            if path == '/api/packages':
                return self.send(packages_for(storage()).catalog(query.get('query', [''])[0], query.get('filter', ['all'])[0], query.get('page', ['0'])[0]))
            if path == '/api/packages/job':
                return self.send(packages_for(storage()).status())
            if path == '/api/packages/analyze':
                sources = [(f['path'], project_path(f['path']).read_text(encoding='utf-8-sig', errors='ignore'))
                           for f in tree() if f['path'].endswith('.tex') and f['size'] < 2_000_000][:200]
                return self.send(packages_for(storage()).analyze(sources))
            if path == '/api/file':
                name = query.get('path', [''])[0]
                p = project_path(name)
                if p.suffix.lower() not in TEXT:
                    raise ValueError('请通过素材预览打开此文件')
                data = p.read_bytes()
                return self.send({'path': name, 'content': data.decode('utf-8-sig'), 'revision': digest(data)})
            if path == '/api/updates':
                return self.send(updates_for(storage()).status())
            if path == '/api/ai/usage':
                return self.send(usage_for(storage().data).status())
            if path == '/api/sync-point':
                with LOCK:return self.send(locate(ROOT,storage().data,current_preview(),{k:v[0] for k,v in query.items()}))
            if path == '/api/history':
                p = project_path(query.get('path', [''])[0])
                folder = storage().history_folder(ROOT, p.relative_to(ROOT))
                entries = sorted((f.name for f in folder.iterdir()), reverse=True) if folder.exists() else []
                return self.send(entries)
            if path == '/api/history-content':
                p = project_path(query.get('path', [''])[0])
                version = query.get('version', [''])[0]
                if not re.fullmatch(r'\d{8}-\d{6}-\d+', version):
                    raise ValueError('版本无效')
                data = (storage().history_folder(ROOT, p.relative_to(ROOT)) / version).read_text(encoding='utf-8-sig')
                return self.send({'content': data})
            if path == '/preview.pdf':
                return self.file(current_preview())
            if path.startswith('/project/'):
                return self.file(project_path(path.removeprefix('/project/')))
            if path.startswith('/vendor/'):
                target = (APP / path.lstrip('/')).resolve()
                if not target.is_relative_to((APP / 'vendor').resolve()):
                    raise ValueError('无效路径')
                return self.file(target)
            target = (APP / 'web' / ('index.html' if path == '/' else path.lstrip('/'))).resolve()
            if not target.is_relative_to((APP / 'web').resolve()):
                raise ValueError('无效路径')
            return self.file(target)
        except FileNotFoundError:
            self.send({'error': '找不到文件'}, 404)
        except Exception as exc:
            self.send({'error': str(exc)}, 400)

    def file(self, path):
        mime = {'.woff2': 'font/woff2', '.mjs': 'text/javascript', '.js': 'text/javascript', '.css': 'text/css',
                '.ftl': 'text/plain', '.wasm': 'application/wasm'}.get(path.suffix, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        if mime.startswith('text/') or mime in {'application/javascript', 'application/json'}:
            mime += '; charset=utf-8'
        self.send(path.read_bytes(), mime=mime)

    def do_POST(self):
        global PROCESS
        try:
            if not self.local_request() or not self.authorized():
                return self.send({'error': '会话验证失败'}, 403)
            length = int(self.headers.get('Content-Length', '0'))
            if length < 0 or length > MAX_BODY:
                return self.send({'error': '文件过大，单次上限 18 MB'}, 413)
            data = json.loads(self.rfile.read(length))
            route = urlsplit(self.path).path
            if route == '/api/shutdown':
                with LOCK:
                    require_idle()
                    self.send({'ok': True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            context = self.headers.get('X-Studio-Project')
            if context and context != project_id(ROOT) and (route.startswith(('/api/ai/', '/api/review/','/api/editor-ai/')) or route in {'/api/history-checkpoint','/api/save','/api/create','/api/upload','/api/rename','/api/delete','/api/compile','/api/search'}):
                return self.send({'error': '项目已在其他窗口切换，未覆盖任何文件。请先保存副本，再重新打开项目。'}, 409)
            if route == '/api/updates/settings':
                return self.send(updates_for(storage()).configure(data))
            if route == '/api/updates/check':
                return self.send(updates_for(storage()).check())
            if route == '/api/updates/download':
                return self.send(updates_for(storage()).download())
            if route == '/api/updates/install':
                with LOCK:
                    require_idle()
                    result=updates_for(storage()).install();self.send(result)
                    threading.Thread(target=self.server.shutdown,daemon=True).start();return
            if route == '/api/ai/usage':
                return self.send(usage_for(storage().data).configure(data.get('limit')))
            if route == '/api/history-checkpoint':
                with LOCK:
                    p=project_path(data.get('path',''))
                    if p.suffix.lower() not in TEXT:raise ValueError('此文件不能创建文本版本')
                    if data.get('revision')!=digest(p.read_bytes()):raise ValueError('文件已变化，请重新保存后创建版本')
                    snapshot(p);return self.send({'ok':True})
            if route == '/api/editor-ai/start':
                with LOCK:
                    require_idle()
                    main=data.get('main') or STATE['main'];project_path(main)
                    return self.send(editor_ai_for(storage()).start(ROOT,main,data,STATE['lines'] if STATE['success'] is False else []))
            if route == '/api/editor-ai/cancel':
                with LOCK:return self.send(editor_ai_for(storage()).cancel(ROOT,data.get('id')))
            if route in {'/api/editor-ai/apply','/api/editor-ai/undo'}:
                with LOCK:
                    require_idle()
                    return self.send(editor_ai_for(storage()).apply(ROOT,data.get('id'),route.endswith('/undo'),snapshot))
            if route == '/api/ai/config':
                return self.send(assistant_for(storage().data).configure(data))
            if route == '/api/ai/start':
                with LOCK:
                    if editor_ai_for(storage()).busy():raise ValueError('编辑器 AI 正在处理，请先等待或停止')
                    attachments = None
                    on_result = None
                    on_progress = None
                    on_finish = None
                    bound_context = None
                    if data.get('task') == 'pages_edit':
                        require_idle();manager=pages_for(storage());ident=data.get('pageContext','');page_root=ROOT
                        parts,attachments=manager.batch_input(ident,page_root,current_preview(),data.get('retryPages'))
                        session=manager._session(ident,page_root)
                        on_result=lambda result:manager.attach_batch(ident,page_root,result)
                        on_progress=lambda result:manager.attach_batch(ident,page_root,result)
                        data={**data,'text':'审阅所选 PDF 页面','provider':'deepseek','parts':parts,
                              'allParts':[{k:p[k] for k in ('part','page','path')} for p in session['parts']],
                              'documentContext':session.get('documentContext',{}),'wholeDocument':session.get('wholeDocument',False),
                              'globalReview':(session.get('result') or {}).get('globalReview') if data.get('retryPages') is not None else None,
                              'seedPageStates':(session.get('result') or {}).get('pageStates',[]) if data.get('retryPages') is not None else []}
                        bound_context=ident
                    elif data.get('task') == 'page_edit':
                        require_idle()
                        text,attachments=pages_for(storage()).ai_input(data.get('pageContext',''),ROOT,current_preview())
                        ident=data['pageContext'];page_root=ROOT;manager=pages_for(storage())
                        on_result=lambda result:manager.attach(ident,page_root,result['edits'],result)
                        data={**data,'text':text,'provider':'deepseek'}
                        bound_context=ident
                    elif data.get('sourceContext'):
                        require_idle()
                        if data.get('task') not in {'check','correct','format','polish','translate','dictionary','workflow'}:raise ValueError('无效的源码任务')
                        manager=pages_for(storage());ident=data['sourceContext'];page_root=ROOT
                        text=manager.source_input(ident,ROOT,current_preview())
                        def source_result(result):
                            result['pageContext']=ident
                            manager.attach(ident,page_root,result.get('edits',[]),result)
                        on_result=source_result
                        data={**data,'text':text,'scope':'selection'}
                        bound_context=ident
                    elif data.get('task') == 'layout':
                        from pypdf import PdfReader
                        preview = current_preview()
                        if not preview.exists():
                            raise ValueError('请先成功编译 PDF')
                        version = int(data.get('pdfVersion',0))
                        if preview.stat().st_mtime_ns != version:
                            raise ValueError('PDF 已更新，请重新载入版面检查')
                        pages = parse_pages(data.get('pages',''),len(PdfReader(preview).pages),3)
                        attachments = [{'page':n,'image':'data:image/png;base64,'+base64.b64encode(page_image(preview,storage().data,project_id(ROOT),n,version).read_bytes()).decode('ascii')} for n in pages]
                        data = {**data,'text':'审阅所选 PDF 页面','provider':'deepseek'}
                    if bound_context:on_finish=lambda job:manager.finish_job(bound_context,page_root,job)
                    job=assistant_for(storage().data).start(data, project_id(ROOT), attachments,on_result,on_progress,on_finish)
                    if bound_context:manager.bind_job(bound_context,page_root,job,data)
                    return self.send(job)
            if route == '/api/ai/task-view':
                with LOCK:return self.send(pages_for(storage()).save_view(data.get('id'),ROOT,data.get('view',{})))
            if route == '/api/ai/task-rebase':
                with LOCK:
                    require_idle();manager=pages_for(storage())
                    return self.send(manager.rebase(data.get('id'),ROOT,STATE['main'],current_preview(),data.get('selected')))
            if route == '/api/ai/page-prepare':
                with LOCK:
                    require_idle()
                    return self.send(pages_for(storage()).prepare(ROOT,STATE['main'],current_preview(),data.get('page',1),data.get('path')))
            if route == '/api/ai/pages-prepare':
                with LOCK:
                    require_idle()
                    return self.send(pages_for(storage()).prepare_pages(ROOT,STATE['main'],current_preview(),data.get('pages'),bool(data.get('wholeDocument'))))
            if route == '/api/ai/source-prepare':
                with LOCK:
                    require_idle()
                    return self.send(pages_for(storage()).prepare_source(ROOT,STATE['main'],current_preview(),data.get('path'),data.get('start'),data.get('end')))
            if route == '/api/ai/page-preview':
                with LOCK:
                    require_idle()
                    return self.send(pages_for(storage()).preview(data['id'],ROOT,current_preview(),data.get('selected')))
            if route in {'/api/ai/page-apply','/api/ai/page-undo'}:
                with LOCK:
                    require_idle();undo=route.endswith('page-undo')
                    changes,session=pages_for(storage()).apply_files(data.get('id'),ROOT,current_preview(),data.get('previewId'),undo,data.get('selected'))
                    for target,_ in changes:snapshot(target)
                    atomic_write_set(changes)
                    session['appliedHash']=None if undo else digest(changes[0][1])
                    session['appliedHashes']={} if undo else {target.relative_to(ROOT).as_posix():digest(content) for target,content in changes}
                    if undo:
                        session['undone']=True
                        session['preview']={}
                    pages_for(storage()).remember(session)
                    return self.send({'ok':True,'path':changes[0][0].relative_to(ROOT).as_posix(),'files':[p.relative_to(ROOT).as_posix() for p,_ in changes],'revision':digest(changes[0][1]),'page':session['page']})
            if route == '/api/review/glossary':
                with LOCK:
                    return self.send(glossary_save(storage().data, project_id(ROOT), data))
            if route == '/api/review/selftest':
                return self.send(selftest())
            if route == '/api/review/references':
                with LOCK:
                    sources = {}
                    total = 0
                    overlays = data.get('sources',{})
                    if not isinstance(overlays,dict):
                        raise ValueError('编辑器内容格式无效')
                    for item in tree():
                        if Path(item['path']).suffix.lower() in {'.tex','.bib'}:
                            if item['size'] > 2_000_000 or len(sources)>=300:
                                raise ValueError('文本文件超过检查上限，请拆分项目')
                            content = overlays.get(item['path'])
                            if content is None:
                                content = project_path(item['path']).read_text(encoding='utf-8-sig',errors='replace')
                            if not isinstance(content,str):
                                raise ValueError('编辑器文本格式无效')
                            total += len(content)
                            if total>8_000_000:
                                raise ValueError('项目文本超过 800 万字符，无法一次检查')
                            sources[item['path']] = content
                    return self.send({**analyze_references(sources, STATE['main']), 'projectId':project_id(ROOT)})
            if route == '/api/review/layout':
                with LOCK:
                    preview = current_preview()
                    if not preview.exists():
                        raise ValueError('请先成功编译 PDF')
                    version, project = preview.stat().st_mtime_ns, project_id(ROOT)
                    pdf_path = str(preview)
                result = subprocess.run([sys.executable,str(APP/'studio_review.py'),'--pdf',pdf_path,'--pages',str(data.get('pages','all'))],
                                        capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=60,
                                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:
                    report = json.loads(result.stdout)
                except (ValueError,TypeError):
                    raise ValueError('PDF 分析器未能启动，请检查 pdfplumber 环境')
                if report.get('error'):
                    raise ValueError(report['error'])
                with LOCK:
                    if project != project_id(ROOT) or not preview.exists() or preview.stat().st_mtime_ns != version:
                        raise ValueError('项目或 PDF 已变化，请重新检查')
                return self.send({**report,'pdfVersion':str(version),'projectId':project})
            if route == '/api/ai/cancel':
                assistant_for(storage().data).cancel(project_id(ROOT), data.get('id'))
                return self.send({'ok': True})
            if route == '/api/storage/locations':
                with LOCK:
                    require_idle()
                    store=storage();store.configure_locations(data.get('projects'),data.get('cache'))
                    pages_for(store).sessions.clear()
                    editor_ai_for(store).sessions.clear()
                    select_project(store.active_project())
                    return self.send(store.describe())
            if route == '/api/projects/open':
                with LOCK:
                    require_idle()
                chosen = data.get('path', '')
                if data.get('pick'):
                    result = subprocess.run([sys.executable, str(APP / 'select_project.py')], capture_output=True, text=True,
                                            encoding='utf-8', errors='replace', timeout=180,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if result.returncode:
                        raise ValueError('文件选择器无法启动；也可以直接输入 .tex 文件的完整路径')
                    chosen = json.loads(result.stdout)['path']
                if not chosen:
                    return self.send({'cancelled': True})
                with LOCK:
                    require_idle()
                    return self.send(select_project(storage().open_project(chosen)))
            if route == '/api/projects/import':
                with LOCK:
                    require_idle()
                    entry = storage().import_project(data.get('name', '导入项目'), data.get('files'), data.get('main'))
                    return self.send(select_project(entry))
            if route == '/api/projects/new':
                with LOCK:
                    require_idle()
                    return self.send(select_project(storage().create_project(data.get('name', '新项目'), data.get('template', 'minimal'))))
            if route == '/api/projects/forget':
                storage().forget_project(data.get('id'))
                return self.send({'ok': True})
            if route == '/api/packages/action':
                with LOCK:
                    if editor_ai_for(storage()).busy():raise ValueError('编辑器 AI 正在处理，请先等待或停止')
                    if pages_for(storage()).busy():raise ValueError('请等待修改效果预览编译完成后再处理宏包')
                    if STATE['running']:
                        raise ValueError('正在编译，请等待完成后再修改宏包缓存')
                    return self.send(packages_for(storage()).start(data.get('action'), data.get('names', [])))
            if route == '/api/packages/cancel':
                packages_for(storage()).cancel()
                return self.send({'ok': True})
            if route == '/api/preview-event':
                event = {'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                         'event': str(data.get('event', 'error'))[:80],
                         'message': str(data.get('message', ''))[:2000],
                         'browser': self.headers.get('User-Agent', '')[:300]}
                storage().data.mkdir(parents=True, exist_ok=True)
                with (storage().data / 'preview-errors.log').open('a', encoding='utf-8') as output:
                    output.write(json.dumps(event, ensure_ascii=False) + '\n')
                return self.send({'ok': True})
            if route in {'/api/save', '/api/create', '/api/upload'}:
                p = project_path(data['path'], write=True)
                with LOCK:
                    if route == '/api/save':
                        if p.suffix.lower() not in TEXT:
                            raise ValueError('此文件不能作为文本编辑')
                        old = p.read_bytes()
                        if data.get('revision') != digest(old):
                            return self.send({'error': '文件已被其他程序修改。请重新载入或另存为，避免覆盖外部改动。'}, 409)
                        content = data['content'].encode('utf-8')
                        if content == old:
                            return self.send({'revision': digest(old)})
                        snapshot(p)
                    else:
                        if p.exists():
                            raise ValueError('同名文件已经存在，请换一个名称')
                        content = base64.b64decode(data['content'], validate=True) if route == '/api/upload' else data.get('content', '').encode('utf-8')
                    p.parent.mkdir(parents=True, exist_ok=True)
                    temp = p.with_name(p.name + '.studio-tmp')
                    temp.write_bytes(content)
                    os.replace(temp, p)
                return self.send({'revision': digest(content)})
            if route == '/api/rename':
                with LOCK:
                    old, new = project_path(data['path'], True), project_path(data['newPath'], True)
                    if new.exists():
                        raise ValueError('目标文件已经存在')
                    snapshot(old)
                    new.parent.mkdir(parents=True, exist_ok=True)
                    old.rename(new)
                return self.send({'ok': True})
            if route == '/api/delete':
                p = project_path(data['path'], True)
                if p.name == 'report.tex' and p.parent == ROOT:
                    raise ValueError('主文档 report.tex 不能删除')
                with LOCK:
                    snapshot(p)
                    p.unlink()
                return self.send({'ok': True})
            if route == '/api/compile':
                main = data.get('main', 'report.tex')
                p = project_path(main)
                if not p.is_file() or p.suffix.lower() != '.tex':
                    raise ValueError('请选择有效的 .tex 主文档')
                with LOCK:
                    if pages_for(storage()).busy():raise ValueError('请等待修改效果预览编译完成')
                    if editor_ai_for(storage()).busy():raise ValueError('编辑器 AI 正在处理，请先等待或停止')
                    if package_busy():
                        raise ValueError('宏包任务尚未完成，请等待后再编译')
                    if STATE['running']:
                        return self.send({'error': '编译正在进行'}, 409)
                    STATE.update(running=True, job=STATE['job'] + 1, lines=[], success=None,
                                 main=main, started=time.time(), diagnostics=[], duration=0)
                    storage().record_project(ROOT, main)
                    threading.Thread(target=compile_job, args=(main, bool(data.get('offline')), STATE['job']), daemon=True).start()
                return self.send({'ok': True})
            if route == '/api/cancel':
                with LOCK:
                    if PROCESS and PROCESS.poll() is None:
                        PROCESS.terminate()
                return self.send({'ok': True})
            if route == '/api/search':
                term = data.get('query', '')
                if not term:
                    return self.send([])
                pattern = re.compile(term if data.get('regex') else re.escape(term), 0 if data.get('case') else re.I)
                results = []
                for item in tree():
                    if not item['editable'] or item['size'] > 2_000_000:
                        continue
                    try:
                        lines = project_path(item['path']).read_text(encoding='utf-8-sig').splitlines()
                    except UnicodeError:
                        continue
                    for i, line in enumerate(lines):
                        match = pattern.search(line)
                        if match:
                            results.append({'path': item['path'], 'line': i + 1, 'column': match.start() + 1,
                                            'text': line[:400], 'before': lines[i - 1][:250] if i else '',
                                            'after': lines[i + 1][:250] if i + 1 < len(lines) else ''})
                            if len(results) >= 300:
                                return self.send(results)
                return self.send(results)
            return self.send({'error': 'Unknown operation'}, 404)
        except FileNotFoundError:
            self.send({'error': '文件不存在'}, 404)
        except Exception as exc:
            self.send({'error': str(exc)}, 400)


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8808)
    args = parser.parse_args()
    # The launcher reuses an existing server instead of spawning another one.
    for port in range(args.port, args.port + 20):
        try:
            server = StudioHTTPServer(('127.0.0.1', port), Handler)
            break
        except OSError:
            continue
    else:
        raise RuntimeError('没有可用的本地端口')
    entry = storage().active_project()
    ROOT = Path(entry['root'])
    STATE['main'] = entry['main']
    seed_preview()
    url = f'http://127.0.0.1:{server.server_port}/?token={TOKEN}'
    storage().data.mkdir(parents=True, exist_ok=True)
    (storage().data / 'runtime.json').write_text(json.dumps({'url': url, 'pid': os.getpid(), 'port': server.server_port, 'app': str(APP), 'home': str(storage().home),
                                                         'pythonVersion': sys.version.split()[0], 'pythonExecutable': sys.executable}), encoding='utf-8')
    print(f'Local LaTeX Studio ready: http://127.0.0.1:{server.server_port}', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
