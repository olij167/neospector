#!/usr/bin/env python3
"""Real native XDND assertions from an independent X11 connection.
Run under Xvfb. This is not a file-manager/owner acceptance test.
Dependency: tkinterdnd2==0.4.4.1, python-xlib, Pillow, NumPy, ffmpeg/ffprobe.
"""
from pathlib import Path
import argparse, json, os, subprocess, sys, tempfile, time

def target(mode, root_path, state_path):
    import tkinter as tk
    from tkinterdnd2 import TkinterDnD, DND_FILES
    if mode == 'minimal':
        sys.path.insert(0,str(Path(root_path)/'app_source'))
        from native_drop import require_native_drop
        app = tk.Tk();require_native_drop(app);app.geometry('420x260+60+60')
        widget = tk.Label(app, text='Native diagnostic drop target'); widget.pack(fill='both',expand=True)
        widget.drop_target_register(DND_FILES)
        received=[]
        def receive(event):
            received.extend(app.tk.splitlist(event.data)); return 'copy'
        widget.dnd_bind('<<Drop>>',receive)
    else:
        sys.path.insert(0,str(Path(root_path)/'app_source'))
        from neospector_console import NeospectorApp
        app=NeospectorApp(test_mode=True);app.geometry('1080x740+20+20')
        if not app.panel_states.get('Library',False):app.toggle_panel('Library')
        if mode=='browser':
            app.add_media(); widget=app.import_window.browser.canvas
        else:widget=app.library.canvas
    def dump():
        try:
            top=widget.winfo_toplevel()
            record={'wrapper':int(top.tk.call('wm','frame',str(top)),16),
                    'widget':widget.winfo_id(),'x':widget.winfo_rootx()+20,'y':widget.winfo_rooty()+35,
                    'tk':app.tk.call('package','provide','Tk'), 'tkdnd':app.tk.call('package','provide','tkdnd'),
                    'native_binary':str(app.tk.call('info','loaded')),
                    'mode':mode, 'native_dnd_available':True if mode=='minimal' else app.dnd_available}
            if mode=='minimal':record['received']=received
            else:
                record['assets']=[{'name':a.name,'path':a.path,'kind':a.kind,'has_audio':a.metadata.get('has_audio')} for a in app.project.assets.values()]
                record['importing']=app.importing
                record['staged']=[] if mode!='browser' else [r.path for r in app.import_window.model.items.values()]
                record['status']=app.status.get()
            p=Path(state_path);temp=p.with_suffix('.tmp');temp.write_text(json.dumps(record));temp.replace(p)
            app.after(100,dump)
        except Exception as e:
            print('DIAGNOSTIC_STATE_ERROR',repr(e),flush=True)
    app.after(800,dump)
    app.after(14000,app.destroy if mode=='minimal' else lambda:app.close(force=True))
    app.mainloop()

def run(mode, case, root_path, fixtures, out):
    from Xlib import X, Xatom, display, protocol
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    path=out/(mode+'-'+case+'.json');state=out/(mode+'-'+case+'-state.json')
    transcript=out/(mode+'-'+case+'.log')
    # Previous run state must not supply stale X window IDs.
    state.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix='neospector-drop-probe-') as sandbox, transcript.open('w') as log:
        env={**os.environ,'OMNE_SEQUENCER_SANDBOX':sandbox,'SDL_AUDIODRIVER':'dummy','PYTHONUNBUFFERED':'1'}
        p=subprocess.Popen([sys.executable,__file__,'--target',mode,'--root',root_path,'--state',str(state)],env=env,stdout=log,stderr=subprocess.STDOUT)
        result={'mode':mode,'case':case,'scope':'real native XDND, synthetic external sender under Xvfb; app test_mode=True; not owner desktop acceptance','events':[]}
        try:
            deadline=time.monotonic()+10
            while not state.exists() and p.poll() is None and time.monotonic()<deadline:time.sleep(.03)
            if not state.exists():raise RuntimeError('target not ready')
            before=json.loads(state.read_text());result['before']=before
            d=display.Display();screen=d.screen();src=screen.root.create_window(1120,5,100,100,0,screen.root_depth,X.InputOutput,X.CopyFromParent,event_mask=X.PropertyChangeMask)
            src.map();selection=d.intern_atom('XdndSelection');uri=d.intern_atom('text/uri-list');copy=d.intern_atom('XdndActionCopy')
            src.change_property(d.intern_atom('XdndTypeList'),Xatom.ATOM,32,[uri,d.intern_atom('text/plain'),d.intern_atom('UTF8_STRING'),d.intern_atom('STRING')])
            src.change_property(d.intern_atom('XdndActionList'),Xatom.ATOM,32,[copy])
            src.set_selection_owner(selection,X.CurrentTime);d.sync();source_id=src.id
            target_window=d.create_resource_object('window',before['wrapper'])
            def send(name,data):
                target_window.send_event(protocol.event.ClientMessage(window=target_window.id,client_type=d.intern_atom(name),data=(32,data)),event_mask=0);d.flush()
            if case in ('vanished-source','vanished-then-normal'):src.destroy();d.sync()
            send('XdndEnter',[source_id,(5<<24)|1,0,0,0]);time.sleep(.05)
            if case=='vanished-then-normal':
                time.sleep(.2)
                result['alive_after_invalid']=p.poll() is None
                if not result['alive_after_invalid']:raise RuntimeError('Invalid drag killed the target before the next drop')
                src=screen.root.create_window(1120,5,100,100,0,screen.root_depth,X.InputOutput,X.CopyFromParent,event_mask=X.PropertyChangeMask)
                src.map();source_id=src.id
                src.change_property(d.intern_atom('XdndTypeList'),Xatom.ATOM,32,[uri,d.intern_atom('text/plain'),d.intern_atom('UTF8_STRING'),d.intern_atom('STRING')])
                src.change_property(d.intern_atom('XdndActionList'),Xatom.ATOM,32,[copy])
                src.set_selection_owner(selection,X.CurrentTime);d.sync()
                send('XdndEnter',[source_id,(5<<24)|1,0,0,0]);time.sleep(.05)
            if case in ('normal','vanished-then-normal'):
                send('XdndPosition',[source_id,0,((before['x']&0xffff)<<16)|(before['y']&0xffff),X.CurrentTime,copy])
                sent_drop=False;finished=False;deadline=time.monotonic()+5
                while time.monotonic()<deadline and p.poll() is None and not finished:
                    if not d.pending_events():time.sleep(.01);continue
                    e=d.next_event()
                    if e.type==X.ClientMessage:
                        name=d.get_atom_name(e.client_type);data=list(e.data[1]);result['events'].append({'name':name,'data':data})
                        if name=='XdndStatus' and (data[1]&1) and not sent_drop:
                            send('XdndDrop',[source_id,0,X.CurrentTime,0,0]);sent_drop=True
                        if name=='XdndFinished':finished=True
                    elif e.type==X.SelectionRequest:
                        prop=e.property or e.target;req=d.create_resource_object('window',e.requestor.id if hasattr(e.requestor,'id') else e.requestor)
                        payload=('\r\n'.join(Path(f).resolve().as_uri() for f in fixtures)+'\r\n').encode('utf-8')
                        req.change_property(prop,e.target,8,payload)
                        req.send_event(protocol.event.SelectionNotify(time=e.time,requestor=req.id,selection=e.selection,target=e.target,property=prop),event_mask=0);d.flush()
                        result['events'].append({'name':'SelectionRequest','target':d.get_atom_name(e.target),'files':len(fixtures)})
                result['finished']=finished
            time.sleep(1.5)
            if state.exists():result['after']=json.loads(state.read_text())
            result['alive_after_protocol']=p.poll() is None
            # A normal WM_DELETE_WINDOW is not used: this is an isolated diagnostic
            # with unsaved generated media. Target has a bounded force-close timer.
            try:p.wait(timeout=14)
            except subprocess.TimeoutExpired:p.kill();p.wait();result['watchdog_killed']=True
            result['exit_code']=p.returncode;d.close()
        except Exception as e:
            result['probe_error']=repr(e)
            if p.poll() is None:p.kill();p.wait()
            result['exit_code']=p.returncode
        finally:
            path.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    print(transcript.read_text())
    if case=='vanished-then-normal':
        after=result.get('after',{})
        media=after.get('received',[]) if mode=='minimal' else after.get('staged',[]) if mode=='browser' else after.get('assets',[])
        assert result.get('alive_after_invalid') and result.get('finished') and result.get('exit_code')==0, result
        assert len(media)==4, result
        if mode=='library':
            assert {x['kind'] for x in media}=={'image','audio'},result
        if mode!='minimal':
            assert 'native/linux-x64/libtkdnd2.9.5.so' in after.get('native_binary',''),result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--target');parser.add_argument('--mode',default='minimal');parser.add_argument('--case',default='normal');parser.add_argument('--root',required=True);parser.add_argument('--state');parser.add_argument('--fixtures');parser.add_argument('--out');a=parser.parse_args()
    if a.target:target(a.target,a.root,a.state)
    else:run(a.mode,a.case,a.root,json.loads(Path(a.fixtures).read_text()),a.out)
