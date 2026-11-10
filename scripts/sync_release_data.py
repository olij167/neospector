#!/usr/bin/env python3
"""Generate the Worker-embedded signed manifest and approved download catalogue.

No private signing key is required; the signed manifest bytes and content are preserved.
"""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
base=ROOT/'web'
feed=json.loads((base/'stable.json').read_text())
doc=json.loads((base/'releases.json').read_text())
assert feed['payload']['version']==doc['version']
assert doc['downloads']['linux-zip']['sha256']==feed['payload']['sha256']
assert doc['downloads']['linux-zip']['bytes']==feed['payload']['bytes']
assert doc['downloads']['linux-zip']['key'].split('/')[-1]==feed['payload']['archive']
assert feed['payload']['version'].startswith('0.')
def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True)
output='// GENERATED: run python3 scripts/sync_release_data.py after editing web/releases.json.\n'
output+='// These objects are release metadata only; never embed a private signing key.\n'
output+='export const SIGNED_FEED = '+encode(feed)+';\n'
output+='export const RELEASE_CATALOGUE = '+encode(doc)+';\n'
(base/'release_data.mjs').write_text(output)
print('OK: Worker release metadata synchronised:',doc['version'])
