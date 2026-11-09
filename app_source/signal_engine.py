"""Deterministic sampled audio envelopes shared by preview and export.

Analysis uses actual FFT bands. Detected onsets are not advertised as verified
beats; the independently editable BPM grid remains a user-authored timing tool.
"""
from __future__ import annotations
import math
import subprocess
import time
from collections import OrderedDict
import numpy as np
from sequencer_model import ProgrammableParameter, Project

BANDS=('full','bass','mid','high','onset')


def analyze_samples(samples,rate:int=24000,hop_seconds:float=.02) -> dict:
    samples=np.asarray(samples,dtype=np.float32).reshape(-1)
    hop=max(1,round(rate*hop_seconds));n=1024
    if len(samples)==0:return {'version':2,'duration':0,'hop_seconds':hop/rate,'bands':{b:[] for b in BANDS},'waveform':[],'onsets':[]}
    duration=len(samples)/rate
    hann=np.hanning(n).astype(np.float32);den=float(n*np.sum(hann*hann))
    freq=np.fft.rfftfreq(n,1/rate)
    masks={'bass':(freq>=20)&(freq<250),'mid':(freq>=250)&(freq<4000),'high':(freq>=4000)&(freq<min(12000,rate/2))}
    result={b:[] for b in BANDS};previous=0.;onsets=[]
    for i in range(0,len(samples),hop):
        block=samples[i:i+n]
        if len(block)<n:block=np.pad(block,(0,n-len(block)))
        spectrum=np.abs(np.fft.rfft(block*hann))**2
        spectrum[1:-1]*=2
        full=float(np.sqrt(np.sum(spectrum)/den));result['full'].append(full)
        for name,mask in masks.items():result[name].append(float(np.sqrt(np.sum(spectrum[mask])/den)))
        flux=max(0.,full-previous);result['onset'].append(flux);previous=full
    reference=max(.02,float(np.percentile(result['full'],98)))
    for key in BANDS:
        ref=reference*.25 if key=='onset' else reference
        result[key]=np.clip(np.asarray(result[key])/ref,0,1).round(6).tolist()
    onset=result['onset'];last=-1.
    for i in range(1,len(onset)-1):
        t=i*hop/rate
        if onset[i]>.35 and onset[i]>=onset[i-1] and onset[i]>onset[i+1] and t-last>.25:onsets.append(round(t,5));last=t
    chunks=max(1,math.ceil(len(samples)/1200));wave=[]
    for i in range(0,len(samples),chunks):wave.append(float(min(1.,np.max(np.abs(samples[i:i+chunks])))))
    return {'version':2,'sample_rate':rate,'hop_seconds':hop/rate,'duration':duration,'bands':result,'waveform':wave,'onsets':onsets,'reference_rms':reference}


def analyze_file(path,*,ffmpeg='ffmpeg',cancel=None) -> dict:
    from process_tools import run_process
    cmd=[str(ffmpeg),'-hide_banner','-loglevel','error','-i',str(path),'-vn','-ac','1','-ar','24000','-f','f32le','pipe:1']
    cp=run_process(cmd,cancel=cancel,timeout=600)
    return analyze_samples(np.frombuffer(cp.stdout,dtype='<f4'),24000)


def smooth_envelope(values,step:float,attack:float,release:float):
    values=np.asarray(values,dtype=np.float32);out=np.empty_like(values);previous=0.
    up=math.exp(-step/attack) if attack>0 else 0.;down=math.exp(-step/release) if release>0 else 0.
    for i,v in enumerate(values):
        coefficient=up if v>previous else down;previous=coefficient*previous+(1-coefficient)*float(v);out[i]=previous
    return out


class SignalEvaluator:
    def __init__(self,project:Project,live_provider=None):
        self.project=project;self.live_provider=live_provider;self.cache=OrderedDict();self.live_state={}

    def _analysis(self,source:str):
        if source=='recorded_mix':return self.project.extra.get('recorded_mix_analysis',{})
        if source=='recorded':return self.project.recorded_analysis
        data=self.project.analysis
        if not data and self.project.waveform:
            data={'hop_seconds':self.project.max_end()/max(1,len(self.project.waveform)-1),'duration':self.project.max_end(),'bands':{'full':self.project.waveform}}
        return data

    def envelope(self,param:ProgrammableParameter,t:float,source='song') -> float:
        data=self._analysis(source)
        if source=='song':
            for event in reversed(self.project.extra.get('analysis_history',[])):
                if event['start']<=t<event['end']:data=event['data'];break
        if source=='recorded' and param.extra.get('recorded_take_id'):data=self.project.extra.get('recorded_analyses',{}).get(param.extra['recorded_take_id'],data)
        if not data:return 0.
        repeat=data.get('repeat_window') if source=='song' else None
        if repeat and t>=repeat['start'] and repeat['duration']>0:
            t=repeat['start']+(t-repeat['start'])%repeat['duration']
        local=t-float(data.get('offset',0.))
        if local<0 or local>float(data.get('duration',self.project.duration)):return 0.
        bands=data.get('bands',{});values=bands.get(param.react_band)
        # Legacy full-wave analysis is labelled and only drives Full; bass/high are
        # not silently claimed to be measured when no spectral data exists.
        if values is None:return 0.
        step=float(data.get('hop_seconds',.02));key=(id(data),source,param.source,param.react_band,param.attack,param.release)
        if key not in self.cache:
            if param.source=='reaction_mix' and source=='song' and 'reference_rms' in data:
                values=np.clip(np.asarray(values,dtype=np.float32)*float(data['reference_rms'])/.18,0,1)
            self.cache[key]=smooth_envelope(values,step,param.attack,param.release)
            while len(self.cache)>64:self.cache.popitem(last=False)
        curve=self.cache[key]
        if len(curve)==0:return 0.
        x=min(len(curve)-1,max(0.,local/step));i=int(x);f=x-i
        return float(curve[i]*(1-f)+curve[min(i+1,len(curve)-1)]*f)

    def microphone(self,param):
        if self.live_provider is None:return 0.
        values,stamp=self.live_provider()
        if param.source=='reaction_mix':values=values.get('_reaction_mix',values)
        v=float(values.get(param.react_band,0.));key=(param.source,param.react_band,param.attack,param.release)
        previous,last=self.live_state.get(key,(0.,stamp-.02));dt=max(0.,min(.5,stamp-last))
        tau=param.attack if v>previous else param.release;coef=math.exp(-dt/tau) if tau>0 else 0.
        out=previous*coef+v*(1-coef);self.live_state[key]=(out,stamp);return out

    def value(self,param:ProgrammableParameter,t:float,signal_time=None) -> float:
        # One deterministic mix clock for live playback and offline export.
        # Identity check avoids touching any other parameter or audio reaction.
        if param is self.project.voice_mix:
            from timed_mix import pingpong_at
            automatic=pingpong_at(self.project,t)
            if automatic is not None:return automatic
        from module_engine import MacroParameter
        if isinstance(param,MacroParameter):return param.render_value(self,t,signal_time)
        if param.mode!='react':return param.evaluate(t)
        signal_time=t if signal_time is None else signal_time
        source=param.source
        if source=='reaction_mix':
            live_values,_=self.live_provider() if self.live_provider else ({},0.)
            v=self.microphone(param) if live_values.get('_has_mix',live_values.get('_has_external')) else self.envelope(param,signal_time)
        elif source=='recorded_mix':v=self.envelope(param,signal_time,'recorded_mix')
        elif source in ('microphone','device'):v=self.microphone(param)
        elif source=='song_recorded':v=min(1.,self.envelope(param,signal_time)+self.envelope(param,signal_time,'recorded'))
        elif source=='mix':v=min(1.,self.envelope(param,signal_time)+self.microphone(param))
        else:v=self.envelope(param,signal_time,'recorded' if source=='recorded' else 'song')
        return param.evaluate(t,v)
