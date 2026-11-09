"""Pure responsive faceplate layout, independent of parameter values/animation."""
def geometry(width,count):
    width=max(180,int(width));minimum=270;maximum=330;gap=16
    cols=max(1,min(max(1,count),int(width//(minimum+gap))))
    usable=max(180,(width-(cols+1)*gap)//cols)
    # Friendly ten-pixel steps avoid reflow churn from scrollbar/rounding changes.
    return cols,min(maximum,max(180,(usable//10)*10))

def expanded(mode,width):
    return mode=='Expanded' or (mode=='Auto' and width>=275)
