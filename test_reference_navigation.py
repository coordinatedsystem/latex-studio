import gzip,json,tempfile,unittest
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import ArrayObject,DictionaryObject,NameObject,FloatObject,TextStringObject,NullObject
from studio_review import analyze_references
from studio_navigation import read_aux_anchors
from studio_sync import locate
from studio_page_edits import sha
from studio_storage import project_id,write_json
from studio_document_tools import impact,check_consistency

class CatalogTests(unittest.TestCase):
    def test_entries_expose_full_bib_and_precise_key_occurrences(self):
        sources={'main.tex':'\\bibliography{refs}\n\\label{ab} \\label{a} \\ref{a} \\cite{one}\n',
                 'refs.bib':'@article{one, title={A {nested} title}, author="A Writer", year={2026}, doi={10.1/example}}'}
        c=analyze_references(sources,'main.tex')['catalog'];entry=c['bibliography'][0]
        self.assertEqual(entry['fields']['title'],'A nested title');self.assertIn('author="A Writer"',entry['raw']);self.assertEqual(entry['usages'][0]['line'],2)
        label=next(e for e in c['labels'] if e['key']=='a');self.assertEqual(label['match'],r'\label{a}');self.assertEqual(len(label['usages']),1)

    def test_aux_anchor_fields_and_impact_propagation(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'main.aux').write_text(r'\newlabel{fig:a}{{2}{iii}{A title}{figure.5}{}}','utf8')
            self.assertEqual(read_aux_anchors(d)['fig:a']['anchor'],'figure.5')
        sources={'main.tex':'\\input{part}\nSee \\ref{fig:a}.','part.tex':'\\label{fig:a}'}
        value=impact(sources,'main.tex','part.tex',1,1,{'pages':{'1':{'part.tex':{'1':1}},'2':{'main.tex':{'2':1}}},'totalPages':2})
        self.assertEqual([p['page'] for p in value['pages']],[1,2]);self.assertEqual(value['labels'][0]['key'],'fig:a');self.assertEqual(value['files'],['main.tex','part.tex'])

class PreciseNavigationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name).resolve();self.root=self.base/'project';self.root.mkdir();self.data=self.base/'data'
        (self.root/'main.tex').write_text('\\bibliography{refs}\n\\label{sec:m}\nSee \\cite{paper} and \\cite{paper}.\n','utf8')
        (self.root/'refs.bib').write_text('@article{paper, title={A useful paper}, author={A Writer}, year={2026}}','utf8')
        writer=PdfWriter();page=writer.add_blank_page(600,800)
        for name,top in [('cite.paper',300),('section.1',700)]:
            dest=writer.add_named_destination(name,0);dest.get_object()[NameObject('/D')]=ArrayObject([page.indirect_reference,NameObject('/XYZ'),FloatObject(60),FloatObject(top),NullObject()])
        annotations=[]
        for left in [100,200]:
            item=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Link'),NameObject('/Rect'):ArrayObject(list(map(FloatObject,[left,595,left+20,610]))),NameObject('/A'):DictionaryObject({NameObject('/S'):NameObject('/GoTo'),NameObject('/D'):TextStringObject('cite.paper')})})
            annotations.append(writer._add_object(item))
        page[NameObject('/Annots')]=ArrayObject(annotations);self.pdf=self.base/'preview.pdf';writer.write(self.pdf)
        sync=self.data/'previews'/(project_id(self.root)+'.synctex.gz');sync.parent.mkdir(parents=True);sync.write_bytes(gzip.compress(('Input:1:'+str(self.root/'main.tex')+'\nUnit:1\nMagnification:1000\n{1\ng1,2:6553600,6553600\ng1,3:6553600,13107200\n}\n').encode()))
        write_json(sync.with_suffix('.json'),{'main':'main.tex','pdfVersion':str(self.pdf.stat().st_mtime_ns),'sources':{p.name:sha(p) for p in self.root.iterdir()},'anchors':{'sec:m':{'anchor':'section.1'}}})

    def test_bib_destination_roundtrip_returns_bib_source(self):
        point=locate(self.root,self.data,self.pdf,{'direction':'forward','kind':'bibliography','key':'paper','path':'refs.bib','line':1})
        self.assertFalse(point['approximate']);self.assertEqual(point['method'],'destination');self.assertEqual(point['page'],1)
        cursor=locate(self.root,self.data,self.pdf,{'direction':'forward','path':'refs.bib','line':1,'column':25});self.assertEqual(cursor['key'],'paper')
        x=(point['bbox'][0]+point['bbox'][2])/2;y=(point['bbox'][1]+point['bbox'][3])/2
        back=locate(self.root,self.data,self.pdf,{'direction':'inverse','page':1,'x':x,'y':y});self.assertEqual(back['path'],'refs.bib');self.assertEqual(back['key'],'paper')

    def test_repeated_citations_on_same_line_have_distinct_columns(self):
        back=locate(self.root,self.data,self.pdf,{'direction':'inverse','page':1,'x':210/600,'y':1-602/800})
        self.assertEqual(back['path'],'main.tex');self.assertGreater(back['column'],20)
        forward=locate(self.root,self.data,self.pdf,{'direction':'forward','kind':'citations','key':'paper','path':'main.tex','line':3,'column':back['column']})
        self.assertEqual(forward['method'],'pdf-link');self.assertGreater(forward['bbox'][0],.3)

    def test_label_uses_compiled_anchor_and_missing_entry_refuses_guess(self):
        value=locate(self.root,self.data,self.pdf,{'direction':'forward','kind':'labels','key':'sec:m','path':'main.tex','line':2})
        self.assertFalse(value['approximate']);self.assertEqual(value['anchor'],'section.1')
        with self.assertRaises(ValueError):locate(self.root,self.data,self.pdf,{'direction':'forward','kind':'bibliography','key':'missing','path':'refs.bib','line':1})

class ConsistencyTests(unittest.TestCase):
    def test_percent_rounding_units_and_real_mismatch(self):
        sources={'main.tex':r'准确率为94.7\%，耗时为1s，学习率为0.01。','results.json':json.dumps({'accuracy':.947369,'duration':{'value':1000,'unit':'ms'},'learning_rate':.02})}
        report=check_consistency(sources);statuses={i['claim']['key']:i['status'] for i in report['items']}
        self.assertEqual(statuses['accuracy'],'match');self.assertEqual(statuses['time'],'match');self.assertEqual(statuses['learning_rate'],'mismatch')
        english=check_consistency({'main.tex':r'Accuracy is 94.7\%. Learning rate is 0.01. Runtime is 1s.','results.json':sources['results.json']})
        self.assertEqual({i['claim']['key']:i['status'] for i in english['items']},statuses)
        qualified=check_consistency({'main.tex':r'Accuracy, which is 94.7\%.','data.json':'{"accuracy":0.946}'})
        self.assertEqual(qualified['items'][0]['status'],'mismatch')

    def test_key_value_tables_and_ambiguous_data_are_not_guessed(self):
        sources={'main.tex':r'\begin{tabular}{lr}参数 & 数值\\学习率 & 0.01\\\end{tabular}', 'a.json':'{"learning_rate":0.01}', 'b.json':'{"learning_rate":0.02}'}
        report=check_consistency(sources);self.assertEqual(len(report['items']),1);item=report['items'][0];self.assertEqual(item['status'],'ambiguous')
        rebound=check_consistency(sources,{item['claim']['id']:next(s['id'] for s in item['sources'] if s['file']=='a.json')})
        self.assertEqual(rebound['items'][0]['status'],'match')

    def test_python_is_parsed_without_executing_it(self):
        with tempfile.TemporaryDirectory() as d:
            marker=Path(d)/'must-not-exist';source='learning_rate=0.02\nopen('+repr(str(marker))+',"w").write("bad")\n'
            report=check_consistency({'main.tex':'learning_rate = 0.01','results.py':source});self.assertFalse(marker.exists());self.assertEqual(report['items'][0]['status'],'mismatch')

if __name__=='__main__':unittest.main()
