"""Small, reversible bulk audio-reaction actions for a *single* module face.

Per-parameter source, band, envelope and keyframes remain independently editable.
Master actions are one project transaction, never one transaction per slider.
"""
from __future__ import annotations
from live_parameter_controls import initial_reaction_changes
from rack_editing import update_parameter


def reaction_summary(effect):
    params=list(effect.params.values())
    active=sum(p.mode=='react' for p in params)
    source={p.source for p in params}
    bands={p.react_band for p in params}
    return {'state':'on' if params and active==len(params) else 'mixed' if active else 'off',
            'depth':sum(p.react_amount for p in params)/len(params) if params else 0.,
            'source':next(iter(source)) if len(source)==1 else 'mixed',
            'band':next(iter(bands)) if len(bands)==1 else 'mixed',
            'active':active,'total':len(params)}


def apply_all_reactions(effect,enabled):
    if effect.extra.get('locked'):
        raise ValueError('Unlock this module before changing reactions.')
    for param in effect.params.values():
        if enabled:
            if param.mode!='react':
                changes=initial_reaction_changes(param,source=effect.extra.get('ux41_master_source'))
                if effect.extra.get('ux41_master_band') is not None:
                    changes['react_band']=effect.extra['ux41_master_band']
                update_parameter(param,changes)
        elif param.mode=='react':
            # Preserve authored animation data and enable it again when leaving
            # reaction mode; an 'off' toggle must silence *all* module reactions.
            update_parameter(param,{'mode':'animate' if param.keyframes else 'static'})
    return reaction_summary(effect)


def apply_all_depth(effect,amount):
    amount=max(-1.,min(1.,float(amount)))
    if effect.extra.get('locked'):
        raise ValueError('Unlock this module before changing reactions.')
    for param in effect.params.values():
        if param.mode!='react':
            update_parameter(param,initial_reaction_changes(param))
        update_parameter(param,{'react_amount':amount})
    return reaction_summary(effect)


def apply_all_routing(effect,*,source=None,band=None):
    """Route every exposed parameter in one undoable rack transaction.

    Does not alter per-parameter reaction depth, envelopes, keys or enabled state.
    Inactive modules can be configured without secretly activating capture.
    """
    from rack_editing import PARAMETER_CHOICES
    if effect.extra.get('locked'):raise ValueError('Unlock this module first.')
    if source is not None and source not in PARAMETER_CHOICES['source']:
        raise ValueError('Invalid module-wide audio source')
    if band is not None and band not in PARAMETER_CHOICES['react_band']:
        raise ValueError('Invalid module-wide reaction band')
    for param in effect.params.values():
        changes={}
        if source is not None:changes['source']=source
        if band is not None:changes['react_band']=band
        if changes:update_parameter(param,changes)
    if source is not None:effect.extra['ux41_master_source']=source
    if band is not None:effect.extra['ux41_master_band']=band
    return reaction_summary(effect)
