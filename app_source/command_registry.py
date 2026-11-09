"""UX2 command substrate.

A command is an intent with stable identity. Tk buttons, menus and shortcuts are
projections of this registry; they are not the source of behaviour or state.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional, Any

Predicate=Callable[[],bool]
Handler=Callable[[],Any]

@dataclass(frozen=True)
class CommandDefinition:
    id: str
    label: str
    handler: Handler
    icon: str=''
    help: str=''
    shortcut: str=''
    enabled: Optional[Predicate]=None
    checked: Optional[Predicate]=None
    scope: str='application'
    target: str=''

    def is_enabled(self)->bool:
        return True if self.enabled is None else bool(self.enabled())

    def is_checked(self):
        return None if self.checked is None else bool(self.checked())

class CommandRegistry:
    def __init__(self):self._items={}
    def register(self,definition:CommandDefinition):
        if not isinstance(definition,CommandDefinition):raise TypeError('Expected CommandDefinition')
        if not definition.id or '.' not in definition.id:raise ValueError('Command IDs must be stable namespaced identifiers')
        if definition.id in self._items:raise ValueError('Duplicate command ID: '+definition.id)
        self._items[definition.id]=definition;return definition
    def get(self,command_id):
        try:return self._items[command_id]
        except KeyError:raise KeyError('Unknown command: '+str(command_id)) from None
    def ids(self):return tuple(self._items)
    def definitions(self):return tuple(self._items.values())
    def by_shortcut(self,shortcut):
        key=str(shortcut or '').strip().lower()
        return next((d for d in self._items.values() if str(d.shortcut or '').strip().lower()==key),None)
    def state(self,command_id):
        d=self.get(command_id);return {'enabled':d.is_enabled(),'checked':d.is_checked()}
    def invoke(self,command_id):
        d=self.get(command_id)
        if not d.is_enabled():return False
        return d.handler()
