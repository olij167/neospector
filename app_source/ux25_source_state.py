"""One camera-activity interpretation for direct overrides and queued sources.

This is a read-only query. It never starts hardware or changes source clocks.
"""
from queue_model import mode_at,current


def active_source(project,layer,now):
    if layer is None:return None,None
    mode=mode_at(layer,now)
    if mode['mode']=='camera':
        asset=project.asset(mode.get('camera_id',''))
        return asset,'override'
    if mode['mode'] in ('queue','hold'):
        clip=current(layer,now)
        return (project.asset(clip.asset_id) if clip else None),'queue'
    return None,None


def queued_camera_active(project,layer,now):
    asset,_=active_source(project,layer,now)
    return bool(asset and asset.kind=='camera')


def active_queued_camera(project,layer,now):
    asset,source=active_source(project,layer,now)
    return bool(source=='queue' and asset and asset.kind=='camera')


def advance_queued_camera(layer,now):
    """Advance a live camera occurrence, retaining the authored queue.

    Without a successor freeze at the queue end (rather than accidentally
    replaying the same camera under a repeat policy).
    """
    from queue_model import ordered,queue_position,take_next,append_switch
    from queue_policies import activate_visual_state,preserve_visual_history
    clips=ordered(layer);q=queue_position(layer,now)
    following=next((clip for clip in clips if clip.start>q+1e-6),None)
    if following:
        take_next(layer,now,following.id)
        return following.id
    activate_visual_state(layer,now);preserve_visual_history(layer,now)
    end=max((clip.end for clip in clips),default=0.)
    append_switch(layer,now,'pause',end,resume_mode='queue')
    return None
