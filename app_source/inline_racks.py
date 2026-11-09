"""Object-owned rack disclosures; retained owner editors, one edit registry."""
import tkinter as tk
from tkinter import ttk
from responsive_controls import PriorityToolbar
from omne_rack import CompactRack


class RackSection(ttk.Frame):
    def __init__(self,parent,app,role,*,expanded=True):
        super().__init__(parent,padding=(2,3))
        self.app=app;self.role=role;self.expanded=bool(expanded);self.cell=None
        self.columnconfigure(0,weight=1)
        self.bar=PriorityToolbar(self,gap=3);self.bar.grid(row=0,column=0,sticky='ew')
        self.toggle_button=self.bar.add_action('',self.toggle,priority=0,pinned=True)
        self.add_button=self.bar.add_action('+ Module',lambda:self.act('add'),priority=0,pinned=True)
        self.bar.add_action('Vary',lambda:self.act('vary'),priority=12)
        self.bar.add_action('Randomise',lambda:self.act('random'),priority=15)
        self.more_button=self.bar.add_action('⋯',self.menu,priority=5,width=3)
        self.body=ttk.Frame(self,height=210);self.body.grid_propagate(False)
        self.body.rowconfigure(0,weight=1);self.body.columnconfigure(0,weight=1)
        self.body.bind('<Configure>',lambda e:self.cell.relayout() if self.cell and self.cell.winfo_exists() else None)
        app.add_tip(self.toggle_button,'Expand or collapse effects here. This does not bypass or change their sound or picture.')
        app.add_tip(self.add_button,'Add a module to '+('the final whole picture' if role=='Master' else 'channel '+role)+'. Other racks keep their own settings.')
        self.paint()
    def paint(self):
        name='Whole picture FX' if self.role=='Master' else 'Rack '+self.role
        count=len(self.cell.target()[0] or []) if self.cell and self.cell.winfo_exists() else 0
        state=(self.expanded,count)
        if state==getattr(self,'_painted',None):return
        self._painted=state
        self.toggle_button.configure(text=('▾ ' if self.expanded else '▸ ')+name+' · '+str(count))
        if self.expanded:self.body.grid(row=1,column=0,sticky='nsew',pady=(3,0))
        else:self.body.grid_remove()
    def toggle(self):
        self.set_expanded(not self.expanded)
    def set_expanded(self,value,*,save=True):
        changed=self.expanded!=bool(value);self.expanded=bool(value);self.paint()
        if changed and hasattr(self.app,'queue_deck'):self.app.queue_deck.reflow(save=False)
        if changed and hasattr(self.app,'deck'):self.app.deck.refresh(True)
        if save and changed:self.app.save_preferences()
    def act(self,kind):
        self.app.open_channel_effects(self.role)
        cell=self.cell
        if cell is None:return
        if kind=='add':cell.open_catalogue()
        elif kind=='vary':cell.local_random(True)
        elif kind=='random':cell.local_random(False)
    def menu(self):
        self.app.open_channel_effects(self.role)
        menu=tk.Menu(self,tearoff=False)
        self.app.deck.populate_menu(menu)
        if self.role=='Master':
            menu.add_separator()
            menu.add_command(label='A/B mixer controls…',command=lambda:self.app.open_channel_effects('Mix'))
            menu.add_command(label='Transition controls…',command=lambda:self.app.open_channel_effects('Transition'))
        self.app.popup_menu(menu,self.more_button)


class InlineRackController(CompactRack):
    """Same owner adapters and parameter widgets; mount each at its own queue."""
    def refresh(self,force=False):
        special=self.scope.get()
        if special not in ('Mix','Transition'):return super().refresh(force)
        # Routing is shown in its own retained contextual editor, without building a hidden duplicate.
        self.scope.set('Master')
        try:return super().refresh(force)
        finally:self.scope.set(special);self.selected_owner_key=None
    def select_owner(self,cell):
        self.selected_owner_key=cell.adapter.key;self.scope.set(cell.scope.get())
        if cell.scope.get()=='Layer':self.app.selected_layer_id=cell.adapter.owner.id
        elif cell.scope.get()=='Clip':
            self.app.selected_layer_id=cell.adapter.parent.id;self.app.selected_clip_id=cell.adapter.owner.id
        self.target_name.set(cell.adapter.title);self._sync_selected(cell)
        self.refresh_toolbar_state()
        if hasattr(self.app.module_library,'destination_caption'):
            self.app.module_library.destination_caption.set('Add to '+cell.adapter.title)
    def relayout(self):
        if not self._ready:return
        app=self.app;pages=getattr(getattr(app,'queue_deck',None),'pages',{})
        sections={'Master':app.whole_rack}
        sections.update({role:page.rack_section for role,page in pages.items() if hasattr(page,'rack_section')})
        for cell in self.owner_cells.values():
            role='Master' if cell.adapter.scope=='Master' else cell.adapter.owner.extra.get('voice')
            section=sections.get(role)
            if section is None:continue
            section.cell=cell;section.paint()
            if section.expanded:
                if str(cell.grid_info().get('in',''))!=str(section.body):
                    cell.grid(in_=section.body,row=0,column=0,sticky='nsew')
                if cell.header.winfo_manager():cell.header.grid_remove()
                if cell.state_label.winfo_manager():cell.state_label.grid_remove()
                if cell.collapsed:cell.collapsed=False;cell.content.grid()
                geometry=(section.body.winfo_width(),section.body.winfo_height(),tuple(cell.card_parts))
                if geometry!=getattr(cell,'_inline_geometry',None):
                    cell._inline_geometry=geometry;cell.relayout()
            elif cell.winfo_manager():cell.grid_remove()
            for key,child in cell.clip_cells.items():
                if key==getattr(self,'inline_clip_key',None):
                    if not child.winfo_manager():child.pack(fill='x',pady=(6,0))
                    child.relayout()
                elif child.winfo_manager():child.pack_forget()
    def flush_history(self):return super().flush_history()
