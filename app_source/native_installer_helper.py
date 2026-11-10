"""Detached native installer helper, packaged as NeospectorUpdater on each OS.

Runs only after user consent. Revalidates signed feed and exact installer bytes,
waits for the UI to quit, launches native OS installer and relaunches the app.
Never evaluates an untrusted shell command or arbitrary manifest path.
"""
from __future__ import annotations
import argparse, json, os, platform, subprocess, sys, time
from pathlib import Path
from installer_updates import platform_id,verify_release,verify_installer
from signed_updates import UpdateError


def run(cmd,timeout=300):
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
    if proc.returncode:raise UpdateError('Native installer verification or execution failed: '+(proc.stderr or proc.stdout)[-500:])
    return proc.stdout


def verify_platform_signature(installer,alias):
    if alias=='windows-x64':
        script=("$s=Get-AuthenticodeSignature -LiteralPath $args[0];"
                "if ($s.Status -ne 'Valid' -or -not $s.SignerCertificate) { exit 2 }")
        # PowerShell -File positional arguments avoid interpolation of filenames.
        with __import__('tempfile').TemporaryDirectory() as d:
            script_file=Path(d)/'check.ps1';script_file.write_text('param([string]$Path)\n$s=Get-AuthenticodeSignature -LiteralPath $Path\nif ($s.Status -ne "Valid" -or -not $s.SignerCertificate) { exit 2 }\n')
            run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script_file),str(installer)],timeout=30)
    if alias.startswith('macos-'):
        out=run(['pkgutil','--check-signature',str(installer)],timeout=30)
        if 'Developer ID Installer:' not in out:raise UpdateError('Missing Developer ID Installer signature')
        run(['spctl','--assess','--type','install','--verbose=4',str(installer)],timeout=30)
    if alias=='linux-x64':
        run(['dpkg-deb','--field',str(installer),'Package'],timeout=30)
        if run(['dpkg-deb','--field',str(installer),'Package']).strip()!='neospector':raise UpdateError('Incorrect Debian package identity')


def install(installer,alias):
    if alias=='linux-x64':
        # pkexec provides native graphical administrator authentication.
        run(['pkexec','/usr/bin/apt-get','install','-y',str(installer)],timeout=600)
    elif alias=='windows-x64':
        run([str(installer),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS'],timeout=600)
    else:
        # macOS administrative authorization is provided by its installer UI.
        # installer -pkg may require elevated permissions; fail closed, never
        # claim a completed unattended update without the OS accepting it.
        run(['osascript','-e',
             'on run argv\nset p to item 1 of argv\ndo shell script "/usr/sbin/installer -pkg " & quoted form of p & " -target /" with administrator privileges\nend run',
             str(installer)],timeout=900)


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--installer',type=Path,required=True);ap.add_argument('--key',type=Path,required=True)
    ap.add_argument('--wait-pid',type=int,required=True);ap.add_argument('--restart',type=Path,required=True)
    ap.add_argument('--expected-version',required=True);args=ap.parse_args(argv)
    alias=platform_id()
    try:
        if not alias:raise UpdateError('Unsupported native OS')
        payload=verify_release(json.loads(args.manifest.read_text()),args.key)
        if payload['version']!=args.expected_version:raise UpdateError('Release changed before installation')
        record=payload['installers'].get(alias)
        if not record or args.installer.name!=record['file']:raise UpdateError('Wrong platform installer')
        verify_installer(args.installer,record)
        verify_platform_signature(args.installer,alias)
        for _ in range(180):
            try:os.kill(args.wait_pid,0)
            except (ProcessLookupError,PermissionError,OSError):break
            time.sleep(.4)
        else:raise UpdateError('Application failed to close')
        # Validate again after the app exited, before privileged installation.
        verify_installer(args.installer,record)
        install(args.installer,alias)
        if alias=='windows-x64':
            subprocess.Popen([str(args.restart)],close_fds=True,creationflags=getattr(subprocess,'DETACHED_PROCESS',0))
        elif alias.startswith('macos-'):
            subprocess.Popen(['open','-a',str(args.restart)],close_fds=True,start_new_session=True)
        else:
            subprocess.Popen([str(args.restart)],close_fds=True,start_new_session=True)
        return 0
    except Exception as exc:
        print('Native update failed; existing installation has not been reported as updated:',exc,file=sys.stderr)
        # The GUI has already exited. If installation fails (including denied
        # system authorization), relaunch the still-installed application.
        try:
            if alias=='windows-x64':
                subprocess.Popen([str(args.restart)],close_fds=True,creationflags=getattr(subprocess,'DETACHED_PROCESS',0))
            elif alias and alias.startswith('macos-'):
                subprocess.Popen(['open','-a',str(args.restart)],close_fds=True,start_new_session=True)
            else:
                subprocess.Popen([str(args.restart)],close_fds=True,start_new_session=True)
        except Exception as restart_error:
            print('Also failed to relaunch installed version:',restart_error,file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
