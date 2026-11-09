"""UX2 panel identity/lifetime substrate.

This pass registers the accepted docked panels without rebuilding them. Later
workspace passes can reconstruct views from these stable contracts while project
state remains outside widget instances.
"""
from __future__ import annotations
from dataclasses import dataclass

LIFETIMES=('contextual','panel','task')

@dataclass(frozen=True)
class PanelDefinition:
    id: str
    title: str
    state_key: str
    icon: str=''
    lifetime: str='panel'
    min_width: int=0
    min_height: int=0
    dock_zones: tuple=()
    state_owner: str='workspace'
    preferred_width: int=0
    preferred_height: int=0
    transient: bool=False

    def __post_init__(self):
        if not self.id or '.' not in self.id:raise ValueError('Panel IDs must be stable namespaced identifiers')
        if self.lifetime not in LIFETIMES:raise ValueError('Unknown UI lifetime: '+self.lifetime)
        if min(self.min_width,self.min_height,self.preferred_width,self.preferred_height)<0:raise ValueError('Panel dimensions cannot be negative')

class PanelRegistry:
    def __init__(self):self._items={};self._aliases={}
    def register(self,definition:PanelDefinition):
        if not isinstance(definition,PanelDefinition):raise TypeError('Expected PanelDefinition')
        if definition.id in self._items:raise ValueError('Duplicate panel ID: '+definition.id)
        self._items[definition.id]=definition
        for alias in (definition.title,definition.state_key):
            if alias:self._aliases[alias]=definition.id
        return definition
    def get(self,panel_id_or_alias):
        key=self._aliases.get(panel_id_or_alias,panel_id_or_alias)
        try:return self._items[key]
        except KeyError:raise KeyError('Unknown panel: '+str(panel_id_or_alias)) from None
    def resolve_state_key(self,panel_id_or_alias):return self.get(panel_id_or_alias).state_key
    def ids(self):return tuple(self._items)
    def definitions(self):return tuple(self._items.values())
