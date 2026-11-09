"""Versioned, bounded workspace state. No widget paths or project data live here.

Legacy preferences enter through migrate_preferences exactly once. The runtime
uses six stable panel IDs and four dock zones, never the old paned projection.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import copy
import math
import re

WORKSPACE_SCHEMA_VERSION = 1
PANEL_NAMES = {
    'panel.programme': 'Programme', 'panel.rack': 'Rack',
    'panel.library': 'Library', 'panel.queues': 'Queues',
    'panel.conductor': 'Conductor', 'panel.audio': 'Audio',
}
PANEL_IDS = tuple(PANEL_NAMES)
ZONES = ('left', 'right', 'bottom', 'centre')
PRESENTATIONS = ('collapsed', 'drawer', 'docked', 'tabbed', 'floating')
EDGES = {'panel.programme':'bottom', 'panel.rack':'bottom',
         'panel.library':'left', 'panel.queues':'bottom',
         'panel.conductor':'right', 'panel.audio':'right'}
DEFAULT_SIZES = {'left':390, 'right':310, 'bottom':330, 'rack_fraction':.46,
                 'right_fraction':.58,'left_fraction':.5,'bottom_fraction':.5,'drawer_left':570, 'drawer_right':420, 'drawer_bottom':390}
LEGACY_NAMES = {'Edit':'Sequence', 'Modules':'Build', 'Full':'Studio', 'Live':'Live'}


def panel_id(value):
    if not isinstance(value,str):return None
    if value in PANEL_NAMES: return value
    return next((k for k,v in PANEL_NAMES.items() if v == value), None)


def _mapping(value):
    return value if isinstance(value,dict) else {}


def _sequence(value):
    return value if isinstance(value,(list,tuple)) else []


def clamp_float_geometry(geometry, bounds):
    """Keep the complete window reachable after a display is unplugged.

    Coordinates use Tk's virtual desktop. Negative geometry offsets are from
    its right/bottom edges, rather than negative absolute screen coordinates.
    """
    bx,by,bw,bh=bounds
    match=re.fullmatch(r'(\d+)x(\d+)([+-]\d+)?([+-]\d+)?',str(geometry))
    width,height=(int(match[1]),int(match[2])) if match else (600,520)
    width=max(330,min(width,max(330,bw-32)));height=max(220,min(height,max(220,bh-64)))
    xx,yy=(match[3],match[4]) if match else (None,None)
    x=bx+32 if xx is None else (bx+bw-width+int(xx) if xx.startswith('-') else int(xx))
    y=by+32 if yy is None else (by+bh-height+int(yy) if yy.startswith('-') else int(yy))
    x=max(bx,min(x,bx+bw-width));y=max(by,min(y,by+bh-height-32))
    return f'{width}x{height}{int(x):+d}{int(y):+d}'


def _number(value, default, low, high):
    try:
        n=float(value)
        if math.isfinite(n): return max(low,min(high,n))
    except (TypeError, ValueError): pass
    return default


def _panels():
    return {pid:{'presentation':'collapsed', 'zone':'centre' if pid in ('panel.programme','panel.rack') else EDGES[pid],
                 'edge':EDGES[pid], 'order':i, 'geometry':'', 'last_presentation':'docked'}
            for i,pid in enumerate(PANEL_IDS)}


def _builtin(name, docked, *, mode='media', sizes=None, tabs=None):
    panels=_panels()
    for i,(pid,zone) in enumerate(docked): panels[pid].update(presentation='docked',zone=zone,order=i)
    for zone,group in (tabs or {}).items():
        for pid in group['members']: panels[pid].update(presentation='tabbed',zone=zone)
    return {'schema_version':WORKSPACE_SCHEMA_VERSION,'panels':panels,
            'sizes':{**DEFAULT_SIZES,**(sizes or {})}, 'tabs':copy.deepcopy(tabs or {}),
            'library_mode':mode,'maximized':'','locked':False}


DEFAULT_WORKSPACES = {
    'Live': _builtin('Live',[('panel.programme','centre'),('panel.rack','centre')]),
    'Sequence': _builtin('Sequence',[('panel.programme','centre'),('panel.library','left'),('panel.queues','bottom')],sizes={'left':360,'bottom':360}),
    'Conduct': _builtin('Conduct',[('panel.programme','centre'),('panel.rack','centre'),('panel.conductor','right'),('panel.audio','right')],sizes={'right':340,'rack_fraction':.30,'right_fraction':.62}),
    'Build': _builtin('Build',[('panel.programme','centre'),('panel.rack','centre'),('panel.library','left')],mode='modules',sizes={'left':430,'rack_fraction':.67}),
    'Studio': _builtin('Studio',[('panel.programme','centre'),('panel.library','left'),('panel.queues','bottom'),('panel.rack','bottom'),('panel.conductor','right'),('panel.audio','right')],
                       sizes={'left':330,'right':300,'bottom':340},
                       tabs={'bottom':{'members':['panel.queues','panel.rack'],'active':'panel.queues'},
                             'right':{'members':['panel.conductor','panel.audio'],'active':'panel.conductor'}}),
}


@dataclass
class WorkspaceState:
    name: str = 'Live'
    panels: dict = field(default_factory=_panels)
    sizes: dict = field(default_factory=lambda:dict(DEFAULT_SIZES))
    tabs: dict = field(default_factory=dict)
    library_mode: str = 'media'
    maximized: str = ''
    locked: bool = False
    schema_version: int = WORKSPACE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, name, data):
        d=copy.deepcopy(data) if isinstance(data,dict) else {}
        panels=_panels()
        for pid,raw in _mapping(d.get('panels')).items():
            if pid not in panels or not isinstance(raw,dict): continue
            p=panels[pid]
            p['presentation']=raw.get('presentation') if raw.get('presentation') in PRESENTATIONS else 'collapsed'
            p['zone']=raw.get('zone') if raw.get('zone') in ZONES else p['zone']
            p['edge']=raw.get('edge') if raw.get('edge') in ('left','right','bottom') else p['edge']
            p['order']=int(_number(raw.get('order'),p['order'],0,100))
            p['geometry']=str(raw.get('geometry',''))[:100]
            p['last_presentation']=raw.get('last_presentation') if raw.get('last_presentation') in PRESENTATIONS else 'docked'
            p['restore_on_show']=bool(raw.get('restore_on_show',False))
            p['tab_peers']=[v for v in _sequence(raw.get('tab_peers')) if isinstance(v,str) and v in PANEL_IDS and v!=pid]
        # Programme always has a returnable persistent surface.
        if panels['panel.programme']['presentation'] in ('collapsed','drawer'):
            panels['panel.programme'].update(presentation='docked',zone='centre')
        sizes={k:_number(_mapping(d.get('sizes')).get(k),v,.15 if k.endswith('_fraction') else 140,.82 if k.endswith('_fraction') else 1800) for k,v in DEFAULT_SIZES.items()}
        tabs={}
        for zone,raw in _mapping(d.get('tabs')).items():
            if zone not in ZONES or not isinstance(raw,dict): continue
            members=list(dict.fromkeys(p for p in _sequence(raw.get('members')) if isinstance(p,str) and p in panels and panels[p]['zone']==zone and panels[p]['presentation'] in ('tabbed','docked')))
            if len(members)>1:
                active=raw.get('active') if raw.get('active') in members else members[0]
                tabs[zone]={'members':members,'active':active}
                for pid in members:panels[pid]['presentation']='tabbed'
        tab_members={p for g in tabs.values() for p in g['members']}
        for pid,p in panels.items():
            if p['presentation']=='tabbed' and pid not in tab_members:p['presentation']='docked'
        drawers=[p for p in panels if panels[p]['presentation']=='drawer']
        for pid in drawers[1:]:panels[pid]['presentation']='collapsed'
        return cls(name=str(name),panels=panels,sizes=sizes,tabs=tabs,
                   library_mode=d.get('library_mode') if d.get('library_mode') in ('media','modules','patches') else 'media',
                   maximized=d.get('maximized') if isinstance(d.get('maximized'),str) and d.get('maximized') in panels else '',locked=bool(d.get('locked',False)))

    def to_dict(self):
        return {'schema_version':WORKSPACE_SCHEMA_VERSION,'panels':copy.deepcopy(self.panels),
                'sizes':dict(self.sizes),'tabs':copy.deepcopy(self.tabs),'library_mode':self.library_mode,
                'maximized':self.maximized,'locked':bool(self.locked)}


def _legacy_module_selected(data):
    return bool(_mapping(data.get('visible')).get('Module Library') or _mapping(data.get('floating')).get('Module Library') or
                any(isinstance(g,dict) and g.get('active')=='Module Library' for g in _mapping(data.get('tabs')).values()))


def _legacy_layout(name, raw):
    """Only this migration knows the retired panel and fixed-pane field names."""
    raw=raw if isinstance(raw,dict) else {}
    if raw.get('schema_version')==WORKSPACE_SCHEMA_VERSION:
        return WorkspaceState.from_dict(name,raw).to_dict()
    s=WorkspaceState.from_dict(name,DEFAULT_WORKSPACES['Live'])
    def old_id(n):return 'panel.library' if n=='Module Library' else panel_id(n)
    for n,visible in _mapping(raw.get('visible')).items():
        pid=old_id(n)
        if pid:
            # A true retired Library view wins over a false Media Library view.
            if n=='Library' and _mapping(raw.get('visible')).get('Module Library'):visible=True
            s.panels[pid]['presentation']='docked' if visible else 'collapsed'
    for zone,names in _mapping(raw.get('order')).items():
        zone='centre' if zone=='main' else zone
        if zone not in ZONES:continue
        for i,n in enumerate(names if isinstance(names,list) else []):
            pid=old_id(n)
            if pid:s.panels[pid].update(zone=zone,order=i)
    for zone,group in _mapping(raw.get('tabs')).items():
        if zone not in ZONES or not isinstance(group,dict):continue
        members=list(dict.fromkeys(old_id(n) for n in _sequence(group.get('members')) if old_id(n)))
        if len(members)>1:
            active=old_id(group.get('active')) or members[0]
            s.tabs[zone]={'members':members,'active':active}
            for pid in members:s.panels[pid].update(zone=zone,presentation='tabbed')
    for n,value in _mapping(raw.get('floating')).items():
        pid=old_id(n)
        if pid:
            s.panels[pid].update(presentation='floating',geometry=value.get('geometry','') if isinstance(value,dict) else '',last_presentation='floating')
    layout=_mapping(raw.get('layout'))
    s.sizes['left']=_number(layout.get('workspace0',layout.get('workspace_left')),390,240,1000)
    s.sizes['right']=_number(layout.get('workspace_right'),310,240,1000)
    s.locked=bool(raw.get('locked',False));s.maximized=old_id(raw.get('maximized')) or ''
    if _legacy_module_selected(raw):s.library_mode='modules'
    return WorkspaceState.from_dict(name,s.to_dict()).to_dict()


def migrate_preferences(prefs):
    """Pure, idempotent conversion; unrelated media/audio/theme preferences survive.

    Old built-ins receive the new task layout, never the rejected all-tools Live.
    Old Custom layouts retain their placements. A custom name takes precedence
    over an old builtin alias. Collisions with NEW builtin names gain (Custom).
    """
    p=copy.deepcopy(prefs) if isinstance(prefs,dict) else {}
    if p.get('workspace_schema_version')==WORKSPACE_SCHEMA_VERSION:
        return p
    custom={};renamed={}
    source=p.get('custom_workspaces',{})
    source=source if isinstance(source,dict) else {}
    for old in sorted(source):
        name=str(old)
        if name in DEFAULT_WORKSPACES:
            name=old+' (Custom)';i=2
            while name in source or name in custom:name=f'{old} (Custom {i})';i+=1
        renamed[old]=name;custom[name]=_legacy_layout(name,source[old])
    selected=str(p.get('workspace','Live'))
    selected=renamed.get(selected,LEGACY_NAMES.get(selected,selected))
    if selected not in DEFAULT_WORKSPACES and selected not in custom:selected='Live'
    legacy={**p.get('workspace_state',{})} if isinstance(p.get('workspace_state'),dict) else {}
    if 'visible' not in legacy:legacy['visible']=p.get('panel_states',{})
    if 'layout' not in legacy:legacy['layout']=p.get('layout',{})
    legacy.setdefault('locked',p.get('workspace_locked',False))
    if selected in custom:
        state=_legacy_layout(selected,legacy) if p.get('workspace_state') else copy.deepcopy(custom[selected])
    else:
        state=copy.deepcopy(DEFAULT_WORKSPACES[selected])
        state['locked']=bool(legacy.get('locked',False))
        if _legacy_module_selected(legacy):state['library_mode']='modules'
        for n,g in _mapping(legacy.get('floating')).items():
            pid='panel.library' if n=='Module Library' else panel_id(n)
            if pid and isinstance(g,dict):state['panels'][pid]['geometry']=str(g.get('geometry',''))
    for key in ('layout','panel_states','channel_layout_v2','channel_layout_v3','workspace_locked'):
        p.pop(key,None)
    p.update(workspace_schema_version=WORKSPACE_SCHEMA_VERSION, workspace=selected,
             workspace_state=state, custom_workspaces=custom,workspace_snapshots={})
    return p


class WorkspaceController:
    """One model for every presentation. Switching never touches the project."""
    def __init__(self,app,prefs=None):
        self.app=app;p=migrate_preferences(prefs)
        self.custom=copy.deepcopy(_mapping(p.get('custom_workspaces')))
        self.snapshots=copy.deepcopy(_mapping(p.get('workspace_snapshots')))
        selected=p.get('workspace','Live')
        if selected not in self.names():selected='Live'
        self.state=WorkspaceState.from_dict(selected,p.get('workspace_state',self._data(selected)))
    def names(self):return tuple(DEFAULT_WORKSPACES)+tuple(sorted(self.custom))
    def _data(self,name):return self.custom.get(name,self.snapshots.get(name,DEFAULT_WORKSPACES.get(name,DEFAULT_WORKSPACES['Live'])))
    def switch(self,name):
        if name not in self.names():raise KeyError(name)
        current=self.capture()
        if current.name in self.custom:self.custom[current.name]=current.to_dict()
        else:self.snapshots[current.name]=current.to_dict()
        self.state=WorkspaceState.from_dict(name,self._data(name));self.app.apply_workspace_state(self.state);return self.state
    def capture(self,name=None):return self.app.capture_workspace_state(name or self.state.name)
    def set_locked(self,value):
        self.state.locked=bool(value);self.app.workspace_lock_changed();return self.state.locked
    def _custom_name(self,name,old=None):
        clean=' '.join(str(name or '').split())
        if not clean:raise ValueError('Workspace name cannot be empty')
        if clean in DEFAULT_WORKSPACES or (clean in self.custom and clean!=old):raise ValueError('Workspace name already exists')
        return clean
    def save_as(self,name):
        clean=self._custom_name(name);state=self.capture(clean)
        self.custom[clean]=state.to_dict();self.state=state
        if hasattr(self.app,'shell'):self.app.shell.state=state
        return clean
    def rename(self,new_name):
        old=self.state.name
        if old not in self.custom:raise ValueError('Built-in workspaces cannot be renamed')
        clean=self._custom_name(new_name,old);state=self.capture(clean)
        self.custom.pop(old);self.custom[clean]=state.to_dict();self.state=state
        if hasattr(self.app,'shell'):self.app.shell.state=state
        return clean
    def delete_custom(self):
        if self.state.name not in self.custom:return False
        self.custom.pop(self.state.name);self.state=WorkspaceState.from_dict('Live',DEFAULT_WORKSPACES['Live'])
        self.app.apply_workspace_state(self.state);return True
    def reset(self):
        name=self.state.name
        data=DEFAULT_WORKSPACES.get(name,self.custom.get(name,DEFAULT_WORKSPACES['Live']))
        self.snapshots.pop(name,None);self.state=WorkspaceState.from_dict(name,data)
        self.app.apply_workspace_state(self.state);return self.state
    def serialize(self):
        state=self.capture()
        if state.name in self.custom:self.custom[state.name]=state.to_dict()
        return {'workspace_schema_version':WORKSPACE_SCHEMA_VERSION,'workspace':state.name,
                'workspace_state':state.to_dict(),'custom_workspaces':copy.deepcopy(self.custom),
                'workspace_snapshots':copy.deepcopy(self.snapshots)}
