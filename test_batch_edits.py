import gzip
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from studio_ai import Assistant
from studio_batch_edits import atomic_write_set
from studio_page_edits import PageEdits,save_source_map,sha

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name);self.root=base/'project';self.root.mkdir();self.data=base/'data';self.data.mkdir()
        (self.root/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\\input{a}\\newpage\\input{b}\\end{document}\n',encoding='utf-8')
        self.originals={'a.tex':b'\xef\xbb\xbf% First\r\n\\small\r\nAn eror.\r\n','b.tex':b'% Second\n\\small\nAn eror.\n'}
        for name,content in self.originals.items():(self.root/name).write_bytes(content)
        self.pdf=base/'baseline.pdf';shutil.copyfile(Path(__file__).parent/'tests/fixtures/report.pdf',self.pdf)
        sync=base/'main.synctex.gz';sync.write_bytes(gzip.compress((f'Input:1:{self.root / "a.tex"}\nInput:2:{self.root / "b.tex"}\nUnit:1\n{{1\ng1,3:4475232,6789236\n}}1\n{{2\ng2,3:4475232,6789236\n}}2\n').encode()))
        save_source_map(self.root,'main.tex',self.pdf,sync,self.data)
        self.manager=PageEdits(SimpleNamespace(data=self.data,runtime=base/'runtime'));self.context=self.manager.prepare_pages(self.root,'main.tex',self.pdf,[1,2])

    def tearDown(self):self.temp.cleanup()

    def edits(self):
        session=self.manager.sessions[self.context['id']];edits=[]
        for part in session['parts']:
            start=part['displayStart']+part['source'].index('eror')
            edits.append({'part':part['part'],'start':start,'end':start+4,'before':'eror','after':'error','reason':'fix typo'})
        return edits

    def preview(self):
        from PIL import Image
        base=Path(self.temp.name);before=base/'before.png';after=base/'after.png';Image.new('RGB',(10,10),'white').save(before);Image.new('RGB',(10,10),'black').save(after)
        def compile_fake(command,**kwargs):
            output=Path(command[command.index('--outdir')+1]);shutil.copyfile(self.pdf,output/'main.pdf');return SimpleNamespace(returncode=0,stdout='',stderr='')
        with patch('studio_page_edits.subprocess.run',side_effect=compile_fake),patch('studio_page_edits.engine_environment',return_value={}),patch('studio_page_edits.page_image',side_effect=lambda p,*args:before if Path(p).name=='before.pdf' else after):
            self.manager.preview(self.context['id'],self.root,self.pdf,[0,1])
            until=time.monotonic()+4
            while self.manager.busy() and time.monotonic()<until:threading.Event().wait(.01)
        result=self.manager.status(self.context['id'],self.root);self.assertTrue(result['success'],result.get('error'));return result

    def test_two_files_share_preview_apply_and_exact_undo(self):
        result={'edits':self.edits()};self.manager.attach_batch(self.context['id'],self.root,result);preview=self.preview()
        self.assertEqual([p['page'] for p in preview['pages']],[1,2]);self.assertTrue(all(p['changed'] for p in preview['pages']))
        for name,raw in self.originals.items():self.assertEqual((self.root/name).read_bytes(),raw)
        with self.assertRaises(ValueError):self.manager.apply_files(self.context['id'],self.root,self.pdf,preview['id'],selected=[0])
        changes,session=self.manager.apply_files(self.context['id'],self.root,self.pdf,preview['id'],selected=[0,1]);self.assertEqual(len(changes),2)
        atomic_write_set(changes);session['appliedHashes']={p.relative_to(self.root).as_posix():sha(p) for p,_ in changes};session['appliedHash']=sha(changes[0][0])
        self.assertTrue((self.root/'a.tex').read_bytes().startswith(b'\xef\xbb\xbf'));self.assertIn(b'\r\n',(self.root/'a.tex').read_bytes())
        undo,_=self.manager.apply_files(self.context['id'],self.root,self.pdf,None,undo=True);atomic_write_set(undo)
        for name,raw in self.originals.items():self.assertEqual((self.root/name).read_bytes(),raw)

    def test_ambiguous_position_and_changed_source_are_rejected(self):
        edits=self.edits();edits[0]['start']+=1;result={'edits':edits};self.manager.attach_batch(self.context['id'],self.root,result)
        self.assertEqual(len(result['edits']),1);self.assertEqual(len(result['rejected']),1)
        (self.root/'a.tex').write_text('external edit',encoding='utf-8')
        with self.assertRaises(ValueError):self.manager.preview(self.context['id'],self.root,self.pdf,[0])

    def test_shared_source_duplicates_merge_and_conflicts_are_reported(self):
        session=self.manager.sessions[self.context['id']];a,b=session['parts'];b.update(path=a['path'],start=a['start'],source=a['source']);edits=self.edits()
        result={'edits':edits};self.manager.attach_batch(self.context['id'],self.root,result);self.assertEqual(len(result['edits']),1)
        edits[1]['after']='erratum';result={'edits':edits};self.manager.attach_batch(self.context['id'],self.root,result)
        self.assertEqual(len(result['edits']),1);self.assertEqual(len(result['rejected']),1)

    def test_atomic_write_failure_restores_every_file(self):
        real_replace=__import__('os').replace;count=[0]
        def fail_second(source,target):
            count[0]+=1
            if count[0]==2:raise OSError('simulated write failure')
            return real_replace(source,target)
        with patch('studio_batch_edits.os.replace',side_effect=fail_second):
            with self.assertRaises(OSError):atomic_write_set([(self.root/'a.tex',b'new a'),(self.root/'b.tex',b'new b')])
        for name,raw in self.originals.items():self.assertEqual((self.root/name).read_bytes(),raw)
        self.assertFalse(list(self.root.glob('*.studio-*')))

    def test_images_are_limited_to_selected_pages(self):
        from PIL import Image
        image=Path(self.temp.name)/'page.png';Image.new('RGB',(10,10),'white').save(image)
        with patch('studio_review.page_image',return_value=image) as render:
            parts,images=self.manager.batch_input(self.context['id'],self.root,self.pdf)
        self.assertEqual([p['page'] for p in parts],[1,2]);self.assertEqual([i['page'] for i in images],[1,2]);self.assertEqual(render.call_count,2)

class ModelBatchTests(unittest.TestCase):
    def run_batch(self,request_handler):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);ai=Assistant(self.folder.name)
        ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'mock-only','model':'mock'}}
        parts=[{'part':i,'page':i+1,'path':f'{i}.tex','source':'An eror.','displayStart':i*40} for i in range(2)]
        with patch('studio_ai.request_json',side_effect=lambda *a,**kw:request_handler(ai,*a,**kw)) as request:
            ai.start({'task':'pages_edit','provider':'deepseek','text':'selected pages','parts':parts,'pageContext':'context'},'a'*20,[{'page':i+1,'image':'data:image/png;base64,dGVzdA=='} for i in range(2)])
            until=time.monotonic()+3
            while ai.busy() and time.monotonic()<until:threading.Event().wait(.01)
        return ai.status('a'*20),request.call_count

    def test_cancel_does_not_start_another_page_request(self):
        def stop(ai,*args,**kwargs):
            ai.cancelled.set()
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"summary":"stopped","edits":[]}'}}]}
        job,count=self.run_batch(stop);self.assertEqual(count,1);self.assertFalse(job['success'])

    def test_failed_page_is_reported_without_discarding_safe_edits(self):
        count=[0]
        def partial(ai,*args,**kwargs):
            count[0]+=1
            if count[0]==2:raise ValueError('unavailable test page')
            return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'fix','edits':[{'before':'eror','after':'error','reason':'typo'}]})}}]}
        job,calls=self.run_batch(partial);self.assertEqual(calls,2);self.assertTrue(job['success']);self.assertEqual(len(job['result']['edits']),1);self.assertEqual(job['result']['issues'][0]['page'],2)

    def test_each_request_contains_only_one_selected_page(self):
        with tempfile.TemporaryDirectory() as folder:
            ai=Assistant(folder);ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'mock-only','model':'mock'}}
            parts=[{'part':0,'page':1,'path':'a.tex','source':'An eror.','displayStart':0},{'part':1,'page':3,'path':'b.tex','source':'An eror.','displayStart':50}]
            response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'fix','edits':[{'before':'eror','after':'error','reason':'typo'}]})}}],'usage':{'total_tokens':8}}
            with patch('studio_ai.request_json',return_value=response) as request:
                ai.start({'task':'pages_edit','provider':'deepseek','text':'selected pages','parts':parts,'pageContext':'context'},'a'*20,[{'page':p,'image':'data:image/png;base64,dGVzdA=='} for p in [1,3]])
                until=time.monotonic()+3
                while ai.busy() and time.monotonic()<until:threading.Event().wait(.01)
            result=ai.status('a'*20);self.assertTrue(result['success'],result.get('error'));self.assertEqual(request.call_count,2)
            for call in request.call_args_list:self.assertEqual(sum(b['type']=='image_url' for b in call.args[1]['messages'][1]['content']),1)
            self.assertEqual([e['page'] for e in result['result']['edits']],[1,3]);self.assertEqual(result['result']['usage']['total_tokens'],16)

if __name__=='__main__':unittest.main()
