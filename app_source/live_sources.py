"""Opt-in local capture. Device acquisition never happens during project loading.

Hardware backends are explicitly selected and errors remain visible. Synthetic
sources exercise the same readers/recorders without requiring capture hardware.
"""
from __future__ import annotations
import json, os, sys, time, threading, subprocess, wave, re
from pathlib import Path
from collections import deque
import numpy as np
from PIL import Image
from media_engine import FFMPEG
from process_tools import popen_options, stop_process, EncoderPipe, run_process
from signal_engine import analyze_samples, analyze_file

CAMERA_SIZE=(640,360)
CAMERA_FPS=20
AUDIO_RATE=24000


def capture_command(kind,device,*,platform_name=None):
    platform_name=platform_name or sys.platform
    if isinstance(device,dict):
        if kind!='microphone':raise ValueError('Device audio is an audio input, not a camera')
        from system_audio import source_command
        return source_command(device,rate=AUDIO_RATE,ffmpeg=FFMPEG)
    cmd=[FFMPEG,'-hide_banner','-loglevel','warning','-nostdin','-threads','1']
    if device=='test':
        cmd+=['-re','-f','lavfi','-i','testsrc2=size=640x360:rate=20' if kind=='camera' else 'sine=frequency=110:sample_rate=24000']
    elif platform_name.startswith('linux'):
        cmd+=['-f','v4l2' if kind=='camera' else 'pulse','-i',str(device or ('/dev/video0' if kind=='camera' else 'default'))]
    elif platform_name=='win32':cmd+=['-f','dshow','-i',('video=' if kind=='camera' else 'audio=')+str(device)]
    elif platform_name=='darwin':cmd+=['-f','avfoundation','-i',str(device)+':none' if kind=='camera' else 'none:'+str(device)]
    else:raise ValueError('No capture adapter for this operating system')
    if kind=='camera':
        cmd+=['-an','-vf','fps=20,scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:color=black','-pix_fmt','rgba','-threads','1','-f','rawvideo','pipe:1']
    else:cmd+=['-vn','-ac','1','-ar',str(AUDIO_RATE),'-f','f32le','pipe:1']
    return cmd


def enumerate_devices():
    result={'camera':[],'microphone':[],'notes':[]}
    if sys.platform.startswith('linux'):
        result['camera']=[str(p) for p in sorted(Path('/dev').glob('video*'))]
        result['microphone']=['default']
        try:
            cp=run_process(['pactl','list','short','sources'],timeout=5)
            result['microphone'] += [row.split()[1] for row in cp.stdout.decode().splitlines() if len(row.split())>1]
        except Exception:result['notes'].append('PulseAudio/PipeWire default input is offered; pactl device listing was unavailable.')
    else:
        backend='dshow' if sys.platform=='win32' else 'avfoundation'
        try:
            cp=run_process([FFMPEG,'-hide_banner','-list_devices','true','-f',backend,'-i','dummy' if backend=='dshow' else ''],check=False,timeout=8)
            text=cp.stderr.decode('utf-8','replace');section='camera'
            for line in text.splitlines():
                if 'audio devices' in line.lower():section='microphone'
                if backend=='dshow':
                    match=re.search(r'"([^"]+)" \((video|audio)\)',line)
                    if match:result['camera' if match[2]=='video' else 'microphone'].append(match[1])
                else:
                    match=re.search(r'\[(\d+)\] (.+)$',line)
                    if match and 'devices' not in match[2]:result[section].append(match[1])
            result['notes'].append(text[-8000:])
        except Exception as exc:result['notes'].append(str(exc))
    for kind in ('camera','microphone'):result[kind]=list(dict.fromkeys(result[kind]+['test']))
    return result


class Capture:
    def __init__(self,kind,device,callback=None):
        self.kind=kind;self.device=device;self.callback=callback;self.latest=None;self.stamp=0.;self.count=0
        self.size=CAMERA_SIZE if kind=='camera' else None;self.fps=CAMERA_FPS if kind=='camera' else None
        self.state='starting';self.error='';self.tail=deque(maxlen=16);self.stop=threading.Event()
        self.command=capture_command(kind,device)
        self.proc=subprocess.Popen(self.command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**popen_options())
        self.reader=threading.Thread(target=self._read,daemon=True);self.logger=threading.Thread(target=self._stderr,daemon=True)
        self.logger.start();self.reader.start()
    def _stderr(self):
        try:
            for line in iter(self.proc.stderr.readline,b''):self.tail.append(line)
        finally:self.proc.stderr.close()
    def _read(self):
        length=CAMERA_SIZE[0]*CAMERA_SIZE[1]*4 if self.kind=='camera' else 1024*4
        try:
            while not self.stop.is_set():
                raw=self.proc.stdout.read(length)
                if len(raw)!=length:break
                stamp=time.monotonic()
                if self.kind=='camera':value=Image.frombytes('RGBA',CAMERA_SIZE,raw)
                else:value=np.frombuffer(raw,dtype='<f4').copy()
                self.latest=value;self.stamp=stamp;self.count+=1;self.state='live'
                if self.callback:self.callback(value,stamp)
            if not self.stop.is_set():
                self.logger.join(timeout=.2);self.state='error';self.error=b''.join(self.tail).decode('utf-8','replace')[-6000:] or 'Capture ended before Stop. Check permission, device, and format.'
        except Exception as exc:self.state='error';self.error=str(exc)
        finally:
            self.proc.stdout.close()
    def close(self):
        self.stop.set();stop_process(self.proc);self.reader.join(timeout=3);self.logger.join(timeout=2);self.state='stopped'


class LiveInputs:
    def __init__(self):
        self.camera=None;self.microphone=None;self._previous_rms=0.;self._signal=({},time.monotonic());self.recording=None;self.lock=threading.RLock();self.last_take=None
    def start_camera(self,device):
        if self.recording:raise ValueError('Finish recording before changing a device')
        self.stop_camera()
        if isinstance(device,dict) and device.get('kind') in ('screen','window'):
            from visual_capture import VisualCapture
            self.camera=VisualCapture(device)
        else:self.camera=Capture('camera',device)
    def start_microphone(self,device):
        if self.recording:raise ValueError('Finish recording before changing a device')
        self.stop_microphone();self._previous_rms=0.;self.microphone=Capture('microphone',device,self._audio)
    def camera_frame(self):return self.camera.latest.copy() if self.camera and self.camera.latest is not None and self.camera.state=='live' else None
    def signal(self):return self._signal
    def _audio(self,samples,stamp):
        data=analyze_samples(samples,AUDIO_RATE);ref=data.get('reference_rms',.02)
        values={k:min(1.,v[0]*ref/.18) if v else 0. for k,v in data['bands'].items()}
        rms=values.get('full',0.)
        values['onset']=min(1.,max(0.,rms-self._previous_rms)*4);self._previous_rms=rms
        self._signal=(values,stamp)
        with self.lock:
            r=self.recording
            if r and r.get('wav'):
                if r['audio_first'] is None:r['audio_first']=stamp-r['clock']
                r['wav'].writeframesraw((np.clip(samples,-1,1)*32767).astype('<i2').tobytes());r['audio_samples']+=len(samples)
                for band,value in values.items():r['bands'][band].append(round(float(value),6))
    def stop_camera(self):
        if self.recording:raise ValueError('Finish recording before stopping the camera')
        if self.camera:self.camera.close();self.camera=None
    def stop_microphone(self):
        if self.recording:raise ValueError('Finish recording before stopping the microphone')
        if self.microphone:self.microphone.close();self.microphone=None
        self._signal=({},time.monotonic())
    def start_recording(self,directory:Path,project_time:float):
        if self.recording:raise ValueError('A take is already recording')
        camera=bool(self.camera and self.camera.state=='live');mic=bool(self.microphone and self.microphone.state=='live')
        if not (camera or mic):raise ValueError('Start a camera or microphone and wait for a live signal first')
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        stem='take-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(time.time_ns()%1000000)
        size=tuple(self.camera.size) if camera else CAMERA_SIZE;fps=int(self.camera.fps) if camera else CAMERA_FPS
        r={'clock':time.monotonic(),'start':project_time,'directory':str(directory),'stem':stem,'video':'','audio':'','video_first':None,'audio_first':None,'audio_samples':0,'bands':{b:[] for b in ('full','bass','mid','high','onset')},'frames':0,'error':'','stop':threading.Event(),'wav':None,'encoder':None,'frame_size':size,'fps':fps}
        if mic:
            r['audio']=str(directory/(stem+'.wav'));r['wav']=wave.open(r['audio']+'.partial','wb');r['wav'].setnchannels(1);r['wav'].setsampwidth(2);r['wav'].setframerate(AUDIO_RATE)
        if camera:
            r['video']=str(directory/(stem+'.mkv'))
            cmd=[FFMPEG,'-hide_banner','-loglevel','warning','-y','-f','rawvideo','-pix_fmt','rgba','-s',f'{size[0]}x{size[1]}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','ultrafast','-crf','18','-pix_fmt','yuv420p','-threads','1','-f','matroska',r['video']+'.partial']
            r['encoder']=EncoderPipe(cmd,directory/(stem+'-encoder.log'))
        with self.lock:self.recording=r
        if camera:
            r['worker']=threading.Thread(target=self._record_video,args=(r,),daemon=True);r['worker'].start()
    def _record_video(self,r):
        try:
            while not r['stop'].is_set():
                frame=self.camera_frame()
                if frame is None:raise RuntimeError('Visual source stopped during the take; recorded material was preserved')
                if r['video_first'] is None:r['video_first']=time.monotonic()-r['clock']
                r['encoder'].write(frame.tobytes());r['frames']+=1
                r['stop'].wait(max(0.,r['clock']+r['frames']/r['fps']-time.monotonic()))
        except Exception as exc:r['error']=str(exc);r['stop'].set()
    def stop_recording(self):
        with self.lock:
            r=self.recording
            if r is None:raise ValueError('No take is recording')
            self.recording=None;r['stop'].set()
            if r['wav']:r['wav'].close()
        if r.get('worker'):r['worker'].join(timeout=10)
        if r['encoder']:
            try:r['encoder'].finish()
            except Exception as exc:r['error']=(r['error']+'\n'+str(exc)).strip()
        duration=max(r['frames']/r['fps'],r['audio_samples']/AUDIO_RATE)
        take={k:r[k] for k in ('start','video','audio','video_first','audio_first','audio_samples','frames','error')}
        take.update(duration=duration,sample_rate=AUDIO_RATE,fps=r['fps'],frame_size=list(r['frame_size']),recording_clock='monotonic; device latency not calibrated',camera_device=self.camera.device if self.camera else None,microphone_device=self.microphone.device if self.microphone else None)
        for key in ('video','audio'):
            path=r[key]
            if path and Path(path+'.partial').exists() and Path(path+'.partial').stat().st_size>0:Path(path+'.partial').replace(path)
        if take['audio'] and Path(take['audio']).exists():
            take['analysis']={'version':2,'source':'recorded-live-envelopes','sample_rate':AUDIO_RATE,'duration':r['audio_samples']/AUDIO_RATE,'hop_seconds':1024/AUDIO_RATE,'bands':r['bands'],'offset':take['start']+(take['audio_first'] or 0)}
        take['manifest']=str(Path(r['directory'])/(r['stem']+'.json'));Path(take['manifest']).write_text(json.dumps(take,indent=2))
        self.last_take=take;return take
    def stop_all(self):
        if self.recording:self.stop_recording()
        self.stop_camera();self.stop_microphone()
    def state(self):
        return {k:{'state':getattr(v,'state','stopped'),'error':getattr(v,'error',''),'device':getattr(v,'device','')} for k,v in (('camera',self.camera),('microphone',self.microphone))}
