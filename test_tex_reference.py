import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio_ai_quality import box_warnings, layout_report
from studio_tex_reference import compatibility, diagnose_missing, local_resources, package_exists, search_bundle
from test_fixture_pdf import write_fixture_pdf


class TexReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='studio-tex-reference-')
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / 'tectonic'
        data = self.cache / 'bundles' / 'data'
        data.mkdir(parents=True)
        (data / 'pinned.index').write_text(
            'article.cls 0 120\nctex.sty 2560 37930\nfontspec.sty 100 200\nbooktabs.sty 300 100\n')

    def test_bundle_answers_come_from_the_pinned_index(self):
        found = search_bundle(self.cache, 'ctex')
        self.assertTrue(found['available'])
        self.assertIn('ctex.sty', found['hits'])
        self.assertTrue(package_exists(self.cache, 'ctex'))
        self.assertTrue(package_exists(self.cache, 'booktabs'))
        self.assertFalse(package_exists(self.cache, 'invented-package'))

    def test_compatibility_flags_unavailable_packages_and_engine_mismatches(self):
        source = ('\\documentclass{article}\n'
                  '\\usepackage{invented-package}\n'
                  '\\usepackage{minted}\n'
                  '\\pdfpagewidth=10cm\n'
                  '\\begin{document}\ntext\n\\end{document}\n')
        report = compatibility(source, self.cache)
        messages = ' | '.join(issue['message'] for issue in report['issues'])
        self.assertIn('invented-package.sty', messages)
        self.assertIn('shell-escape', messages)
        self.assertIn('pdfTeX', messages)
        self.assertTrue(all(issue['severity'] == 'error' for issue in report['issues']))
        self.assertEqual(report['basis'], '固定 bundle 索引 + Windows 字体注册表')

    def test_project_local_class_and_style_files_are_not_called_missing(self):
        project = Path(self.tmp.name) / 'project'
        (project / 'styles').mkdir(parents=True)
        (project / 'styles' / 'mystyle.sty').write_text('')
        (project / 'myclass.cls').write_text('')
        local = local_resources(project)
        self.assertEqual(local, {'mystyle.sty', 'myclass.cls'})
        source = '\\documentclass{myclass}\n\\usepackage{mystyle}\n'
        self.assertEqual(compatibility(source, self.cache, local=local)['issues'], [])

    def test_font_existence_follows_the_installed_registry_and_if_font_exists_tf(self):
        with patch('studio_tex_reference.installed_font_families', return_value=['Times New Roman', 'SimSun']):
            bad = compatibility('\\setmainfont{Missing Font}\n', self.cache)
            self.assertTrue(any('Missing Font' in issue['message'] for issue in bad['issues']))
            guarded = compatibility('\\IfFontExistsTF{Missing Font}{\\setmainfont{Missing Font}}{}\n', self.cache)
            self.assertFalse(any('Missing Font' in issue['message'] for issue in guarded['issues']))
            good = compatibility('\\setmainfont{Times New Roman}\n', self.cache)
            self.assertEqual(good['issues'], [])

    def test_missing_resources_are_classified_against_the_same_index(self):
        log = ("! LaTeX Error: File `ctex.sty' not found.\n"
               "! LaTeX Error: File `notinbundle.sty' not found.\n")
        result = {item['name']: item['inPinnedBundle'] for item in diagnose_missing(log, self.cache)}
        self.assertTrue(result['ctex.sty'])
        self.assertFalse(result['notinbundle.sty'])

    def test_box_warnings_and_layout_recheck_name_real_evidence(self):
        over, under = box_warnings('Overfull \\hbox (12.3pt too wide) in paragraph at lines 8--9\n'
                                   'Underfull \\vbox (badness 10000) detected at line 14\n')
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0]['line'], 8)
        self.assertEqual(under[0]['line'], 14)
        pdf = Path(self.tmp.name) / 'page.pdf'
        write_fixture_pdf(pdf)
        clean = layout_report(pdf, pdf)
        self.assertEqual(clean['status'], 'checked')
        self.assertEqual(clean['warnings'], [])
        dirty = layout_report(pdf, pdf, 'Overfull \\hbox (5.0pt too wide) in paragraph at lines 3--4\n')
        self.assertEqual(dirty['status'], 'review')
        self.assertIn('Overfull', dirty['warnings'][0])
        self.assertIn('3', dirty['warnings'][0])

    def test_page_count_change_is_reported_as_a_layout_risk(self):
        from pypdf import PdfWriter
        before = Path(self.tmp.name) / 'one.pdf'
        writer = PdfWriter()
        writer.add_blank_page(595, 842)
        with before.open('wb') as handle:
            writer.write(handle)
        after = Path(self.tmp.name) / 'three.pdf'
        write_fixture_pdf(after)
        report = layout_report(before, after)
        self.assertEqual(report['status'], 'review')
        self.assertTrue(any('页数' in warning for warning in report['warnings']))
        self.assertEqual(report['details']['pages'], {'before': 1, 'after': 3})


if __name__ == '__main__':
    unittest.main()
