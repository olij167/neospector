#!/usr/bin/env python3
"""Offline publication acceptance: signed Linux UX41 immutable archive + live catalogue keys."""
import base64,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'web/stable.json').read_text());payload=manifest['payload']
assert (payload['schema'],payload['product'],payload['channel'],payload['platform'],payload['version'])==(1,'Neospector','stable','linux-x86_64','0.7.25-ux41')
archive=ROOT/'source'/payload['archive']
with archive.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
assert payload['sha256']==sha and payload['bytes']==archive.stat().st_size
with tempfile.TemporaryDirectory(prefix='neospector-verify-') as tmp:
    t=Path(tmp);(t/'data').write_bytes(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii'))
    (t/'sig').write_bytes(base64.b64decode(manifest['signature'],validate=True))
    p=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(ROOT/'web/public.pem'),'-rawin','-in',str(t/'data'),'-sigfile',str(t/'sig')],capture_output=True)
    if p.returncode:raise SystemExit('Signature mismatch: '+p.stderr.decode(errors='replace'))
cat=json.loads((ROOT/'web/releases.json').read_text());a=cat['downloads']['linux-zip']
assert a['ready'] and a['key']=='neospector/updates/'+payload['archive'] and a['sha256']==sha and a['bytes']==payload['bytes']
for k in ('windows-x64','macos-arm64','macos-x64','linux','windows-x64-portable','macos-arm64-pkg','macos-x64-pkg'):assert not cat['downloads'][k]['ready'], 'Native installer incorrectly marked as live'
print('PASS: signed UX41 manifest, archive and download alias agree; native aliases remain disabled.')
