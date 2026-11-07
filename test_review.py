import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from studio_ai import Assistant
from studio_review import analyze_references, glossary_get, glossary_save, inspect_geometry, inspect_pdf, parse_pages, relevant_terms

PROJECT='a'*20


class ReferenceTests(unittest.TestCase):
    def test_follows_reachable_files_and_bibliography(self):
        sources={'main.tex':'\\input{parts/intro}\n\\ref{fig:x} \\citep[p. 4]{paper}\n\\bibliography{refs}',
                 'parts/intro.tex':'\\label{fig:x}', 'refs.bib':'@article{paper, title={A paper}, year={2025}}',
                 'unreachable.tex':'\\label{fig:x} \\cite{missing}'}
        result=analyze_references(sources,'main.tex')
        self.assertEqual(result['files'],['main.tex','parts/intro.tex','refs.bib'])
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['bibliography'],1)

    def test_resolves_optional_macro_label_argument(self):
        text=r'\newcommand{\fig}[4][.9]{\begin{figure}\includegraphics{#2}\caption{#3}\label{#4}\end{figure}}'+'\n'+r'\fig{img.pdf}{Caption}{fig:a}\fig[.5]{b.pdf}{Other}{fig:b}\ref{fig:a}\cref{fig:a,fig:b}'
        result=analyze_references({'main.tex':text},'main.tex')
        self.assertEqual(result['labels'],2)
        self.assertEqual(result['issues'],[])

    def test_reports_duplicates_missing_keys_and_cycles(self):
        result=analyze_references({'main.tex':'\\input{part}\n\\label{x}\\label{x}\\ref{y}\\cite{missing}\n\\bibliography{refs}',
                                   'part.tex':'\\input{main}', 'refs.bib':'@book{dup,title={one}}\n@book{dup,title={two}}'},'main.tex')
        codes={i['code'] for i in result['issues']}
        self.assertTrue({'include-cycle','duplicate-label','duplicate-bib','missing-label','missing-citation'}<=codes)

    def test_skips_comments_code_and_nested_fake_bib_entries(self):
        result=analyze_references({'main.tex':'% \\label{bad}\n\\begin{verbatim}\n\\cite{bad}\n\\end{verbatim}\n\\bibliography{refs}\\nocite{*}',
                                   'refs.bib':'@article{real,title={An example @book{fake, title={nested}}}}'},'main.tex')
        self.assertEqual(result['labels'],0)
        self.assertEqual(result['bibliography'],1)
        self.assertEqual(result['issues'],[])

    def test_never_resolves_outside_project(self):
        result=analyze_references({'main.tex':'\\input{../outside}\n\\input{D:/private}\n\\input{missing}'},'main.tex')
        self.assertEqual(result['files'],['main.tex'])
        self.assertTrue(any(i['code']=='dynamic-input' for i in result['issues']))
        self.assertTrue(any(i['code']=='missing-file' for i in result['issues']))


class LayoutTests(unittest.TestCase):
    def test_bounds_and_small_text_are_hints(self):
        chars=[{'text':'x','x0':98,'x1':106,'top':15,'bottom':21,'size':6} for _ in range(15)]
        result=inspect_geometry(100,100,chars,[])
        codes={i['code'] for i in result['issues']}
        self.assertTrue({'outside-page','small-type','tight-margin'}<=codes)
        self.assertEqual(result['issues'][0]['page'],1)
        self.assertIsNotNone(result['issues'][0]['bbox'])

    def test_vector_only_page_not_mislabeled_blank(self):
        self.assertEqual(inspect_geometry(100,100,[],[],graphic_count=3)['issues'],[])
        self.assertEqual(inspect_geometry(100,100,[],[])['issues'][0]['code'],'blank-page')

    def test_page_ranges_reject_unbounded_or_invalid_values(self):
        self.assertEqual(parse_pages('1,3-4',5,3),[1,3,4])
        for value in ['0','11','2-1','1-5000','one','1,2,3,4']:
            with self.assertRaises(ValueError):
                parse_pages(value,10,3)

    def test_reads_real_existing_report_without_modifying_it(self):
        path=Path(__file__).parent/'tests/fixtures/report.pdf'
        if not path.is_file():
            self.skipTest('Report is not present')
        before=path.stat().st_mtime_ns
        report=inspect_pdf(path,'1-2')
        self.assertEqual(report['scannedPages'],2)
        self.assertEqual(path.stat().st_mtime_ns,before)


class GlossaryAndVisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='studio-review-test-')
        self.ai=Assistant(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def wait(self):
        deadline=time.monotonic()+3
        while self.ai.busy() and time.monotonic()<deadline:
            threading.Event().wait(.01)
        result=self.ai.status(PROJECT)
        self.assertFalse(result['running'])
        return result

    def test_project_scoped_glossary_and_revision_conflicts(self):
        data={'terms':[{'source':'反向传播','target':'backpropagation','note':'算法'}],'revision':''}
        saved=glossary_save(self.temp.name,PROJECT,data)
        self.assertTrue(saved['revision'])
        self.assertEqual(glossary_get(self.temp.name,'b'*20)['terms'],[])
        self.assertEqual(relevant_terms(self.temp.name,PROJECT,'使用反向传播。')[0]['target'],'backpropagation')
        with self.assertRaises(ValueError):
            glossary_save(self.temp.name,PROJECT,data)
        with self.assertRaises(ValueError):
            glossary_save(self.temp.name,'../outside',data)

    def test_invalid_and_duplicate_terms_do_not_overwrite(self):
        for terms in [[{'source':'a','target':''}], [{'source':'A','target':'x'},{'source':'a','target':'y'}], [{'source':'a\nb','target':'c'}]]:
            with self.assertRaises(ValueError):
                glossary_save(self.temp.name,PROJECT,{'terms':terms,'revision':''})
        self.assertEqual(glossary_get(self.temp.name,PROJECT)['terms'],[])

    def test_deepseek_receives_only_matched_glossary_entries(self):
        glossary_save(self.temp.name,PROJECT,{'terms':[{'source':'反向传播','target':'backpropagation'},{'source':'无关词','target':'unrelated'}],'revision':''})
        self.ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'fake','model':'deepseek-flash'}}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'完成','edits':[{'before':'使用反向传播。','after':'Use backpropagation.'}]})}}]}
        with patch('studio_ai.request_json',return_value=response) as request:
            self.ai.start({'task':'translate','provider':'deepseek','text':'使用反向传播。'},PROJECT)
            job=self.wait()
        self.assertTrue(job['success'])
        prompt=json.loads(request.call_args.args[1]['messages'][1]['content'])
        self.assertEqual(len(prompt['terminology']),1)
        self.assertEqual(job['result']['terminology'][0]['target'],'backpropagation')

    def test_vision_uses_only_attached_pages_and_has_no_source_edits(self):
        self.ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'fake','model':'deepseek-flash'}}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'一项建议','issues':[{'page':2,'message':'图例偏小','evidence':'下部图例','suggestion':'增大字号'}]})}}]}
        with patch('studio_ai.request_json',return_value=response) as request:
            self.ai.start({'task':'layout','provider':'deepseek','text':'review'},PROJECT,[{'page':2,'image':'data:image/png;base64,dGVzdA=='}])
            job=self.wait()
        self.assertTrue(job['success'])
        blocks=request.call_args.args[1]['messages'][1]['content']
        self.assertEqual(sum(b['type']=='image_url' for b in blocks),1)
        self.assertEqual(job['result']['edits'],[])
        self.assertNotIn('fake',json.dumps(job))
        response['choices'][0]['message']['content']='{"issues":[{"page":99,"message":"invalid"}]}'
        with patch('studio_ai.request_json',return_value=response):
            self.ai.start({'task':'layout','provider':'deepseek','text':'review'},PROJECT,[{'page':2,'image':'data:image/png;base64,dGVzdA=='}])
            self.assertFalse(self.wait()['success'])

    def test_probe_uses_fixed_sample_instead_of_supplied_document(self):
        self.ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'fake','model':'deepseek-flash'}}
        response={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'fixed','edits':[{'before':'eror','after':'error'}]})}}]}
        with patch('studio_ai.request_json',return_value=response) as request:
            self.ai.start({'task':'probe','provider':'deepseek','text':'PRIVATE DOCUMENT'},PROJECT)
            job=self.wait()
        self.assertTrue(job['result']['sampleCorrected'])
        self.assertNotIn('PRIVATE DOCUMENT',json.dumps(request.call_args.args))


if __name__=='__main__':
    unittest.main()
