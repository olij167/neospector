"""UX42 responsive projection for the retained Neospector Tk instrument.

No Tk calls, side effects, user preference writes or platform/monitor-brand branches.
All measurements passed here are Tk window coordinates. Tk already handles its
font and widget scaling; multiplying by a second DPI ratio would double-scale.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

_WINDOW = re.compile(r'^(\d+)x(\d+)([+-]\d+)?([+-]\d+)?$')


def minimum_window_size(screen_width: int, screen_height: int) -> tuple[int,int]:
    """A 736px minimum remains usable in the compact, scrollable workstation."""
    return (max(320,min(860,int(screen_width)-64)),
            max(260,min(600,int(screen_height)-64)))


def startup_geometry(saved: str, bounds: tuple[int,int,int,int]) -> str:
    """Clamp startup size and position to the currently connected display.

    Do not restore a stale 4K size on a 1366x768 laptop. The function only
    projects window chrome; it never changes saved user workspace settings.
    Offsets of the form `-0` are relative to the far edge in Tk's WM syntax.
    """
    bx,by,bw,bh=(int(v) for v in bounds)
    bw=max(320,bw);bh=max(260,bh)
    safe_w=max(240,bw-64);safe_h=max(240,bh-64)
    m=_WINDOW.fullmatch(str(saved).strip())
    if m:
        req_w,req_h=int(m.group(1)),int(m.group(2))
        width=min(max(320,req_w),safe_w)
        height=min(max(240,req_h),safe_h)
        sx,sy=m.group(3),m.group(4)
        x=bx+32 if sx is None else (bx+bw-width+int(sx) if sx.startswith('-') else int(sx))
        y=by+32 if sy is None else (by+bh-height+int(sy) if sy.startswith('-') else int(sy))
    else:
        width=min(1440,safe_w);height=min(940,safe_h)
        x=bx+32;y=by+32
    x=max(bx,min(x,bx+bw-width-32))
    y=max(by,min(y,by+bh-height-32))
    # Negative absolute offsets have special meaning in Tk geometry strings;
    # restore to the currently visible primary area if the virtual origin is
    # negative rather than accidentally attaching to the far right/bottom.
    if x<0:x=0
    if y<0:y=0
    return f'{width}x{height}+{x}+{y}'


@dataclass(frozen=True)
class StageProjection:
    programme: tuple[int,int,int,int]
    rack: tuple[int,int,int,int] | None
    browser: tuple[int,int,int,int] | None
    queue: tuple[int,int,int,int] | None
    available_queue_height: int
    mode: str
    left_width: int
    queue_width: int


def project_stage(width: int, height: int, *, browser: bool, rack: bool,
                  roles: tuple[str,...], visual_top: int, queue_height: int,
                  browser_ideal_height: int = 320, gap: int = 8) -> StageProjection:
    """Lay out the physical stage without modifying queue, playback or rack state.

    A/B/Music always share a bottom-right overlay, including when all three
    are open; the browser and rack reside beside the preview, never over it.
    Layout depends on the actual window size, not its monitor's pixel count.
    """
    w,h=max(1,int(width)),max(1,int(height))
    g=max(0,min(24,int(gap)))
    centre_min=min(440,max(280,int(w*.51)))
    media_width=min(500,max(300,int(w*.285))) if browser else 0
    rack_width=min(500,max(305,int(w*.33))) if rack else 0
    left_width=min(max(media_width,rack_width),max(0,w-centre_min-g))
    px=left_width+g if left_width else 0
    pw=max(1,w-px)
    programme=(px,0,pw,h)
    rack_rect=browser_rect=None
    if browser and rack:
        # The browser remains a shelf; it doesn't become a full-height sidebar
        # when the rack opens. Both retained widget trees remain mounted.
        bh=max(120,min(int(browser_ideal_height),max(120,int(h*.57))))
        bh=min(bh,max(1,h//2))
        rh=max(1,h-bh-g)
        rack_rect=(0,0,left_width,rh)
        browser_rect=(0,rh+g,left_width,max(1,h-rh-g))
    elif browser:
        browser_rect=(0,0,left_width,h)
    elif rack:
        rack_rect=(0,0,left_width,h)
    roles=tuple(roles)
    top=max(0,min(int(visual_top),max(0,h-120)))
    available=max(0,h-top-2*g-4)
    qw=min(440,max(264,int(w*.305))) if roles else 0
    qw=min(qw,max(1,w-2*g))
    qh=min(max(1,int(queue_height)),max(1,h-g-2)) if roles else 0
    queue=(w-qw-g,max(0,h-g-qh),qw,qh) if roles and queue_height>0 else None
    mode='compact' if w<1120 or h<650 else 'wide' if w>=2400 else 'standard'
    return StageProjection(programme,rack_rect,browser_rect,queue,available,mode,left_width,qw)
