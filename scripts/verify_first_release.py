#!/usr/bin/env python3
"""Validate the accepted owner-signed UX41 archive before publishing to GitHub."""
import base64,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
expected=json.loads((ROOT/'web/stable.json').read_text());data=expected['payload'];signed=expected['signature']
archive=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path.home()/'Downloads'/data['archive']
if archive.name!=data['archive']:raise SystemExit('Unexpected release archive name')
if not archive.is_file():raise SystemExit('Missing archive: '+str(archive))
with archive.open('rb') as fh:sha=hashlib.file_digest(fh,'sha256').hexdigest()
if sha!=data['sha256'] or archive.stat().st_size!=data['bytes']:raise SystemExit('Signed archive checksum/size mismatch')
cat=json.loads((ROOT/'web/releases.json').read_text());rec=cat['downloads']['linux-zip']
if not rec['ready'] or rec['sha256']!=sha or rec['bytes']!=data['bytes'] or rec['key'].split('/')[-1]!=archive.name:raise SystemExit('Catalogue mismatch')
if any(x.get('ready') for k,x in cat['downloads'].items() if k!='linux-zip'):raise SystemExit('Unaccepted native installer enabled')
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'msg').write_bytes(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode())
 (p/'sig').write_bytes(base64.b64decode(signed,validate=True))
 check=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(ROOT/'web/public.pem'),'-rawin','-in',str(p/'msg'),'-sigfile',str(p/'sig')],capture_output=True)
 if check.returncode:raise SystemExit('Release signature did not verify: '+check.stderr.decode(errors='replace'))
print('PUBLISH PRECHECK PASS:',data['version'],archive.name,sha,'(signature and catalogue verified)')
