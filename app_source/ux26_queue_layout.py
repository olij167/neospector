"""UX26 finite, content-weighted queue trays. No arbitrary A/B priority.

A queue owns a non-scrolling header/current/transport. Only its upcoming
occurrences grow with content, and only that region shrinks on contention.
"""
from __future__ import annotations

ROW=42
GAP=5
# Measured with the actual Tk queue chrome at a 1400x880 host: the A/B
# collapsed card requests ~109px; its previous 163px reservation left a
# conspicuous empty strip. The expanded card needs ~130px + visible rows.
VISUAL_CLOSED=114
VISUAL_OPEN_BASE=130
AUDIO_CLOSED=105
AUDIO_OPEN_BASE=120
AUDIO_MIXER_MIN=230
AUDIO_MIXER_IDEAL=365


def requested_height(role,expanded,upcoming):
    """Return natural tray height; even an empty expanded list gets one row."""
    count=max(0,int(upcoming))
    if role=='Music':return AUDIO_OPEN_BASE+max(1,count)*ROW if expanded else AUDIO_CLOSED
    return VISUAL_OPEN_BASE+max(1,count)*ROW if expanded else VISUAL_CLOSED


def allocate(roles,wanted,available,expanded=None):
    """Split fixed space fairly by content demand, never promoting to full sidebar.

    Both visual queues use the same size rule. Under constraint, reserve their
    minimum chrome and divide the remaining flexible area in proportion to the
    extra rows requested. The capped list's own canvas does the scrolling.
    """
    roles=tuple(roles)
    if not roles:return {}
    expanded=expanded or {}
    usable=max(0,int(available)-(len(roles)-1)*GAP)
    minimum={r:((AUDIO_OPEN_BASE if r=='Music' else VISUAL_OPEN_BASE)+ROW
                if expanded.get(r) else AUDIO_CLOSED if r=='Music' else VISUAL_CLOSED) for r in roles}
    if sum(wanted[r] for r in roles)<=usable:return {r:int(wanted[r]) for r in roles}
    base=sum(minimum.values())
    if usable<base:
        # Impossible minimum (tiny window): preserve identical rules and let
        # the output chrome own its minimum OS/window size.
        each=max(90,usable//len(roles))
        return {r:each for r in roles}
    spare=usable-base
    extras={r:max(0,int(wanted[r])-minimum[r]) for r in roles}
    result=dict(minimum)
    pending=set(roles)
    while pending and spare>0:
        total=sum(extras[r] for r in pending)
        if total<=0:break
        grants={r:min(extras[r],int(spare*extras[r]/total)) for r in pending}
        if not any(grants.values()):
            # Deterministic stable tie-breaking (A before B, not list order).
            r=sorted(pending,key=lambda r:(-extras[r],r))[0]
            grants[r]=1
        for r,n in grants.items():result[r]+=n;extras[r]-=n;spare-=n
        pending={r for r in pending if extras[r]>0}
    return result
