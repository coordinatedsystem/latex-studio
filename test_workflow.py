import tempfile,unittest,gzip,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from studio_usage import Usage
from studio_sync import locate
from studio_storage import project_id,write_json
from studio_page_edits import sha
from pypdf import PdfWriter

class UsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.usage=Usage(self.tmp.name)
    def test_limit_survives_restart_and_never_dispatches_over_limit(self):
        self.usage.configure(1);calls=[]
        self.usage.request(lambda:calls.append(1) or {'usage':{'total_tokens':12}})
        with self.assertRaisesRegex(ValueError,'上限'):Usage(self.tmp.name).request(lambda:calls.append(2))
        self.assertEqual(calls,[1]);self.assertEqual(self.usage.status()['tokens'],12)
    def test_concurrent_requests_reserve_before_network(self):
        self.usage.configure(3);calls=[]
        def worker(_):
            try:self.usage.request(lambda:calls.append(1) or {})
            except ValueError:pass
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(worker,range(12)))
        self.assertEqual(len(calls),3);self.assertEqual(self.usage.status()['requests'],3)
    def test_failure_is_counted_and_daily_reset_preserves_limit(self):
        self.usage.configure(2)
        with self.assertRaises(RuntimeError):self.usage.request(lambda:(_ for _ in ()).throw(RuntimeError('mock')))
        self.assertEqual(self.usage.status()['failures'],1)
        write_json(self.usage.path,{'day':'2000-01-01','limit':2,'requests':8,'tokens':90,'failures':2})
        self.assertEqual(self.usage.status()['requests'],0);self.assertEqual(self.usage.status()['limit'],2)
    def test_invalid_limits_and_unlimited(self):
        for n in [-1,True,1.2,'3',10001]:
            with self.assertRaises(ValueError):self.usage.configure(n)
        self.usage.configure(0);self.assertIsNone(self.usage.status()['remaining'])
    def test_editor_and_full_assistant_share_budget_before_dispatch(self):
        from studio_ai import Assistant
        from studio_editor_ai import EditorAI
        from studio_usage import usage_for
        from unittest.mock import patch
        from types import SimpleNamespace
        data=Path(self.tmp.name).resolve();usage_for(data).configure(1)
        assistant=Assistant(data);assistant.job={'requestCount':0}
        with patch('studio_ai.request_json',return_value={'usage':{'total_tokens':20}}) as network:
            assistant.request('mock',{})
            editor=EditorAI(SimpleNamespace(data=data))
            config={'deepseek':{'configured':True,'key':'mock','model':'mock'}}
            with patch('studio_ai.assistant_for',return_value=SimpleNamespace(config=lambda raw:config)):
                session={'mode':'repair','question':'','requestCount':0}
                with self.assertRaisesRegex(ValueError,'上限'):editor.model(session,'hello','main.tex','mock error')
            self.assertEqual(session['requestCount'],0);self.assertEqual(network.call_count,1)

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name).resolve();self.root=self.base/'project';self.root.mkdir();self.data=self.base/'data';(self.root/'main.tex').write_text('hello\nworld','utf8')
        self.pdf=self.base/'preview.pdf';writer=PdfWriter();writer.add_blank_page(width=600,height=800);writer.write(self.pdf)
        self.sync=self.data/'previews'/(project_id(self.root)+'.synctex.gz');self.sync.parent.mkdir(parents=True)
        self.sync.write_bytes(gzip.compress(('Input:1:'+str(self.root/'main.tex')+'\nInput:2:'+str(self.base/'external.tex')+'\nUnit:1\nMagnification:1000\n{1\ng1,1:6553600,6553600\ng1,2:6553600,13107200\ng2,999:6553600,6553600\n}\n').encode()))
        write_json(self.sync.with_suffix('.json'),{'pdfVersion':str(self.pdf.stat().st_mtime_ns),'sources':{'main.tex':sha(self.root/'main.tex')}})
    def test_forward_and_reverse_point(self):
        point=locate(self.root,self.data,self.pdf,{'direction':'forward','path':'main.tex','line':2})
        self.assertEqual(point['line'],2);self.assertTrue(.24<point['y']<.26)
        reverse=locate(self.root,self.data,self.pdf,{'direction':'inverse','page':1,'x':point['x'],'y':point['y']})
        self.assertEqual(reverse['path'],'main.tex');self.assertEqual(reverse['line'],2)
    def test_stale_source_and_nonfinite_coords_refused(self):
        for x in ['nan','inf',-1,2]:
            with self.assertRaises(ValueError):locate(self.root,self.data,self.pdf,{'page':1,'x':x,'y':.2})
        (self.root/'main.tex').write_text('changed','utf8')
        with self.assertRaisesRegex(ValueError,'重新编译'):locate(self.root,self.data,self.pdf,{'direction':'forward','path':'main.tex','line':1})

if __name__=='__main__':unittest.main()
