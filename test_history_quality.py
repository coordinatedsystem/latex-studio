import tempfile,unittest,json
from pathlib import Path
from types import SimpleNamespace
from studio_history import capture,versions
from studio_ai_quality import lock_source,unlock_result,edit_problem
from studio_ai import validate_edits,actionable_result

class HistoryQualityTests(unittest.TestCase):
    def test_versions_keep_latest_bytes_deduplicate_and_survive_restart(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d).resolve();root=base/'project';root.mkdir();p=root/'main.tex';store=SimpleNamespace(data=base/'data')
            p.write_bytes(b'\xef\xbb\xbfOld\r\n');old=capture(store,root,p,'修改前');self.assertEqual(capture(store,root,p),old)
            p.write_bytes(b'\xef\xbb\xbfNew\r\n');new=capture(store,root,p,'编辑保存');items=versions(SimpleNamespace(data=base/'data'),root,p)
            self.assertEqual([i['id'] for i in items],[new,old]);self.assertEqual(items[0]['reason'],'编辑保存')
            from studio_storage import project_id
            self.assertEqual((store.data/'history'/project_id(root)/'main.tex'/new).read_bytes(),p.read_bytes())
            for n in range(40):p.write_text(str(n));capture(store,root,p)
            self.assertEqual(len(versions(store,root,p)),30)
    def test_locked_math_and_citations_restore_exactly_with_line_remapping(self):
        source='Start\n\\[x^2\n+y=3\\]\nSame\nSame\n';masked,locked=lock_source(source)
        result={'edits':[{'before':'Same','after':'Better','line':4}]};unlock_result(result,locked,masked)
        self.assertEqual(result['edits'][0]['line'],5);_,target=validate_edits(source,result['edits']);self.assertTrue(target.endswith('Same\nBetter\n'))
        key=next(iter(locked));edit=unlock_result({'edits':[{'before':key,'after':key}]},locked);self.assertEqual(edit['edits'][0]['after'],next(iter(locked.values())))
    def test_unit_changes_negation_loss_and_stronger_claims_are_blocked(self):
        with self.assertRaisesRegex(ValueError,'单位'):validate_edits('Runtime 12 ms.',[{'before':'12 ms','after':'12 s'}])
        validate_edits('耗时12毫秒。',[{'before':'耗时12毫秒。','after':'Runtime 12 milliseconds.'}])
        self.assertIsNotNone(edit_problem('The result may improve accuracy.','The result improves accuracy.'))
        self.assertIsNotNone(edit_problem('并未证明有效。','Proves effective.','translate'))
        self.assertIsNotNone(edit_problem('Results indicate improvement.','Results prove improvement.'))
        self.assertIsNotNone(edit_problem('Accuracy is 94.7%.','Accuracy may improve to 94.7%.'))
        edits,target,rejected=actionable_result('Accuracy is 94.7%.',{'edits':[{'before':' is ','after':' improves to '}]},'polish')
        self.assertEqual(edits,[]);self.assertEqual(target,'Accuracy is 94.7%.');self.assertTrue(rejected)
        self.assertIsNotNone(edit_problem('An ordinary result.','A rewritten result.','edit','只调整排版间距'))
        self.assertIsNone(edit_problem(r'\setlength{\parskip}{0pt}',r'\setlength{\parskip}{5pt}','edit','只调整排版间距'))
