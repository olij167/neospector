import os,tempfile,unittest
from unittest.mock import patch
from effects_engine import make_effect
from neospector_console import NeospectorApp
from module_engine import group_effects,children,compile_rack
from sequencer_model import project_to_dict,project_from_dict

class InstrumentRackTests(unittest.TestCase):
    def setUp(self):
        self.profile=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'OMNE_SEQUENCER_SANDBOX':self.profile.name});self.env.start()
        self.app=NeospectorApp(test_mode=True);self.app.geometry('1400x940');self.errors=[]
        self.app.report_callback_exception=lambda *e:self.errors.append(e)
        self.app.project.master_rack=[make_effect('liquid'),make_effect('echo'),make_effect('tile')]
        self.app.open_channel_effects('Master');self.app.update()
    def tearDown(self):
        self.app.close(force=True);self.env.stop();self.profile.cleanup()
    def test_single_owner_and_wrapping_rack(self):
        self.assertFalse(self.app.inline_rack_mode)
        cell=self.app.deck.selected_cell();cards=list(cell.card_parts.values())
        self.assertEqual(1,len([c for c in self.app.deck.owner_cells.values() if c.winfo_ismapped()]))
        self.assertGreaterEqual(len({c[0].winfo_y() for c in cards}),1)
        self.assertTrue(all(c[0].winfo_ismapped() for c in cards))
        self.assertIn('Final Output',self.app.deck.breadcrumb.get())
    def test_reaction_stays_inside_module_and_survives_external_click(self):
        deck=self.app.deck;fx=self.app.project.master_rack[0];deck.open_parameter(fx.id,'amount');self.app.update()
        cell=deck.selected_cell();shell=cell.card_parts[fx.id][0];tray=cell.tray
        self.assertEqual(str(shell.details_host),str(shell.companion_host.pack_info()['in']))
        self.app.viewport.canvas.event_generate('<ButtonPress-1>');self.app.update()
        self.assertTrue(tray.winfo_ismapped());self.assertFalse(deck.contextual.active())
        row=next(r for r in cell.rows if r.param is fx.params['amount'])
        x=row.scale.winfo_rootx()+row.scale.winfo_width()//2;y=row.scale.winfo_rooty()+row.scale.winfo_height()//2
        # UX10 uses a primary dial instead of the historical horizontal fader.
        self.assertTrue(row.dial.winfo_ismapped())
        x=row.dial.winfo_rootx()+row.dial.winfo_width()//2
        y=row.dial.winfo_rooty()+row.dial.winfo_height()//2
        self.assertTrue(str(self.app.winfo_containing(x,y)).startswith(str(row.dial)))
        self.assertEqual([],self.errors)
        bottom=cell.scroll.canvas.winfo_rooty()+cell.scroll.canvas.winfo_height()
        self.assertLessEqual(tray.source_box.winfo_rooty()+tray.source_box.winfo_height(),bottom)
        self.assertLessEqual(tray.depth_scale.winfo_rooty()+tray.depth_scale.winfo_height(),bottom)
    def test_group_navigation_edit_promote_undo_roundtrip(self):
        p=self.app.project;g=group_effects(p.master_rack,[p.master_rack[0].id,p.master_rack[1].id],'Dream Trails')
        self.app.deck.refresh(True);self.app.deck.enter_group(g.id);self.app.update()
        self.assertIn('Dream Trails',self.app.deck.breadcrumb.get())
        child=children(g)[0];self.app.deck.edit_group_parameter((child.id,),'amount',{'value':.43});self.app.update()
        self.assertAlmostEqual(.43,children(p.master_rack[0])[0].params['amount'].value)
        self.app.deck.promote_group_parameter((child.id,),'amount');self.app.update()
        self.assertTrue(p.master_rack[0].params)
        restored=project_from_dict(project_to_dict(p));self.assertEqual(len(compile_rack(p.master_rack)),len(compile_rack(restored.master_rack)))
        self.app.undo();self.app.update();self.assertFalse(self.app.project.master_rack[0].params)
        self.app.deck.leave_group();self.app.update();self.assertEqual([],self.errors)
    def test_variation_protection_keeps_manual_control(self):
        cell=self.app.deck.selected_cell();fx=self.app.project.master_rack[0]
        self.app.deck.toggle_variation_protection(fx.id);self.app.update()
        row=next(r for r in cell.rows if r.param is fx.params['amount'])
        self.assertTrue(row.editable());row.apply(.35);row.finish()
        self.assertAlmostEqual(.35,row.normal.get(),places=2)
        from omne_randomise import vary_rack
        value=fx.params['amount'].value;vary_rack(self.app.project.master_rack,seed=42,variation=1)
        self.assertEqual(value,fx.params['amount'].value)

    def test_placement_survives_refresh(self):
        from instrument_model import assign_source
        from sequencer_model import add_asset
        a=add_asset(self.app.project,kind='colour',path='',name='Still',metadata={'colour':'#aa5599'})
        c=assign_source(self.app.project,'A',a.id,duration=10)
        self.app.open_channel_effects('A',clip_id=c.id);self.app.update()
        self.app.deck.show_placement();self.app.deck.refresh(True);self.app.update()
        self.assertTrue(self.app.deck.selected_cell().main.winfo_ismapped())
        self.app.deck.relayout();self.app.update()
        self.assertTrue(self.app.deck.selected_cell().main.winfo_ismapped())

    def test_replaced_project_recovers_valid_owner(self):
        self.app.deck.scope.set('Clip')
        from instrument_model import new_instrument
        self.app.project=new_instrument();self.app.selected_clip_id=None;self.app.selected_layer_id=self.app.project.layers[0].id
        self.app.deck.refresh(True);self.app.update()
        self.assertIsNotNone(self.app.deck.selected_cell())
        self.assertIsNotNone(self.app.deck.target()[0])

    def test_save_rack_keeps_reaction_and_group_state(self):
        from module_engine import group_effects
        from sequencer_model import _effect_from
        p=self.app.project;fx=p.master_rack[0];fx.params['amount'].mode='react';fx.params['amount'].source='song'
        group_effects(p.master_rack,[p.master_rack[0].id,p.master_rack[1].id],'Saved Group')
        self.app.deck.refresh(True)
        saved=self.app.deck.save_named_rack('My Treatment')
        stored=self.app.catalog.ingredient(saved[0]) if isinstance(saved,tuple) else saved
        if not isinstance(stored,dict):stored=self.app.catalog.ingredient(saved)
        got=[_effect_from(raw) for raw in stored['payload']['rack']]
        self.assertEqual('react',children(got[0])[0].params['amount'].mode)

    def test_undo_inside_group_keeps_navigation(self):
        p=self.app.project;g=group_effects(p.master_rack,[p.master_rack[0].id,p.master_rack[1].id],'Dream Trails')
        self.app.deck.refresh(True);self.app.deck.enter_group(g.id);self.app.update()
        child=children(g)[0]
        self.app.deck.edit_group_parameter((child.id,),'amount',{'value':.6});self.app.undo();self.app.update()
        self.assertEqual((g.id,),self.app.deck.group_path)
        self.assertIsNotNone(self.app.deck.resolve_group())

    def test_current_item_with_prepared_cycle_has_explicit_guard(self):
        from sequencer_model import add_asset,Clip
        from queue_model import append_switch
        from queue_policies import preserve_visual_history
        p=self.app.project;layer=p.layers[0];asset=add_asset(p,path='',kind='colour',name='Current colour')
        old=Clip('old-current',asset.id,start=0,duration=8);old.rack=[make_effect('blur')];layer.clips=[old]
        preserve_visual_history(layer,8);append_switch(layer,8,'queue',0);layer.clips=[Clip('future-cycle',asset.id,start=0,duration=8)]
        self.app.playhead=2
        self.app.open_channel_effects('A',clip_id=old.id);self.app.update()
        cell=self.app.deck.selected_cell();self.assertEqual('Clip',cell.adapter.scope);self.assertTrue(cell.frozen)
        layer.locked=True;before=project_to_dict(p);self.assertIsNone(cell.activate_current());self.assertEqual(before,project_to_dict(p))
        layer.locked=False;cell.activate_current();self.app.update()
        self.assertFalse(self.app.deck.selected_cell().frozen)
        self.assertEqual('old-current',self.app.deck.selected_cell().adapter.owner.id)

    def test_switching_owner_finishes_fader_and_rejects_late_motion(self):
        deck=self.app.deck;cell=deck.selected_cell();fx=self.app.project.master_rack[0]
        row=next(r for r in cell.rows if r.param is fx.params['amount']);row.apply(.4)
        self.app.open_channel_effects('B');self.app.update();before=project_to_dict(self.app.project)
        row.write(.9);row.finish();self.assertEqual(before,project_to_dict(self.app.project))
        self.assertFalse(row.active);self.assertIsNone(self.app.gesture)
