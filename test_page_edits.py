import gzip
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from studio_ai import Assistant, actionable_result, validate_edits
from studio_page_edits import PageEdits, project_files, save_source_map, sha
from studio_storage import project_id


class ActionableTests(unittest.TestCase):
    def test_repeated_text_uses_explicit_line_without_guessing(self):
        source='same\nother\nsame\n'
        edits,target=validate_edits(source,[{'before':'same','after':'changed','line':3}])
        self.assertEqual(target,'same\nother\nchanged\n')
        self.assertEqual(edits[0]['start'],11)
        with self.assertRaises(ValueError):validate_edits(source,[{'before':'same','after':'changed'}])

    def test_presentation_numbers_can_change_but_facts_and_formulas_cannot(self):
        source=r'\setlength{\parskip}{2pt} Result 97.50. $x^2$ \includegraphics[width=0.4\linewidth]{fig.pdf}'
        _,target=validate_edits(source,[{'before':'{2pt}','after':'{4pt}'},{'before':'width=0.4','after':'width=0.6'}])
        self.assertIn('width=0.6',target)
        for before,after in [('97.50','99.50'),('$x^2$','$x^3$'),('fig.pdf','other.pdf')]:
            with self.assertRaises(ValueError):validate_edits(source,[{'before':before,'after':after}])

    def test_safe_edits_survive_an_unrelated_rejected_suggestion(self):
        edits,target,rejected=actionable_result('An eror. Result 12.',{'edits':[{'before':'eror','after':'error'},{'before':'12','after':'13'}]})
        self.assertEqual(target,'An error. Result 12.')
        self.assertEqual(len(edits),1);self.assertEqual(len(rejected),1)

    def test_custom_figure_paths_and_labels_are_protected(self):
        source=r'\fig[0.4]{plot.pdf}{Caption}{fig:demo}'
        _,target=validate_edits(source,[{'before':'[0.4]','after':'[0.6]'}]);self.assertIn('[0.6]',target)
        for before,after in [('plot.pdf','other.pdf'),('fig:demo','fig:other')]:
            with self.assertRaises(ValueError):validate_edits(source,[{'before':before,'after':after}])

    def test_single_page_model_contract_and_completion_hook(self):
        with tempfile.TemporaryDirectory() as data:
            ai=Assistant(data);ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'fake-test-only','model':'deepseek-flash'}}
            source='An eror.';response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'已修正','edits':[{'before':'eror','after':'error','line':1,'reason':'修复错字'}]})}}]}
            results=[]
            with patch('studio_ai.request_json',return_value=response) as request:
                ai.start({'task':'page_edit','provider':'deepseek','text':source,'pageContext':'context'},'a'*20,[{'page':1,'image':'data:image/png;base64,dGVzdA=='}],results.append)
                deadline=time.monotonic()+3
                while ai.busy() and time.monotonic()<deadline:threading.Event().wait(.01)
            job=ai.status('a'*20)
            self.assertTrue(job['success']);self.assertEqual(len(results),1)
            blocks=request.call_args.args[1]['messages'][1]['content'];self.assertEqual(sum(b['type']=='image_url' for b in blocks),1)
            with self.assertRaises(ValueError):ai.start({'task':'page_edit','provider':'deepseek','text':source},'a'*20,[{'page':1,'image':'fake'},{'page':2,'image':'fake'}])


class PageContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-page-test-');base=Path(self.temp.name)
        self.root=base/'project';self.root.mkdir();self.data=base/'data';self.data.mkdir()
        self.source=b'\xef\xbb\xbf\\documentclass{article}\r\n\\begin{document}\r\n\\small\r\nAn eror.\r\n\\end{document}\r\n'
        (self.root/'main.tex').write_bytes(self.source)
        self.pdf=base/'original.pdf';shutil.copyfile(Path(__file__).parent/'tests/fixtures/report.pdf',self.pdf)
        sync=base/'main.synctex.gz';sync.write_bytes(gzip.compress(('SyncTeX Version:1\nInput:1:'+str(self.root/'main.tex')+'\nUnit:1\nContent:\n{1\ng1,4:4475232,6789236\n}1\n').encode()))
        save_source_map(self.root,'main.tex',self.pdf,sync,self.data)
        self.storage=SimpleNamespace(data=self.data,runtime=base/'runtime');self.manager=PageEdits(self.storage)
        self.context=self.manager.prepare(self.root,'main.tex',self.pdf,1)

    def tearDown(self):self.temp.cleanup()

    def test_maps_only_current_page_and_rejects_source_changes(self):
        self.assertIn('An eror.',self.context['source'])
        self.assertEqual(self.context['page'],1)
        with self.assertRaises(ValueError):self.manager.context(self.context['id'],self.root.parent)
        (self.root/'main.tex').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):self.manager.ai_input(self.context['id'],self.root,self.pdf)

    def test_source_selection_is_exact_and_stale_source_is_rejected(self):
        full=(self.root/'main.tex').read_text(encoding='utf-8-sig');start=full.index('An eror.');end=start+len('An eror.')
        context=self.manager.prepare_source(self.root,'main.tex',self.pdf,'main.tex',start,end)
        self.assertEqual(context['source'],'An eror.');self.assertEqual(context['start'],start);self.assertEqual(context['mode'],'source')
        self.assertEqual(self.manager.source_input(context['id'],self.root,self.pdf),'An eror.')
        with self.assertRaises(ValueError):self.manager.prepare_source(self.root,'main.tex',self.pdf,'../outside.tex',0,1)
        with self.assertRaises(ValueError):self.manager.prepare_source(self.root,'main.tex',self.pdf,'main.tex',True,end)
        (self.root/'main.tex').write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):self.manager.source_input(context['id'],self.root,self.pdf)

    def test_preview_does_not_modify_original_and_apply_requires_same_selection(self):
        from PIL import Image
        base=Path(self.temp.name);before=base/'before.png';after=base/'after.png'
        Image.new('RGB',(12,12),'white').save(before);Image.new('RGB',(12,12),'black').save(after)
        source=self.context['source'];edits=validate_edits(source,[{'before':'eror','after':'error'}])[0]
        self.manager.attach(self.context['id'],self.root,edits)
        def compile_fake(command,**kwargs):
            output=Path(command[command.index('--outdir')+1]);shutil.copyfile(self.pdf,output/'main.pdf')
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch('studio_page_edits.subprocess.run',side_effect=compile_fake),patch('studio_page_edits.engine_environment',return_value={}),patch('studio_page_edits.page_image',side_effect=lambda pdf,*a:before if Path(pdf).name=='before.pdf' else after):
            self.manager.preview(self.context['id'],self.root,self.pdf,[0])
            deadline=time.monotonic()+4
            while self.manager.busy() and time.monotonic()<deadline:threading.Event().wait(.01)
        result=self.manager.status(self.context['id'],self.root);self.assertTrue(result['success']);self.assertTrue(result['changed'])
        self.assertEqual((self.root/'main.tex').read_bytes(),self.source)
        with self.assertRaises(ValueError):self.manager.apply_data(self.context['id'],self.root,self.pdf,result['id'],selected=[])
        target,content,session=self.manager.apply_data(self.context['id'],self.root,self.pdf,result['id'],selected=[0])
        self.assertIn(b'error',content);self.assertTrue(content.startswith(b'\xef\xbb\xbf'));self.assertIn(b'\r\n',content)
        target.write_bytes(content);session['appliedHash']=sha(target)
        _,undo,_=self.manager.apply_data(self.context['id'],self.root,self.pdf,result['id'],undo=True)
        self.assertEqual(undo,self.source)
        target.write_bytes(b'external change')
        with self.assertRaises(ValueError):self.manager.apply_data(self.context['id'],self.root,self.pdf,result['id'],undo=True)


if __name__=='__main__':unittest.main()
