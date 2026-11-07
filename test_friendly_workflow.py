import copy
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_batch_edits as batch_fixture
from studio_ai import Assistant
from studio_page_edits import PageEdits,save_source_map
from studio_change_focus import focus,locate

class HistoryTests(unittest.TestCase):
    setUp=batch_fixture.BatchTests.setUp
    tearDown=batch_fixture.BatchTests.tearDown
    edits=batch_fixture.BatchTests.edits
    preview=batch_fixture.BatchTests.preview

    def attach(self):
        result={'summary':'mock','edits':self.edits()}
        self.manager.attach_batch(self.context['id'],self.root,result)
        return result

    def test_restart_keeps_source_bytes_edits_selection_and_preview(self):
        result=self.attach();preview=self.preview()
        self.manager.save_view(self.context['id'],self.root,{'selected':[1],'view':'comparison','settings':{'task':'polish','instruction':'example','key':'NEVER'}})
        s=self.manager.sessions[self.context['id']];s['imagePages']={};self.manager.remember(s)
        fresh=PageEdits(self.manager.storage);detail=fresh.describe_task(self.context['id'],self.root,self.pdf)
        self.assertEqual(detail['result'],result);self.assertEqual(detail['preview']['id'],preview['id']);self.assertEqual(detail['view']['selected'],[1]);self.assertFalse(detail['stale'])
        self.assertEqual(fresh.sessions[self.context['id']]['files']['a.tex']['originalBytes'],self.originals['a.tex'])
        self.assertNotIn('key',detail['view']['settings']);self.assertFalse((Path(fresh.sessions[self.context['id']]['folder'])/'project').exists())
        self.assertEqual(len(fresh.task_list(self.root,self.pdf)),1)

    def test_evicted_preview_images_are_regenerated_from_saved_pdfs(self):
        self.attach();self.preview();session=self.manager.sessions[self.context['id']]
        path=Path(session['imagePages']['1']['after']);path.unlink()
        replacement=Path(self.temp.name)/'regenerated.png';replacement.write_bytes(b'cached')
        with patch('studio_page_edits.page_image',return_value=replacement) as render:
            self.assertEqual(self.manager.image(session['id'],self.root,'after',1),replacement)
            self.assertEqual(render.call_args.args[0],Path(session['candidatePdf']))

    def test_invalid_batch_does_not_leave_internal_source_copies(self):
        before=set(self.manager.sessions)
        with self.assertRaises(ValueError):self.manager.prepare_pages(self.root,'main.tex',self.pdf,[1,999])
        self.assertEqual(set(self.manager.sessions),before)

    def test_stale_task_survives_but_cannot_apply(self):
        self.attach();(self.root/'a.tex').write_bytes(self.originals['a.tex']+b'% new user content\r\n')
        self.assertTrue(PageEdits(self.manager.storage).describe_task(self.context['id'],self.root,self.pdf)['stale'])
        with self.assertRaises(ValueError):self.manager.preview(self.context['id'],self.root,self.pdf,[0])
        self.assertTrue(self.manager.readiness(self.root,'main.tex',self.pdf)['needsCompile'])

    def test_rebase_keeps_user_changes_and_original_encoding_without_ai(self):
        self.attach();extra=b'% user addition\r\n';(self.root/'a.tex').write_bytes(extra+self.originals['a.tex'])
        # Keep BOM at file start, with new material before the original text.
        raw=b'\xef\xbb\xbf'+extra+self.originals['a.tex'][3:];(self.root/'a.tex').write_bytes(raw)
        save_source_map(self.root,'main.tex',self.pdf,Path(self.temp.name)/'main.synctex.gz',self.data)
        with patch('studio_ai.request_json',side_effect=AssertionError('no API allowed')):
            new=self.manager.rebase(self.context['id'],self.root,'main.tex',self.pdf,[0])
        self.assertNotEqual(new['id'],self.context['id']);self.assertTrue(new['result']['rebased']);self.assertEqual(new['view']['selected'],[0]);self.assertIn('% user addition',new['source'])
        self.assertEqual(self.manager.sessions[new['id']]['files']['a.tex']['originalBytes'],raw)
        self.assertEqual(len(new['result']['edits']),2);self.assertEqual((self.root/'a.tex').read_bytes(),raw)
        self.assertEqual(len(self.manager.task_list(self.root,self.pdf)),2)

    def test_ambiguous_rebase_rejects_changed_page_keeps_other_page(self):
        self.attach();(self.root/'a.tex').write_bytes(self.originals['a.tex']+b'An eror.\r\n')
        save_source_map(self.root,'main.tex',self.pdf,Path(self.temp.name)/'main.synctex.gz',self.data)
        new=self.manager.rebase(self.context['id'],self.root,'main.tex',self.pdf,[0,1]);self.assertEqual(len(new['result']['edits']),1);self.assertEqual(new['result']['edits'][0]['path'],'b.tex');self.assertTrue(new['result']['rejected'])
        self.assertEqual(len(self.manager.sessions[self.context['id']]['edits']),2)

    def test_interrupted_job_keeps_completed_page_and_pending_retry(self):
        result=self.attach();result['pageStates']=[{'part':0,'page':1,'status':'completed'},{'part':1,'page':2,'status':'running'}];self.manager.remember(self.manager.sessions[self.context['id']])
        self.manager.bind_job(self.context['id'],self.root,{'id':'job','running':True,'task':'pages_edit','success':None}, {'task':'pages_edit','instruction':'example','key':'NEVER'})
        c=PageEdits(self.manager.storage).describe_task(self.context['id'],self.root,self.pdf)
        self.assertFalse(c['job']['running']);self.assertEqual(c['result']['pendingPages'],[2]);self.assertEqual(c['result']['pageStates'][0]['status'],'completed');self.assertEqual(len(c['result']['edits']),2);self.assertNotIn('key',c['request'])

    def test_retry_only_renders_failed_pages_and_rejects_completed_pages(self):
        result=self.attach();result['failedPages']=[2];result['pendingPages']=[]
        from PIL import Image
        image=Path(self.temp.name)/'p.png';Image.new('RGB',(5,5),'white').save(image)
        with patch('studio_review.page_image',return_value=image) as render:
            parts,images=self.manager.batch_input(self.context['id'],self.root,self.pdf,[2])
            self.assertEqual([p['page'] for p in parts],[2]);self.assertEqual(render.call_count,1)
        for bad in [[1],[True],[],[3]]:
            with self.assertRaises(ValueError):self.manager.batch_input(self.context['id'],self.root,self.pdf,bad)

    def test_history_is_confined_to_project_and_invalid_ids_rejected(self):
        self.attach();fresh=PageEdits(self.manager.storage)
        for ident,root in [(self.context['id'],self.root.parent),('../x',self.root)]:
            with self.assertRaises(ValueError):fresh.context(ident,root)
        self.assertEqual(fresh.task_list(self.root.parent,self.pdf),[])

    def test_real_pdf_text_focus_and_pixel_fallback(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        textpdf=Path(self.temp.name)/'text.pdf';writer=PdfWriter()
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        for text in ['An eror.','A corrected error.']:
            page=writer.add_blank_page(width=595,height=842);page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(('BT /F1 12 Tf 70 720 Td ('+text+') Tj ET').encode());page[NameObject('/Contents')]=writer._add_object(stream)
        writer.write(textpdf)
        box=locate(textpdf,1,'An eror.');self.assertEqual(box['page'],1);self.assertTrue(all(0<=v<=1 for v in box['box']))
        self.assertEqual(locate(textpdf,1,'corrected error.',True)['page'],2);self.assertIsNone(locate(textpdf,1,'\\small'))
        self.attach();s=self.manager.sessions[self.context['id']];s['edits'][0].update(before='\\small',after='\\normalsize');s['preview']={'success':True,'id':'preview','selected':[0],'totalPages':2,'pages':[{'page':1,'bounds':[.1,.2,.8,.7]}]};s['candidatePdf']=str(textpdf)
        located=focus(self.manager,s['id'],self.root,index=0,preview_id='preview');self.assertEqual(located['kind'],'pixels');self.assertEqual(located['after']['box'],[.1,.2,.8,.7])

class ProgressiveTests(unittest.TestCase):
    def test_progress_publishes_before_next_request_and_retry_preserves_completed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            ai=Assistant(folder);ai.config=lambda raw=False:{'deepseek':{'configured':True,'key':'mock','model':'mock'}}
            parts=[{'part':i,'page':i+1,'path':f'{i}.tex','source':'An eror.','displayStart':i*40} for i in range(2)]
            images=[{'page':i+1,'image':'data:image/png;base64,dGVzdA=='} for i in range(2)];events=[];calls=[]
            reply={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'fix','edits':[{'before':'eror','after':'error','reason':'typo'}]})}}],'usage':{'total_tokens':9}}
            def request(*args,**kwargs):
                calls.append(args[1]);self.assertEqual(sum(b['type']=='image_url' for b in args[1]['messages'][1]['content']),1)
                if len(calls)==2:
                    self.assertTrue(any(len(r['edits'])==1 and r['pageStates'][0]['status']=='completed' for r in events));raise ValueError('mock second-page failure')
                return reply
            def wait():
                deadline=time.monotonic()+5
                while ai.busy() and time.monotonic()<deadline:threading.Event().wait(.01)
                self.assertFalse(ai.busy())
            with patch('studio_ai.request_json',side_effect=request):
                ai.start({'task':'pages_edit','provider':'deepseek','text':'pages','parts':parts},'a'*20,images,on_progress=lambda r:events.append(copy.deepcopy(r)));wait()
                first=ai.status('a'*20)['result'];self.assertEqual(first['failedPages'],[2]);self.assertEqual(first['usage']['total_tokens'],9)
                ai.start({'task':'pages_edit','provider':'deepseek','text':'retry','parts':[parts[1]],'allParts':parts,'seedPageStates':first['pageStates']},'a'*20,[images[1]]);wait()
            final=ai.status('a'*20);self.assertTrue(final['success']);self.assertEqual(len(calls),3);self.assertEqual(final['requestCount'],1);self.assertEqual([e['page'] for e in final['result']['edits']],[1,2]);self.assertEqual(final['result']['usage']['total_tokens'],18);self.assertEqual([p['attempts'] for p in final['result']['pageStates']],[1,2])

if __name__=='__main__':unittest.main()
