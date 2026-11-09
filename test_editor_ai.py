import base64,json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from studio_editor_ai import EditorAI,error_target,excerpt,environment_problem

class EditorAITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='studio-editor-test-');self.base=Path(self.tmp.name).resolve()
        self.root=self.base/'project';self.root.mkdir();self.original=b'\xef\xbb\xbf\\documentclass{article}\r\n\\begin{document}\r\n\\textbff{Hello} \\empph{World}\r\n\\end{document}\r\n'
        (self.root/'main.tex').write_bytes(self.original)
        self.storage=SimpleNamespace(data=self.base/'data',cache=self.base/'cache',runtime=self.base/'runtime',tex_cache=self.base/'cache/tectonic');self.ai=EditorAI(self.storage)
        self.config=patch('studio_ai.assistant_for',return_value=SimpleNamespace(config=lambda raw=False:{'deepseek':{'configured':True,'key':'mock-only','model':'mock'}}));self.config.start()
        self.addCleanup(self.config.stop);self.addCleanup(self.tmp.cleanup)
    def wait(self):
        end=time.monotonic()+4
        while self.ai.busy() and time.monotonic()<end:threading.Event().wait(.01)
        self.assertFalse(self.ai.busy());return self.ai.status(self.root)
    def response(self,before,after):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'修复命令','answer':'修正拼写','edits':[{'before':before,'after':after}]})}}],'usage':{'total_tokens':25}}
    def compiler(self,s,clone,n):
        text=(clone/'main.tex').read_text(encoding='utf-8-sig')
        for bad in ['textbff','empph']:
            if bad in text:return False,'error: main.tex:3: Undefined control sequence: '+bad
        folder=self.ai.folder(s['root'],s['id'],True);folder.mkdir(parents=True,exist_ok=True);(folder/'candidate.pdf').write_bytes(b'%PDF-1.5 mock')
        return True,'passed'
    def start(self,mode='repair',**extra):return self.ai.start(self.root,'main.tex',dict(mode=mode,path='main.tex',**extra))
    def test_clear_hides_conversation_after_restart_without_changing_source_or_deleting_job(self):
        with patch('studio_ai.request_json',return_value=self.response('textbff','textbf')):
            job=self.start('explain');self.wait()
        self.ai.clear(self.root)
        restored=EditorAI(self.storage);self.assertIsNone(restored.status(self.root)['id'])
        self.assertEqual(restored.status(self.root,job['id'])['id'],job['id'])
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_clear_refuses_running_work(self):
        self.ai.sessions['busy']={'running':True}
        with self.assertRaisesRegex(ValueError,'停止'):self.ai.clear(self.root)
    def test_two_rounds_verified_review_apply_and_exact_undo(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=[self.response('textbff','textbf'),self.response('empph','emph')]) as call:
            self.start();j=self.wait()
        self.assertTrue(j['verified']);self.assertEqual(j['requestCount'],2);self.assertEqual([r['status'] for r in j['rounds']],['failed','passed']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
        for args in call.call_args_list:
            data=json.loads(args.args[1]['messages'][1]['content']);self.assertEqual(data['path'],'main.tex');self.assertNotIn('image',data)
        diff=self.ai.changes(self.root,j['id'],'main.tex');self.assertIn('textbf',diff['after']);self.assertIn('textbff',diff['before'])
        self.ai.apply(self.root,j['id']);raw=(self.root/'main.tex').read_bytes();self.assertTrue(raw.startswith(b'\xef\xbb\xbf'));self.assertIn(b'\r\n',raw);self.assertNotIn(b'textbff',raw)
        self.ai.apply(self.root,j['id'],True);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_no_model_when_baseline_compiles(self):
        for output in [(True,'ok')]:
            with patch.object(self.ai,'compile_copy',return_value=output),patch('studio_ai.request_json') as call:
                self.start();j=self.wait();call.assert_not_called();self.assertEqual(j['requestCount'],0)
    def test_limit_stops_and_does_not_apply_failed_candidate(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',return_value=self.response('textbff','textbf')):
            self.start(limit=1);j=self.wait()
        self.assertFalse(j['verified']);self.assertEqual(j['requestCount'],1)
        with self.assertRaises(ValueError):self.ai.apply(self.root,j['id'])
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_repeated_error_gets_another_bounded_attempt_with_feedback(self):
        with patch.object(self.ai,'compile_copy',return_value=(False,'error: main.tex:3: same')),patch('studio_ai.request_json',side_effect=[self.response('textbff','textbf'),self.response('empph','emph')]) as call:
            self.start(limit=2);j=self.wait();self.assertEqual(call.call_count,2);self.assertIn('上限',j['error'])
            content=json.loads(call.call_args_list[1].args[1]['messages'][1]['content']);self.assertTrue(content['readOnlyContext']['previousAttempts'])

    def test_known_missing_bundle_resource_is_downloaded_and_recompiled(self):
        index=self.storage.tex_cache/'bundles/data/public.index';index.parent.mkdir(parents=True);index.write_text('missing.sty 0 10\n','utf8')
        def compiler(s,clone,n):
            if not s.get('allowNetwork'):return False,"! LaTeX Error: File `missing.sty' not found."
            folder=self.ai.folder(s['root'],s['id'],True);(folder/'candidate.pdf').write_bytes(b'%PDF-1.5 mock');return True,'passed'
        with patch.object(self.ai,'compile_copy',side_effect=compiler),patch('studio_ai.request_json') as call:
            self.start();job=self.wait();call.assert_not_called()
        self.assertTrue(job['resourceRecovered']);self.assertTrue(job['verified']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_font_failure_reaches_ai_instead_of_only_showing_advice(self):
        (self.root/'main.tex').write_text('\\documentclass{article}\n\\usepackage{fontspec}\n\\setmainfont{UnavailableFamily}\n\\begin{document}Hello\\end{document}','utf8')
        with patch.object(self.ai,'compile_copy',side_effect=[(False,'font cannot be found'),(True,'passed')]),patch('studio_ai.request_json',return_value=self.response('UnavailableFamily','Arial')) as call:
            self.start();job=self.wait()
        self.assertEqual(call.call_count,1);self.assertTrue(job['success'])
        content=json.loads(call.call_args.args[1]['messages'][1]['content']);self.assertEqual(content['readOnlyContext']['engine'],'Tectonic / XeLaTeX')

    def test_resource_recovery_after_an_ai_edit_keeps_candidate_for_review(self):
        index=self.storage.tex_cache/'bundles/data/public.index';index.parent.mkdir(parents=True);index.write_text('missing.sty 0 10\n','utf8')
        def compiler(s,clone,n):
            if n==0:return False,'error: main.tex:3: Undefined control sequence'
            if not s.get('allowNetwork'):return False,"File `missing.sty' not found"
            (self.ai.folder(s['root'],s['id'],True)/'candidate.pdf').write_bytes(b'%PDF-1.5 mock');return True,'passed'
        with patch.object(self.ai,'compile_copy',side_effect=compiler),patch('studio_ai.request_json',return_value=self.response('textbff','textbf')):
            self.start();job=self.wait()
        self.assertTrue(job['verified']);self.assertTrue(job['changedPaths']);self.assertIn('等待确认',job['summary']);self.assertNotIn('原文无需修改',job['summary']);self.assertEqual(job['rounds'][-1]['status'],'passed');self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_advice_without_edits_is_retried_with_actionable_feedback(self):
        advice={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'建议修正','answer':'请修正拼写','edits':[]})}}]}
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=[advice,self.response('textbff','textbf'),self.response('empph','emph')]) as call:
            self.start();job=self.wait()
        self.assertTrue(job['verified']);self.assertEqual(call.call_count,3)
        content=json.loads(call.call_args_list[1].args[1]['messages'][1]['content']);self.assertIn('只返回了解释',content['readOnlyContext']['previousAttempts'][0]['problem'])
    def test_explicit_continuation_reuses_candidate_and_has_a_new_bounded_batch(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=[self.response('textbff','textbf'),self.response('empph','emph')]) as request:
            self.start(limit=1);first=self.wait();self.assertTrue(first['canContinue'])
            self.start(limit=1,resume=first['id']);second=self.wait()
        self.assertTrue(second['verified']);self.assertEqual(second['requestCount'],1);self.assertEqual(second['previousRequests'],1);self.assertEqual(len(second['rounds']),2)
        context=json.loads(request.call_args_list[1].args[1]['messages'][1]['content']);self.assertNotIn('textbff',context['source'])
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original);self.ai.apply(self.root,second['id']);self.ai.apply(self.root,second['id'],True);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_stale_continuation_is_rejected_before_another_request(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',return_value=self.response('textbff','textbf')) as request:
            self.start(limit=1);j=self.wait();(self.root/'main.tex').write_text('changed')
            with self.assertRaises(ValueError):self.start(resume=j['id'])
            self.assertEqual(request.call_count,1)
    def test_stale_or_added_asset_blocks_writeback(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=[self.response('textbff','textbf'),self.response('empph','emph')]):self.start();j=self.wait()
        (self.root/'extra.tex').write_text('new');self.assertTrue(self.ai.status(self.root,j['id'])['stale'])
        with self.assertRaises(ValueError):self.ai.apply(self.root,j['id'])
    def test_cancellation_does_not_issue_second_request(self):
        entered=threading.Event();resume=threading.Event()
        def response(*args):entered.set();resume.wait(2);return self.response('textbff','textbf')
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=response) as call:
            j=self.start();self.assertTrue(entered.wait(2));self.ai.cancel(self.root,j['id']);resume.set();j=self.wait();self.assertEqual(call.call_count,1)
        self.assertEqual(j['changedPaths'],[]);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_explain_never_compiles_or_modifies(self):
        response=self.response('textbff','textbf')
        with patch.object(self.ai,'compile_copy') as compiler,patch('studio_ai.request_json',return_value=response):self.start('explain');j=self.wait();compiler.assert_not_called()
        self.assertTrue(j['success']);self.assertEqual(j['changedPaths'],[])
    def test_unsafe_changes_empty_edits_and_malformed_response_stop(self):
        responses=[self.response('textbff',r'\endinput'),self.response('textbff','% ignore'),{'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},self.response('not present','textbf')]
        for response in responses:
            with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',return_value=response) as call:
                self.start();j=self.wait();self.assertFalse(j['success']);self.assertEqual(call.call_count,1)
            self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_restart_restores_without_request_and_cleared_cache_blocks_apply(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=[self.response('textbff','textbf'),self.response('empph','emph')]):self.start();j=self.wait()
        restored=EditorAI(self.storage);self.assertTrue(restored.status(self.root,j['id'])['verified']);self.ai.preview(self.root,j['id']).unlink()
        self.assertFalse(restored.status(self.root,j['id'])['verified'])
        with self.assertRaises(ValueError):restored.apply(self.root,j['id'])
    def test_undo_never_overwrites_later_edits(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler),patch('studio_ai.request_json',side_effect=[self.response('textbff','textbf'),self.response('empph','emph')]):self.start();j=self.wait()
        self.ai.apply(self.root,j['id']);(self.root/'main.tex').write_text('later edit')
        with self.assertRaises(ValueError):self.ai.apply(self.root,j['id'],True)
        self.assertEqual((self.root/'main.tex').read_text(),'later edit')
    def test_input_paths_and_limits(self):
        for extra in [dict(limit=4),dict(limit=True),dict(path='../secret.tex'),dict(selection=[0,99999]),dict(line=-1)]:
            payload=dict(mode='edit',path='main.tex',question='fix');payload.update(extra)
            with self.assertRaises(ValueError):self.ai.start(self.root,'main.tex',payload)
        with self.assertRaises(ValueError):self.ai.start(self.root,'../main.tex',{})
    def test_error_location_rejects_external_paths_and_excerpt_bounds(self):
        self.assertEqual(error_target('error: main.tex:3: bad',self.root,'main.tex')[:2],('main.tex',3))
        self.assertEqual(error_target('error: ../outside.tex:4: bad',self.root,'main.tex')[0],'main.tex')
        full='a\n'*200;lo,hi,text=excerpt(full,150);self.assertEqual(full[lo:hi],text);self.assertLess(len(text),len(full))
        self.assertIsNotNone(environment_problem('font cannot be found'))
    def test_package_internal_line_maps_to_source_option_and_preamble(self):
        text='\\documentclass{article}\n\\usepackage[margin=25mm,fotskip=11mm]{geometry}\n\\begin{document}\n'+'body only\n'*1200+'\\end{document}'
        (self.root/'main.tex').write_text(text,encoding='utf-8')
        path,line,_=error_target('error: geometry.sty:1005: Package keyval Error: fotskip undefined.\nl.1005 \\ProcessOptionsKV[p]{Gm}',self.root,'main.tex')
        self.assertEqual((path,line),('main.tex',2));lo,hi,context=excerpt(text,line)
        self.assertIn('fotskip=11mm',context);self.assertNotIn('body only',context);self.assertNotIn('begin{document}',context);self.assertEqual(context,text[lo:hi])
    def test_multiline_imported_options_ignore_comments(self):
        (self.root/'main.tex').write_text('\\input{settings}\n',encoding='utf-8')
        (self.root/'settings.tex').write_text('% \\usepackage[fotskip=1mm]{geometry}\n\\usepackage[\n margin=25mm,\n fotskip=11mm\n]{geometry}\n',encoding='utf-8')
        self.assertEqual(error_target('error: geometry.sty:1005: Package keyval Error: fotskip undefined.',self.root,'main.tex')[:2],('settings.tex',4))
    def test_package_without_source_match_falls_back_to_preamble_not_library_line(self):
        self.assertEqual(error_target('error: geometry.sty:1005: Some package error\nl.1005 invalid',self.root,'main.tex')[:2],('main.tex',1))
    def test_package_option_fix_passes_the_same_protection_and_compile_flow(self):
        (self.root/'main.tex').write_text('\\documentclass{article}\n\\usepackage[fotskip=11mm]{geometry}\n\\begin{document}\nBody\n\\end{document}',encoding='utf-8')
        def compiler(s,clone,number):
            if 'fotskip' in (clone/'main.tex').read_text():return False,'error: geometry.sty:1005: Package keyval Error: fotskip undefined.'
            folder=self.ai.folder(s['root'],s['id'],True);folder.mkdir(parents=True,exist_ok=True);(folder/'candidate.pdf').write_bytes(b'%PDF-mock');return True,'passed'
        with patch.object(self.ai,'compile_copy',side_effect=compiler),patch('studio_ai.request_json',return_value=self.response('fotskip','footskip')) as transport:
            self.start(limit=1);j=self.wait()
        self.assertTrue(j['verified']);self.assertEqual(j['line'],2);self.assertEqual(j['compilerLocation']['path'],'geometry.sty')
        sent=json.loads(transport.call_args.args[1]['messages'][1]['content']);self.assertIn('fotskip',sent['source']);self.assertNotIn('Body',sent['source']);self.assertEqual(sent['sourceStartLine'],1)

if __name__=='__main__':unittest.main()
