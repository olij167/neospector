"""Neospector one-decision update workflow: check, consent, verify, install, restart.

The UI never touches application files or executes downloads.  The separate
installer re-verifies the pinned Ed25519 signature and archive checksum.
"""
from __future__ import annotations
import json, os, platform, shutil, subprocess, sys, threading, tkinter as tk
from pathlib import Path
from tkinter import ttk
from release_identity import VERSION
from signed_updates import UpdateError
from installer_updates import FEED, platform_id, fetch_release, download_installer, verify_installer

# Frozen PyInstaller builds have an immutable /opt/neospector application folder.
# Their stand-alone updater helpers are deliberately shipped outside _internal.
ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]


def updater_command(root=ROOT):
    """Find the detached *native installer* helper, never the source ZIP updater."""
    base=Path(root)
    key=base/'updates/public.pem'
    if getattr(sys,'frozen',False):
        binary=base/('NeospectorUpdater.exe' if sys.platform=='win32' else 'NeospectorUpdater')
        # macOS .app: the updater is a signed Contents/MacOS executable.
        if sys.platform=='darwin':
            binary=Path(sys.executable).resolve().parent/'NeospectorUpdater'
        if not binary.is_file() or not key.is_file():raise UpdateError('Native updater is not installed.')
        return [str(binary)],key
    helper=Path(__file__).with_name('native_installer_helper.py')
    if not helper.is_file() or not key.is_file():raise UpdateError('Native updater or publisher key missing.')
    return [sys.executable,str(helper)],key


def can_update():
    return platform_id() is not None


class UpdateController:
    def __init__(self, app):
        self.app = app
        self.running = False
        self.available = None
        self.downloaded = None
        self.window = None
        self.status = 'Not checked'
        self.status_var = tk.StringVar(master=app, value=self.status)
        self.consent = False

    def _dispatch(self, fn, *args):
        try:
            self.app.after(0, lambda: fn(*args))
        except (RuntimeError, tk.TclError):
            pass

    def _set(self, message):
        self.status = message
        try:
            self.status_var.set(message)
            if self.window is not None and self.window.winfo_exists():
                self._refresh()
        except tk.TclError:
            pass

    def feed(self):
        return str(getattr(self.app, 'native_update_feed_url', FEED))

    def check(self, silent=False):
        if not can_update():
            # This cannot offer a broken installer on unsupported native builds.
            self._set('No native installer is available for this platform.')
            if not silent:
                self.show()
            return False
        try:
            _, public_key = updater_command()
        except UpdateError as exc:
            self._set(str(exc))
            if not silent:
                self.show()
            return False
        if self.running:
            return False
        self.running = True
        if not silent:
            self.show()
        self._set('Checking for updates…')
        def work():
            try:
                found = fetch_release(self.feed(), public_key, VERSION)
                self._dispatch(self._on_result, found)
            except Exception as exc:
                self._dispatch(self._on_check_error, str(exc))
        threading.Thread(target=work, name='Neospector release check', daemon=True).start()
        return True

    def _on_result(self, found):
        self.running = False
        self.available = found
        self.downloaded = None
        self.consent = False
        if found:
            self._set('New version available: ' + found[0]['version'])
            self.show()
        else:
            self._set('Neospector is up to date (' + VERSION + ')')

    def _on_check_error(self, error):
        self.running = False
        # Offline startup is always silent. A manually opened panel shows status.
        self._set('Unable to check for updates: ' + error[:200])

    def show(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            self._refresh()
            return self.window
        win = self.window = tk.Toplevel(self.app)
        win.title('Neospector · Updates')
        win.transient(self.app)
        win.geometry('475x280')
        win.minsize(400, 235)
        win.protocol('WM_DELETE_WINDOW', self.decline)
        shell = ttk.Frame(win, padding=18)
        shell.pack(fill='both', expand=True)
        ttk.Label(shell, text='NEOSPECTOR UPDATE', style='Title.TLabel').pack(anchor='w')
        ttk.Label(shell, text='Installed: ' + VERSION, style='Muted.TLabel').pack(anchor='w', pady=(5, 12))
        ttk.Label(shell, textvariable=self.status_var, wraplength=430).pack(anchor='w', fill='x', pady=(0, 9))
        self.notes = tk.Text(shell, height=4, wrap='word', relief='flat', state='disabled')
        self.notes.pack(fill='both', expand=True)
        footer = ttk.Frame(shell)
        footer.pack(fill='x', pady=(12, 0))
        self.decline_button = ttk.Button(footer, text='Not now', command=self.decline)
        self.decline_button.pack(side='left')
        self.update_button = ttk.Button(footer, text='Update now', command=self.accept)
        self.update_button.pack(side='right')
        self.check_button = ttk.Button(footer, text='Check now', command=lambda: self.check(silent=False))
        self.check_button.pack(side='right', padx=(0, 8))
        self._refresh()
        return win

    def _refresh(self):
        if self.window is None or not self.window.winfo_exists():
            return
        text = (self.available[0]['notes'] if self.available else
                'Updates are checked without interrupting playback. Your saved media, projects and settings are preserved.')
        self.notes.configure(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', text)
        self.notes.configure(state='disabled')
        self.update_button.configure(state='normal' if self.available and not self.running and not self.consent else 'disabled')
        # Available release has exactly two decisions: Update now / Not now.
        if self.available:
            self.check_button.pack_forget()
        elif not self.check_button.winfo_manager():
            self.check_button.pack(side='right',padx=(0,8))
        self.check_button.configure(state='disabled' if self.running else 'normal')
        self.decline_button.configure(state='disabled' if self.consent else 'normal')

    def decline(self):
        # Decline changes no playback state, project file, or preference.
        if self.consent:
            return False
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
        return True

    def _update_blocker(self):
        app = self.app
        if getattr(app, 'closing', False):
            return 'Neospector is already closing.'
        if getattr(app, 'dirty', False):
            return 'Save or discard your project changes first, then choose Update now.'
        if (getattr(app, 'rendering', False) or getattr(app, 'output_recording', None)
                or getattr(app, 'output_busy', False) or getattr(app, 'capture_busy', False)):
            return 'Finish recording, capture or export before updating.'
        return None

    def accept(self):
        """One affirmative action; subsequent steps have no secondary consent."""
        if not self.available or self.running or self.consent:
            return False
        blocker = self._update_blocker()
        if blocker:
            self._set(blocker)
            return False
        try:
            updater_command()
        except UpdateError as exc:
            self._set(str(exc))
            return False
        self.consent = True
        self.running = True
        record, envelope = self.available
        self._set('Downloading and verifying ' + record['version'] + '…')
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'omne-sequencer/updates'
        def work():
            try:
                cache.mkdir(parents=True, exist_ok=True)
                alias=platform_id()
                installer_record=record['installers'][alias]
                archive = download_installer(self.feed(), installer_record, cache/installer_record['file'])
                signed_manifest = cache / ('signed-' + record['version'] + '.json')
                temp_manifest = signed_manifest.with_suffix('.tmp')
                temp_manifest.write_text(json.dumps(envelope, sort_keys=True) + '\n', encoding='utf-8')
                os.replace(temp_manifest, signed_manifest)
                self._dispatch(self._downloaded, archive, signed_manifest)
            except Exception as exc:
                self._dispatch(self._on_error, str(exc))
        threading.Thread(target=work, name='Neospector verified download', daemon=True).start()
        return True

    def _on_error(self, error):
        self.running = False
        self.consent = False
        self._set('Update unavailable: ' + error[:200] + ' — current version unchanged.')

    def _downloaded(self, archive, manifest):
        self.running = False
        self.downloaded = (archive, manifest)
        try:
            self._install_verified()
        except Exception as exc:
            self._on_error(str(exc))

    def _install_verified(self):
        if not self.consent or not self.available or not self.downloaded:
            return False
        blocker = self._update_blocker()
        if blocker:
            self._on_error(blocker)
            return False
        archive, manifest = self.downloaded
        record = self.available[0]
        verify_installer(archive, record['installers'][platform_id()])
        command, _ = updater_command()
        log = archive.parent / 'install.log'
        # Use the actual platform launcher after native installation.
        if sys.platform=='linux':restart=Path('/usr/bin/neospector')
        elif sys.platform=='win32':restart=Path(sys.executable if getattr(sys,'frozen',False) else os.environ.get('NEOSPECTOR_INSTALLED_EXE',''))
        else:restart=Path('/Applications/Neospector.app')
        if not str(restart) or str(restart)=='.':raise UpdateError('Native installation path unknown')
        command += ['--installer',str(archive),'--manifest',str(manifest),
                    '--key',str(updater_command()[1]),'--wait-pid',str(os.getpid()),
                    '--restart',str(restart),'--expected-version',record['version']]
        # Existing save/close path is authoritative; no forced termination.
        app = self.app
        app.close()
        if not getattr(app, 'closing', False):
            self._on_error('Application close was cancelled. No update installed.')
            return False
        with log.open('ab') as out:
            subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.DEVNULL,
                             stdout=out, stderr=subprocess.STDOUT, close_fds=True,
                             start_new_session=True)
        return True
