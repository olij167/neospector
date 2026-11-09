"""Capture the real native interface and check bounds of its primary controls."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app_source'))
from PIL import ImageGrab
from neospector_console import NeospectorApp


def main():
    out = ROOT / 'evidence/r5c2/screenshots'
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='r5c2-ui-') as profile:
        os.environ['OMNE_SEQUENCER_SANDBOX'] = profile
        app = NeospectorApp(test_mode=True)
        errors, checks = [], []
        app.report_callback_exception = lambda *args: errors.append(repr(args))

        def pump(seconds=.4):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.update()
                time.sleep(.005)

        def bounds(widget):
            return (widget.winfo_rootx(), widget.winfo_rooty(),
                    widget.winfo_width(), widget.winfo_height())

        def contained(widget, owner):
            x, y, w, h = bounds(widget)
            ox, oy, ow, oh = bounds(owner)
            return bool(widget.winfo_ismapped() and x >= ox and y >= oy
                        and x+w <= ox+ow and y+h <= oy+oh)

        def shot(name):
            app.lift()
            pump()
            x, y, w, h = bounds(app)
            primary = [app.play_button, app.randomise_button, app.global_camera_group,
                       app.global_mic_button, app.record_button, app.visual_master_fader,
                       *app.deck.primary_actions, app.conductor.random_button]
            clipped = [str(c) for c in primary if not contained(c, app)]
            for dial in app.conductor.dials:
                if not contained(dial.entry, app.conductor_tab):
                    clipped.append('Conductor numeric: '+str(dial.entry))
            for role, fader in app.queue_deck.channel_faders.items():
                if not contained(fader.scale, app.queue_deck.pages[role]):
                    clipped.append('Visual fader: '+role)
            for role, fader in app.source_strip.faders.items():
                if not contained(fader.scale, app.source_strip):
                    clipped.append('Audio fader: '+role)
            row = next((r for r in app.deck.rows if hasattr(r, 'canvas') and r.winfo_ismapped()), None)
            if row is not None:
                for c in (row.canvas, row.entry):
                    if not contained(c, app.deck.scroll.canvas):
                        clipped.append('First module: '+str(c))
            for role in ('A', 'B'):
                page = app.queue_deck.pages[role]
                if not page.canvas.winfo_ismapped() or page.canvas.winfo_height() < 42:
                    clipped.append(role+' upcoming card area')
            if not app.library.winfo_ismapped() or app.library.winfo_height() < 65:
                clipped.append('Library browser area')
            panels = {'library': app.library, 'visuals': app.queue_deck,
                      'A upcoming': app.queue_deck.pages['A'].canvas,
                      'B upcoming': app.queue_deck.pages['B'].canvas,
                      'music': app.source_strip.music_host,
                      'conductor': app.conductor, 'audio': app.source_strip}
            sizes = {k: [v.winfo_width(), v.winfo_height(), bool(v.winfo_ismapped())]
                     for k, v in panels.items()}
            ImageGrab.grab(bbox=(x, y, x+w, y+h)).save(out / (name+'.png'))
            checks.append(dict(image=name+'.png', size=[w, h], clipped=clipped, panels=sizes))

        try:
            app.geometry('1440x940+0+0')
            pump(.8)
            shot('r5c2-empty')
            app.open_example()
            pump(1)
            app.new_treatment()
            pump(.7)
            shot('r5c2-instrument')
            app.geometry('1080x740+0+0')
            app.load_layout({})
            pump(.6)
            shot('r5c2-small')
            app.geometry('1440x940+0+0')
            app.load_layout({})
            app.queue_deck.add_channel()
            pump(.6)
            shot('r5c2-three-channels')
            app.queue_deck.add_channel()
            pump(.4)
            shot('r5c2-four-channels')
            app.apply_theme('Space Funk', False)
            pump(.5)
            shot('r5c2-space')
            app.tk.call('tk', 'scaling', 2.0)
            app.geometry('1440x1000+0+0')
            app.load_layout({})
            pump(.5)
            shot('r5c2-scaled')
            report = dict(checks=checks, callback_errors=errors,
                          phase_errors=app.playback_diagnostics().get('phase_errors', []),
                          environment='Native Tk under Xvfb; no physical/audible device acceptance')
            (out / 'review.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
            return int(bool(errors) or any(c['clipped'] for c in checks)
                       or bool(report['phase_errors']))
        finally:
            app.close(force=True)


if __name__ == '__main__':
    raise SystemExit(main())
