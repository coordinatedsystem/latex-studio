"""Connected review regression checks; all provider calls are local mocks."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pypdf import PdfWriter
from studio_ai import Assistant
from studio_document_context import reading_context
from studio_batch_edits import BatchEditsMixin

class DocumentContextTests(unittest.TestCase):
    def test_full_context_includes_sources_outline_and_all_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'main.tex').write_text('\\section{First}\nAlpha\n\\section{Second}\nBeta','utf8')
            writer=PdfWriter();writer.add_blank_page(595,842);writer.add_blank_page(595,842);pdf=root/'document.pdf';writer.write(pdf)
            value,adjacent=reading_context(root,'main.tex',pdf,[1,2],True)
            self.assertIn('Alpha',value['documentSource']);self.assertEqual([i['title'] for i in value['outline']],['First','Second'])
            self.assertEqual([i['page'] for i in value['pageSummaries']],[1,2]);self.assertEqual(set(adjacent),{'1','2'})
            with self.assertRaisesRegex(ValueError,'所有页面'):reading_context(root,'main.tex',pdf,[1],True)
            (root/'main.tex').write_text('a'*60001,'utf8')
            with self.assertRaisesRegex(ValueError,'尚未调用 AI'):reading_context(root,'main.tex',pdf,[1,2],True)

    def test_shared_context_previous_summary_and_readonly_edits(self):
        with tempfile.TemporaryDirectory() as folder:
            ai=Assistant(folder);ai.job={};seen=[];overview={'summary':'Use consistent terms','issues':[],'tokens':5,'completed':True}
            parts=[{'part':n,'page':n+1,'path':'main.tex','source':'An eror.','displayStart':n*20,'readOnly':n==1,'adjacent':{'1':'Opening'}} for n in range(2)]
            options={'parts':parts,'allParts':parts,'images':[{'page':1},{'page':2}],'wholeDocument':True,'documentContext':{'outline':['First']},'pageContext':'mock'}
            def edit(text,opts,config):
                seen.append(copy.deepcopy(opts));return {'summary':'page summary','edits':[{'start':3,'end':7,'before':'eror','after':'error'}],'usage':{'total_tokens':2}}
            with patch.object(ai,'document_overview',return_value=overview) as global_call,patch.object(ai,'page_edit',side_effect=edit):
                result=ai.page_workflow(options,{})
                self.assertEqual(global_call.call_count,1);self.assertEqual(len(result['edits']),1);self.assertEqual(result['usage']['total_tokens'],9)
                self.assertEqual(seen[1]['recentSummaries'],[{'page':1,'summary':'page summary'}]);self.assertEqual(seen[1]['globalReview'],overview)
                retry={**options,'parts':[parts[1]],'images':[{'page':2}],'seedPageStates':result['pageStates'],'globalReview':result['globalReview']}
                ai.page_workflow(retry,{})
                self.assertEqual(global_call.call_count,1)

    def test_readonly_page_rejected_at_application_boundary(self):
        from types import SimpleNamespace
        import threading
        session={'parts':[{'readOnly':True}],'pages':[1]}
        manager=SimpleNamespace(lock=threading.RLock(),_session=lambda *args:session,remember=lambda s:None)
        result={'edits':[{'part':0,'start':0,'end':0,'before':'','after':'injection'}]}
        BatchEditsMixin.attach_batch(manager,'id',Path('.'),result)
        self.assertEqual(result['edits'],[]);self.assertIn('仅可审阅',result['rejected'][0]['reason'])

if __name__=='__main__':unittest.main()
