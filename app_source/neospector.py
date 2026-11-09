#!/usr/bin/env python3
"""Run the Neospector OmN-e R5 instrument; compatibility imports remain unchanged."""
import sys
from pathlib import Path
if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--audio-loopback-worker':
        from system_audio_worker import main
        main(sys.argv[2])
    else:
        from neospector_console import NeospectorApp
        app=NeospectorApp()
        if len(sys.argv)>1 and Path(sys.argv[1]).is_file():
            path=sys.argv[1];app.after(650,lambda:app.open_project(path))
        app.mainloop()
