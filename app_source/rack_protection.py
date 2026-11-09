"""Explicitly separate composition locks from autonomous Conductor authorship."""

def composition_locked(effect):
    from module_engine import children
    return bool((effect.extra.get('locked') or effect.extra.get('variation_locked')) or any(composition_locked(child) for child in children(effect)))

def conductor_protected(effect):
    from module_engine import children
    return bool((effect.extra.get('locked') or effect.extra.get('variation_locked')) or any(p.extra.get('conductor_locked') or
                (p.keyframes and not p.extra.get('conductor_generated')) for p in effect.params.values()) or
                any(conductor_protected(child) for child in children(effect)))
