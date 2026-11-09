"""Term evidence, normalization, safety and provider contract checks; no real API."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from studio_terms import Terms,occurrences
from studio_ai import Assistant
from studio_document_tools import check_consistency,impact

class TermTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.data=self.root/'private';self.manager=Terms(self.data)
        self.sources={'main.tex':r'\documentclass{article}'+ '\r\n'+r'\begin{document}\input{chapter}\end{document}',
            'chapter.tex':'反向传播。训练使用反向传递。反向传递。BP 神经网络。\r\n'+r'\label{反向传递} $反向传递$ % 反向传递'+'\r\n'+r'\begin{verbatim}反向传递\end{verbatim}'}
        self.original={}
        for n,t in self.sources.items():self.original[n]=b'\xef\xbb\xbf'+t.encode('utf8');(self.root/n).write_bytes(self.original[n])
        self.ident,_=self.manager.prepare(self.root,self.sources,'main.tex')
        result={'groups':[{'preferred':'反向传播','variants':['反向传递','不存在的词'],'target':'backpropagation','relation':'same','note':'同义'},
            {'preferred':'BP','variants':['BP','神经网络'],'target':'neural network','relation':'abbreviation'}]}
        self.manager.attach(self.root,self.ident,result);self.result=result
    def tearDown(self):self.tmp.cleanup()
    def test_grounding_protects_commands_formula_comments_and_code(self):
        g=self.result['groups'][0];self.assertEqual([v['text'] for v in g['variants']],['反向传播','反向传递']);self.assertEqual(g['variants'][1]['count'],2)
        self.assertFalse(occurrences('XBP BP2 BP_network BP','BP')[:-1]);self.assertEqual(len(occurrences('XBP BP2 BP_network BP','BP')),1)
    def test_plan_apply_restart_undo_preserve_exact_bytes(self):
        plan=self.manager.plan(self.root,self.ident,[{'id':0}]);self.assertEqual(plan['count'],2)
        calls=[];save=lambda p,reason:calls.append(reason)
        self.manager.apply(self.root,self.ident,plan['id'],save);after=(self.root/'chapter.tex').read_bytes()
        self.assertIn(r'\label{反向传递}'.encode('utf8'),after);self.assertIn(b'\r\n',after);self.assertTrue(after.startswith(b'\xef\xbb\xbf'))
        Terms(self.data).apply(self.root,self.ident,plan['id'],save,True)
        self.assertEqual((self.root/'chapter.tex').read_bytes(),self.original['chapter.tex']);self.assertEqual(len(calls),4)
    def test_new_source_blocks_apply_and_undo(self):
        plan=self.manager.plan(self.root,self.ident,[{'id':0}]);p=self.root/'main.tex';p.write_bytes(self.original['main.tex']+b'changed')
        with self.assertRaisesRegex(ValueError,'文档已变化'):self.manager.apply(self.root,self.ident,plan['id'],lambda *args:None)
        self.assertEqual((self.root/'chapter.tex').read_bytes(),self.original['chapter.tex'])
    def test_abbreviation_and_invalid_replacement_blocked(self):
        for choices in [[{'id':1}],[{'id':0,'preferred':r'\input{bad}'}],[{'id':0},{'id':0}]]:
            with self.assertRaises(ValueError):self.manager.plan(self.root,self.ident,choices)
    def test_alias_definitions_and_parallel_concepts_are_not_duplicated(self):
        for text in ['反向传播又称反向传递。','本文也将反向传播称为反向传递。','反向传播与反向传递。','反向传播（反向传递）。']:
            p=self.root/'chapter.tex';p.write_text(text,'utf8');sources={**self.sources,'chapter.tex':text};ident,_=self.manager.prepare(self.root,sources,'main.tex')
            r={'groups':[{'preferred':'反向传播','variants':['反向传递'],'relation':'same','target':'backpropagation'}]};self.manager.attach(self.root,ident,r)
            plan=self.manager.plan(self.root,ident,[{'id':0}]);self.assertEqual(plan['count'],0);self.assertEqual(len(plan['skipped']),1)

    def test_provider_workflow_attaches_anchored_terms_without_writing(self):
        ai=Assistant(self.data);output={'groups':[{'preferred':'反向传播','variants':['反向传递'],'target':'backpropagation','relation':'same'}]}
        config={'deepseek':{'model':'test','key':'test-only','configured':True}}
        with patch.object(ai,'config',return_value=config),patch('studio_ai.request_json',return_value={'choices':[{'message':{'content':json.dumps(output)}}]}) as request:
            ai.start({'task':'terms','provider':'deepseek','text':'反向传播与反向传递'},'project-test',on_result=lambda r:self.manager.attach(self.root,self.ident,r))
            deadline=time.monotonic()+5
            while ai.busy() and time.monotonic()<deadline:time.sleep(.01)
            job=ai.status('project-test');self.assertTrue(job['success'],job);self.assertEqual(job['requestCount'],1);self.assertTrue(job['result']['groups']);self.assertEqual(request.call_count,1)
        self.assertEqual((self.root/'chapter.tex').read_bytes(),self.original['chapter.tex'])

class EvidenceTests(unittest.TestCase):
    def test_code_constant_is_not_paper_ground_truth_until_confirmed(self):
        sources={'main.tex':'学习率为 0.1。','config.py':'lr = 0.5\n'}
        r=check_consistency(sources);self.assertEqual(r['items'][0]['status'],'ambiguous')
        item=r['items'][0];bound=check_consistency(sources,{item['claim']['id']:item['sources'][0]['id']})
        self.assertEqual(bound['items'][0]['status'],'mismatch');self.assertEqual(bound['items'][0]['binding'],'manual')
    def test_unknown_table_cells_are_not_scientific_claims(self):
        r=check_consistency({'main.tex':r'\begin{tabular}{lr}姓名&学号\\张三&12345678\\\end{tabular}'})
        self.assertEqual(r['items'],[])
    def test_export_values_keep_automatic_rounding(self):
        r=check_consistency({'main.tex':r'accuracy is 94.7\%.','results.json':'{"accuracy":0.9466}'})
        self.assertEqual(r['items'][0]['status'],'match');self.assertEqual(r['items'][0]['binding'],'export')
    def test_float_caption_tracks_label_and_usage(self):
        text='\\begin{figure}\n\\caption{A figure}\n\\label{fig:a}\n\\end{figure}\nSee \\ref{fig:a}'
        r=impact({'main.tex':text},'main.tex','main.tex',2,2)
        self.assertEqual([e['key'] for e in r['labels']],['fig:a']);self.assertTrue(r['references'])

if __name__=='__main__':unittest.main()
