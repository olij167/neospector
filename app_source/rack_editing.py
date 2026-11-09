"""Rack-local editing without holding authority over a replaced project or scope."""
from __future__ import annotations
import copy
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RackContext:
    project: object
    scope: str
    rack: list
    owner: object

    @classmethod
    def capture(cls, deck):
        rack, owner = deck.target()
        return cls(deck.app.project, deck.scope.get(), rack, owner)

    def resolve(self, deck, module_id=None):
        rack, owner = deck.target()
        if (deck.app.project is not self.project or deck.scope.get() != self.scope
                or rack is not self.rack or owner is not self.owner or rack is None):
            return None
        module = next((fx for fx in rack if fx.id == module_id), None) if module_id else None
        if module_id and module is None:
            return None
        return rack, module, owner


def move_module(rack, module_id, direction):
    """Move a current module one place; a locked neighbour is a fixed boundary."""
    if direction not in (-1, 1):
        return False
    index = next((i for i, fx in enumerate(rack) if fx.id == module_id), None)
    if index is None or not 0 <= index + direction < len(rack):
        return False
    other = index + direction
    if rack[index].extra.get('locked') or rack[other].extra.get('locked'):
        return False
    rack[index], rack[other] = rack[other], rack[index]
    return True


PARAMETER_CHOICES = {
    'mode': ('static', 'animate', 'react'),
    'source': ('reaction_mix', 'song', 'microphone', 'mix', 'recorded', 'recorded_mix', 'song_recorded'),
    'react_band': ('full', 'bass', 'mid', 'high', 'onset'),
    'interpolation': ('linear', 'smooth', 'hold'),
}
PARAMETER_NUMBERS = ('value', 'minimum', 'maximum', 'react_amount', 'attack', 'release', 'threshold')


def update_parameter(param, changes):
    """Validate the entire edit before touching values, authored keys or metadata."""
    trial = copy.deepcopy(param)
    for key, value in changes.items():
        if key in PARAMETER_CHOICES:
            if value not in PARAMETER_CHOICES[key]:
                raise ValueError('Choose a valid ' + key.replace('_', ' ') + '.')
        elif key in PARAMETER_NUMBERS:
            value = float(value)
            if not math.isfinite(value):
                raise ValueError('Values must be finite.')
        elif key in ('combine_animation', 'conductor_locked', 'react_full_range'):
            value = bool(value)
        else:
            raise ValueError('Unknown parameter field: ' + key)
        if key in ('conductor_locked','react_full_range'):
            trial.extra[key] = value
        else:
            setattr(trial, key, value)
    if trial.maximum <= trial.minimum:
        raise ValueError('Maximum must be greater than minimum.')
    if trial.attack < 0 or trial.release < 0:
        raise ValueError('Attack and release cannot be negative.')
    if not trial.minimum <= trial.value <= trial.maximum:
        raise ValueError('Base must lie inside the displayed range.')
    if not -1 <= trial.react_amount <= 1 or not 0 <= trial.threshold <= .99:
        raise ValueError('Reaction amount must be −1–1; threshold must be 0–0.99.')
    if trial.attack > 4 or trial.release > 8:
        raise ValueError('Attack must be 0–4 seconds; release must be 0–8 seconds.')
    trial.normalized()
    param.__dict__.update(trial.__dict__)
