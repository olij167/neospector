"""Modeless in-app update controller. Network and hashing never block Tk."""
from __future__ import annotations
import json,os,platform,subprocess,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,messagebox
from release_identity import VERSION
from signed_updates import DEFAULT_FEED,UpdateError,fetch_release,download_release,verify_archive

ROOT=Path(__file__).resolve().parents[1]

class UpdateController:
    def __init__(self,app):
        self.app=app;self.running=False;self.available=None;self.downloaded=None;self.window=None
        self.status='Not checked';self.status_var=tk.StringVar(master=app,value=self.status)

    def _set(self,message):
        self.status=message
        try:self.status_var.set(message)
        except tk.TclError:pass
        if self.window is not None:
            try:
                if self.window.winfo_exists():self._refresh()
            except tk.TclError:pass

    def _dispatch(self,callback,*args):
        try:self.app.after(0,lambda:callback(*args))
        except (RuntimeError,tk.TclError):pass

    def feed(self):return str(getattr(self.app,'update_feed_url',DEFAULT_FEED))

    def check(self,silent=False):
        if not sys.platform.startswith('linux') or platform.machine()!='x86_64':
            self._set('In-app updates are currently supported on Linux x86-64 only.')
            if not silent:self.show()
            return False
        if self.running:return False
        self.running=True
        if not silent:self.show()
        self._set('Checking signed release feed…')
        def work():
            try:
                result=fetch_release(self.feed(),ROOT/'updates/public.pem',VERSION)
                self._dispatch(self._on_result,result,silent)
            except Exception as e:self._dispatch(self._on_error,str(e),silent)
        threading.Thread(target=work,name='Neospector release check',daemon=True).start()
        return True

    def _on_result(self,result,silent):
        self.running=False
        self.available=result
        if result:
            record,_=result
            self._set('Verified update available: '+record['version'])
            self.show()
        else:self._set('Neospector is up to date ('+VERSION+')')

    def _on_error(self,error,silent):
        self.running=False
        # Offline / unprovisioned feeds should not interrupt performance or startup.
        self._set('Update check unavailable: '+error[:220])
        if not silent and self.window and self.window.winfo_exists():self._refresh()

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify();self.window.lift();self._refresh();return self.window
        win=self.window=tk.Toplevel(self.app)
        win.title('Neospector · Updates');win.transient(self.app);win.geometry('520x335');win.minsize(440,290)
        shell=ttk.Frame(win,padding=15);shell.pack(fill='both',expand=True)
        ttk.Label(shell,text='SOFTWARE UPDATES',style='Title.TLabel').pack(anchor='w')
        ttk.Label(shell,text='Installed version  '+VERSION,style='Muted.TLabel').pack(anchor='w',pady=(4,12))
        ttk.Label(shell,textvariable=self.status_var,wraplength=480).pack(anchor='w',fill='x',pady=(0,10))
        self.notes=tk.Text(shell,height=7,wrap='word',relief='flat',state='disabled')
        self.notes.pack(fill='both',expand=True)
        footer=ttk.Frame(shell);footer.pack(fill='x',pady=(12,0))
        ttk.Button(footer,text='Close',command=win.destroy).pack(side='left')
        self.check_button=ttk.Button(footer,text='Check now',command=lambda:self.check(silent=False))
        self.check_button.pack(side='left',padx=8)
        self.download_button=ttk.Button(footer,text='Download verified update',command=self.download)
        self.download_button.pack(side='right')
        self.install_button=ttk.Button(footer,text='Install & restart',command=self.install)
        self.install_button.pack(side='right',padx=(0,8))
        self._refresh();return win

    def _refresh(self):
        if not self.window or not self.window.winfo_exists():return
        version=self.available[0]['version'] if self.available else ''
        text=(f'NEOSPECTOR {version}\n\n'+self.available[0]['notes']) if self.available else (
            'Neospector checks for signed updates over HTTPS. Offline checks are silent at startup.\n\n'
            'Your programme, media and prior installation are preserved. Updates are applied only on request.')
        self.notes.configure(state='normal');self.notes.delete('1.0','end');self.notes.insert('1.0',text);self.notes.configure(state='disabled')
        self.check_button.configure(state='disabled' if self.running else 'normal')
        self.download_button.configure(state='normal' if self.available and not self.running and not self.downloaded else 'disabled')
        self.install_button.configure(state='normal' if self.downloaded and not self.running else 'disabled')

    def download(self):
        if not self.available or self.running:return False
        record,envelope=self.available;self.running=True;self._set('Downloading verified Neospector '+record['version']+'…')
        cache=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'omne-sequencer/updates'
        def work():
            try:
                cache.mkdir(parents=True,exist_ok=True)
                archive=download_release(self.feed(),record,cache/record['archive'])
                manifest=cache/('signed-'+record['version']+'.json')
                manifest.write_text(json.dumps(envelope,indent=2)+'\n')
                self._dispatch(self._downloaded,archive,manifest)
            except Exception as e:self._dispatch(self._on_error,str(e),False)
        threading.Thread(target=work,name='Neospector update download',daemon=True).start()
        return True

    def _downloaded(self,archive,manifest):
        self.running=False;self.downloaded=(archive,manifest)
        self._set('Verified download ready — installation will restart Neospector.')

    def install(self):
        if not self.downloaded or self.running:return False
        app=self.app;archive,manifest=self.downloaded
        # Verify before initiating the close path; the independent installer repeats it.
        try:verify_archive(archive,self.available[0])
        except UpdateError as e:messagebox.showerror('Neospector update',str(e),parent=self.window);return False
        if not messagebox.askyesno('Install Neospector update',
            'Close Neospector and install the signed update?\n\nSave any current project changes first. '
            'The previous application directory and media will remain intact.',parent=self.window):return False
        if getattr(app,'dirty',False):
            messagebox.showinfo('Save your project first','Save or discard project changes using File before installing.',parent=self.window)
            return False
        if getattr(app,'output_recording',None) or getattr(app,'output_busy',False) or getattr(app,'capture_busy',False):
            messagebox.showinfo('Finish capture first','Stop recording or export before installing an update.',parent=self.window)
            return False
        log=archive.parent/'install.log'
        try:app.close()
        except Exception as e:
            messagebox.showerror('Cannot close Neospector',str(e),parent=self.window);return False
        if not getattr(app,'closing',False):return False
        # A new process waits for the original PID to exit before touching files.
        # It inherits NO private shell state and requires no sudo.
        with log.open('ab') as output:
            subprocess.Popen([sys.executable,str(ROOT/'tools/update_installer.py'),
                '--archive',str(archive),'--manifest',str(manifest),'--wait-pid',str(os.getpid())],
                cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT,
                start_new_session=True,close_fds=True)
        return True
