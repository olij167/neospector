#!/usr/bin/env python3
"""Compile safe, owner-editable JSON content into the existing Cloudflare Worker pages.
Never commits, pushes, dispatches builds or deploys."""
import argparse
import json
from pathlib import Path
import re
import shutil

MEDIA_PREFIX='/downloads/neospector/media/'
ASSET=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:webp|png|jpg|jpeg|gif|mp4|webm)$',re.I)
SECTION=re.compile(r'^[a-z][a-z0-9-]{0,40}$')


def validate_media(entry, *, docs=False):
    if not isinstance(entry,dict) or entry.get('type') not in ('image','video'):
        raise ValueError('Media must have image/video type')
    url=entry.get('src','')
    if not isinstance(url,str) or not url.startswith(MEDIA_PREFIX) or not ASSET.fullmatch(url[len(MEDIA_PREFIX):]):
        raise ValueError('Media must reference a local, safe /downloads/neospector/media/ filename')
    if entry['type']=='image' and not str(entry.get('alt','')).strip():
        raise ValueError('Each image must have descriptive alternative text')
    for k in ('alt','caption'):
        if len(str(entry.get(k,'')))>350:raise ValueError(f'{k} too long')
    return entry


def validate(home, docs, media_folder=None):
    if home.get('schema')!=1 or docs.get('schema')!=1:raise ValueError('Content schema mismatch')
    for k in ('product','description','detail','eyebrow','download_heading','public_test_notice'):
        if not isinstance(home.get(k),str) or len(home[k])>1200:raise ValueError('Invalid home '+k)
    media=home.get('media',[])
    if not isinstance(media,list) or len(media)>20:raise ValueError('Slide count must be 0–20')
    for row in media:validate_media(row)
    if not isinstance(docs.get('sections'),list) or len(docs['sections'])>80:raise ValueError('Invalid documentation sections')
    seen=set()
    for sec in docs['sections']:
        if not SECTION.fullmatch(str(sec.get('id',''))) or sec['id'] in seen:raise ValueError('Invalid or duplicate section ID')
        seen.add(sec['id'])
        if len(str(sec.get('title','')))>150 or len(str(sec.get('body','')))>12000:raise ValueError('Section content too long')
        for item in sec.get('media',[]):validate_media(item,docs=True)
    if media_folder:
        all_media=media[:]
        for sec in docs['sections']:all_media.extend(sec.get('media',[]))
        for item in all_media:
            f=media_folder/item['src'][len(MEDIA_PREFIX):]
            if not f.is_file() or f.is_symlink():raise ValueError('Referenced media missing: '+str(f))
    hidden=home.get('hidden_history_versions',[])
    if not isinstance(hidden,list) or len(hidden)>100 or len(set(str(x) for x in hidden))!=len(hidden):
        raise ValueError('History visibility must list at most 100 unique versions')
    if any(not isinstance(v,str) or not re.fullmatch(r'\d+\.\d+\.\d+',v) for v in hidden):
        raise ValueError('History visibility entries must be version numbers')
    appearance=home.get('appearance') or {}
    if not isinstance(appearance,dict):raise ValueError('Appearance must be an object')
    if appearance and (set(appearance)!={'accent','background','foreground'} or
                       any(not isinstance(v,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in appearance.values())):
        raise ValueError('Appearance colors must be six-digit hexadecimal colors')
    commerce=home.get('commerce') or {}
    if commerce.get('enabled'):
        raise ValueError('Ko-fi checkout is not yet implemented; commerce.enabled must remain false')
    return True


def embed_json(obj):
    # Script-data injection prevention: </script> and HTML tags cannot be parsed.
    return json.dumps(obj,ensure_ascii=True,separators=(',',':')).replace('<',r'\u003c').replace('>',r'\u003e').replace('&',r'\u0026')


def pages(templates, home_data, docs_data):
    validate(home_data,docs_data)
    home=(templates/'home.html').read_text(encoding='utf-8')
    home_style=(templates/'home.css').read_text(encoding='utf-8')
    docs_style=(templates/'docs.css').read_text(encoding='utf-8')
    appearance=home_data.get('appearance') or {}
    if appearance:
        home_style+='\n:root{--accent:'+appearance['accent']+';--bg:'+appearance['background']+';--fg:'+appearance['foreground']+'}\n'
        docs_style+='\n:root{--gold:'+appearance['accent']+';background:'+appearance['background']+';color:'+appearance['foreground']+'}\n'
    home=home.replace('/*SITE_STYLE*/',home_style)
    home=home.replace('/*SITE_CONTENT*/',embed_json(home_data))
    home=home.replace('/*SITE_SCRIPT*/',(templates/'home.js').read_text(encoding='utf-8'))
    docs=(templates/'docs.html').read_text(encoding='utf-8')
    docs=docs.replace('/*DOCS_STYLE*/',docs_style)
    docs=docs.replace('/*DOCS_CONTENT*/',embed_json(docs_data))
    docs=docs.replace('/*DOCS_SCRIPT*/',(templates/'docs.js').read_text(encoding='utf-8'))
    return home,docs


def compile_repo(repo, *, preview_dir=None):
    repo=Path(repo).expanduser().resolve()
    content=repo/'web'
    h=json.loads((content/'site_content.json').read_text(encoding='utf-8'))
    d=json.loads((content/'docs_content.json').read_text(encoding='utf-8'))
    validate(h,d,content/'site_media')
    # The public current version cannot be hidden from the changelog.
    release_file=content/'releases.json'
    if release_file.is_file():
        current=json.loads(release_file.read_text(encoding='utf-8')).get('version')
        if current in h.get('hidden_history_versions',[]):raise ValueError('Cannot hide the current public release from website history')

    home,docs=pages(content/'site_templates',h,d)
    (content/'download_page.mjs').write_text('export const DOWNLOAD_PAGE = '+json.dumps(home,ensure_ascii=True)+';\n',encoding='utf-8')
    (content/'docs_page.mjs').write_text('export const DOCS_PAGE = '+json.dumps(docs,ensure_ascii=True)+';\n',encoding='utf-8')
    (content/'site_history.mjs').write_text('export const SITE_HIDDEN_HISTORY = new Set('+json.dumps(h.get('hidden_history_versions',[]))+');\n',encoding='utf-8')
    if preview_dir:
        dest=Path(preview_dir).expanduser().resolve();dest.mkdir(parents=True,exist_ok=True)
        # Preview release metadata is illustrative only; no downloads are fetched.
        sample={'version':'1.0.0','release_stage':'public-test','downloads':{}}
        for alias,ext in [('linux','deb'),('windows-x64','exe'),('macos-arm64-pkg','pkg'),('macos-x64-pkg','pkg')]:
            sample['downloads'][alias]={'ready':True,'key':f'neospector/releases/Neospector_1.0.0_{alias}.{ext}',
                'sha256':'a'*64,'bytes':38000000,'stage':'public-test'}
        shim='<script>/* OFFLINE PREVIEW: simulated installer data only */const originalFetch=window.fetch.bind(window);window.fetch=(url,opts)=>String(url).endsWith("releases.json")?Promise.resolve({ok:true,json:async()=>('+json.dumps(sample)+')}):originalFetch(url,opts);</script>'
        home=home.replace('<script>',''+shim+'\n<script>',1)
        home=home.replace('/downloads/neospector/docs','./guide.html').replace('/downloads/neospector/changelog','https://omne.space/downloads/neospector/changelog')
        docs=docs.replace('/downloads/neospector"','./index.html"').replace('/downloads/neospector/changelog','https://omne.space/downloads/neospector/changelog')
        for filename,markup in [('index.html',home),('guide.html',docs)]:
            (dest/filename).write_text(markup.replace(MEDIA_PREFIX,'./media/'),encoding='utf-8')
        media_dest=dest/'media';media_dest.mkdir(exist_ok=True)
        for media in (content/'site_media').iterdir():
            if media.is_file() and ASSET.fullmatch(media.name):shutil.copy2(media,media_dest/media.name)
    return home,docs


def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--preview-dir',type=Path)
    args=p.parse_args();compile_repo(args.repo,preview_dir=args.preview_dir)
    print('Neospector pages compiled locally. No build, commit, push or website deployment.')

if __name__=='__main__': main()
