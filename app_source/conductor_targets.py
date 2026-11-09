"""One default for missing Conductor targets; explicit project choices take priority."""

DEFAULTS = {'evolve_treatment': True, 'evolve_sources': False, 'evolve_sound': False}


def enabled(conductor, key):
    return bool(conductor.extra.get(key, DEFAULTS[key]))
