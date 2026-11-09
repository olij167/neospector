"""Small deterministic pedal packing and honest, semantic parameter control policy."""
from __future__ import annotations

STEPPED={'rows','columns','taps','waves','spacing','steps','count','segments','iterations'}
SWITCHES={'enabled','active','invert_on','mirror_on','clamp','sync','loop'}

def parameter_kind(name,minimum,maximum):
    name=str(name).lower()
    if name in SWITCHES and minimum==0 and maximum==1:return 'switch'
    if name in STEPPED:return 'steps'
    if float(minimum)<0<float(maximum):return 'bipolar'
    return 'continuous'

def dense_pack(columns,items):
    """First-fit packing. Order is signal order; placement never changes that order.

    Items are (id, desired slot area). For two-slot effects try horizontal, then
    vertical if a preceding row has an available single slot; fill holes before
    growing rows. The last row may be sparse.
    """
    columns=max(1,int(columns));occupied=set();result={}
    for ident,area in items:
        area=max(1,int(area))
        footprints=[(1,1)] if area==1 or columns==1 else [(2,1),(1,2)]
        if area>=4 and columns>=2:footprints=[(2,2),(2,1),(1,2)]
        if columns==1 and area>=2:footprints=[(1,min(2,area))]
        chosen=None
        for y in range(len(items)*3+3):
            for x in range(columns):
                candidates=[]
                for w,h in footprints:
                    if x+w>columns:continue
                    cells={(xx,yy) for yy in range(y,y+h) for xx in range(x,x+w)}
                    if cells.isdisjoint(occupied):candidates.append((w,h,cells))
                if candidates:
                    # At the same free starting position prefer width; the
                    # vertical option rescues a one-slot gap before next row.
                    w,h,cells=candidates[0];chosen=(x,y,w,h,cells);break
            if chosen:break
        if chosen is None:raise RuntimeError('Pedal cannot be placed')
        x,y,w,h,cells=chosen;occupied.update(cells);result[ident]=(x,y,w,h)
    return result
