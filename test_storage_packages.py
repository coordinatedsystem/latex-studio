"""Project isolation and package lifecycle regression tests; no live network."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from studio_storage import StudioStorage, project_id
from studio_packages import PackageManager


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-library-test-')
        self.root = Path(self.temp.name)
        self.app = self.root / 'latex-studio'
        self.app.mkdir()
        self.store = StudioStorage(self.app)

    def tearDown(self):
        self.temp.cleanup()

    def test_windows_bom_config_preserves_installed_home_and_project(self):
        home=self.root/'home';project=self.root/'original-project'
        (self.app/'installation.json').write_text(json.dumps({'home':str(home),'defaultProject':str(project)}),encoding='utf-8-sig')
        store=StudioStorage(self.app)
        self.assertTrue(store.installed);self.assertEqual(store.home,home);self.assertEqual(store.default_root,project)

    @staticmethod
    def file(path, value):
        return {'path': path, 'content': base64.b64encode(value).decode()}

    def test_import_keeps_assets_and_detects_main(self):
        files = [self.file('chapters/part.tex', b'Chapter text'),
                 self.file('main.tex', b'\\documentclass{article}\n\\input{chapters/part.tex}'),
                 self.file('figures/test.png', b'PNG-content'), self.file('run.exe', b'not imported')]
        result = self.store.import_project('Sample', files)
        root = Path(result['root'])
        self.assertEqual(result['main'], 'main.tex')
        self.assertEqual((root / 'figures/test.png').read_bytes(), b'PNG-content')
        self.assertTrue((root / 'chapters/part.tex').exists())
        self.assertFalse((root / 'run.exe').exists())
        self.assertEqual(result['skipped'], ['run.exe'])
        self.assertEqual(self.store.settings()['active']['id'], project_id(root))

    def test_bad_paths_and_case_collisions_leave_no_partial_import(self):
        for name in ['../escape.tex', '/escape.tex', 'C:/escape.tex', '.git/evil.tex']:
            with self.assertRaises(ValueError):
                self.store.import_project('bad', [self.file(name, b'bad')])
        with self.assertRaises(ValueError):
            self.store.import_project('duplicate', [self.file('main.tex', b'a'), self.file('MAIN.tex', b'b')])
        self.assertEqual(list(self.store.projects.iterdir()), [])

    def test_project_paths_do_not_share_history_or_preview(self):
        a = self.store.create_project('A')
        b = self.store.create_project('B', 'report')
        self.assertNotEqual(self.store.preview_path(a['root']), self.store.preview_path(b['root']))
        self.assertNotEqual(self.store.history_folder(a['root'], Path('main.tex')), self.store.history_folder(b['root'], Path('main.tex')))
        self.assertIn('\\section{', (Path(b['root']) / 'main.tex').read_text(encoding='utf-8'))
        self.assertEqual(self.store.open_project(str(Path(a['root']) / 'main.tex'))['id'], a['id'])


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-package-test-')
        self.root = Path(self.temp.name)
        self.app = self.root / 'latex-studio'
        self.app.mkdir()
        self.store = StudioStorage(self.app)
        self.ident = 'a' * 64
        data = self.store.tex_cache/'bundles/data'
        cache = data / self.ident
        cache.mkdir(parents=True)
        self.values = {'SHA256SUM': self.ident.encode(), 'demo.sty': b'\\RequirePackage{helper}\n',
                       'helper.sty': b'helper resources\n', 'article.cls': b'core class\n'}
        self.ranges = {}
        lines = []
        for i, (name, value) in enumerate(self.values.items()):
            offset = i * 1000
            self.ranges[(offset, len(value))] = value
            lines.append(f'{name} {offset} {len(value)}')
        (data / (self.ident + '.index')).write_text('\n'.join(lines), encoding='utf-8')
        (data / 'bundle.prefetch').write_text('article.cls\n', encoding='utf-8')
        (cache / 'article.cls').write_bytes(self.values['article.cls'])
        self.manager = PackageManager(self.store)
        self.manager._range = lambda start, size: self.ranges[(start, size)]
        self.manager._probe = lambda name, touched: (True, 'Offline validation passed')

    def tearDown(self):
        self.temp.cleanup()

    def test_install_dependency_integrity_quarantine_and_restore(self):
        self.assertFalse(self.manager.catalog('demo')['items'][0]['cached'])
        self.manager._install('demo.sty')
        self.assertTrue((self.manager.cache / 'helper.sty').exists())
        self.assertTrue(self.manager.catalog('demo')['items'][0]['verified'])
        self.assertTrue(self.manager._check('demo.sty')['valid'])
        self.manager._remove('demo.sty')
        self.assertFalse((self.manager.cache / 'demo.sty').exists())
        self.assertTrue((self.manager.cache / 'helper.sty').exists(), 'Shared dependencies must remain available')
        self.assertTrue(self.manager.catalog('demo', 'removed')['items'][0]['removed'])
        self.manager._restore('demo.sty')
        self.assertEqual((self.manager.cache / 'demo.sty').read_bytes(), self.values['demo.sty'])
        self.assertIn('demo.sty', (self.manager.index_path.parent / 'bundle.prefetch').read_text())

    def test_detects_same_size_corruption_and_repairs_dependency(self):
        self.manager._install('demo.sty')
        resource = self.manager.cache / 'helper.sty'
        resource.write_bytes(b'x' * len(self.values['helper.sty']))
        self.assertFalse(self.manager._check('demo.sty')['valid'])
        self.manager._repair('demo.sty')
        self.assertEqual(resource.read_bytes(), self.values['helper.sty'])
        self.assertTrue(self.manager._check('demo.sty')['valid'])

    def test_cannot_remove_core_or_download_path_traversal(self):
        with self.assertRaises(ValueError):
            self.manager._remove('article.cls')
        with self.assertRaises(ValueError):
            self.manager.start('install', ['../file.sty'])

    def test_project_scan_distinguishes_cached_missing_and_custom(self):
        result = self.manager.analyze([('main.tex', '\\documentclass{article}\n\\usepackage{demo,custom}')])
        indexed = {r['name']: r for r in result}
        self.assertTrue(indexed['article.cls']['cached'])
        self.assertFalse(indexed['demo.sty']['cached'])
        self.assertFalse(indexed['custom.sty']['available'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
