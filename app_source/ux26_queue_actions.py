"""Per-queue immediate Stop and remove-current over existing authored clocks.

Do not delete source assets, stop the programme or mutate an unrelated lane.
The preserved history makes these actions safe for recording and undo.
"""
from __future__ import annotations


def stop_queue(project,role,now):
    from queue_policies import (set_music_policy,set_music_origin,set_visual_policy)
    from queue_model import append_switch
    if role=='Music':
        from music_queue import items
        set_music_policy(project,'finish',now)
        last=max((float(e['start'])+float(e['duration']) for e in items(project)),default=0.)
        set_music_origin(project,now,last)
    else:
        from instrument_model import voice
        layer=voice(project,role)
        set_visual_policy(layer,'finish',now)
        last=max((c.end for c in layer.clips),default=0.)
        append_switch(layer,now,'queue',last)
    project.touch()
    return True


def remove_playing(project,role,occurrence_id,now):
    """Remove the active occurrence and advance to its neighbour instantly.

    Unlike a plain reorder/remove, the old performed interval is held in
    queue_history/music_queue_history, while the clock moves to the survivor.
    """
    if not occurrence_id:return False
    if role=='Music':
        from music_queue import items,remove
        from queue_policies import preserve_music_history,set_music_origin
        before=items(project)
        ids=[e['id'] for e in before]
        if occurrence_id not in ids:return False
        at=ids.index(occurrence_id)
        successor=next((i for i in ids[at+1:] if i!=occurrence_id),None)
        if successor is None and project.extra.get('music_queue_policy')=='repeat':
            successor=next((i for i in ids if i!=occurrence_id),None)
        preserve_music_history(project,now)
        remove(project,occurrence_id)
        later=items(project)
        item=next((e for e in later if e['id']==successor),None)
        pos=item['start'] if item else max((e['start']+e['duration'] for e in later),default=0.)
        set_music_origin(project,now,pos)
    else:
        from instrument_model import voice
        from queue_model import ordered,remove,append_switch
        layer=voice(project,role)
        before=ordered(layer);ids=[c.id for c in before]
        if occurrence_id not in ids:return False
        at=ids.index(occurrence_id)
        successor=next((i for i in ids[at+1:] if i!=occurrence_id),None)
        if successor is None and layer.extra.get('queue_policy')=='repeat':
            successor=next((i for i in ids if i!=occurrence_id),None)
        remove(project,occurrence_id,now=now)
        later=ordered(layer)
        item=next((c for c in later if c.id==successor),None)
        pos=item.start if item else max((c.end for c in later),default=0.)
        append_switch(layer,now,'queue',pos)
    project.touch()
    return True
