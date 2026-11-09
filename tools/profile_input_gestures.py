"""Model/history lower bound; omits Tk, drawing, playback and audio costs.

Run from the release root: python tools/profile_input_gestures.py
Fifteen repeats per case; nearest-rank p95 is the largest of 15 samples.
"""
import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app_source'))
from omne_sequencer import SequencerApp
from sequencer_model import ProjectHistory, Clip
from instrument_model import new_instrument
from omne_conductor import ConductorPanel


class Variable:
    def __init__(self, value): self.value = value
    def set(self, value): self.value = value
    def get(self): return self.value


def profile():
    rows = []
    for count in (10, 100, 1000, 5000):
        project = new_instrument()
        project.layers[0].clips = [Clip(str(i), 'asset', start=i*4, duration=4) for i in range(count)]
        app = SimpleNamespace(project=project, history=ProjectHistory(project), gesture=None,
            playhead=0., get_edit_target=lambda: (project.layers[0], None), changed=lambda **kw: None,
            deck=SimpleNamespace(refresh=lambda **kw: None), conductor=SimpleNamespace(refresh=lambda: None),
            programme_time=lambda: 0., policy_changed=lambda: None)
        panel = SimpleNamespace(app=app, active=None, loading=False,
                                values={'variation': Variable(.5)}, refresh=lambda: None)
        result = {'clips': count}
        for mode in ('generic', 'conductor'):
            samples = {key: [] for key in ('begin', 'update_model_only', 'end')}
            for repeat in range(15):
                app.history.undo_stack.clear()
                value = .3 if repeat % 2 else .7
                start = time.perf_counter()
                if mode == 'generic': SequencerApp.begin_gesture(app, 'program')
                else: ConductorPanel.begin(panel, 'variation')
                samples['begin'].append((time.perf_counter()-start)*1000)
                start = time.perf_counter()
                if mode == 'generic': project.layers[0].opacity.value = value
                else: ConductorPanel.changed(panel, 'variation', value)
                samples['update_model_only'].append((time.perf_counter()-start)*1000)
                start = time.perf_counter()
                if mode == 'generic': SequencerApp.end_gesture(app)
                else: ConductorPanel.end(panel)
                samples['end'].append((time.perf_counter()-start)*1000)
            result[mode] = {key: {'median_ms': round(statistics.median(values), 3),
                                 'p95_ms': round(max(values), 3)} for key, values in samples.items()}
        rows.append(result)
    return rows


if __name__ == '__main__': print(json.dumps(profile(), indent=2))
