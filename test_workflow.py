import tempfile,unittest,gzip,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from studio_sync import locate
from studio_storage import project_id,write_json
from studio_page_edits import sha
from pypdf import PdfWriter

class UnrestrictedRequestsTests(unittest.TestCase):
    def test_old_usage_file_cannot_block_requests(self):
        from studio_ai import Assistant
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            write_json(Path(d)/'ai-usage.json',{'day':'2099-01-01','limit':1,'requests':100000})
            assistant=Assistant(d);assistant.job={'requestCount':0}
            with patch('studio_ai.request_json',return_value={}) as network:
                for _ in range(3):assistant.request('mock',{})
                self.assertEqual(network.call_count,3)

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
