"""One timestamped compositor for the live Programme monitor and final export."""
from __future__ import annotations
import math
from pathlib import Path
from bisect import bisect_right
from instrument_model import style_from, camera_placement_at
from sequencer_model import _effect_from, _parameter_from, ProgrammableParameter
from PIL import Image,ImageChops,ImageColor
from effects_engine import adjust,apply_effect,blend_images,crossfade,mask_image,multiply_alpha,transition_image
from frame_sources import FrameSources
from signal_engine import SignalEvaluator
from module_engine import compile_rack
from queue_model import mode_at,queue_position


class _SignalClock:
    """Evaluation adapter: authored time and audio acquisition time are separate."""
    def __init__(self,evaluator,offset):self.evaluator=evaluator;self.offset=offset
    def value(self,param,t):return self.evaluator.value(param,t,t+self.offset)


class ProgrammeRenderer:
    def __init__(self,*,live_camera=None,live_microphone=None,max_readers=6,missing_policy='error'):
        self.missing_policy=missing_policy;self.missing={}
        self.sources=FrameSources(max_readers=max_readers,live=live_camera)
        self.live_microphone=live_microphone;self.project=None;self.signals=None;self.memo={};self.style_history={};self.master_history=[];self.master_transitions=[];self.mix_history=[];self.plan={};self.rack_plan={}
    def close(self):self.sources.close()

    def render(self,project,t,size=None,*,transparent=False,bypass_effects=False):
        if self.project is not project:
            if self.signals is None:self.signals=SignalEvaluator(project,self.live_microphone)
            else:
                if self.signals.project.analysis is not project.analysis or self.signals.project.recorded_analysis is not project.recorded_analysis:self.signals.cache.clear()
                self.signals.project=project
            self.project=project
            self.style_history={i:[(e['start'],e['end'],style_from(e['style'],l)) for e in l.extra.get('treatment_history',[])] for i,l in enumerate(project.layers)}
            self.master_history=[(e['start'],e['end'],[_effect_from(f) for f in e['rack']]) for e in project.extra.get('master_history',[])]
            self.master_transitions=[(e['start'],e['end'],[_effect_from(f) for f in e['from']],[_effect_from(f) for f in e['to']],e.get('fade_end',e['end'])) for e in project.extra.get('master_transitions',[])]
            self.mix_history=[(e['start'],e['end'],_parameter_from(e['mix'],project.voice_mix),e['mode'],e['blend']) for e in project.extra.get('mixer_history',[])]
            self.plan={};self.rack_plan={}
            for i,l in enumerate(project.layers):
                clips=sorted(l.clips,key=lambda c:(c.start,c.channel,c.id))
                self.plan[i]=(clips,[c.start for c in clips],max((c.duration for c in clips),default=0.))
        self.size=tuple(size or (project.width,project.height));self.t=float(t);self.memo={};self.transparent=transparent;self.bypass=bypass_effects;self.work=0
        self.empty=Image.new('RGBA',self.size);self.layer_indices={l.id:i for i,l in enumerate(project.layers)}
        image=self._programme(float(t))
        from visual_channels import master_at
        level=master_at(project,'visual',float(t))
        if level<1.:
            black=Image.new('RGBA',self.size,(0,0,0,0 if transparent else 255))
            image=Image.blend(black,image,level)
        return image

    def _reference(self,mask,layer_index,t):
        if mask.kind not in {'alpha','luma'}:return None
        index=self.layer_indices.get(mask.layer_id)
        if index is None or index>=layer_index:raise ValueError('A mask may reference an earlier layer only; choose a valid mask source')
        return self._layer(index,t)

    def _rack(self,image,rack,t,history,limit=None,*,effect_time=None,signal_time=None):
        if self.bypass:return image
        if any(fx.kind=='module' for fx in rack):
            key=id(rack)
            if key not in self.rack_plan:self.rack_plan[key]=(rack,compile_rack(rack))
            rack=self.rack_plan[key][1]
        stop=len(rack) if limit is None else limit
        effect_time=t if effect_time is None else effect_time
        signal_time=t if signal_time is None else signal_time
        signals=self.signals if effect_time==signal_time else _SignalClock(self.signals,signal_time-effect_time)
        for i,fx in enumerate(rack[:stop]):
            image=apply_effect(image,fx,effect_time,signals,delayed=lambda delay,i=i:history(t-delay,i))
        return image

    def _clip(self,clip,layer_index,t,*,no_fade=False,limit=None,session_t=None):
        session_t=t if session_t is None else session_t
        key=('clip',clip.id,round(t,7),round(session_t,7),no_fade,limit)
        if key in self.memo:return self.memo[key]
        if t<clip.start-1e-7 or t>=clip.end-1e-7:return self.empty
        self.work+=1
        if self.work>256:raise ValueError('Temporal effect stack exceeds the per-frame work budget; reduce echo taps or stack depth')
        gap=clip.extra.get('queue_gap')
        if gap:
            mode=gap.get('mode','transparent')
            if mode=='colour':return Image.new('RGBA',self.size,ImageColor.getrgb(gap.get('colour','#000000'))+(255,))
            if mode=='hold':
                from queue_policies import visual_state_at
                state=visual_state_at(self.project.layers[layer_index],session_t)
                previous=max((c for c in state.clips if c.end<=clip.start+1e-7 and not c.extra.get('queue_gap')),key=lambda c:c.end,default=None)
                if previous is None and clip.extra.get('held_gap_clip'):
                    from sequencer_model import project_from_dict
                    previous=project_from_dict({'layers':[{'id':'held-gap','name':'Held gap','clips':[clip.extra['held_gap_clip']]}]}).layers[0].clips[0]
                if previous:return self._clip(previous,layer_index,previous.end-1/self.project.fps,session_t=session_t)
            return self.empty
        asset=self.project.asset(clip.asset_id)
        if self.missing_policy=='transparent' and (asset is None or (asset.kind in ('image','video','audio') and not Path(asset.path).is_file())):
            self.missing[clip.asset_id]=asset.name if asset else 'Missing source';self.memo[key]=self.empty;return self.empty
        self.missing.pop(clip.asset_id,None)
        if asset is None:raise ValueError('Clip references a missing asset')
        local=max(0.,clip.in_point+(t-clip.start)*clip.playback_rate)
        if asset.duration>0 and asset.kind=='video':
            window=clip.extra.get('source_window',[0.,asset.duration]);lo=max(0.,float(window[0]));hi=min(asset.duration,float(window[1]));span=max(1/self.project.fps,hi-lo)
            if clip.source_policy=='loop':local=lo+(max(0.,local-lo)%span)
            else:local=min(local,max(lo,hi-1/self.project.fps))
        history_step=round((self.t-session_t)*self.project.fps,3)
        image=self.sources.frame(asset,local,self.size,reader_key=f'{clip.id}:{history_step}',fit=clip.fit,fps=self.project.fps,project_size=(self.project.width,self.project.height))
        parameter_t=t-float(clip.extra.get('captured_queue_offset',0.))
        scale=self.signals.value(clip.scale,parameter_t,session_t);angle=math.radians(self.signals.value(clip.rotation,parameter_t,session_t))
        if abs(scale)<1e-8:return self.empty
        dx=self.signals.value(clip.x,parameter_t,session_t)*self.size[0]/2;dy=self.signals.value(clip.y,parameter_t,session_t)*self.size[1]/2
        if abs(scale-1)>1e-7 or abs(angle)>1e-7 or abs(dx)>1e-7 or abs(dy)>1e-7:
            w,h=self.size;cx=w/2;cy=h/2;ca=math.cos(angle)/scale;sa=math.sin(angle)/scale
            matrix=(ca,sa,cx-ca*(cx+dx)-sa*(cy+dy),-sa,ca,cy+sa*(cx+dx)-ca*(cy+dy))
            image=image.transform(self.size,Image.Transform.AFFINE,matrix,Image.Resampling.BICUBIC)
        if not self.bypass:
            for name,param in clip.effects.items():image=adjust(image,name,self.signals.value(param,parameter_t,session_t))
        if not clip.extra.get('rack_bypassed',False):
            image=self._rack(image,clip.rack,t,lambda past,upto:self._clip(clip,layer_index,past,no_fade=no_fade,limit=upto,session_t=session_t+(past-t)),limit,effect_time=parameter_t,signal_time=session_t)
        if limit is not None:self.memo[key]=image;return image
        image=mask_image(image,clip.mask,self._reference(clip.mask,layer_index,session_t))
        opacity=self.signals.value(clip.opacity,parameter_t,session_t)
        if not no_fade:
            if clip.fade_in>0:opacity*=min(1.,max(0.,(t-clip.extra.get('fade_start',clip.start))/clip.fade_in))
            if clip.fade_out>0:opacity*=min(1.,max(0.,(clip.extra.get('fade_end',clip.end)-t)/clip.fade_out))
        image=multiply_alpha(image,opacity);self.memo[key]=image;return image

    def _layer(self,index,t,limit=None):
        key=('layer',index,round(t,7),limit)
        if key in self.memo:return self.memo[key]
        source_layer=self.project.layers[index]
        l=next((style for a,b,style in reversed(self.style_history.get(index,[])) if a<=t<b),source_layer)
        if not l.enabled:return self.empty
        from queue_policies import visual_state_at
        source_layer=visual_state_at(source_layer,t)
        source=mode_at(source_layer,t);qtime=queue_position(source_layer,t);seam_context=None
        if source['mode']=='camera':
            asset=self.project.asset(source.get('camera_id',''))
            if asset is None:raise ValueError('Camera assignment is missing')
            image=self.sources.frame(asset,t,self.size,fit='cover',fps=self.project.fps,project_size=(self.project.width,self.project.height))
        else:
            if source_layer is self.project.layers[index]:clips,starts,maxdur=self.plan[index]
            else:
                clips=sorted(source_layer.clips,key=lambda c:(c.start,c.channel,c.id));starts=[c.start for c in clips];maxdur=max((c.duration for c in clips),default=0.)
            lo=bisect_right(starts,qtime-maxdur-1e-6);hi=bisect_right(starts,qtime+1e-7)
            active=[c for c in clips[lo:hi] if c.start-1e-7<=qtime<c.end-1e-7]
            if source['mode']=='hold':active=[c for c in active if c.id==source.get('clip_id')]
            if not active:return self.empty
            from queue_seams import active_seam
            seam=active_seam(sorted(source_layer.clips,key=lambda c:(c.start,c.id)),source_layer.extra.get('queue_seam'))
            if seam:seam_context=(seam,max(c.end for c in source_layer.clips),qtime)
            elif active[0].extra.get('captured_queue_seam'):
                captured=active[0].extra['captured_queue_seam'];seam_context=(captured['seam'],captured['length'],qtime-captured['origin'])
            by_id={c.id:c for c in active}
            transition=next((tr for tr in reversed(source_layer.transitions) if tr.start-1e-7<=qtime<tr.end and tr.from_clip in by_id and tr.to_clip in by_id),None)
            if transition is not None and (l.mixer_mode=='auto' or transition.extra.get('queue_authored')):
                a=self._clip(by_id[transition.from_clip],index,qtime,no_fade=True,session_t=t);b=self._clip(by_id[transition.to_clip],index,qtime,no_fade=True,session_t=t)
                image=transition_image(a,b,transition,qtime)
                for c in active:
                    if c.id not in (transition.from_clip,transition.to_clip):image=Image.alpha_composite(image,self._clip(c,index,qtime,session_t=t))
            else:
                channels={}
                for name in ('A','B'):
                    channel_clips=[c for c in active if c.channel==name]
                    if channel_clips:
                        channel=self.empty
                        for c in channel_clips:channel=Image.alpha_composite(channel,self._clip(c,index,qtime,session_t=t))
                        channels[name]=channel
                if 'B' not in channels:image=channels.get('A',self.empty)
                elif 'A' not in channels:image=channels['B']
                else:
                    a,b=channels['A'],channels['B'];mix=self.signals.value(l.mix,t)
                    if l.mixer_mode=='crossfade':image=crossfade(a,b,mix)
                    elif l.mixer_mode=='matte':
                        matte=ImageChops.multiply(b.convert('L'),b.getchannel('A'));image=a.copy();image.putalpha(ImageChops.multiply(a.getchannel('A'),matte))
                    else:image=blend_images(a,b,'normal',mix if l.mixer_mode=='over' else 1.)
        if not self.bypass:
            for name,param in l.effects.items():
                if name not in {'brightness','contrast','gamma','saturation','hue','sharpness','blur'}:raise ValueError(f'Unsupported adjustment: {name}')
                image=adjust(image,name,self.signals.value(param,t))
        if not l.extra.get('rack_bypassed',False):
            image=self._rack(image,l.rack,t,lambda past,upto:self._layer(index,past,upto),limit)
        if limit is not None:self.memo[key]=image;return image
        image=mask_image(image,l.mask,self._reference(l.mask,index,t));image=multiply_alpha(image,self.signals.value(l.opacity,t))
        if seam_context is not None:
            from queue_seams import seam_gain
            seam,length,position=seam_context;image=multiply_alpha(image,float(seam_gain(position,length,seam)))
        self.memo[key]=image;return image

    def _programme(self,t,limit=None):
        key=('programme',round(t,7),limit)
        if key in self.memo:return self.memo[key]
        image=self.empty if self.transparent else Image.new('RGBA',self.size,ImageColor.getrgb(self.project.background)+(255,))
        solo=any(l.solo and l.enabled for l in self.project.layers)
        voices={l.extra.get('voice'):i for i,l in enumerate(self.project.layers)}
        used=set()
        ic=voices.get('Camera')
        camera=self.empty;placement='above';camera_blend='normal'
        if ic is not None:
            camera_layer=self.project.layers[ic]
            camera_style=next((s for a,b,s in reversed(self.style_history.get(ic,[])) if a<=t<b),camera_layer)
            placement=camera_placement_at(camera_layer,t);camera_blend=camera_style.blend_mode
            if not solo or camera_style.solo:camera=self._layer(ic,t)
            used.add(ic)
            if placement=='below':image=blend_images(image,camera,camera_blend)
        if self.project.instrument_mode and t>=float(self.project.extra.get('channel_mix_since',float('inf'))):
            from visual_channels import ROLES,mix_images
            layers=[(i,l) for i,l in enumerate(self.project.layers) if l.extra.get('voice') in ROLES]
            frames=[];levels=[]
            for i,l in layers:
                used.add(i)
                style=next((s for a,b,s in reversed(self.style_history.get(i,[])) if a<=t<b),l)
                frame=self._layer(i,t) if not solo or style.solo else self.empty
                frames.append(frame);levels.append(self.signals.value(style.opacity,t) if style.enabled else 0.)
            # Later-generation instruments sometimes use the independent voice
            # compositor. Ping-pong must still travel fully between A and B.
            from timed_mix import pingpong_at
            automatic=pingpong_at(self.project,t)
            if automatic is not None:
                for index,(_,channel) in enumerate(layers):
                    if channel.extra.get('voice')=='A':levels[index]*=1.-automatic
                    elif channel.extra.get('voice')=='B':levels[index]*=automatic
            combined=mix_images(frames,levels,self.size)
            image=Image.alpha_composite(image,combined)
            if ic is not None and placement=='between':image=blend_images(image,camera,camera_blend)
        elif self.project.instrument_mode and 'A' in voices and 'B' in voices:
            ia,ib=voices['A'],voices['B'];used.update((ia,ib))
            la,lb=self.project.layers[ia],self.project.layers[ib]
            a=self._layer(ia,t) if not solo or la.solo else self.empty
            b=self._layer(ib,t) if not solo or lb.solo else self.empty
            param,mode,blend=self.project.voice_mix,self.project.voice_mixer_mode,self.project.voice_blend
            for t0,t1,hp,hm,hb in reversed(self.mix_history):
                if t0<=t<t1:param,mode,blend=hp,hm,hb;break
            mix=self.signals.value(param,t)
            if ic is not None and placement=='between':
                # The camera sits over A and under B. Crossfade to B also fades
                # this inserted composite; Blend mode overlays B by its amount.
                a=blend_images(a,camera,camera_blend)
            if b.getchannel('A').getbbox() is None:combined=a
            elif a.getchannel('A').getbbox() is None:combined=b
            elif mode=='crossfade':
                from ux16_transitions import composited_mix
                combined=composited_mix(self.project,a,b,mix,t,self.signals)
            else:combined=blend_images(a,b,blend,mix)
            image=Image.alpha_composite(image,combined)
        for i,l in enumerate(self.project.layers):
            if i in used or (solo and not l.solo):continue
            style=next((s for a,b,s in reversed(self.style_history.get(i,[])) if a<=t<b),l)
            image=blend_images(image,self._layer(i,t),style.blend_mode)
        if ic is not None and placement=='above':image=blend_images(image,camera,camera_blend)
        rack=next((r for a,b,r in reversed(self.master_history) if a<=t<b),self.project.master_rack)
        if not self.project.extra.get('rack_bypassed',False):
            transition=next((e for e in reversed(self.master_transitions) if e[0]<=t<e[1]),None)
            if transition:
                start,end,old,new,fade_end=transition;mix=max(0.,min(1.,(t-start)/(fade_end-start)))
                previous=self._rack(image,old,t,lambda past,upto:self._programme(past,upto),limit)
                upcoming=self._rack(image,new,t,lambda past,upto:self._programme(past,upto),limit)
                image=crossfade(previous,upcoming,mix)
            else:image=self._rack(image,rack,t,lambda past,upto:self._programme(past,upto),limit)
        self.memo[key]=image;return image
