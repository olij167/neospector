"""UX29 source placement eligibility. One list, no destination filter or mode coupling."""
from ux22_project_browser import eligible_destinations

def file_destinations(assets):
    assets=list(assets)
    return tuple(role for role in ('A','B','Music') if assets and all(role in eligible_destinations(a) for a in assets))

def source_destinations(source):
    if source.get('capture_available') is False:return ()
    kind=source.get('kind')
    if kind in ('camera','screen','window'):return ('A','B')
    if kind in ('microphone','system','application'):return ('Music',)
    return ()

ROLE_NAMES={'A':'Channel A','B':'Channel B','Music':'Audio queue'}
LIVE_ROLE_NAMES={'A':'Channel A','B':'Channel B','Music':'Audio · timed reaction cue'}
ACTIONS={'now':'▶ Take now','next':'⏭ Play next','queue':'＋ Add to end'}
