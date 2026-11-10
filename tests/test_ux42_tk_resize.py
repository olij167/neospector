"""UX42 native Tk smoke: resize the actual instrument without resetting a queue."""
from pathlib import Path
import os,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform in ('darwin','win32'),'Requires a native desktop or xvfb-run')
class NativeResponsiveSmoke(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='neospector-ux42-layout-')
        self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.temp.name,'NEOSPECTOR_NO_NATIVE_DROP':'1'})
        self.env.start()
        from neospector_console import NeospectorApp
        self.app=NeospectorApp(test_mode=True)
        self.app.update()
    def tearDown(self):
        try:self.app.close(force=True)
        finally:self.env.stop();self.temp.cleanup()
    def test_resize_keeps_queues_and_preview_contained(self):
        app=self.app
        app.sidebar.set_open('A',True)
        app.sidebar.set_open('B',True)
        app.set_audio_tray_open(True)
        app.update()
        refs={role:app.sidebar.sections[role]['frame'] for role in ('A','B','Music')}
        for width,height in ((860,600),(1280,720),(1920,1080),(2560,1440),(3440,1440)):
            with self.subTest(width=width,height=height):
                app.geometry(f'{width}x{height}+0+0')
                app.update()
                p=app.shell.frames['panel.programme'];q=app.shell.frames['panel.library']
                self.assertTrue(p.winfo_ismapped())
                self.assertTrue(q.winfo_ismapped())
                self.assertGreater(p.winfo_width(),200)
                self.assertLessEqual(p.winfo_x()+p.winfo_width(),app.shell.stage.winfo_width()+2)
                self.assertGreaterEqual(q.winfo_y(),0)
                self.assertLessEqual(q.winfo_y()+q.winfo_height(),app.shell.stage.winfo_height()+2)
                self.assertTrue(all(app.sidebar.sections[r]['frame'] is refs[r] for r in refs))
        self.assertEqual(app.sidebar.stack_roles(),('A','B','Music'))
if __name__=='__main__':unittest.main()
