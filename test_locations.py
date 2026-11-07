import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from studio_storage import StudioStorage,project_id,write_json,read_json
from studio_engine import engine_environment

class LocationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.app=self.base/'app';self.app.mkdir();self.store=StudioStorage(self.app)
  self.old=self.store.projects/'Example';self.old.mkdir(parents=True);(self.old/'main.tex').write_bytes(b'original source\r\n');self.store.default_root=self.old;self.store.record_project(self.old,'main.tex')
  self.store.tex_cache.mkdir(parents=True);(self.store.tex_cache/'resource').write_bytes(b'cached-resource')
  self.projects=self.base/'new-projects';self.cache=self.base/'new-cache'
 def tearDown(self):self.temp.cleanup()
 def test_migration_moves_contents_retargets_active_project_and_survives_restart(self):
  self.store.configure_locations(str(self.projects),str(self.cache));new=self.projects/'Example'
  self.assertEqual((new/'main.tex').read_bytes(),b'original source\r\n');self.assertFalse(self.old.exists());self.assertEqual((self.cache/'tectonic/resource').read_bytes(),b'cached-resource')
  fresh=StudioStorage(self.app);self.assertEqual(fresh.active_project()['root'],str(new));self.assertEqual(fresh.cache,self.cache);self.assertEqual(fresh.default_root,new)
 def test_migration_preserves_pdf_history_and_task_paths(self):
  data=self.store.data;oldid=project_id(self.old);newid=project_id(self.projects/'Example');folder=data/'page-edits'/oldid/('a'*32);folder.mkdir(parents=True);(folder/'before.pdf').write_bytes(b'%PDF-original')
  write_json(folder/'session.json',{'root':str(self.old),'projectId':oldid,'folder':str(folder),'candidatePdf':str(folder/'candidate.pdf'),'source':'D:\\source\\literal','result':{'edits':[{'before':'unchanged','after':'also unchanged'}]},'imagePages':{'1':{'before':str(data/'review-previews'/oldid/'before.png')}}})
  (data/'previews').mkdir();(data/'previews'/(oldid+'.pdf')).write_bytes(b'%PDF-preview');(data/'glossaries').mkdir();write_json(data/'glossaries'/(oldid+'.json'),{'terms':[]})
  self.store.configure_locations(str(self.projects),str(self.cache));task=read_json(data/'page-edits'/newid/('a'*32)/'session.json',{})
  self.assertEqual(task['root'],str(self.projects/'Example'));self.assertEqual(task['source'],'D:\\source\\literal');self.assertIn(newid,task['candidatePdf']);self.assertIn(newid,task['imagePages']['1']['before']);self.assertEqual((data/'previews'/(newid+'.pdf')).read_bytes(),b'%PDF-preview')
 def test_nonempty_destination_is_not_overwritten(self):
  self.projects.mkdir();(self.projects/'existing.txt').write_text('keep')
  with self.assertRaises(ValueError):self.store.configure_locations(str(self.projects),str(self.cache))
  self.assertTrue(self.old.is_dir());self.assertEqual((self.projects/'existing.txt').read_text(),'keep')
 def test_editor_ai_sessions_and_preview_follow_directory_move(self):
  oldid=project_id(self.old);ident='b'*32;folder=self.store.data/'editor-ai'/oldid/ident
  write_json(folder/'session.json',{'root':str(self.old),'projectId':oldid,'candidates':{'main.tex':'literal D:/unchanged'},'running':False})
  preview=self.store.cache/'editor-ai'/oldid/ident/'candidate.pdf';preview.parent.mkdir(parents=True);preview.write_bytes(b'%PDF-candidate')
  self.store.configure_locations(str(self.projects),str(self.cache));newroot=self.projects/'Example';newid=project_id(newroot)
  task=read_json(self.store.data/'editor-ai'/newid/ident/'session.json',{})
  self.assertEqual(task['root'],str(newroot));self.assertEqual(task['projectId'],newid);self.assertEqual(task['candidates']['main.tex'],'literal D:/unchanged');self.assertEqual((self.cache/'editor-ai'/newid/ident/'candidate.pdf').read_bytes(),b'%PDF-candidate')
 def test_overlap_relative_and_application_targets_rejected(self):
  for a,b in [(str(self.projects),str(self.projects/'cache')),('relative',str(self.cache)),(str(self.app/'vendor'),str(self.cache)),(str(self.old/'inside'),str(self.cache))]:
   with self.subTest(a=a,b=b):
    with self.assertRaises(ValueError):self.store.configure_locations(a,b)
  self.assertTrue(self.old.exists())
 def test_failed_settings_write_rolls_back_moved_directories(self):
  with patch('studio_locations.write_json',side_effect=OSError('test write failure')):
   with self.assertRaises(OSError):self.store.configure_locations(str(self.projects),str(self.cache))
  self.assertTrue(self.old.is_dir());self.assertTrue((self.store.tex_cache/'resource').exists());self.assertFalse(self.projects.exists());self.assertEqual(self.store.active_project()['root'],str(self.old))
 def test_font_and_temporary_caches_follow_configured_location(self):
  self.store.configure_locations(str(self.projects),str(self.cache));env=engine_environment(self.store.runtime,self.store.data,self.store.tex_cache)
  self.assertEqual(Path(env['TECTONIC_CACHE_DIR']),self.cache/'tectonic');self.assertEqual(Path(env['TEMP']),self.cache/'tmp');self.assertIn((self.cache/'fonts').as_posix(),(self.store.data/'fonts.conf').read_text())

if __name__=='__main__':unittest.main()
