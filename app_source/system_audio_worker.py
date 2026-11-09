"""Optional Windows WASAPI loopback worker; stdout is raw float32 mono PCM."""
import json, sys

def main(payload=None):
    import numpy as np
    import soundcard as sc
    options=json.loads(payload if payload is not None else sys.argv[1])
    if options.get('list'):
        print(json.dumps([dict(kind='system',backend='wasapi',device=str(s.id),label='Device audio · '+s.name) for s in sc.all_speakers()]));return
    mic=sc.get_microphone(id=options['device'],include_loopback=True);rate=int(options.get('rate',24000))
    # SoundCard documents invalid single-channel WASAPI recordings: acquire both
    # channels then downmix, instead of requesting a mono WASAPI capture stream.
    with mic.recorder(samplerate=rate,channels=2,blocksize=4096) as recorder:
        while True:
            block=recorder.record(numframes=1024)
            sys.stdout.buffer.write(np.asarray(block.mean(axis=1),dtype='<f4').tobytes());sys.stdout.buffer.flush()

if __name__=='__main__':
    try:main()
    except BrokenPipeError:pass
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
