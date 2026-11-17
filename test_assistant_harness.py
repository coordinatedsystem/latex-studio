import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio_assistant_session import SessionJournal,ModelContext,ToolCallRecovery,encoded
from studio_assistant_tools import ToolRegistry,ToolSpec,builtin_schemas
import test_document_assistant as fixtures

class HarnessContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'events.jsonl';self.journal=SessionJournal(self.path)
    def record(self,n,text='source'):
        return {'tool':'read_file','args':{'path':'main.tex','start':n},'summary':{'totalLines':100},'content':text,'nativeCall':{'id':'read'+str(n),'type':'function','function':{'name':'read_file','arguments':'{}'}}}
    def test_normal_growth_keeps_every_previous_message_byte_identical(self):
        context=ModelContext([{'role':'system','content':'stable'},{'role':'user','content':'goal'}],self.journal)
        trail=[];previous=[]
        for n in range(8):
            messages,stats=context.prepare(trail)
            self.assertEqual(messages[:len(previous)],previous)
            if previous:self.assertGreater(stats['reusedPrefixChars'],0)
            previous=copy.deepcopy(messages);trail.append(self.record(n))
        self.assertEqual(SessionJournal(self.path).request_contexts()[-1],previous)
    def test_compaction_retains_current_goal_and_recent_results_without_extra_model_call(self):
        context=ModelContext([{'role':'user','content':'DELETE LECTURE SECTION'}],self.journal,max_chars=9000)
        trail=[self.record(n,'text '+str(n)+' x'*2000) for n in range(8)]
        messages,stats=context.prepare(trail)
        self.assertGreater(stats['compactions'],0)
        self.assertIn('DELETE LECTURE SECTION',encoded(messages));self.assertIn('text 7',encoded(messages))
    def test_journal_recovers_only_an_incomplete_tail(self):
        self.journal.append('turn/start',{'mode':'agent'})
        with self.path.open('ab') as file:file.write(b'{"seq":2')
        restored=SessionJournal(self.path)
        self.assertEqual(restored.events[-1]['type'],'session/recovered')
        self.assertEqual(len(list(self.path.parent.glob('*.interrupted-*'))),1)
    def test_complete_corrupt_line_is_not_silently_discarded(self):
        self.path.write_bytes(b'bad\n')
        with self.assertRaises(ValueError):SessionJournal(self.path)
    def test_projection_copy_cannot_mutate_logged_request(self):
        messages,_=self.journal.context([{'role':'user','content':'original'}]);messages[0]['content']='changed'
        self.assertEqual(SessionJournal(self.path).request_contexts()[0][0]['content'],'original')
    def test_recovery_distinguishes_unstarted_and_unknown_operations(self):
        calls=[{'id':'one','tool':'edit','args':{}},{'id':'two','tool':'compile','args':{}}]
        recovery=ToolCallRecovery(calls);recovery.started(calls[0]);records=recovery.recover()
        self.assertEqual(records[0]['summary']['error'],'TOOL_OUTCOME_UNKNOWN')
        self.assertEqual(records[1]['summary']['error'],'ABORTED_BEFORE_DISPATCH')
        self.assertEqual(recovery.recover(),[])
    def test_restart_recovers_logged_result_and_marks_uncertain_edit_without_dispatch(self):
        self.journal.context([{'role':'user','content':'goal'}],request=False)
        self.journal.append('turn/start',{'mode':'agent'});self.journal.append('step/start',{'step':1})
        calls=[{'id':'read1','tool':'read_file','args':{'path':'main.tex'}},{'id':'edit1','tool':'edit','args':{'path':'main.tex','before':'a','after':'b'}}]
        self.journal.append('assistant/response',{'step':1,'value':{'calls':calls}})
        self.journal.append('tool/call',{'step':1,'id':'read1'});self.journal.append('tool/result',{'step':1,'id':'read1','result':{'text':'real source'}})
        self.journal.append('tool/call',{'step':1,'id':'edit1'})
        restored=SessionJournal(self.path);restored.recover_interrupted_turn()
        self.assertIn('real source',encoded(restored.messages));self.assertIn('TOOL_OUTCOME_UNKNOWN',encoded(restored.messages))
        count=len(restored.events);restored.recover_interrupted_turn();self.assertEqual(len(restored.events),count)
        self.assertEqual(restored.events[-1]['type'],'turn/end')

    def test_registry_permission_and_schema_are_the_same_registration(self):
        registry=ToolRegistry();schema=next(s for s in builtin_schemas('agent') if s['function']['name']=='edit')
        spec=ToolSpec(schema,lambda:None,('agent',),True);dispose=registry.register(spec)
        self.assertEqual(registry.schemas('chat'),[])
        with self.assertRaises(ValueError):registry.resolve('edit','chat')
        self.assertTrue(registry.resolve('edit','agent').exclusive)
        with self.assertRaises(ValueError):registry.register(spec)
        registry.schemas('agent')[0]['function']['name']='mutated';self.assertEqual(spec.name,'edit')
        dispose();dispose();self.assertEqual(registry.schemas('agent'),[])

class HarnessIntegrationTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp;response=fixtures.AssistantTests.response;run_job=fixtures.AssistantTests.run_job;wait=fixtures.AssistantTests.wait;compiler=fixtures.AssistantTests.compiler;edit_responses=fixtures.AssistantTests.edit_responses
    def test_request_log_reconstructs_exact_network_messages_and_excludes_key(self):
        responses=iter(self.edit_responses());sent=[]
        def remote(url,payload,headers):sent.append(copy.deepcopy(payload['messages']));return next(responses)
        with patch('studio_ai.request_json',side_effect=remote),patch.object(self.ai,'compile_copy',side_effect=self.compiler):
            job=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'修复拼写','stepLimit':12});job=self.wait(job['id'])
        self.assertTrue(job['success'])
        path=self.ai.folder(self.root,job['id'])/'events.jsonl';journal=SessionJournal(path)
        self.assertEqual(journal.request_contexts(),sent)
        self.assertNotIn('Bearer',path.read_text('utf8'));self.assertNotIn('mock-only',path.read_text('utf8'))
        for a,b in zip(sent,sent[1:]):self.assertEqual(b[:len(a)],a)
    def test_transient_provider_failure_retries_same_request_without_repeating_edit(self):
        responses=[ValueError('服务请求失败（HTTP 503）')]+self.edit_responses()
        with patch.object(self.ai.cancel_event,'wait',return_value=False),patch.object(self.ai,'compile_copy',side_effect=self.compiler):job=self.run_job(responses)
        self.assertTrue(job['success']);self.assertEqual(job['requestCount'],5)
        self.assertEqual(sum(e['tool']=='edit' and e['status']=='done' for e in job['events']),1)
        journal=SessionJournal(self.ai.folder(self.root,job['id'])/'events.jsonl')
        self.assertEqual(len(journal.request_contexts(attempts=True)),5)
        self.assertEqual(journal.request_contexts(attempts=True)[0],journal.request_contexts(attempts=True)[1])
    def test_cancellation_settles_undispatched_native_calls_without_editing(self):
        native={'choices':[{'finish_reason':'tool_calls','message':{'content':'读取后再修改','tool_calls':[{'id':'read1','type':'function','function':{'name':'read_file','arguments':json.dumps({'path':'main.tex'})}},{'id':'edit1','type':'function','function':{'name':'edit','arguments':json.dumps({'path':'main.tex','before':'Hello','after':'Changed'})}}]}}]}
        original_tool=self.ai.tool
        def cancel_after_read(*args,**kwargs):
            result=original_tool(*args,**kwargs);self.ai.cancel_event.set();return result
        with patch.object(self.ai,'tool',side_effect=cancel_after_read):job=self.run_job([native])
        self.assertFalse(job['success']);self.assertFalse(job['changedPaths'])
        journal=SessionJournal(self.ai.folder(self.root,job['id'])/'events.jsonl')
        recovered=[e for e in journal.events if e['type']=='tool/recovered']
        self.assertEqual(len(recovered),1);self.assertEqual(recovered[0]['data']['summary']['error'],'ABORTED_BEFORE_DISPATCH')
        self.assertEqual(journal.events[-1]['type'],'turn/end')
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_event_storage_initialization_failure_releases_running_state(self):
        with patch('studio_assistant_session.SessionJournal',side_effect=ValueError('invalid stored events')):job=self.run_job([])
        self.assertFalse(job['success']);self.assertFalse(self.ai.busy())

    def test_fatal_credentials_error_is_not_retried(self):
        job=self.run_job([ValueError('服务请求失败（HTTP 401）：密钥无效')])
        self.assertFalse(job['success']);self.assertEqual(job['requestCount'],1)
    def test_continue_restores_the_logged_prefix_before_new_user_goal(self):
        first=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response('search',{'query':'Hello'})],question='修复命令拼写',stepLimit=2)
        old=SessionJournal(self.ai.folder(self.root,first['id'])/'events.jsonl').messages
        seen=[];responses=iter([self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response('compile'),self.response(message='完成',done=True)])
        def remote(url,payload,headers):seen.append(copy.deepcopy(payload['messages']));return next(responses)
        with patch('studio_ai.request_json',side_effect=remote),patch.object(self.ai,'compile_copy',side_effect=self.compiler):
            job=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'继续','resume':first['id'],'stepLimit':8});job=self.wait(job['id'])
        self.assertTrue(job['success']);self.assertEqual(seen[0][:len(old)],old)
        self.assertIn('继续',seen[0][len(old)]['content'])


class RepeatedCallProgressTests(unittest.TestCase):
    """Regressions for the stalled-edit turn: repeats redirect, they do not hand the task back."""
    setUp=fixtures.AssistantTests.setUp;response=fixtures.AssistantTests.response;run_job=fixtures.AssistantTests.run_job;wait=fixtures.AssistantTests.wait;compiler=fixtures.AssistantTests.compiler

    def test_elided_edit_arguments_are_absent_instead_of_fake_anchors(self):
        from studio_assistant_context import compact_tool,ELIDED_MARK
        body='x'*900
        record={'tool':'edit','args':{'path':'main.tex','before':body,'after':'short'},'summary':{'edits':1},'content':body}
        compact=compact_tool(record)
        self.assertNotIn('before',compact['args']);self.assertNotIn(body,json.dumps(compact,ensure_ascii=False))
        self.assertNotIn(ELIDED_MARK,json.dumps(compact,ensure_ascii=False))
        self.assertEqual(record['args']['before'],body)
        short={'tool':'edit','args':{'path':'main.tex','before':'Hello','after':'Bye'},'summary':{'edits':1},'content':'ok'}
        self.assertEqual(compact_tool(short)['args']['before'],'Hello')

    def test_placeholder_edit_is_rejected_with_a_specific_instruction(self):
        calls=[self.response('read_file',{'path':'main.tex'}),
               self.response('edit',{'path':'main.tex','before':'[已执行的历史替换内容，共 32 字符]','after':'x'}),
               self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),
               self.response('compile'),self.response(message='已完成',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler) as compiler:job=self.run_job(calls)
        self.assertTrue(job['success']);self.assertTrue(job['verified'])
        failed=next(e for e in job['events'] if e['tool']=='edit' and e['status']=='failed')
        self.assertIn('占位',failed['detail'])

    def test_identical_edit_retry_is_skipped_and_the_turn_still_compiles(self):
        calls=[self.response('read_file',{'path':'main.tex'}),
               self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),
               self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),
               self.response('compile'),self.response(message='已修复并通过验证',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler) as compiler:
            with patch.object(self.ai,'tool',wraps=self.ai.tool) as tool:job=self.run_job(calls)
        self.assertTrue(job['success']);self.assertTrue(job['verified']);self.assertTrue(job['candidateReady'])
        self.assertEqual(compiler.call_count,1)
        self.assertEqual(sum(e['tool']=='edit' and e['status']=='done' for e in job['events']),1)
        self.assertEqual(tool.call_count,4) # automatic recovery compile, then a cached model compile

    def test_a_real_loop_is_still_stopped(self):
        calls=[self.response('list_files')]*6
        with patch.object(self.ai,'tool',wraps=self.ai.tool) as tool:job=self.run_job(calls)
        self.assertFalse(job['success']);self.assertIn('重复',job['error'])
        self.assertEqual(tool.call_count,1)

    def test_follow_up_reference_keeps_previous_answer_and_read_evidence(self):
        advice='一、确定偏僵硬（建议改写）\n1. 第 196 行：“虽……但……”建议只陈述数字。\n2. 第 202 行：删去“不宜据此推断”。'
        first=self.run_job([self.response('read_file',{'path':'main.tex'}),self.response(message=advice,done=True)],question='文章有没有僵硬的表达')
        self.assertTrue(first['success'])
        seen=[];responses=iter([self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response('compile'),self.response(message='已按建议修改',done=True)])
        def remote(url,payload,headers):seen.append(json.dumps(payload['messages'],ensure_ascii=False));return next(responses)
        with patch('studio_ai.request_json',side_effect=remote),patch.object(self.ai,'compile_copy',side_effect=self.compiler):
            job=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'把你建议改写的改一下','resume':first['id'],'stepLimit':8});job=self.wait(job['id'])
        self.assertTrue(job['success']);self.assertIn('第 202 行',seen[0]);self.assertIn('inspectedEarlier',seen[0])
        self.assertEqual((self.root/'main.tex').read_bytes(),self.original)


class PdfRenderSafetyTests(unittest.TestCase):
    """PDFium is process-global and not thread-safe: concurrent use poisoned every later load."""
    setUp=fixtures.AssistantTests.setUp;response=fixtures.AssistantTests.response;run_job=fixtures.AssistantTests.run_job;wait=fixtures.AssistantTests.wait;compiler=fixtures.AssistantTests.compiler

    def test_preview_verification_and_page_rendering_share_one_lock(self):
        import threading,tempfile
        from pathlib import Path
        from studio_pdfium import LOCK
        from studio_ai_quality import verify_preview_pdf
        from studio_review import page_image
        from test_fixture_pdf import write_fixture_pdf
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);pdf=Path(tmp.name)/'doc.pdf';write_fixture_pdf(pdf)
        errors=[];stop=threading.Event()
        def verify():
            while not stop.is_set():
                try:verify_preview_pdf(pdf)
                except Exception as exc:errors.append(repr(exc)[:120]);return
        def render():
            while not stop.is_set():
                try:page_image(pdf,Path(tmp.name)/'pages','0123456789abcdef0123',1,pdf.stat().st_mtime_ns)
                except Exception as exc:errors.append(repr(exc)[:120]);return
        threads=[threading.Thread(target=verify) for _ in range(2)]+[threading.Thread(target=render) for _ in range(2)]
        for thread in threads:thread.start()
        stop.wait(3);stop.set()
        for thread in threads:thread.join(10)
        self.assertEqual(errors,[])
        self.assertEqual(verify_preview_pdf(pdf),3)
        self.assertIs(LOCK,__import__('studio_pdfium',fromlist=['LOCK']).LOCK)

    def test_render_failure_is_not_reported_as_a_source_error(self):
        responses=[self.response('read_file',{'path':'main.tex'}),
                   self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),
                   self.response('compile'),self.response(message='需要重启渲染组件',question=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self._render_fail):
            job=self.run_job(responses)
        self.assertFalse(job['verified']);self.assertFalse(job['candidateReady'])
        self.assertIn('重启',job['answer'])
        event=next(e for e in job['events'] if e['tool']=='compile' and e['status']=='failed')
        self.assertIn('渲染',event['detail'])

    @staticmethod
    def _render_fail(s,clone,n):
        s['previewFailure']='候选 PDF 无法预览'
        return False,'compiled but render failed'

    def test_diagnostics_reports_the_newest_attempt_and_its_location(self):
        from studio_document_assistant import DocumentAssistant
        s={'main':'main.tex','chatMode':'agent','editRevision':3,'compiledRevision':3,'lastCompiled':False,'previewFailure':None,
           'lastLog':'error: main.tex:12: Undefined control sequence \foo\n'}
        ai=self.ai;clone=self.root
        result=ai.capabilities.execute(s,clone,'diagnostics',{},set())
        self.assertFalse(result['stale']);self.assertEqual(result['errorLine'],12);self.assertIn('main.tex',result['next'])


class CompileFailureGuidanceTests(unittest.TestCase):
    """The same compiler error after an edit means the edit missed; say so instead of repeating."""
    setUp=fixtures.AssistantTests.setUp;response=fixtures.AssistantTests.response;run_job=fixtures.AssistantTests.run_job;wait=fixtures.AssistantTests.wait

    def test_same_tex_error_after_edits_is_named_and_eventually_stopped(self):
        same=(False,'error: main.tex:3: Undefined control sequence \foo\n')
        responses=[self.response('read_file',{'path':'main.tex'}),
                   self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),
                   self.response('compile'),
                   self.response('edit',{'path':'main.tex','before':'Hello','after':'Hello!'}),
                   self.response('compile'),
                   self.response('edit',{'path':'main.tex','before':'Hello!','after':'Hello!!'}),
                   self.response('compile'),
                   self.response(message='完成',done=True)]
        with patch.object(self.ai,'compile_copy',return_value=same):job=self.run_job(responses)
        self.assertFalse(job['success']);self.assertIn('同一个编译错误',job['error'])
        self.assertTrue(any(e['tool']=='compile' and '第 3 行' in (e['detail'] or '') for e in job['events']))

    def test_failed_anchor_names_the_closest_line_or_escaping_problem(self):
        root=self.root
        body='\\documentclass{article}\n\\begin{document}\nHello \\textbff{world}.\n\\end{document}\n'
        (root/'main.tex').write_text(body,'utf8')
        # The model double-escaped the backslash; the file only has single backslashes.
        overescaped='\\\\textbff{world}'
        result=self.run_job([self.response('read_file',{'path':'main.tex'}),
                             self.response('edit',{'path':'main.tex','before':overescaped,'after':'x'}),
                             self.response(message='需要重新读取',question=True)])
        event=next(e for e in result['events'] if e['tool']=='edit' and e['status']=='failed')
        self.assertIn('反斜杠',event['detail'])

    def test_failed_anchor_points_at_the_current_line(self):
        root=self.root
        body='\\documentclass{article}\n\\begin{document}\nHello \\textbff{world}.\nMore text here.\n\\end{document}\n'
        (root/'main.tex').write_text(body,'utf8')
        result=self.run_job([self.response('read_file',{'path':'main.tex'}),
                             self.response('edit',{'path':'main.tex','before':'Some old sentence that is gone.','after':'x'}),
                             self.response(message='需要重新读取',question=True)])
        event=next(e for e in result['events'] if e['tool']=='edit' and e['status']=='failed')
        self.assertTrue('行' in event['detail'])
