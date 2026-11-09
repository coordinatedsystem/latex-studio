"""Essential regressions: requested deletion, exact scope and usable PDF preview."""
import tempfile,unittest
from pathlib import Path
from studio_ai import actionable_result,validate_edits
from studio_ai_quality import lock_source,verify_preview_pdf

class RequestedEditTests(unittest.TestCase):
    def test_remove_references_and_repeated_citations_without_a_deletion_ratio_limit(self):
        refs='\\begin{thebibliography}{9}\n'+r'\bibitem{a} Author. A reference from 2024. '*8+'\n\\end{thebibliography}'
        source=r'Body \cite{a}, and again \cite{a}.'+'\n'+refs
        result={'edits':[{'before':r'\cite{a}','after':'','replace_all':True},{'before':refs,'after':''}]}
        edits,target,rejected=actionable_result(source,result,'polish','删除参考文献及正文引用')
        self.assertEqual(len(edits),3);self.assertFalse(rejected);self.assertEqual(target,'Body , and again .\n')
        self.assertEqual(lock_source(source,editable=True),(source,{}))
    def test_scope_and_project_boundaries_still_apply(self):
        with self.assertRaises(ValueError):validate_edits('same same',[{'before':'same','after':'new'}],True)
        with self.assertRaises(ValueError):validate_edits('body',[{'before':'body','after':r'\input{../private}'}],True)
        with self.assertRaises(ValueError):validate_edits('body',[{'start':1,'before':'body','after':''}],True)
    def test_pdf_must_open_and_render_not_just_have_a_pdf_header(self):
        from test_fixture_pdf import write_fixture_pdf
        with tempfile.TemporaryDirectory() as tmp:
            pdf=Path(tmp)/'candidate.pdf';write_fixture_pdf(pdf);self.assertEqual(verify_preview_pdf(pdf),3)
            pdf.write_bytes(b'%PDF-1.5 broken')
            with self.assertRaisesRegex(ValueError,'无法预览'):verify_preview_pdf(pdf)
