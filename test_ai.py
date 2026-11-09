"""No document leaves the machine: provider contracts exercised with mock responses."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from studio_ai import Assistant, local_check, signature, validate_edits, seal


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-ai-test-')
        self.ai = Assistant(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def wait_job(self):
        deadline = time.monotonic() + 5
        while self.ai.busy() and time.monotonic() < deadline:
            threading.Event().wait(.01)
        job = self.ai.status('project-a')
        self.assertFalse(job['running'])
        return job

    def test_local_structure_and_no_network(self):
        text = '\\begin{document}\n\\label{x}\\label{x}\ntext  \n\\end{figure}\n'
        with patch('studio_ai.request_json', side_effect=AssertionError('network called')):
            self.ai.start({'text':text,'task':'check','provider':'local','scope':'file'}, 'project-a')
            result = self.wait_job()['result']
        self.assertTrue(any('重复标签' in i['message'] for i in result['issues']))
        self.assertTrue(any('不匹配' in i['message'] for i in result['issues']))
        self.assertEqual(result['edits'][0]['after'], 'text\n')
        self.assertFalse(self.ai.status('project-b').get('result'))

    def test_exact_edits_and_protected_facts(self):
        source = '错字，结果为 12。$x^2$ \\ref{fig:a}'
        edits, target = validate_edits(source, [{'before':'错字','after':'正字'}])
        self.assertEqual(edits[0]['start'], 0)
        self.assertIn('正字', target)
        for before, after in [('12','13'), ('$x^2$','$x^3$'), ('\\ref{fig:a}','\\ref{fig:b}')]:
            with self.assertRaises(ValueError):
                validate_edits(source, [{'before':before,'after':after}])
        with self.assertRaises(ValueError):
            validate_edits('same same', [{'before':'same','after':'other'}])
        with self.assertRaises(ValueError):
            validate_edits('abcdef', [{'before':'abc','after':'a'}, {'before':'bcde','after':'b'}])

    def test_comments_and_verbatim_not_false_positive(self):
        text = '% \\begin{foo}\n\\begin{verbatim}\n{ \\end{bad}  \n\\end{verbatim}\n'
        result = local_check(text)
        self.assertFalse(result['issues'])
        self.assertFalse(result['edits'])

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_keys_encrypted_masked_preserved_and_removed(self):
        self.ai.configure({'deepseekKey':'private-test-key','model':'deepseek-flash','youdaoId':'test-id','youdaoSecret':'test-secret'})
        raw = Path(self.temp.name, 'ai-settings.json').read_text()
        self.assertNotIn('private-test-key', raw)
        self.assertNotIn('test-secret', raw)
        public = json.dumps(self.ai.config())
        self.assertNotIn('private-test-key', public)
        self.assertNotIn('test-secret', public)
        self.ai.configure({'deepseekKey':''})
        self.assertEqual(self.ai.config(True)['deepseek']['key'], 'private-test-key')
        self.ai.configure({'cleardeepseekKey':True})
        self.assertFalse(self.ai.config()['deepseek']['configured'])
        value = seal('中文🔑')
        self.assertEqual(seal(value, True), '中文🔑')

    def test_signature_and_youdao_contract(self):
        q = '这是一个长度大于二十个字符的测试文本用于签名校验'
        expected = hashlib.sha256(('id'+q[:10]+str(len(q))+q[-10:]+'salt'+'123'+'secret').encode()).hexdigest()
        self.assertEqual(signature(q,'id','secret','salt','123'), expected)
        self.ai.config = lambda raw=False: {'youdao':{'configured':True,'appId':'id','secret':'secret'}}
        with patch('studio_ai.request_json', return_value={'errorCode':'0','translation':['Academic writing.']}) as request:
            self.ai.start({'text':'学术写作。','task':'translate','provider':'youdao'}, 'project-a')
            job = self.wait_job()
        self.assertTrue(job['success'])
        args = request.call_args
        self.assertEqual(args.args[0], 'https://openapi.youdao.com/api')
        self.assertEqual(args.args[1]['signType'], 'v3')
        self.assertTrue(args.kwargs['form'])
        with self.assertRaises(ValueError):
            self.ai.start({'text':'\\section{标题}','task':'translate','provider':'youdao'}, 'project-a')

    def test_deepseek_and_workflow_contract(self):
        self.ai.config = lambda raw=False: {'deepseek':{'configured':True,'model':'deepseek-flash','key':'secret'}}
        response = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'corrected','issues':[], 'edits':[{'before':'eror','after':'error','reason':'typo'}]})}}], 'usage':{'total_tokens':10}}
        response2 = {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'formatted','issues':[], 'edits':[]})}}], 'usage':{'total_tokens':8}}
        with patch('studio_ai.request_json', side_effect=[response, response2]) as request:
            self.ai.start({'text':'eror\n','task':'workflow','provider':'deepseek'}, 'project-a')
            job = self.wait_job()
        self.assertTrue(job['success'])
        self.assertEqual(request.call_count, 2)
        self.assertEqual(job['result']['usage']['total_tokens'], 18)
        self.assertEqual(job['result']['edits'][0]['after'], 'error\n')
        self.assertEqual(request.call_args.args[1]['response_format'], {'type':'json_object'})
        self.assertNotIn('secret', json.dumps(job))

    def test_dictionary_renders_definitions_without_html_or_persistent_cache(self):
        self.ai.config = lambda raw=False: {'youdao':{'configured':True,'appId':'id','secret':'secret'}}
        response = {'errorCode':'0','result':{'ec':{'basic':{'phonetic':'test','explains':['n. 测试']},'sentenceSample':[{'sentence':'<b>test</b> sentence','translation':'测试例句'}]}}}
        with patch('studio_ai.request_json', return_value=response) as request:
            self.ai.start({'text':'test','task':'dictionary','provider':'youdao'}, 'project-a')
            job = self.wait_job()
        self.assertTrue(job['success'])
        self.assertIn('n. 测试', job['result']['dictionary'])
        self.assertNotIn('<b>', job['result']['dictionary'])
        self.assertEqual(request.call_args.args[0], 'https://openapi.youdao.com/v2/dict')
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_cancel_discards_inflight_result_and_blocks_new_jobs(self):
        entered, release = threading.Event(), threading.Event()
        self.ai.config = lambda raw=False: {'deepseek':{'configured':True,'model':'deepseek-flash','key':'secret'}}
        def response(*args, **kwargs):
            entered.set(); release.wait(3)
            return {'choices':[{'finish_reason':'stop','message':{'content':'{"edits":[]}'}}]}
        with patch('studio_ai.request_json', side_effect=response):
            job = self.ai.start({'text':'abc','task':'check','provider':'deepseek'}, 'project-a')
            self.assertTrue(entered.wait(2))
            with self.assertRaises(ValueError):
                self.ai.cancel('project-b', job['id'])
            self.ai.cancel('project-a', job['id'])
            with self.assertRaises(ValueError):
                self.ai.start({'text':'abc','task':'check','provider':'local'}, 'project-a')
            release.set()
            result = self.wait_job()
        self.assertFalse(result['success'])
        self.assertNotIn('result', result)

    def test_no_keys_fail_before_network(self):
        with patch('studio_ai.request_json', side_effect=AssertionError('network called')):
            with self.assertRaises(ValueError):
                self.ai.start({'text':'document','task':'format','provider':'deepseek'}, 'project-a')

    def test_cancel_finishes_promptly_and_late_response_cannot_replace_next_job(self):
        entered,release=threading.Event(),threading.Event();attached=[]
        self.ai.config=lambda raw=False:{'deepseek':{'configured':True,'model':'mock','key':'mock'}}
        def response(*args,**kwargs):
            entered.set();release.wait(3)
            return {'choices':[{'message':{'content':'{"groups":[]}'}}]}
        with patch('studio_ai.request_json',side_effect=response):
            job=self.ai.start({'text':'synthetic terms','task':'terms','provider':'deepseek'},'project-a',on_result=attached.append)
            self.assertTrue(entered.wait(1));self.ai.cancel('project-a',job['id'])
            deadline=time.monotonic()+1
            while self.ai.busy() and time.monotonic()<deadline:time.sleep(.01)
            self.assertFalse(self.ai.busy());self.assertEqual(self.ai.status('project-a')['stage'],'已停止')
            next_job=self.ai.start({'text':'clean text','task':'check','provider':'local'},'project-a');self.wait_job()
            release.set();time.sleep(.1)
            self.assertEqual(self.ai.status('project-a')['id'],next_job['id']);self.assertEqual(attached,[])


if __name__ == '__main__':
    unittest.main()
