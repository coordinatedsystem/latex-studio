"""Synthetic regressions for permissions, context isolation, progress and linked projects."""
import json,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from studio_assistant_policy import context_policy,approve,decide,schemas
from studio_project_sync import connect,synchronize,sha
from studio_assistant_browser import public_target
import test_document_assistant as fixtures

class AgentWorkspaceTests(unittest.TestCase):
    setUp=fixtures.AssistantTests.setUp
    response=fixtures.AssistantTests.response
    run_job=fixtures.AssistantTests.run_job
    wait=fixtures.AssistantTests.wait
    compiler=fixtures.AssistantTests.compiler

    def test_disabled_context_does_not_leak_previous_prefix_or_tools(self):
        first=self.run_job([self.response(message='OLD_HISTORY_SECRET',done=True)],mode='chat')
        seen=[]
        def remote(url,payload,headers):seen.append(payload);return self.response(message='new only',done=True)
        with patch('studio_ai.request_json',side_effect=remote):
            s=self.ai.start(self.root,'main.tex',{'mode':'chat','question':'new','resume':first['id'],
                'contextPolicy':{key:False for key in context_policy(None)}})
            job=self.wait(s['id'])
        self.assertTrue(job['success'])
        self.assertNotIn('OLD_HISTORY_SECRET',json.dumps(seen,ensure_ascii=False))
        self.assertFalse({'references','glossary','read_attachment','layout_check','read_page'} & {t['function']['name'] for t in seen[0]['tools']})
        with self.assertRaisesRegex(ValueError,'禁用'):
            self.ai.tool(self.ai.sessions[job['id']],self.root,'glossary',{},set())

    def test_auxiliary_edit_waits_for_real_ui_approval_and_can_undo(self):
        original=b'value = 1\r\n';(self.root/'helper.py').write_bytes(original)
        calls=[self.response('read_file',{'path':'helper.py'}),
            self.response('edit',{'path':'helper.py','before':'value = 1','after':'value = 2'}),
            self.response('compile'),self.response(message='候选通过验证',done=True)]
        def compile_ok(s,clone,n):
            pdf=self.ai.folder(s['root'],s['id'],True)/'candidate.pdf';pdf.parent.mkdir(parents=True,exist_ok=True);pdf.write_bytes(b'%PDF-1.5 test');return True,'ok'
        with patch('studio_ai.request_json',side_effect=calls),patch.object(self.ai,'compile_copy',side_effect=compile_ok):
            s=self.ai.start(self.root,'main.tex',{'mode':'agent','question':'更新 helper.py 中的 value','stepLimit':8})
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                live=self.ai.status(self.root,s['id'])
                if live.get('pendingPermission'):break
                time.sleep(.01)
            self.assertEqual((self.root/'helper.py').read_bytes(),original)
            self.assertEqual(live['pendingPermission']['target'],'helper.py')
            decide(self.ai,self.root,s['id'],live['pendingPermission']['id'],'once')
            job=self.wait(s['id'])
        self.assertTrue(job['success']);self.assertTrue(job['verified'])
        self.ai.apply(self.root,s['id']);self.assertIn('2',(self.root/'helper.py').read_text())
        self.ai.apply(self.root,s['id'],True);self.assertEqual((self.root/'helper.py').read_bytes(),original)

    def test_declined_permission_cannot_be_regranted_by_model_arguments(self):
        s={'chatMode':'agent','permissionDenied':[['auxiliary','helper.py']]}
        with self.assertRaisesRegex(ValueError,'拒绝'):approve(self.ai,s,'auxiliary','helper.py')

    def test_cancel_unblocks_pending_permission_without_dispatching(self):
        self.ai.journal=None
        s={'id':'0'*32,'root':str(self.root),'chatMode':'agent','revision':0,'running':True}
        errors=[]
        def worker():
            try:approve(self.ai,s,'auxiliary','helper.py')
            except ValueError as exc:errors.append(str(exc))
        thread=threading.Thread(target=worker);thread.start()
        deadline=time.monotonic()+2
        while not s.get('pendingPermission') and time.monotonic()<deadline:time.sleep(.01)
        self.assertTrue(s.get('pendingPermission'));self.ai.cancel_event.set();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertTrue(errors);self.assertIsNone(s.get('pendingPermission'))

    def test_renderer_failure_cannot_be_mistaken_for_source_repair(self):
        with self.assertRaisesRegex(ValueError,'渲染'):
            self.ai.capabilities.edit({'previewFailure':'renderer'},self.root,{'path':'main.tex'},set(),'edit')

    def test_semantically_repeated_candidate_is_detected_beyond_call_arguments(self):
        import hashlib
        full=(self.root/'main.tex').read_text('utf-8-sig');after=full.replace('Hello','Hi')
        digest=hashlib.sha256(after.encode('utf8')).hexdigest()
        s={'previewFailure':None,'chatMode':'agent','candidateFingerprints':{'main.tex':[digest,digest]}}
        with self.assertRaisesRegex(ValueError,'相同源码'):
            self.ai.capabilities.edit(s,self.root,{'path':'main.tex','before':'Hello','after':'Hi'}, {'main.tex'},'edit')

    def test_undo_does_not_restore_rejected_files_from_older_sessions(self):
        import base64
        helper=self.root/'helper.py';helper.write_bytes(b'value = 1\n')
        calls=[self.response('read_file',{'path':'main.tex'}),self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),self.response('compile'),self.response(message='通过验证',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):job=self.run_job(calls)
        s=self.ai.sessions[job['id']]
        s['originals']['helper.py']=base64.b64encode(helper.read_bytes()).decode()
        self.ai.apply(self.root,job['id']);helper.write_bytes(b'value = 9\n')
        self.ai.apply(self.root,job['id'],True)
        self.assertEqual(helper.read_bytes(),b'value = 9\n');self.assertEqual((self.root/'main.tex').read_bytes(),self.original)

    def test_browser_has_no_network_before_approval(self):
        with patch('socket.getaddrinfo') as dns,patch('studio_assistant_browser.browse') as fetch,patch('studio_assistant_policy.approve',side_effect=ValueError('denied')):
            with self.assertRaises(ValueError):self.ai.capabilities.browser({'chatMode':'agent'},self.root,{'url':'https://example.com'},set(),'browser')
            fetch.assert_not_called()
            dns.assert_not_called()

    def test_public_reader_rejects_private_addresses_and_file_urls(self):
        for url in ('file:///D:/secret','http://example.com','https://user:pass@example.com','https://example.com:8443'):
            with self.assertRaises(ValueError):public_target(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaisesRegex(ValueError,'内网'):public_target('https://example.com')

    def test_repeated_read_with_existing_candidate_compiles_without_another_request(self):
        read=self.response('read_file',{'path':'main.tex'})
        calls=[read,self.response('edit',{'path':'main.tex','before':'textbff','after':'textbf'}),read,read,self.response(message='候选已经通过验证',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler) as compile_copy:
            job=self.run_job(calls)
        self.assertTrue(job['success']);self.assertTrue(job['verified']);self.assertEqual(compile_copy.call_count,1)

    def test_mixed_repeat_and_real_progress_does_not_trigger_stall(self):
        def batch(calls):return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'calls':calls})}}],'usage':{}}
        calls=[self.response('read_file',{'path':'main.tex'}),self.response('list_files'),
               batch([{'tool':'list_files','args':{}},{'tool':'edit','args':{'path':'main.tex','before':'Hello','after':'Greetings'}}]),
               batch([{'tool':'list_files','args':{}},{'tool':'edit','args':{'path':'main.tex','before':'textbff','after':'textbf'}}]),
               self.response('compile'),self.response(message='候选通过验证',done=True)]
        with patch.object(self.ai,'compile_copy',side_effect=self.compiler):job=self.run_job(calls)
        self.assertTrue(job['success']);self.assertTrue(job['verified'])

class LinkedProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.local=self.base/'local';self.source=self.base/'source'
        self.local.mkdir();self.source.mkdir();self.store=SimpleNamespace(data=self.base/'data')
        for root in (self.local,self.source):(root/'main.tex').write_text('original','utf8')

    def test_both_directions_and_conflict_do_not_lose_either_version(self):
        self.assertFalse(connect(self.store,self.local,self.source)['conflicts'])
        (self.source/'main.tex').write_text('external','utf8')
        self.assertEqual(synchronize(self.store,self.local)['updated'][0]['direction'],'source')
        self.assertEqual((self.local/'main.tex').read_text(),'external')
        (self.local/'main.tex').write_text('editor','utf8');synchronize(self.store,self.local)
        self.assertEqual((self.source/'main.tex').read_text(),'editor')
        (self.local/'main.tex').write_text('local change','utf8');(self.source/'main.tex').write_text('other change','utf8')
        conflict=synchronize(self.store,self.local)['conflicts'][0]
        self.assertEqual((self.local/'main.tex').read_text(),'local change');self.assertEqual((self.source/'main.tex').read_text(),'other change')
        synchronize(self.store,self.local,{**conflict,'choice':'source'})
        self.assertEqual((self.local/'main.tex').read_text(),'other change')
        backups=[p.read_text() for p in (self.store.data/'sync-history').rglob('main.tex')]
        self.assertIn('local change',backups)

    def test_initial_differences_are_conflicts_not_guessed(self):
        (self.source/'main.tex').write_text('changed earlier','utf8')
        self.assertEqual(len(connect(self.store,self.local,self.source)['conflicts']),1)
        self.assertEqual((self.local/'main.tex').read_text(),'original')

    def test_stale_conflict_resolution_and_deletions_are_not_applied(self):
        connect(self.store,self.local,self.source)
        (self.source/'main.tex').unlink()
        conflict=synchronize(self.store,self.local)['conflicts'][0]
        self.assertTrue((self.local/'main.tex').exists())
        (self.local/'main.tex').write_text('new edit','utf8')
        with self.assertRaisesRegex(ValueError,'再次变化'):synchronize(self.store,self.local,{**conflict,'choice':'local'})

    def test_parent_directory_link_is_rejected(self):
        with self.assertRaises(ValueError):connect(self.store,self.local,self.base)

    def test_new_file_after_link_is_copied_without_deleting_existing(self):
        connect(self.store,self.local,self.source)
        (self.source/'new.csv').write_text('x,y\n1,2','utf8')
        synchronize(self.store,self.local)
        self.assertEqual((self.local/'new.csv').read_bytes(),(self.source/'new.csv').read_bytes())
