"""UX42: display changes change projections, never authored workspace state."""
import copy, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))

class ViewportTests(unittest.TestCase):
    def test_restores_saved_large_window_inside_smaller_monitor(self):
        from ux42_viewport import startup_geometry
        value=startup_geometry('3840x2160+2100+1100',(0,0,1366,768))
        self.assertEqual(value,'1302x704+32+32')

    def test_uses_available_desktop_and_preserves_reachable_saved_location(self):
        from ux42_viewport import startup_geometry
        self.assertEqual(startup_geometry('1200x780+100+80',(0,0,2560,1440)), '1200x780+100+80')

    def test_missing_and_corrupt_geometry_safe(self):
        from ux42_viewport import startup_geometry
        self.assertEqual(startup_geometry('not a geometry',(0,0,1280,720)),'1216x656+32+32')

    def test_does_not_enforce_larger_minimum_than_screen(self):
        from ux42_viewport import minimum_window_size
        self.assertEqual(minimum_window_size(1280,720),(860,600))
        self.assertEqual(minimum_window_size(800,590),(736,526))

    def test_layout_matrix_nonoverlap_and_bounded(self):
        from ux42_viewport import project_stage
        for w,h in [(736,460),(920,520),(1280,620),(1440,850),(1920,1080),(2560,1440),(3440,1440),(3840,2160)]:
            for browser in (False, True):
                for rack in (False,True):
                    for roles in ((),('A',),('A','B','Music')):
                        with self.subTest(w=w,h=h,browser=browser,rack=rack,roles=roles):
                            plan=project_stage(w,h, browser=browser, rack=rack,
                                               roles=roles, visual_top=130, queue_height=345)
                            self.assertGreater(plan.programme[2],0)
                            self.assertLessEqual(plan.programme[0]+plan.programme[2],w)
                            self.assertLessEqual(plan.programme[3],h)
                            if plan.rack:
                                self.assertLessEqual(plan.rack[0]+plan.rack[2],plan.programme[0])
                            if plan.browser:
                                self.assertLessEqual(plan.browser[0]+plan.browser[2],plan.programme[0])
                            if plan.queue:
                                x,y,qw,qh=plan.queue
                                self.assertGreaterEqual(y,0)
                                self.assertLessEqual(x+qw,w)
                                self.assertLessEqual(y+qh,h)
                            self.assertGreaterEqual(plan.available_queue_height,0)

    def test_more_screen_width_goes_to_preview_not_ever_wider_docks(self):
        from ux42_viewport import project_stage
        narrow=project_stage(1440,900,browser=True,rack=False,roles=(),visual_top=100,queue_height=0)
        wide=project_stage(3840,2160,browser=True,rack=False,roles=(),visual_top=100,queue_height=0)
        self.assertGreater(wide.programme[2]-narrow.programme[2],2100)
        self.assertLessEqual(wide.browser[2],540)

    def test_model_independent_no_changes_to_workspace_state(self):
        from ux42_viewport import project_stage
        from workspace_system import WorkspaceState
        data=WorkspaceState.from_dict('Studio',{}).to_dict();old=copy.deepcopy(data)
        project_stage(800,590,browser=True,rack=True,roles=('A','B'),visual_top=100,queue_height=240)
        self.assertEqual(data,old)

    def test_queue_is_bottom_anchored(self):
        from ux42_viewport import project_stage
        for roles in (('A',),('A','B'),('A','B','Music')):
            p=project_stage(1440,900,browser=True,rack=False,roles=roles,visual_top=180,queue_height=400)
            self.assertEqual(p.queue[1]+p.queue[3],900-8)

if __name__=='__main__':unittest.main()
