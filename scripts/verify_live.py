#!/usr/bin/env python3
"""Check live HTTPS feed, public alias and entire release; read-only."""
import argparse,hashlib,json,urllib.request,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--url',default='https://omne.space/neospector/updates/stable.json');a=p.parse_args()
if not a.url.startswith('https://') or urllib.parse.urlsplit(a.url).hostname!='omne.space':raise SystemExit('Only the official HTTPS host may be verified')
expected=json.loads((ROOT/'web/stable.json').read_text());feed=urllib.request.urlopen(urllib.request.Request(a.url,headers={'Accept':'application/json','User-Agent':'Neospector-Updater/1'}),timeout=12)
remote=feed.read(32769)
if len(remote)>32768:raise SystemExit('Feed too large')
if json.loads(remote)!=expected:raise SystemExit('Published feed differs from approved signed manifest')
record=expected['payload'];url=urllib.parse.urljoin(a.url,record['archive'])
if urllib.parse.urlsplit(url).netloc!=urllib.parse.urlsplit(a.url).netloc:raise SystemExit('Cross-host release URL')
h=hashlib.sha256();length=0
with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'application/zip','User-Agent':'Neospector-Updater/1'}),timeout=20) as response:
    if response.geturl().split('/')[2]!=urllib.parse.urlsplit(a.url).hostname:raise SystemExit('Archive redirected to another host')
    while True:
        b=response.read(1024*1024)
        if not b:break
        length+=len(b)
        if length>record['bytes']:raise SystemExit('Oversized download')
        h.update(b)
if length!=record['bytes'] or h.hexdigest()!=record['sha256']:raise SystemExit('Live ZIP checksum mismatch')
alias='https://omne.space/downloads/neospector/files/latest/linux-zip'
with urllib.request.urlopen(urllib.request.Request(alias,headers={'User-Agent':'Neospector-Updater/1'},method='HEAD'),timeout=12) as res:
    if res.status!=200:raise SystemExit('Public latest alias is not live')
print('LIVE VERIFIED: HTTPS signed feed + full ZIP + public latest alias; version',record['version'])
