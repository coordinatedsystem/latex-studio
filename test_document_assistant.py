import base64,json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from studio_document_assistant import DocumentAssistant

class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='studio-conversation-');self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name).resolve();self.root=self.base/'project';self.root.mkdir()
        self.original=b'\xef\xbb\xbf\\documentclass{article}\r\n\\begin{document}\r\nHello \\textbff{world}.\r\n\\end{document}\r\n';(self.root/'main.tex').write_bytes(self.original)
        self.storage=SimpleNamespace(data=self.base/'data',cache=self.base/'cache',runtime=self.base/'runtime',tex_cache=self.base/'cache/tex',preview_path=lambda r:self.base/'missing.pdf');self.ai=DocumentAssistant(self.storage)
        config=patch('studio_ai.assistant_for',return_value=SimpleNamespace(config=lambda raw=False:{'deepseek':{'configured':True,'model':'mock','key':'mock-only'}}));config.start();self.addCleanup(config.stop)
    def response(self,tool=None,args=None,message='继续',done=False,**extra):
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'message':message,'calls':[{'tool':tool,'args':args or {}}] if tool else [],'done':done,**extra})}}],'usage':{'total_tokens':30,'prompt_tokens':20,'completion_tokens':10,'prompt_cache_hit_tokens':5}}
    def run_job(self,responses,mode='agent',**extra):
        with patch('studio_ai.request_json',side_effect=responses):
            s=self.ai.start(self.root,'main.tex',{'mode':mode,'question':'修复错误，保留正文','stepLimit':12,**extra});return self.wait(s['id'])
    def wait(self,ident):
        end=time.monotonic()+5
        while self.ai.busy() and time.monotonic()<end:threading.Event().wait(.01)
        self.assertFalse(self.ai.busy());return self.ai.status(self.root,ident)
    def compiler(self,s,clone,n):
        if 'textbff' in (clone/'main.tex').read_text('utf-8-sig'):return False,'Undefined control sequence textbff'
        pdf=self.ai.folder(s['root'],s['id'],True)/'candidate.pdf';pdf.parent.mkdir(parents=True,exist_ok=True);pdf.write_bytes(b'%PDF-1.5 test');return True,'ok'
    def edit_responses(self):return [self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response('compile'),self.response(message='已解决',done=True)]
    def test_agent_reads_edits_verifies_then_applies_and_undoes_exactly(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):j=self.run_job(self.edit_responses())
        self.assertTrue(j['verified']);self.assertTrue(j['success']);self.assertEqual(j['requestCount'],4);self.assertEqual(j['usage']['cached_tokens'],20);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
        self.ai.apply(self.root,j['id']);self.assertNotIn(b'textbff',(self.root/'main.tex').read_bytes());self.ai.apply(self.root,j['id'],True);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_continue_preserves_goal_and_read_permission(self):
        first=self.run_job([self.response('search',{'query':'Hello'}),self.response('read_file',{'path':'main.tex'})],question='删除讲义相关内容',stepLimit=2)
        self.assertFalse(first['success'])
        captured=[]
        responses=iter([self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response('compile'),self.response(message='候选已完成',done=True)])
        def remote(url,payload,headers):
            captured.append(payload['messages']);return next(responses)
        with patch('studio_ai.request_json',side_effect=remote),patch.object(self.ai,'compile_copy',side_effect=self.compiler):
            job=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'继续','resume':first['id'],'stepLimit':6});job=self.wait(job['id'])
        self.assertTrue(job['verified']);self.assertTrue(job['success'])
        self.assertIn('删除讲义相关内容',json.dumps(captured[0],ensure_ascii=False))
        self.assertIn('Hello',json.dumps(captured[0],ensure_ascii=False))
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_alternating_repeated_reads_stop_without_reexecuting(self):
        calls=[self.response('search',{'query':'Hello'}),self.response('read_file',{'path':'main.tex'})]*3
        with patch.object(self.ai,'tool',wraps=self.ai.tool) as tool:job=self.run_job(calls)
        self.assertFalse(job['success']);self.assertIn('重复',job['error'])
        self.assertEqual(tool.call_count,2)

    def test_false_completion_requires_real_candidate(self):
        job=self.run_job([self.response(message='已删除讲义相关内容',done=True),self.response(message='已删除讲义相关内容',done=True)])
        self.assertFalse(job['success']);self.assertFalse(job['changedPaths']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_continue_does_not_reuse_reads_after_external_change(self):
        first=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response('search',{'query':'Hello'})],stepLimit=2)
        (self.root/'main.tex').write_text('Changed externally','utf8')
        job=self.run_job([self.response('edit',{'path':'main.tex','before':'Changed','after':'Different'}),self.response(message='需要重新读取',done=True)],resume=first['id'],question='继续')
        self.assertFalse(job['changedPaths']);self.assertTrue(any(e['tool']=='edit' and e['status']=='failed' for e in job['events']))

    def test_large_prompt_usage_does_not_interrupt_edits_before_compile(self):
        responses=self.edit_responses()
        for response in responses:response['usage'].update(total_tokens=40000,prompt_tokens=39990)
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):job=self.run_job(responses)
        self.assertTrue(job['success']);self.assertTrue(job['verified']);self.assertGreater(job['tokens'],65000)

    def test_default_agent_can_finish_after_initial_steps_when_edits_progress(self):
        responses=[self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'})]
        responses += [self.response('edit',{'path':'main.tex','before':'Hello','after':'Hello x'}) for _ in range(23)]
        responses += [self.response('compile'),self.response(message='候选已验证',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):job=self.run_job(responses,stepLimit=24)
        self.assertTrue(job['success']);self.assertTrue(job['verified']);self.assertGreater(job['requestCount'],24)

    def test_chat_cannot_modify_or_compile(self):
        with patch.object(self.ai,'compile_copy') as compiler:j=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'Hello','after':'Changed'}),self.response('compile'),self.response(message='Chat 只讨论',done=True)],'chat')
        compiler.assert_not_called();self.assertFalse(j['changedPaths']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original);self.assertEqual(sum(e['status']=='failed' for e in j['events']),2)
    def test_compile_failure_is_returned_to_agent_and_fixed(self):
        responses=[self.response('read_file',{'path':'main.tex'}),self.response('compile'),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response('compile'),self.response(message='修复完成',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler) as compiler:j=self.run_job(responses)
        self.assertEqual(compiler.call_count,2);self.assertTrue(j['verified']);self.assertTrue(j['success'])
    def test_done_cannot_bypass_failed_verification(self):
        with patch.object(self.ai,'compile_copy',return_value=(False,'bad')):j=self.run_job(self.edit_responses()+[self.response(message='完成',done=True)]*10)
        self.assertFalse(j['verified']);self.assertFalse(j['success']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
        with self.assertRaises(ValueError):self.ai.apply(self.root,j['id'])
    def test_edit_requires_read_and_rejects_project_escape(self):
        j=self.run_job([self.response('edit',{'path':'main.tex','before':'Hello','after':'Changed'}),self.response('read_file',{'path':'../outside.txt'}),self.response(message='需要有效范围',done=True)])
        self.assertEqual(sum(e['status']=='failed' for e in j['events']),2);self.assertFalse(j['changedPaths'])
    def test_identical_tools_stop_instead_of_burning_budget(self):
        j=self.run_job([self.response('list_files')]*4);self.assertEqual(j['requestCount'],3);self.assertFalse(j['success']);self.assertIn('重复',j['error'])
    def test_compile_result_reused_until_an_edit_changes_revision(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler) as compiler:j=self.run_job([self.response('compile'),self.response('compile'),self.response(message='需修改',done=True)])
        self.assertEqual(compiler.call_count,1)
    def test_attachment_access_is_explicit_and_project_scoped(self):
        a=self.ai.attachment(self.root,{'name':'notes.txt','content':base64.b64encode(b'Guidance').decode()})
        other=self.base/'other';other.mkdir()
        with self.assertRaises(ValueError):self.ai.attachment_meta(other,a['id'])
        j=self.run_job([self.response('read_attachment',{'id':a['id']}),self.response(message='附件可读',done=True)],'chat',attachments=[a['id']]);self.assertTrue(j['success'])
    def test_pending_candidates_survive_follow_up_without_writing_original(self):
        first=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response(message='还需确认细节',question=True)])
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):second=self.run_job([self.response('compile'),self.response(message='完成',done=True)],resume=first['id'])
        self.assertTrue(second['verified']);self.assertEqual(second['changedPaths'],['main.tex']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_stale_candidate_cannot_overwrite_later_source(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):j=self.run_job(self.edit_responses())
        (self.root/'main.tex').write_text('later work','utf8')
        with self.assertRaises(ValueError):self.ai.apply(self.root,j['id'])
    def test_cancellation_discards_late_model_output(self):
        entered=threading.Event();release=threading.Event()
        def remote(*a,**k):entered.set();release.wait(3);return self.response('edit',{'path':'main.tex','before':'Hello','after':'Changed'})
        with patch('studio_ai.request_json',side_effect=remote):
            job=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'修改正文'});self.assertTrue(entered.wait(2));self.ai.cancel(self.root,job['id']);j=self.wait(job['id']);release.set()
        self.assertFalse(j['success']);self.assertFalse(j['changedPaths']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_chat_history_is_compacted_locally_and_keeps_latest_question(self):
        first=self.run_job([self.response(message='上下文已了解',done=True)],'chat')
        with patch('studio_ai.request_json',return_value=self.response(message='继续回答',done=True)) as remote:
            job=self.ai.start(self.root,'main.tex',{'mode':'chat','question':'后续问题','resume':first['id']});j=self.wait(job['id'])
        messages=remote.call_args.args[1]['messages'];self.assertIn('后续问题',messages[-1]['content']);self.assertTrue(any(m['content']=='上下文已了解' for m in messages));self.assertEqual(j['requestCount'],1)

    def test_mixed_tool_batch_executes_read_before_edit_and_compile(self):
        batch=self.response();batch['choices'][0]['message']['content']=json.dumps({'message':'读取后修改并验证','calls':[{'tool':'read_file','args':{'path':'main.tex'}},{'tool':'edit','args':{'path':'main.tex','before':'textbff','after':'textbf'}},{'tool':'compile','args':{}}]})
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):j=self.run_job([batch,self.response(message='完成',done=True)])
        self.assertTrue(j['verified']);self.assertEqual(j['requestCount'],2)
    def test_bad_json_can_be_corrected_without_restarting_the_task(self):
        bad={'choices':[{'finish_reason':'stop','message':{'content':'{' }}]}
        j=self.run_job([bad,self.response(message='已纠正格式',done=True)],'chat')
        self.assertTrue(j['success']);self.assertEqual(j['requestCount'],2)

    def test_attachment_images_are_downscaled_before_model_input(self):
        import io
        from PIL import Image
        from studio_document_assistant import image_payload
        path=self.base/'large.png';Image.new('RGB',(3200,2400),'white').save(path)
        encoded=image_payload(path);raw=base64.b64decode(encoded.split(',',1)[1])
        with Image.open(io.BytesIO(raw)) as image:self.assertEqual(image.size,(1600,1200))
        self.assertLess(len(raw),path.stat().st_size)
    def test_chat_can_discuss_pending_agent_changes_without_write_permission(self):
        first=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response(message='需要继续',question=True)])
        second=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response(message='解释候选',done=True)],'chat',resume=first['id'])
        self.assertTrue(second['changedPaths'])
        with self.assertRaisesRegex(ValueError,'Chat'):self.ai.apply(self.root,second['id'])
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_native_tool_results_are_linked_to_the_actual_assistant_call(self):
        native={'choices':[{'finish_reason':'tool_calls','message':{'content':None,'tool_calls':[{'id':'call-read','type':'function','function':{'name':'read_file','arguments':json.dumps({'path':'main.tex'})}}]}}]}
        answer={'choices':[{'finish_reason':'stop','message':{'content':'已查看源码，命令拼写有误。'}}]}
        with patch('studio_ai.request_json',side_effect=[native,answer]) as remote:
            start=self.ai.start(self.root,'main.tex',{'mode':'chat','question':'解释文件'});j=self.wait(start['id'])
        self.assertTrue(j['success']);payload=remote.call_args.args[1];self.assertIn('tools',payload);self.assertNotIn('response_format',payload)
        self.assertTrue(any(m['role']=='tool' and m['tool_call_id']=='call-read' for m in payload['messages']))
    def test_final_legacy_answer_does_not_require_done_flag(self):
        answer=self.response();answer['choices'][0]['message']['content']=json.dumps({'message':'检查结果：字号较小，应核对正文可读性。','calls':[]})
        j=self.run_job([answer],'chat');self.assertTrue(j['success']);self.assertIn('检查结果',j['answer'])
    def test_partial_layout_findings_are_not_replaced_by_a_generic_error(self):
        result=self.ai.partial_report({'layoutEvidence':{'pages':[1,3],'totalPages':5,'issues':[{'page':3,'message':'正文过小'}]}},'模型连接失败')
        self.assertIn('第 3 页',result);self.assertIn('正文过小',result);self.assertIn('模型连接失败',result)

    def test_cancel_during_tool_does_not_run_the_next_tool_in_the_batch(self):
        entered=threading.Event();release=threading.Event();called=[]
        def blocked(s,clone,name,args,read):
            called.append(name);entered.set();release.wait(2);return {'totalLines':4}
        batch=self.response();batch['choices'][0]['message']['content']=json.dumps({'calls':[{'tool':'read_file','args':{'path':'main.tex'}},{'tool':'edit','args':{'path':'main.tex','before':'Hello','after':'Changed'}}]})
        with patch.object(self.ai,'tool',side_effect=blocked),patch('studio_ai.request_json',return_value=batch):
            start=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'检查文件'});self.assertTrue(entered.wait(2));stopping=self.ai.cancel(self.root,start['id']);self.assertTrue(stopping['stopRequested']);release.set();j=self.wait(start['id'])
        self.assertEqual(called,['read_file']);self.assertFalse(j['success']);self.assertIn('已停止',j['messages'][-1]['content']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_layout_inspection_checks_cancellation_between_pages(self):
        from pypdf import PdfWriter
        from studio_review import inspect_pdf
        pdf=self.base/'two-pages.pdf';writer=PdfWriter();writer.add_blank_page(600,800);writer.add_blank_page(600,800)
        with pdf.open('wb') as f:writer.write(f)
        checked=[]
        inspect_pdf(pdf,checkpoint=lambda:checked.append(True));self.assertEqual(len(checked),2)
        with self.assertRaisesRegex(ValueError,'stopped'):inspect_pdf(pdf,checkpoint=lambda:(_ for _ in ()).throw(ValueError('stopped')))

    def test_discussing_verified_changes_does_not_compile_them_again(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):first=self.run_job(self.edit_responses())
        with patch.object(self.ai,'compile_copy') as compiler,patch('studio_ai.request_json',return_value=self.response(message='简短说明：只修复命令拼写。',done=True)):
            job=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'刚才的回复简短一点，不要改文档','resume':first['id']});second=self.wait(job['id'])
        compiler.assert_not_called();self.assertTrue(second['verified']);self.assertTrue(second['candidateReady']);self.assertEqual((self.root/'main.tex').read_bytes(),self.original)
    def test_changed_source_does_not_block_a_follow_up_discussion(self):
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):first=self.run_job(self.edit_responses())
        (self.root/'main.tex').write_text('User later changes','utf8')
        second=self.run_job([self.response(message='讨论当前版本',done=True)],'chat',resume=first['id'])
        self.assertTrue(second['success']);self.assertFalse(second['changedPaths']);self.assertEqual((self.root/'main.tex').read_text('utf8'),'User later changes')
    def test_follow_up_does_not_automatically_repeat_prior_layout_review(self):
        first=self.run_job([self.response(message='已完成排版检查',done=True)],'chat')
        with patch.object(self.ai,'compile_copy') as compiler,patch.object(self.ai,'tool') as tool:
            second=self.run_job([self.response(message='缩短配套文件说明',done=True)],resume=first['id'],question='配套文件与复现方法不用说这么仔细')
        compiler.assert_not_called();tool.assert_not_called();self.assertTrue(second['success'])

    def test_discussing_unverified_candidates_does_not_force_compilation_or_allow_apply(self):
        first=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response(message='待继续',question=True)])
        with patch.object(self.ai,'compile_copy') as compiler:second=self.run_job([self.response(message='简短解释候选修改',done=True)],resume=first['id'],question='只解释刚才的修改，不要执行')
        compiler.assert_not_called();self.assertTrue(second['success']);self.assertFalse(second['candidateReady']);self.assertFalse(second['verified'])
        with self.assertRaises(ValueError):self.ai.apply(self.root,second['id'])
    def test_inspection_can_report_a_compile_error_without_being_forced_to_edit(self):
        with patch.object(self.ai,'compile_copy',return_value=(False,'Undefined control sequence')):j=self.run_job([self.response('compile'),self.response(message='编译失败，命令拼写有误。未修改文档。',done=True)],question='只检查能否编译，不要修改')
        self.assertTrue(j['success']);self.assertFalse(j['changedPaths']);self.assertFalse(j['verified'])

if __name__=='__main__':unittest.main()
