import io,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from studio_updates import Updates,file_sha
from studio_version import VERSION

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name)
        self.up=Updates(SimpleNamespace(data=base/'data',cache=base/'cache',home=base/'home'))
        parts=list(map(int,VERSION.split('.')));parts[-1]+=1;next_version='.'.join(map(str,parts))
        self.body=b'MZmock installer';self.release={'version':next_version,'file':f'distribution/LaTeX-Studio-{next_version}-win64-Setup.exe','sha256':__import__('hashlib').sha256(self.body).hexdigest(),'size':len(self.body),'notes':'test'}
    def test_defaults_are_opt_in_and_credentials_not_exposed(self):
        value=self.up.status();self.assertFalse(value['automatic']);self.assertFalse(value['configured'])
        self.assertEqual(self.up.token(),'')
        with patch('studio_updates.seal',return_value='encrypted'):
            self.up.configure({'token':'mock-token','automatic':True})
        self.assertNotIn('mock-token',str(self.up.status()));self.assertNotIn('encrypted',str(self.up.status()))
    def test_manifest_rejects_external_paths_versions_and_missing_hash(self):
        for extra in [{'file':'../../setup.exe'},{'file':'https://evil.invalid/setup.exe'},{'version':'2.0.0-rc1'},{'sha256':''},{'size':101*1024*1024}]:
            with self.assertRaises(ValueError):self.up.validate({**self.release,**extra},'a'*40)
    def test_fixed_commit_check_returns_idle(self):
        with patch.object(self.up,'json',side_effect=[{'object':{'sha':'b'*40}},self.release]) as request:
            result=self.up.check()
        self.assertFalse(result['job']['running']);self.assertTrue(result['release']['available'])
        self.assertEqual(request.call_args_list[0].args[0],'git/ref/heads/main')
        self.assertIn('ref='+'b'*40,request.call_args_list[1].args[0])
    def test_verified_download_and_recheck_before_install(self):
        release=self.up.validate(self.release,'c'*40);self.up.release=release
        with patch.object(self.up,'open',return_value=io.BytesIO(self.body)):self.up.fetch(release)
        self.assertTrue(self.up.status()['ready']);self.assertEqual(file_sha(self.up.installer),release['sha256'])
        self.up.installer.write_bytes(b'MZtampered')
        with patch('studio_updates.subprocess.Popen') as execute:
            with self.assertRaisesRegex(ValueError,'已变化'):self.up.install()
            execute.assert_not_called()
    def test_bad_download_is_not_runnable(self):
        release=self.up.validate(self.release,'d'*40)
        with patch.object(self.up,'open',return_value=io.BytesIO(b'corrupted')):self.up.fetch(release)
        self.assertFalse(self.up.status()['ready']);self.assertIsNotNone(self.up.status()['job'].get('error'))
        self.assertFalse(list(self.up.store.cache.rglob('*.part')))
if __name__=='__main__':unittest.main()
