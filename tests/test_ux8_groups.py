import copy
import unittest
from effects_engine import make_effect
from module_engine import group_effects, children, edit_internal_parameter, internal_parameter_target, compile_rack
from instrument_groups import promote_internal_parameter, GroupWorkspace
from sequencer_model import Keyframe, _encode, _effect_from

class GroupPersistenceTests(unittest.TestCase):
    def nested(self):
        leaf=make_effect('liquid');rack=[leaf]
        nested=group_effects(rack,[leaf.id],'Inner')
        top=group_effects(rack,[nested.id],'Outer')
        return top,nested.id,leaf.id
    def test_nested_promotion_preserves_reaction_keys_and_roundtrip(self):
        top,nested,leaf=self.nested();path=(nested,leaf)
        edit_internal_parameter(top,path,'amount',{'value':.42,'mode':'react','source':'microphone','react_amount':-.4})
        subs=children(top);inner=children(subs[0]);inner[0].params['amount'].keyframes=[Keyframe(0,.1),Keyframe(1,.7)]
        subs[0].extra['children']=_encode(inner);top.extra['children']=_encode(subs)
        key=promote_internal_parameter(top,(nested,),path,'amount')
        self.assertEqual(key,promote_internal_parameter(top,(nested,),path,'amount'))
        inner=children(top)[0];self.assertEqual(1,len(inner.params));self.assertEqual(2,len(inner.params[key].keyframes))
        self.assertEqual('microphone',inner.params[key].source)
        edit_internal_parameter(top,path,'amount',{'value':.61})
        restored=_effect_from(_encode(top));self.assertAlmostEqual(.61,internal_parameter_target(restored,path,'amount')[2].value)
        self.assertEqual(len(compile_rack([top])),len(compile_rack([restored])))
    def test_edit_after_outer_promotion_uses_outer_owner(self):
        top,nested,leaf=self.nested();path=(nested,leaf)
        inner_key=promote_internal_parameter(top,(nested,),path,'amount')
        outer_key=promote_internal_parameter(top,(),(nested,),inner_key)
        edit_internal_parameter(top,path,'amount',{'value':.73})
        self.assertAlmostEqual(.73,top.params[outer_key].value)
    def test_manual_animation_write_updates_authored_key_and_uses_real_owner(self):
        from instrument_groups import GroupParameterMotion
        from types import SimpleNamespace
        from instrument_app import InstrumentApp
        top,nested,leaf=self.nested();path=(nested,leaf)
        edit_internal_parameter(top,path,'amount',{'mode':'animate'})
        owner=object()
        app=SimpleNamespace(gesture_time=.75,playing=False,reviewing=False,gesture={'kind':'program'},
            changed=lambda **kw:None)
        app.write_parameter=lambda p,v,o:InstrumentApp.write_parameter(app,p,v,o)
        motion=GroupParameterMotion(top,path,'amount',owner)
        motion.write(app,.62)
        updated=internal_parameter_target(top,path,'amount')[2]
        self.assertEqual('animate',updated.mode)
        self.assertAlmostEqual(.62,updated.animated_value(.75))
        self.assertTrue(updated.keyframes)

    def test_record_motion_keeps_parameter_identity_and_clip_clock(self):
        from instrument_groups import GroupParameterMotion
        from instrument_app import InstrumentApp
        from sequencer_model import Clip
        from types import SimpleNamespace
        top,nested,leaf=self.nested();path=(nested,leaf)
        edit_internal_parameter(top,path,'amount',{'mode':'react'})
        owner=Clip.__new__(Clip);owner.manual=False
        clocks=[]
        def clock(actual,t):
            self.assertIs(owner,actual);clocks.append(t);return t-.25
        app=SimpleNamespace(gesture_time=.5,playing=True,reviewing=False,gesture={'kind':'program'},
            record_automation=SimpleNamespace(get=lambda:True),project=SimpleNamespace(fps=24),
            programme_time=lambda:1.25,parameter_edit_clock=clock,changed=lambda **kw:None)
        app.write_parameter=lambda p,v,o:InstrumentApp.write_parameter(app,p,v,o)
        motion=GroupParameterMotion(top,path,'amount',owner)
        motion.write(app,.3);motion.write(app,.7)
        updated=internal_parameter_target(top,path,'amount')[2]
        self.assertEqual('react',updated.mode);self.assertTrue(updated.combine_animation)
        self.assertAlmostEqual(.7,updated.animated_value(1.))
        self.assertEqual(1,len(app.gesture['parameter_started']))
        self.assertTrue(owner.manual);self.assertIn(1.25,clocks)

    def test_nested_member_structure_roundtrip_and_mapping_guard(self):
        from instrument_groups import edit_group_members
        top,nested,leaf=self.nested();added=make_effect('blur')
        edit_group_members(top,(nested,),lambda members:members.append(copy.deepcopy(added)))
        self.assertEqual([leaf,added.id],[c.id for c in children(children(top)[0])])
        before=_encode(top)
        top.extra['locked']=True
        with self.assertRaises(ValueError):edit_group_members(top,(nested,),lambda members:members.clear())
        top.extra.pop('locked');self.assertEqual(before,_encode(top))
        restored=_effect_from(_encode(top));self.assertEqual(2,len(compile_rack([restored])))

    def test_locked_promotion_is_atomic(self):
        top,nested,leaf=self.nested();subs=children(top);subs[0].extra['locked']=True;top.extra['children']=_encode(subs)
        before=_encode(top)
        with self.assertRaises(ValueError):promote_internal_parameter(top,(nested,),(nested,leaf),'amount')
        self.assertEqual(before,_encode(top))
    def test_stale_workspace_never_writes(self):
        class App:
            def transaction(self,label,fn):return fn()
        class Rack:
            app=App()
            def resolve_group(self):return None
        workspace=object.__new__(GroupWorkspace);workspace.root_rack=Rack();workspace.app=workspace.root_rack.app
        self.assertFalse(workspace.edit_parameter(('missing',),'amount',{'value':.5}))
        self.assertFalse(workspace.promote_parameter(('missing',),'amount'))
        self.assertFalse(workspace.add_module(make_effect('blur')))
        self.assertFalse(workspace.change_member('missing','remove'))

class GroupWidgetTests(unittest.TestCase):
    def test_real_faders_keep_identity_and_nested_navigation(self):
        import tkinter as tk
        from types import SimpleNamespace
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        try:
            leaf=make_effect('liquid');rack=[leaf]
            inner=group_effects(rack,[leaf.id],'Inner')
            top=group_effects(rack,[inner.id],'Outer')
            app=SimpleNamespace(ui_chrome={'field_bg':'#202020','panel_bg':'#181818'},add_tip=lambda *a:None,
                focus_get=root.focus_get,can_edit=lambda owner:True)
            opened=[]
            holder=SimpleNamespace(app=app,resolve_group=lambda:(top,top,()),target=lambda:(rack,None),enter_group=opened.append)
            view=GroupWorkspace(root,holder);view.pack();view.refresh();root.update()
            buttons=[w for card in view.chain.winfo_children() for w in card.winfo_children() if isinstance(w,__import__('tkinter').ttk.Button)]
            next(w for w in buttons if w.cget('text')=='Open group →').invoke()
            self.assertEqual([inner.id],opened)
            holder.resolve_group=lambda:(top,children(top)[0],(inner.id,))
            view.refresh();root.update()
            key=((inner.id,leaf.id),'amount');fader=view.faders[key]
            self.assertIn('amount',fader.key)
            edit_internal_parameter(top,key[0],key[1],{'value':.36})
            view.open_controls(key[0],key[1])
            controls=fader.controls
            fader.control_vars['release'].set('0.731')
            view.refresh(force=True)
            self.assertIs(controls,fader.controls)
            self.assertEqual('0.731',fader.control_vars['release'].get())
            self.assertEqual('Single strip',view.area.policy.flow)
            self.assertTrue(view.area.allow_vertical)
            front_buttons=view.cards[leaf.id][2]
            self.assertTrue(all(not b.winfo_manager() for b in front_buttons))
            view.toggle_more(leaf.id);root.update()
            self.assertTrue(all(b.winfo_manager()=='pack' for b in front_buttons))
            self.assertIs(fader,view.faders[key]);self.assertAlmostEqual(.36,fader.param.value)
        finally:root.destroy()

class GroupGestureIntegrationTests(unittest.TestCase):
    def test_group_add_reorder_bypass_remove_and_roundtrip(self):
        import tkinter as tk
        import tempfile,os
        from unittest.mock import patch
        from neospector_console import NeospectorApp
        try:probe=tk.Tk();probe.destroy()
        except tk.TclError as exc:self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as profile, patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':profile}):
            app=NeospectorApp(test_mode=True)
            try:
                leaf=make_effect('liquid');app.project.master_rack=[leaf]
                top=group_effects(app.project.master_rack,[leaf.id],'Chain')
                app.open_channel_effects('Master');app.deck.refresh(True);app.deck.enter_group(top.id);app.update()
                view=app.deck.group_view;added=make_effect('blur')
                self.assertTrue(view.add_module(added));app.update()
                self.assertEqual([leaf.id,added.id],[c.id for c in children(top)])
                self.assertTrue(view.change_member(added.id,'earlier'));app.update()
                self.assertEqual([added.id,leaf.id],[c.id for c in children(top)])
                self.assertTrue(view.change_member(added.id,'bypass'));app.update()
                self.assertFalse(children(top)[0].enabled)
                restored=_effect_from(_encode(top));self.assertEqual(1,len(compile_rack([restored])))
                self.assertTrue(view.change_member(added.id,'remove'));app.update()
                self.assertEqual([leaf.id],[c.id for c in children(top)])
                view.promote_parameter((leaf.id,),'amount');app.update()
                before=_encode(app.project.master_rack)
                view.change_member(leaf.id,'remove');app.update()
                self.assertEqual(before,_encode(app.project.master_rack))
            finally:app.close(force=True)

    def test_drag_undo_and_escape_restore_animation(self):
        import tkinter as tk
        import tempfile,os
        from unittest.mock import patch
        from neospector_console import NeospectorApp
        try:probe=tk.Tk();probe.destroy()
        except tk.TclError as exc:self.skipTest(str(exc))
        with tempfile.TemporaryDirectory() as profile, patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':profile}):
            app=NeospectorApp(test_mode=True)
            try:
                leaf=make_effect('liquid');leaf.params['amount'].mode='animate'
                leaf.params['amount'].keyframes=[Keyframe(0,.2),Keyframe(2,.8)]
                app.project.master_rack=[leaf]
                top=group_effects(app.project.master_rack,[leaf.id],'Motion')
                app.open_channel_effects('Master');app.deck.refresh(True);app.deck.enter_group(top.id);app.update()
                view=app.deck.group_view;key=((leaf.id,),'amount');before=_encode(app.project.master_rack)
                fader=view.faders[key];count=len(app.history.undo_stack)
                fader.apply(.3);fader.apply(.6);fader.finish_input();app.update()
                self.assertEqual(count+1,len(app.history.undo_stack))
                app.undo();app.update();self.assertEqual(before,_encode(app.project.master_rack))
                # Undo replaces the project, so navigate into its live group again.
                app.deck.enter_group(app.project.master_rack[0].id);app.update()
                fader=app.deck.group_view.faders[key];fader.apply(.7)
                fader.finish_input(cancel=True);app.update()
                self.assertEqual(before,_encode(app.project.master_rack))
                self.assertIsNone(getattr(app,'_active_input_control',None))
            finally:app.close(force=True)

if __name__=='__main__':unittest.main()
