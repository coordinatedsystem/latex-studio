"""Regression for missing newly added application files in release payloads."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parent/'tools'))
from build_release import verify_app


class PayloadTests(unittest.TestCase):
    def test_missing_and_modified_new_module_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';app=root/'app'
            repo.mkdir();app.mkdir()
            for folder in ('web','vendor','assets'):(repo/folder).mkdir()
            names=('server.py','bootstrap_install.py','launch.ps1','Launch.vbs','version.json','README.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md','studio_terms.py','web/terms-desk.js')
            for name in names:
                for base in (repo,app):
                    (base/name).parent.mkdir(parents=True,exist_ok=True)
                    (base/name).write_text('fixture',encoding='utf8')
            self.assertEqual(verify_app(repo,app),len(names))
            (app/'studio_terms.py').unlink()
            with self.assertRaisesRegex(ValueError,'studio_terms'):verify_app(repo,app)
            (app/'studio_terms.py').write_text('stale',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'studio_terms'):verify_app(repo,app)
            (app/'studio_terms.py').write_text('fixture',encoding='utf8')
            (app/'web/terms-desk.js').unlink()
            with self.assertRaisesRegex(ValueError,'terms-desk'):verify_app(repo,app)
            (app/'web/terms-desk.js').write_text('fixture',encoding='utf8')
            (app/'stale.py').write_text('old module',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'unexpected'):verify_app(repo,app)
