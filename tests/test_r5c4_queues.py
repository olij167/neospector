import copy, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app_source'))
import numpy as np
from instrument_model import new_instrument,voice
from sequencer_model import Clip,add_asset,new_id,project_from_dict,project_to_dict
from queue_model import set_boundary,queue_position,materialize
from programme_renderer import ProgrammeRenderer
from audio_bus import AudioMixer,add_sound

class QueueRegression(unittest.TestCase):
    def fixture(self):
        p=new_instrument();p.master_rack=[];l=voice(p,'A');l.rack=[];l.mixer_mode='over';l.extra['queue_policy']='repeat'
        for i,colour in enumerate(['#ff0000','#0000ff']):
            a=add_asset(p,path='',kind='colour',name=colour,metadata={'colour':colour})
            l.clips.append(Clip(new_id('c'),a.id,start=i*4,duration=4))
        return p,l
    def frame(self,p,t):
        r=ProgrammeRenderer()
        try:return np.array(r.render(p,t,(16,16)))
        finally:r.close()
    def test_current_boundary_live_without_auto_and_prior_frame_unchanged(self):
        p,l=self.fixture();before=self.frame(p,.5)
        try:set_boundary(p,l.id,l.clips[0].id,l.clips[1].id,'dissolve',1,now=1)
        except ValueError as exc:self.fail(str(exc))
        self.assertEqual(l.mixer_mode,'over');np.testing.assert_array_equal(self.frame(p,.5),before)
        pixel=self.frame(p,3.5)[8,8];self.assertGreater(pixel[0],80);self.assertGreater(pixel[2],80)
    def test_repeat_edit_preserves_prior_cycle_and_clock(self):
        p,l=self.fixture();before=[self.frame(p,t) for t in (3.5,7.5,8.5)]
        try:set_boundary(p,l.id,l.clips[0].id,l.clips[1].id,'dissolve',1,now=9)
        except ValueError as exc:self.fail(str(exc))
        for t,f in zip((3.5,7.5,8.5),before):np.testing.assert_array_equal(self.frame(p,t),f)
        self.assertAlmostEqual(queue_position(l,11.5),3.5)
    def test_started_overlap_targets_next_cycle(self):
        p,l=self.fixture();set_boundary(p,l.id,l.clips[0].id,l.clips[1].id,'dissolve',1)
        before=self.frame(p,3.7)
        set_boundary(p,l.id,l.clips[0].id,l.clips[1].id,'dissolve',.5,now=3.5)
        np.testing.assert_array_equal(self.frame(p,3.7),before)
        self.assertAlmostEqual(queue_position(l,7.2),.2)
    def test_music_loops_per_sample_and_gap_silent(self):
        from queue_gaps import add_music_gap
        from queue_policies import set_music_policy
        p=new_instrument();a=add_asset(p,path='',kind='audio',name='tone',duration=2)
        add_sound(p,a.id,duration=2);add_music_gap(p,1);set_music_policy(p,'repeat')
        class PCM:
            def read(self,a,t,n):return np.full((n,2),.2,dtype=np.float32)
            def read_positions(self,a,t):return np.full((len(t),2),.2,dtype=np.float32)
        mix=AudioMixer(p,rate=10,cache=PCM());out=mix.block(1.8,15)
        self.assertGreater(out[0,0],.1);np.testing.assert_array_equal(out[2:12],0);self.assertGreater(out[-1,0],.1)
    def test_gap_identity_repeat_capture_and_export(self):
        from queue_gaps import add_visual_gap
        from export_scope import resolve_export_range
        p,l=self.fixture();gap=add_visual_gap(p,l.id,2,index=0)
        self.assertEqual(gap.start,0);self.assertFalse(gap.asset_id)
        np.testing.assert_array_equal(self.frame(p,1),self.frame(p,11))
        restored=project_from_dict(project_to_dict(p));self.assertEqual(voice(restored,'A').clips[0].id,gap.id)
        take=materialize(p,0,20);self.assertEqual(len([c for c in voice(take,'A').clips if c.extra.get('queue_gap')]),2)
        scope=resolve_export_range(p,'visual',now=0,layer_id=l.id);self.assertEqual(scope['duration'],10)
        scope=resolve_export_range(p,'duration',now=0,duration=20);self.assertEqual(scope['duration'],20)
if __name__=='__main__':unittest.main()

class QueueNativeInput(unittest.TestCase):
    def setUp(self):
        import os,tkinter as tk
        if not os.environ.get('DISPLAY'):self.skipTest('Tk display required')
        from types import SimpleNamespace
        from sequencer_model import ProjectHistory
        from queue_transition_ui import BoundaryEditor
        from queue_transitions import boundary
        self.root=tk.Tk();self.root.geometry('470x410')
        p,l=QueueRegression().fixture();self.layer=l
        self.app=SimpleNamespace(project=p,playing=False,reviewing=False,gesture=None,history=ProjectHistory(p),ui_chrome={'field_bg':'#111111','selection_bg':'#222222','foreground':'#ffffff','muted_fg':'#aaaaaa','accent':'#55aaaa'})
        def begin(kind):
            if self.app.gesture:return
            before=project_to_dict(self.app.project);self.app.history.checkpoint_snapshot(before);self.app.gesture={'before':before}
        def end():self.app.gesture=None
        def cancel():
            before=self.app.gesture['before'];self.app.gesture=None;self.app.history.undo_stack.pop();self.app.project=project_from_dict(before)
        self.app.begin_gesture=begin;self.app.end_gesture=end;self.app.cancel_gesture=cancel;self.app.changed=lambda **kw:None
        self.editor=BoundaryEditor(self.root,self.app,'A',boundary(p,'A',l.clips[0].id,l.clips[1].id));self.editor.pack(fill='both',expand=True);self.root.update()
    def tearDown(self):
        if hasattr(self,'root'):self.root.destroy()
    def test_pointer_updates_actual_overlap_before_release_one_undo(self):
        cv=self.editor.canvas;cv.event_generate('<ButtonPress-1>',x=220,y=25);cv.event_generate('<B1-Motion>',x=190,y=25);self.root.update()
        self.assertLess(self.layer.clips[1].start,4,'Drag must change actual queue before release')
        cv.event_generate('<B1-Motion>',x=170,y=25);self.root.geometry('370x410');self.root.update();cv.event_generate('<ButtonRelease-1>',x=170,y=25)
        self.assertEqual(len(self.app.history.undo_stack),1);self.assertIsNone(self.app.gesture)
    def test_entry_live_escape_restores_and_stale_project_cannot_edit(self):
        self.editor.entry.focus_force();self.root.update();self.editor.seconds.set('.7');self.editor.entry.event_generate('<KeyRelease>',keysym='7');self.root.update()
        self.assertAlmostEqual(self.layer.clips[1].start,3.3)
        self.editor.entry.event_generate('<Escape>');self.root.update();self.assertAlmostEqual(voice(self.app.project,'A').clips[1].start,4)
        replacement=project_from_dict(project_to_dict(self.app.project));self.app.project=replacement
        self.editor.preset(.5);self.assertAlmostEqual(voice(replacement,'A').clips[1].start,4)

class QueueHistoryPCM(unittest.TestCase):
    def test_music_current_boundary_repeat_pcm_and_take_history(self):
        from music_queue import transition,take
        from queue_policies import music_position
        p=new_instrument();p.extra['music_queue_policy']='repeat'
        a=add_asset(p,path='',kind='audio',name='left',duration=4);b=add_asset(p,path='',kind='audio',name='right',duration=4)
        first=add_sound(p,a.id);second=add_sound(p,b.id,start=4)
        class PCM:
            def read(self,asset,t,n):
                pcm=np.zeros((n,2),np.float32);pcm[:,0 if asset.id==a.id else 1]=.3;return pcm
        def samples(t):return AudioMixer(p,rate=20,cache=PCM()).block(t,4)
        before=samples(3.5);transition(p,first['id'],1,now=9)
        np.testing.assert_array_equal(samples(3.5),before)
        midpoint=samples(11.5)[0];self.assertGreater(midpoint[0],.2);self.assertGreater(midpoint[1],.2)
        old=samples(11.5);take(p,second['id'],12)
        np.testing.assert_array_equal(samples(11.5),old);self.assertAlmostEqual(music_position(p,12),3)
    def test_materialized_history_matches_previous_and_edited_cycles(self):
        p,l=QueueRegression().fixture();set_boundary(p,l.id,l.clips[0].id,l.clips[1].id,'dissolve',1,now=9)
        captured=materialize(p,0,18)
        for t in (.5,3.5,7.5,8.5,11.5,14.5,16):
            np.testing.assert_array_equal(QueueRegression().frame(captured,t),QueueRegression().frame(p,t))
    def test_colour_and_held_gap_survive_partial_capture(self):
        from queue_gaps import add_visual_gap
        p,l=QueueRegression().fixture();gap=add_visual_gap(p,l.id,1,index=1,mode='hold');take=materialize(p,4,5)
        frame=QueueRegression().frame(take,4.5);self.assertGreater(frame[8,8,0],200)
        gap.extra['queue_gap']={'mode':'colour','colour':'#00ff00'}
        self.assertGreater(QueueRegression().frame(p,4.5)[8,8,1],200)

class QueuePendingManual(unittest.TestCase):
    def test_take_interrupts_pending_generation_immediately_without_rewriting_past(self):
        from queue_policies import preserve_visual_history
        from queue_model import append_switch,take_next
        p,l=QueueRegression().fixture();past=QueueRegression().frame(p,1)
        preserve_visual_history(l,8);append_switch(l,8,'queue',0)
        l.clips[0].duration=5;l.clips[1].start=5
        take_next(l,2)
        self.assertAlmostEqual(queue_position(l,2),4)
        np.testing.assert_array_equal(QueueRegression().frame(p,1),past)
        self.assertEqual(QueueRegression().frame(p,2)[8,8,2],255)
    def test_music_take_and_policy_interrupt_pending_cycle(self):
        from queue_policies import preserve_music_history,set_music_origin,music_position,set_music_policy
        from music_queue import take
        p=new_instrument();a=add_asset(p,path='',kind='audio',name='tone',duration=4)
        first=add_sound(p,a.id);second=add_sound(p,a.id,start=4)
        preserve_music_history(p,8);set_music_origin(p,8)
        p.extra['sound_events'][1]['start']=5
        take(p,second['id'],2);self.assertAlmostEqual(music_position(p,2),4)
        self.assertAlmostEqual(music_position(p,1),1)
        set_music_policy(p,'finish',3);self.assertAlmostEqual(music_position(p,10),12)

class QueueWorkspace(unittest.TestCase):
    def test_queue_toolbar_gap_drag_and_audition_keep_programme_clock(self):
        import os,tempfile,time,gc
        from unittest.mock import patch
        if not os.environ.get('DISPLAY'):self.skipTest('Tk display required')
        from neospector_console import NeospectorApp
        from queue_transition_ui import open_queue_transition,BoundaryEditor
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':folder}):
            app=NeospectorApp(test_mode=True);errors=[];app.report_callback_exception=lambda *e:errors.append(str(e))
            try:
                app.geometry('1080x740');app.shell.show('Queues');app.update();p=app.project;l=voice(p,'A');a=add_asset(p,path='',kind='colour',name='red',metadata={'colour':'#ff0000'})
                l.clips=[Clip('a',a.id,start=0,duration=4),Clip('b',a.id,start=4,duration=4)];app.refresh_all();app.update()
                column=app.queue_deck.pages['A'];column.refresh(True);column.selected='a';column.add_gap();app.update()
                self.assertEqual(len(l.clips),3);self.assertTrue(l.clips[1].extra.get('queue_gap'))
                self.assertEqual(column.loop_queue_button.cget('text'),'Loop queue')
                gap_id=l.clips[1].id;column.selected=gap_id;column.duration();app.update()
                from tkinter import ttk
                def descendants(w):
                    yield w
                    for child in w.winfo_children():yield from descendants(child)
                duration_entry=next(w for w in descendants(app._context_tray['body']) if isinstance(w,ttk.Entry))
                duration_entry.focus_force();app.update();duration_entry.delete(0,'end');duration_entry.insert(0,'2');duration_entry.event_generate('<KeyRelease>',keysym='2');app.update()
                self.assertEqual(next(c for c in l.clips if c.id==gap_id).duration,2)
                duration_entry.event_generate('<Return>');app.update();column.refresh(True);app.update()
                gap_hit=next(h for h in column.hits if h[0]==gap_id and h[3]=='clip');other_hit=next(h for h in column.hits if h[0]=='b' and h[3]=='clip')
                column.canvas.event_generate('<ButtonPress-1>',x=30,y=int(gap_hit[1]+10),rootx=100,rooty=100);column.canvas.event_generate('<B1-Motion>',x=30,y=int(other_hit[1]+10),rootx=100,rooty=180);column.canvas.event_generate('<ButtonRelease-1>',x=30,y=int(other_hit[1]+10),rootx=100,rooty=180);app.update()
                self.assertEqual(l.clips[-1].id,gap_id)
                open_queue_transition(app,'A','a',l.clips[1].id);app.update()
                def descend(w):
                    yield w
                    for child in w.winfo_children():yield from descend(child)
                editor=next(w for w in descend(app._context_tray['body']) if isinstance(w,BoundaryEditor));editor.preset(.25);app.update()
                self.assertAlmostEqual(l.transitions[0].duration,.25);before=app.playhead;editor.audition();app.update();self.assertEqual(app.playhead,before)
                self.assertFalse(errors,errors)
            finally:app.close(force=True);app=None;gc.collect()

class QueueRepeatMutation(unittest.TestCase):
    def test_shuffle_repeating_future_is_eligible_and_prior_frame_unchanged(self):
        from playable_queues import shuffle_future
        p,l=QueueRegression().fixture()
        a=add_asset(p,path='',kind='colour',name='green',metadata={'colour':'#00ff00'});l.clips.append(Clip('green',a.id,start=8,duration=4))
        before=QueueRegression().frame(p,.5)
        count=shuffle_future(p,'A',now=1,seed=2)
        self.assertGreater(count,0)
        np.testing.assert_array_equal(QueueRegression().frame(p,.5),before)

class QueueGapResize(unittest.TestCase):
    def test_resize_and_reorder_gap_schedule_next_loop_preserve_old_pixels(self):
        from queue_gaps import add_visual_gap,edit_queue
        from queue_model import set_duration,reorder
        p,l=QueueRegression().fixture();gap=add_visual_gap(p,l.id,1,index=1);before=QueueRegression().frame(p,4.5)
        edit_queue(p,'A',set_duration,gap.id,2,now=2)
        self.assertEqual(next(c for c in l.clips if c.id==gap.id).duration,2)
        np.testing.assert_array_equal(QueueRegression().frame(p,4.5),before)
        edit_queue(p,'A',reorder,l.id,gap.id,2,now=2.5)
        np.testing.assert_array_equal(QueueRegression().frame(p,4.5),before)

class QueueFinishHold(unittest.TestCase):
    def test_explicit_finish_and_hold_render_differently_and_capture_hold(self):
        from queue_policies import set_visual_policy
        p,l=QueueRegression().fixture();set_visual_policy(l,'finish')
        finished=QueueRegression().frame(p,9)
        set_visual_policy(l,'hold');held=QueueRegression().frame(p,9)
        self.assertGreater(held[8,8,2],200);self.assertFalse(np.array_equal(finished,held))
        captured=materialize(p,0,12);np.testing.assert_array_equal(held,QueueRegression().frame(captured,9))
