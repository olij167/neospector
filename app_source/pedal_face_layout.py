"""UX14 deterministic, bounded faceplate arrangement; no UI or model dependencies."""
from dataclasses import dataclass
import math

FACE_HEIGHT=184
MIN_WIDTH=210
GAP=6

@dataclass(frozen=True)
class FaceArrangement:
    columns:int
    positions:dict
    cell_width:int
    rowspans:dict|None=None
    height:int=FACE_HEIGHT


def face_pages(parameter_count:int,wide:bool)->int:
    return max(1,math.ceil(max(0,parameter_count)/(6 if wide else 3)))


def place_faces(width:int,items):
    """items are (stable ID, visible parameter count).

    Groups with more than 3 controls span two columns when there is room;
    otherwise they use banked controls inside a single fixed-height face.
    """
    width=max(160,int(width));columns=max(1,min(5,(width-GAP)//(MIN_WIDTH+GAP)))
    from ux16_layout import dense_pack
    # Respect a group's actual parameter count, but allow a uniform one-slot
    # module when the control inventory is small.
    footprints=[(fid,4 if count>8 else 2 if count>3 else 1) for fid,count in items]
    # In a one-column viewport, tall cards waste space and conceal the
    # next module. Use a regular-height face with banked parameters instead.
    if columns==1:footprints=[(fid,1) for fid,_area in footprints]
    packed=dense_pack(columns,footprints)
    positions={fid:(y,x,w) for fid,(x,y,w,h) in packed.items()}
    rowspans={fid:h for fid,(x,y,w,h) in packed.items()}
    cell_width=max(160,(width-(columns+1)*GAP)//columns)
    return FaceArrangement(columns,positions,cell_width,rowspans)
