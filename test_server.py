"""Meaningful workspace-operation checks; all mutations use an isolated temp project."""
import base64
import http.cookiejar
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import server


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_root, cls.original_app = server.ROOT, server.APP
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        cls.worker = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.worker.start()
        cls.base = 'http://127.0.0.1:' + str(cls.http.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.worker.join()
        server.ROOT, server.APP = cls.original_root, cls.original_app

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='latex-studio-test-')
        server.ROOT = Path(self.temp.name).resolve()
        server.APP = server.ROOT / 'latex-studio'
        server.APP.mkdir()
        (server.APP / 'web').mkdir()
        (server.APP / 'web' / 'index.html').write_text('<html>test</html>', encoding='utf-8')
        (server.ROOT / 'report.tex').write_text('第一行\n目标文字\n第三行\n', encoding='utf-8')
        (server.ROOT / 'code').mkdir()
        (server.ROOT / 'code' / 'demo.py').write_text('def target():\n    return 42\n', encoding='utf-8')
        jar = http.cookiejar.CookieJar()
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.client.open(self.base + '/?token=' + server.TOKEN).read()

    def tearDown(self):
        self.temp.cleanup()

    def call(self, route, data=None, origin=None):
        headers = {'Content-Type': 'application/json'}
        if origin:
            headers['Origin'] = origin
        req = urllib.request.Request(self.base + route, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            with self.client.open(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_save_revision_history_and_conflict(self):
        _, opened = self.call('/api/file?path=report.tex')
        status, saved = self.call('/api/save', {'path': 'report.tex', 'content': '新内容\n', 'revision': opened['revision']})
        self.assertEqual(status, 200)
        self.assertEqual((server.ROOT / 'report.tex').read_text(encoding='utf-8'), '新内容\n')
        _, versions = self.call('/api/history?path=report.tex')
        self.assertEqual(len(versions), 1)
        _, history = self.call('/api/history-content?path=report.tex&version=' + versions[0])
        self.assertIn('目标文字', history['content'])
        status, _ = self.call('/api/save', {'path': 'report.tex', 'content': '覆盖', 'revision': opened['revision']})
        self.assertEqual(status, 409)
        self.assertEqual((server.ROOT / 'report.tex').read_text(encoding='utf-8'), '新内容\n')
        self.call('/api/save', {'path': 'report.tex', 'content': '新内容\n', 'revision': saved['revision']})
        _, versions = self.call('/api/history?path=report.tex')
        self.assertEqual(len(versions), 1, 'Unchanged saves should not consume history slots')

    def test_ai_routes_are_authenticated_scoped_and_do_not_write_source(self):
        original = (server.ROOT / 'report.tex').read_bytes()
        status, config = self.call('/api/ai/config')
        self.assertEqual(status, 200)
        self.assertFalse(config['deepseek']['configured'])
        status, started = self.call('/api/ai/start', {'text':'test  \n','provider':'local','task':'check','scope':'file'})
        self.assertEqual(status, 200)
        import time
        for _ in range(50):
            _, job = self.call('/api/ai/job?id=' + started['id'])
            if not job['running']:
                break
            time.sleep(.01)
        self.assertTrue(job['success'])
        self.assertEqual((server.ROOT / 'report.tex').read_bytes(), original)
        req = urllib.request.Request(self.base + '/api/ai/start', data=json.dumps({'text':'test'}).encode(), headers={'Content-Type':'application/json', 'X-Studio-Project':'other-project'})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.client.open(req)
        self.assertEqual(caught.exception.code, 409)

    def test_editor_ai_endpoints_require_authentication_and_current_project(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(self.base+'/api/editor-ai/job')
        self.assertEqual(caught.exception.code,401)
        for route in ['/api/editor-ai/job','/api/editor-ai/diff?id=bad&path=report.tex','/api/editor-ai/preview.pdf?id=bad']:
            request=urllib.request.Request(self.base+route,headers={'X-Studio-Project':'other'})
            with self.assertRaises(urllib.error.HTTPError) as caught:self.client.open(request)
            self.assertEqual(caught.exception.code,409)
        for route in ['start','apply','undo','cancel']:
            request=urllib.request.Request(self.base+'/api/editor-ai/'+route,data=b'{}',headers={'Content-Type':'application/json','X-Studio-Project':'other'})
            with self.assertRaises(urllib.error.HTTPError) as caught:self.client.open(request)
            self.assertEqual(caught.exception.code,409)
        original=(server.ROOT/'report.tex').read_bytes()
        status,_=self.call('/api/editor-ai/start',{'main':'../external.tex','mode':'repair'})
        self.assertEqual(status,400);self.assertEqual((server.ROOT/'report.tex').read_bytes(),original)

    def test_external_change_rejects_stale_save(self):
        _, opened = self.call('/api/file?path=report.tex')
        (server.ROOT / 'report.tex').write_text('外部修改', encoding='utf-8')
        status, _ = self.call('/api/save', {'path': 'report.tex', 'content': '旧编辑器内容', 'revision': opened['revision']})
        self.assertEqual(status, 409)
        self.assertEqual((server.ROOT / 'report.tex').read_text(encoding='utf-8'), '外部修改')

    def test_state_reports_the_actual_python_runtime(self):
        status, state = self.call('/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(state['pythonVersion'], server.sys.version.split()[0])
        self.assertEqual(state['pythonExecutable'], server.sys.executable)
        self.assertGreaterEqual(tuple(map(int, state['pythonVersion'].split('.')[:2])), (3,10))

    def test_live_service_port_cannot_be_bound_twice(self):
        first = server.StudioHTTPServer(('127.0.0.1',0), server.Handler)
        try:
            with self.assertRaises(OSError):
                duplicate = server.StudioHTTPServer(first.server_address, server.Handler)
                duplicate.server_close()
        finally:
            first.server_close()

    def test_project_review_uses_unsaved_overlays_and_scopes_glossary(self):
        previous=server.STATE['main']
        server.STATE['main']='report.tex'
        try:
            (server.ROOT/'part.tex').write_text('\\label{target}',encoding='utf-8')
            status,result=self.call('/api/review/references',{'sources':{'report.tex':'\\input{part}\\ref{target}'}})
            self.assertEqual(status,200)
            self.assertEqual(result['issues'],[])
            self.assertEqual(result['labels'],1)
            self.assertNotIn('input',(server.ROOT/'report.tex').read_text(encoding='utf-8'))
            _,initial=self.call('/api/review/glossary')
            status,saved=self.call('/api/review/glossary',{'terms':[{'source':'测试','target':'test','note':''}],'revision':initial['revision']})
            self.assertEqual(status,200)
            self.assertEqual(saved['terms'][0]['target'],'test')
            status,_=self.call('/api/review/glossary',{'terms':[],'revision':initial['revision']})
            self.assertEqual(status,400)
            request=urllib.request.Request(self.base+'/api/review/glossary',headers={'X-Studio-Project':'other-project'})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.client.open(request)
            self.assertEqual(caught.exception.code,409)
        finally:
            server.STATE['main']=previous

    def test_visual_and_probe_requests_fail_clearly_without_pdf_or_keys(self):
        status,result=self.call('/api/ai/start',{'task':'layout','provider':'deepseek','pages':'1','pdfVersion':'0'})
        self.assertEqual(status,400)
        self.assertIn('PDF',result['error'])
        status,result=self.call('/api/ai/start',{'task':'probe','provider':'deepseek'})
        self.assertEqual(status,400)
        self.assertIn('密钥',result['error'])

    def test_search_context_regex_and_invalid_regex(self):
        status, found = self.call('/api/search', {'query': '目标文字'})
        self.assertEqual(status, 200)
        self.assertEqual(found[0]['line'], 2)
        self.assertEqual(found[0]['before'], '第一行')
        self.assertEqual(found[0]['after'], '第三行')
        _, found = self.call('/api/search', {'query': r'def\s+target', 'regex': True})
        self.assertEqual(found[0]['path'], 'code/demo.py')
        status, _ = self.call('/api/search', {'query': '[', 'regex': True})
        self.assertEqual(status, 400)

    def test_create_rename_delete_upload_and_main_protection(self):
        self.assertEqual(self.call('/api/create', {'path': 'code/new.py', 'content': '# 新建\n'})[0], 200)
        self.assertEqual(self.call('/api/create', {'path': 'code/new.py', 'content': ''})[0], 400)
        self.assertEqual(self.call('/api/rename', {'path': 'code/new.py', 'newPath': 'code/moved.py'})[0], 200)
        self.assertTrue((server.ROOT / 'code/moved.py').exists())
        self.assertEqual(self.call('/api/delete', {'path': 'code/moved.py'})[0], 200)
        self.assertFalse((server.ROOT / 'code/moved.py').exists())
        self.assertEqual(self.call('/api/delete', {'path': 'report.tex'})[0], 400)
        raw = b'\x89PNG\r\n\x1a\n'
        self.assertEqual(self.call('/api/upload', {'path': 'figures/example.png', 'content': base64.b64encode(raw).decode()})[0], 200)
        self.assertEqual((server.ROOT / 'figures/example.png').read_bytes(), raw)

    def test_paths_and_request_boundaries(self):
        for path in ['../outside.tex', 'latex-portable/cache/file.tex', '.git/config.tex', 'build/a.tex', 'latex-studio/server.py', 'C:/outside.tex']:
            self.assertEqual(self.call('/api/create', {'path': path, 'content': 'x'})[0], 400, path)
        self.assertEqual(self.call('/api/create', {'path': 'evil.tex'}, origin='https://foreign.example')[0], 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.base + '/api/file?path=report.tex')
        self.assertEqual(ctx.exception.code, 401)
        self.assertFalse((server.ROOT / 'evil.tex').exists())

    def test_failed_compile_keeps_last_successful_preview(self):
        (server.APP / 'preview.pdf').write_bytes(b'previous-success')
        server.STATE.update(running=True, lines=[], success=None, job=99)
        server.compile_job('report.tex', True, 99)  # Isolated project has no compiler.
        self.assertFalse(server.STATE['running'])
        self.assertFalse(server.STATE['success'])
        self.assertEqual((server.APP / 'preview.pdf').read_bytes(), b'previous-success')
        self.assertFalse(list((server.ROOT / 'build').glob('studio-*')))

    def test_session_token_survives_restart_and_migrates_existing_session(self):
        old_token = 'test-existing-local-session-' + 'x' * 20
        (server.APP / 'runtime.json').write_text(json.dumps({'url': 'http://127.0.0.1:8808/?token=' + old_token}), encoding='utf-8')
        self.assertEqual(server.load_session_token(server.APP), old_token)
        (server.APP / 'runtime.json').unlink()
        self.assertEqual(server.load_session_token(server.APP), old_token)

    def test_pdf_response_and_preview_failure_diagnostics(self):
        raw = b'%PDF-1.5\npreview-test'
        (server.APP / 'preview.pdf').write_bytes(raw)
        with self.client.open(self.base + '/preview.pdf?v=123') as response:
            self.assertEqual(response.headers['Content-Type'], 'application/pdf')
            self.assertEqual(response.read(), raw)
        status, _ = self.call('/api/preview-event', {'event': 'viewer-error', 'message': 'worker test failure'})
        self.assertEqual(status, 200)
        self.assertIn('worker test failure', (server.storage().data / 'preview-errors.log').read_text(encoding='utf-8'))
        self.assertEqual(self.call('/api/state')[1]['serverBuild'], server.SERVER_BUILD)

    def test_import_api_preserves_original_and_rejects_old_project_writes(self):
        original_root = server.ROOT
        _, before = self.call('/api/state')
        content = '\\documentclass{article}\n\\begin{document}Hello\\end{document}'
        status, opened = self.call('/api/projects/import', {'name': 'Imported', 'files': [
            {'path': 'main.tex', 'content': base64.b64encode(content.encode()).decode()}]})
        self.assertEqual(status, 200)
        self.assertEqual(opened['main'], 'main.tex')
        self.assertNotEqual(server.ROOT, original_root)
        self.assertTrue((original_root / 'report.tex').exists())
        self.assertFalse(self.call('/api/state')[1]['hasPdf'])
        request = urllib.request.Request(self.base + '/api/save', data=json.dumps({'path': 'main.tex', 'content': 'wrong project'}).encode(),
            headers={'Content-Type': 'application/json', 'X-Studio-Project': before['projectId']})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.client.open(request)
        self.assertEqual(ctx.exception.code, 409)
        self.assertEqual((server.ROOT / 'main.tex').read_text(encoding='utf-8'), content)


if __name__ == '__main__':
    unittest.main(verbosity=2)
