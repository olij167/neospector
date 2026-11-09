"""Stable occurrence-pair addresses for the docked queue boundary controls."""
from __future__ import annotations

VISUAL_KINDS = {
    'cut': 'Cut', 'dissolve': 'Dissolve', 'fade_colour': 'Through colour',
    'wipe_left': 'Wipe ←', 'wipe_right': 'Wipe →', 'wipe_up': 'Wipe ↑',
    'wipe_down': 'Wipe ↓', 'slide_left': 'Slide ←', 'slide_right': 'Slide →',
    'iris_open': 'Iris open', 'iris_close': 'Iris close',
    'pixel_dissolve': 'Pixel dissolve',
}


def boundary_labels(entries, role, layer=None, project=None):
    """Cheap card labels over the queue snapshot already loaded by the view."""
    result = {}
    transitions = {(t.from_clip, t.to_clip): t for t in layer.transitions} if layer else {}
    for a, b in zip(entries, entries[1:]):
        if role == 'Music':
            overlap = a['start'] + a['duration'] - b['start']
            fades = min(a.get('fade_out', 0), b.get('fade_in', 0))
            if overlap > 1e-6:
                title = 'Crossfade' if abs(fades - overlap) < 1e-6 else 'Overlap'
                label = f'{title} {overlap:.2g}s'
            elif overlap < -1e-6:label = f'Gap {-overlap:.2g}s'
            else:label = 'Edge fades' if a.get('fade_out') or b.get('fade_in') else 'Cut'
            result[a['id']] = (b['id'], label)
        else:
            tr = transitions.get((a.id, b.id))
            overlap = a.end - b.start
            if tr:label = f"{VISUAL_KINDS.get(tr.kind, tr.kind)} {tr.duration:.2g}s"
            elif overlap > 1e-6:label = f'Overlap {overlap:.2g}s'
            elif overlap < -1e-6:label = f'Gap {-overlap:.2g}s'
            else:label = 'Edge fades' if a.fade_out or b.fade_in else 'Cut'
            result[a.id] = (b.id, label)
    if entries:
        music=role=='Music';store=project.extra if music and project is not None else layer.extra if layer is not None else {}
        repeating=store.get('music_queue_policy' if music else 'queue_policy')=='repeat'
        if repeating or store.get('music_queue_seam' if music else 'queue_seam'):
            from queue_seams import active_seam
            seam=active_seam(entries,store.get('music_queue_seam' if music else 'queue_seam')) or {}
            ident=lambda e:e['id'] if music else e.id
            prefix='Loop' if repeating else 'Edges'
            label=prefix+' · Cut' if seam.get('kind','cut')=='cut' else f"{prefix} · Fade {seam['duration']:.2g}s"
            result[ident(entries[-1])]=(ident(entries[0]),label)
    return result


def boundary(project, role, from_id, to_id=None):
    """Resolve a fresh pair; never apply a stale card index after a reorder."""
    if role == 'Music':
        from music_queue import items
        entries = items(project)
        ident = lambda e: e['id']
    else:
        from instrument_model import voice
        from queue_model import ordered
        layer = voice(project, role)
        entries = ordered(layer)
        ident = lambda e: e.id
    index = next((i for i, e in enumerate(entries) if ident(e) == from_id), -1)
    if entries and index==len(entries)-1:
        store=project.extra if role=='Music' else layer.extra
        if store.get('music_queue_policy' if role=='Music' else 'queue_policy')=='repeat' or store.get('music_queue_seam' if role=='Music' else 'queue_seam'):
            from queue_seams import seam_info
            info=seam_info(project,role,entries,layer=None if role=='Music' else layer)
            if to_id is not None and info['to_id']!=to_id:raise ValueError('The loop edge changed. Reopen this boundary.')
            return info
    if index < 0 or index + 1 >= len(entries):
        raise ValueError('Add a following item to edit this boundary.')
    a, b = entries[index:index + 2]
    if to_id is not None and ident(b) != to_id:
        raise ValueError('These items are no longer neighbours. Reopen the boundary.')
    if role == 'Music':
        seconds = max(0., min(a['start'] + a['duration'] - b['start'],
                              a.get('fade_out', 0), b.get('fade_in', 0)))
        kind = 'crossfade' if seconds else 'cut'
        maximum = min(a['duration'], b['duration']) * .8
        from queue_gaps import gap_name
        names = [gap_name(e) or (project.asset(e['asset_id']).name if project.asset(e['asset_id']) else 'Missing source') for e in (a,b)]
        curve=b.get('curve','equal_power');compatibility=False
        durations = [e['duration'] for e in (a, b)]
    else:
        tr = next((t for t in layer.transitions
                   if t.from_clip == from_id and t.to_clip == b.id), None)
        seconds, kind = (tr.duration, tr.kind) if tr else (0., 'cut')
        maximum = min(a.duration, b.duration) * .49
        from queue_gaps import gap_name
        names = [gap_name(e) or (project.asset(e.asset_id).name if project.asset(e.asset_id) else 'Missing source') for e in (a,b)]
        curve=tr.easing if tr else 'smooth';compatibility=layer.mixer_mode!='auto' and not (tr and tr.extra.get('queue_authored'))
        durations = [a.duration, b.duration]
    return dict(from_id=from_id, to_id=ident(b), kind=kind, seconds=seconds,
                maximum=maximum, names=names, durations=durations,curve=curve,compatibility=compatibility)


def set_boundary(project, role, from_id, to_id, kind, seconds, *, now=None,curve=None):
    info = boundary(project, role, from_id, to_id)
    if info.get('seam'):
        from queue_seams import set_seam
        return set_seam(project,role,info,kind,seconds,now=now,curve=curve)
    if role == 'Music':
        if kind not in ('cut', 'crossfade'):
            raise ValueError('Choose Cut or Crossfade for Music.')
        from music_queue import transition
        return transition(project, from_id, seconds, to_id=to_id,
                          now=now, cut=kind == 'cut',curve=curve)
    from instrument_model import voice
    from queue_model import set_boundary as visual_boundary
    return visual_boundary(project, voice(project, role).id, from_id,
                           info['to_id'], kind, seconds, now=now,curve=curve)
