"""Stable analysis jobs and a finite representative window for repeated Music."""
import json
from audio_bus import sound_events


def analysis_signature(project):
    events=sound_events(project)
    keys=('sound_routes','sound_route_history','music_queue_policy',
          'music_queue_origins','music_queue_history','music_queue_seam')
    # Event flattening does not describe the clock/seam gain applied by the
    # sample mixer. Include those authored inputs without visual FX payloads.
    clock_keys=('queue_policy','source_switches','queue_seam')
    route_ids={e.get('route_id') for e in events}
    clocks=[]
    for layer in project.layers:
        if 'voice:'+str(layer.extra.get('voice')) not in route_ids:continue
        clocks.append((layer.id,{k:layer.extra.get(k) for k in clock_keys},
            [(r['start'],r['end'],{k:r['state'].get('extra',{}).get(k) for k in clock_keys})
             for r in layer.extra.get('queue_history',[])]))
    return json.dumps([events,{k:project.extra.get(k) for k in keys},
        [(aid,project.assets[aid].path,project.assets[aid].duration)
         for aid in sorted({e['asset_id'] for e in events if e.get('asset_id')})
         if aid in project.assets],clocks],sort_keys=True)


def analysis_window(project):
    events=sound_events(project)
    cycle=max((e['start']+e['duration'] for e in events),default=0.)
    if (project.extra.get('music_queue_policy')=='repeat' and 0<cycle<=3600
            and all(e.get('route_id')=='soundtrack' for e in events)):
        origin=max([0.]+[o['start'] for o in project.extra.get('music_queue_origins',[])]
                   +[r['end'] for r in project.extra.get('music_queue_history',[])])
        return origin,origin+cycle,{'start':origin,'duration':cycle}
    return 0.,min(project.max_end(),3600),None
