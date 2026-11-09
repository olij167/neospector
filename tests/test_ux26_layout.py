import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
from ux26_queue_layout import requested_height,allocate,GAP,VISUAL_CLOSED

class UX26Layout(unittest.TestCase):
    def test_collapsed_is_identical_for_both_visuals(self):
        self.assertEqual(requested_height('A',False,0),requested_height('B',False,70))
        self.assertEqual(VISUAL_CLOSED,requested_height('A',False,20))
    def test_expanded_empty_has_one_real_row(self):
        self.assertEqual(requested_height('A',True,0),requested_height('B',True,1))
        self.assertEqual(42,requested_height('A',True,2)-requested_height('A',True,1))
    def test_one_queue_can_expand_to_natural_height(self):
        want={'A':requested_height('A',True,15)}
        self.assertEqual(want,allocate(('A',),want,1200,{'A':True}))
    def test_two_queues_share_remaining_space_proportionally(self):
        w={'A':requested_height('A',True,14),'B':requested_height('B',True,3)}
        a=allocate(('A','B'),w,610,{'A':True,'B':True})
        self.assertLessEqual(sum(a.values())+GAP,610)
        self.assertGreater(a['A'],a['B'])
        self.assertGreaterEqual(a['B'],requested_height('B',True,0))
        rev=allocate(('B','A'),w,610,{'A':True,'B':True})
        self.assertEqual(a,rev)
    def test_no_stretching_when_content_is_short(self):
        w={'A':requested_height('A',True,0),'B':requested_height('B',False,300)}
        self.assertEqual(w,allocate(('A','B'),w,900,{'A':True,'B':False}))
