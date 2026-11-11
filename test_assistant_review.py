import tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from studio_document_assistant import DocumentAssistant
from studio_assistant_comparison import align,source_diff
from studio_assistant_history import groups,delete,restore,messages

class ReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'project';self.root.mkdir()
  self.ai=DocumentAssistant(SimpleNamespace(data=self.base/'data',cache=self.base/'cache'))
 def seed(self,n,question,history=None,chain=None,running=False):
  from studio_storage import project_id
  ident=f'{n:032x}';rows=(history or [])+[{'role':'user','content':question,'mode':'agent'},{'role':'assistant','content':'done','mode':'agent'}]
  s={'id':ident,'root':str(self.root.resolve()),'projectId':project_id(self.root),'question':question,'created':n,'messages':rows,'running':running,'chatMode':'agent','stage':'done'}
  if chain:s['conversationId']=chain
  self.ai.sessions[ident]=s;self.ai.remember(s);return s
 def test_changed_content_aligns_across_different_pages(self):
  def word(t,p):return {'text':t,'page':p,'box':[.1,.2,.4,.3]}
  result=align([word('start',1),word('OLD',2),word('finish',2)],[word('start',1),word('NEW',1),word('finish',1)])
  change=result['changes'][0];self.assertEqual(change['before'][0]['page'],2);self.assertEqual(change['after'][0]['page'],1)
  self.assertTrue(change['before'][0]['boxes']);self.assertTrue(change['after'][0]['boxes'])
 def test_deletion_uses_surviving_context_without_fake_green_changed_content(self):
  a=[{'text':t,'page':1,'box':[.1,.2,.4,.3]} for t in ['keep','delete','tail']];result=align(a,[a[0],a[2]])
  self.assertEqual(result['changes'][0]['after'],[]);self.assertIsNotNone(result['changes'][0]['afterAnchor'])
 def test_source_diff_contains_line_numbers_and_replacement(self):
  rows=source_diff('a\nold\nz','a\nnew\nz')[0]['rows'];self.assertEqual(rows[1]['beforeLine'],2);self.assertEqual(rows[1]['after'],'new');self.assertEqual(rows[1]['kind'],'replace')
 def test_legacy_rounds_group_into_one_conversation_and_restore_full_messages(self):
  first=self.seed(1,'first');second=self.seed(2,'second',first['messages']);self.seed(3,'independent')
  history=groups(self.ai,self.root);self.assertEqual(len(history),2);self.assertEqual(len(next(g for g in history if g['id']==first['id'])['turns']),2)
  self.assertEqual(len(messages(self.ai,self.root,second)),4)
 def test_delete_removes_all_turns_and_undo_restores_without_touching_documents(self):
  first=self.seed(1,'first');second=self.seed(2,'second',first['messages'],first['id']);doc=self.root/'main.tex';doc.write_text('original')
  result=delete(self.ai,self.root,first['id']);self.assertEqual(result['count'],2);self.assertEqual(groups(self.ai,self.root),[])
  restore(self.ai,self.root,result['restoreToken']);self.assertEqual(len(groups(self.ai,self.root)),1);self.assertEqual(doc.read_text(),'original')
 def test_running_conversation_and_invalid_ids_cannot_be_deleted(self):
  session=self.seed(1,'active',running=True)
  with self.assertRaises(ValueError):delete(self.ai,self.root,session['id'])
  with self.assertRaises(ValueError):delete(self.ai,self.root,'../outside')
