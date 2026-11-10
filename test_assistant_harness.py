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
