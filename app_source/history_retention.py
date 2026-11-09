"""Owned temporary segment FIFO and short-lock interval reservations.

Manual projects, saved takes and source media never enter this cache. Unproven
project history pruning is deliberately excluded; an explicit metadata growth
cap suspends autonomy instead of deleting state needed for replay.
"""
import math,threading,uuid,copy
from pathlib import Path

DEFAULTS={'seconds':600.,'bytes':2*1024**3,'free_reserve':1024**3,'metadata_events':20000,'metadata_bytes':128*1024**2}

def coverage(spans):
    result=[]
    for a,b in sorted(spans):
        if b<=a:continue
        if result and a<=result[-1][1]+1e-8:result[-1]=(result[-1][0],max(b,result[-1][1]))
        else:result.append((float(a),float(b)))
    return result

def plan_retirement(units,*,now,window_seconds,byte_budget,pinned_ids):
    if not all(math.isfinite(float(x)) for x in (now,window_seconds,byte_budget)) or window_seconds<=0 or byte_budget<0:raise ValueError('Invalid history quota')
    ordered=sorted(units,key=lambda u:(u['end'],u['start'],u['id']));total=sum(u['bytes'] for u in ordered if u['owned_temporary']);retire=[]
    for u in ordered:
        eligible=u['owned_temporary'] and not u.get('referenced') and not u.get('active') and u['id'] not in pinned_ids
        if eligible and (u['end']<now-window_seconds or total>byte_budget):retire.append(u['id']);total-=u['bytes']
    kept=[u for u in ordered if u['id'] not in retire]
    return {'retire_ids':retire,'retain_ids':[u['id'] for u in kept], 'coverage_intervals':coverage([(u['start'],u['end']) for u in kept if u['owned_temporary']]),'unmet_budget':total>byte_budget,'retained_bytes':total}

class Reservations:
    def __init__(self):self.lock=threading.RLock();self.entries={}
    def reserve(self,start,end,ids=()):
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end:raise ValueError('Invalid reservation interval')
        token=uuid.uuid4().hex
        with self.lock:self.entries[token]=(float(start),float(end),set(ids))
        return token
    def release(self,token):
        with self.lock:self.entries.pop(token,None)
    def pinned(self,units):
        with self.lock:
            return {u['id'] for u in units if any(u['id'] in ids or (u['start']<end and u['end']>start) for start,end,ids in self.entries.values())}

def owned_file(path,root):
    if Path(root).is_symlink():return False
    p=Path(path);root=Path(root).resolve()
    if p.is_symlink() or not p.is_file():return False
    try:
        if not p.resolve().is_relative_to(root):return False
        relative=p.absolute().relative_to(root)
        current=root
        for part in relative.parts:
            current=current/part
            if current.is_symlink():return False
        return True
    except (ValueError,OSError):return False

def segment_paths(segment):
    result={segment[k] for k in ('video','audio','manifest') if segment.get(k)}
    result.update(s['path'] for s in segment.get('raw_sources',[]) if s.get('path'))
    for camera in segment.get('camera_sources',[]):result.update(segment_paths(camera))
    return result

def segment_units(segments,root):
    units=[]
    for n,s in enumerate(segments):
        s.setdefault('id',s.get('manifest') or f"segment-{s['start']}-{n}")
        paths=segment_paths(s);owned=all(owned_file(p,root) for p in paths)
        units.append(dict(id=s['id'],start=s['start'],end=s['start']+s['duration'],bytes=sum(Path(p).stat().st_size for p in paths if Path(p).is_file()) if owned else 0,owned_temporary=owned,referenced=False,active=False))
    return units

def retire_segments(segments,root,*,now,window_seconds,byte_budget,pinned_ids):
    units=segment_units(segments,root);result=plan_retirement(units,now=now,window_seconds=window_seconds,byte_budget=byte_budget,pinned_ids=pinned_ids)
    kept=[s for s in segments if s['id'] not in result['retire_ids']];keep_paths={Path(p).resolve() for s in kept for p in segment_paths(s)}
    # Caller holds the same metadata lock as reservation creation. Determine the
    # entire surviving reference set before unlinking any complete retired unit.
    for s in segments:
        if s['id'] not in result['retire_ids']:continue
        for path in segment_paths(s):
            if Path(path).resolve() not in keep_paths and owned_file(path,root):Path(path).unlink(missing_ok=True)
    result['segments']=kept;return result

def metadata_count(project):
    total=0
    def visit(value):
        nonlocal total
        if isinstance(value,dict):
            for key,v in value.items():
                if isinstance(v,list) and (key.endswith('history') or key.endswith('transitions') or key in ('source_switches','keyframes','sound_events','clips','transitions')):total+=len(v)
                visit(v)
        elif isinstance(value,list):
            for v in value:visit(v)
    from sequencer_model import project_to_dict
    visit(project_to_dict(project));return total
