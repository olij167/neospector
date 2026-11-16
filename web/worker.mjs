/** Neospector downloads, backed by PUBLIC olij167/neospector GitHub Releases.
 * Routes: omne.space/downloads/neospector* and omne.space/neospector/updates/*
 * No Cloudflare R2, account tokens or signing secrets required.
 * Neospector verifies Ed25519 signatures and SHA-256 over downloaded updates.
 */
import { DOWNLOAD_PAGE } from './download_page.mjs';
import { DOCS_PAGE } from './docs_page.mjs';
import { SITE_HIDDEN_HISTORY } from './site_history.mjs';
import { SIGNED_FEED, RELEASE_CATALOGUE } from './release_data.mjs';
import { SIGNED_INSTALLERS } from './native_release.mjs';
const ROOT = '/downloads/neospector';
const UPDATE = '/neospector/updates/';
const REPO = 'https://github.com/olij167/neospector/releases/download/v'+SIGNED_FEED.payload.version+'/';
const NATIVE_REPO = SIGNED_INSTALLERS?.payload?.version ? 'https://github.com/olij167/neospector/releases/download/v'+SIGNED_INSTALLERS.payload.version+'/' : null;
const TEST_TAG = RELEASE_CATALOGUE?.release_stage === 'public-test' && /^v\d+\.\d+\.\d+$/.test(RELEASE_CATALOGUE.preview_tag||'') ? RELEASE_CATALOGUE.preview_tag : null;
export function testingAssetRepo(catalogue,id,record){
  if(catalogue?.release_stage!=='public-test'||record?.stage!=='public-test')return null;
  if(!['linux','windows-x64','macos-arm64-pkg','macos-x64-pkg'].includes(id))return null;
  const tag=catalogue?.preview_tag;
  if(typeof tag!=='string'||!/^v\d+\.\d+\.\d+$/.test(tag)||record?.release_tag!==tag)return null;
  if(typeof record.key!=='string'||!/^neospector\/releases\/Neospector_[A-Za-z0-9_.-]+\.(?:deb|exe|pkg)$/.test(record.key))return null;
  return 'https://github.com/olij167/neospector/releases/download/'+tag+'/';
}

const ALIASES = new Set(['linux','linux-zip','windows-x64','macos-arm64','macos-x64','windows-x64-portable','macos-arm64-pkg','macos-x64-pkg']);
const FILENAME = /^Neospector_[A-Za-z0-9_.-]+\.(?:zip|deb|exe|dmg|pkg)$/;
const SECURITY = {'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'};
const CONTENT = {zip:'application/zip',deb:'application/vnd.debian.binary-package',exe:'application/octet-stream',dmg:'application/x-apple-diskimage',pkg:'application/octet-stream'};
const result=(body,status=200,headers={})=>new Response(body,{status,headers:{...SECURITY,...headers}});
const fileName=(name)=>typeof name==='string'&&FILENAME.test(name)&&!name.includes('..')&&!name.includes('/')?name:null;
const isDownload=(path)=>path===ROOT||path===ROOT+'/'||path.startsWith(ROOT+'/');
const assetUrl=(name, repo=REPO)=>repo+encodeURIComponent(name);
async function upstream(request,name,{isJson=false,download=false,repo=REPO}={}){
  const headers=new Headers();
  const range=request.headers.get('range');
  if(range){if(isJson||!/^bytes=(?:\d+-\d*|-\d+)$/.test(range))return result('Invalid Range',416);headers.set('Range',range);}
  // Some GitHub CDN requests return transient 5xx responses. Try the exact
  // immutable tag twice. Never redirect clients away from omne.space.
  let fetched;
  for(let attempt=0;attempt<2;attempt++){
    try{fetched=await fetch(assetUrl(name,repo),{method:request.method,headers,redirect:'follow'});}catch{fetched=null;}
    if(fetched&&[200,206].includes(fetched.status))break;
    if(fetched&&[400,401,403,404,416].includes(fetched.status))break;
  }
  if(!fetched)return result('Release host unavailable',503);
  if(![200,206].includes(fetched.status))return result('Release asset unavailable',fetched.status===404?404:503);
  const h=new Headers(SECURITY);
  h.set('Content-Type',isJson?'application/json; charset=utf-8':CONTENT[name.split('.').at(-1)]||'application/octet-stream');
  h.set('Cache-Control',isJson?'no-store':'public, max-age=300');
  if(download)h.set('Content-Disposition',`attachment; filename="${name}"`);
  for(const field of ['content-length','content-range','accept-ranges','etag','last-modified']){
    const value=fetched.headers.get(field);if(value)h.set(field,value);
  }
  return new Response(request.method==='HEAD'?null:fetched.body,{status:fetched.status,headers:h});
}
function catalogue(){ return RELEASE_CATALOGUE; }
function localJson(request,data){
 return result(request.method==='HEAD'?null:JSON.stringify(data),200,{
  'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'
 });
}
function esc(s){return String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));}
function changelogPage(){
 /* NEOSPECTOR-HISTORY-V2: shared neutral site visual language, no installer changes */
 const entries=(RELEASE_CATALOGUE.history||[])
  .filter(x=>!SITE_HIDDEN_HISTORY.has(x.version))
  .map(x=>`<article class="entry"><div class="entry-head"><h2>v${esc(x.version)} · ${esc(x.title)}</h2><time>${esc(x.date)}</time></div>${x.stage==='public-test'?'<p class="stage">Public test release</p>':''}<p class="entry-notes">${esc(x.notes).replaceAll('\n','<br>')}</p></article>`)
  .join('')||'<p class="empty">No public releases are listed.</p>';
 return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><meta name="theme-color" content="#151515"><title>Neospector — Release history</title><style>
:root{color-scheme:dark;--bg:#151515;--fg:#eeeae5;--dim:#b2adab;--line:#424044;--accent:#dfb558;font:16px/1.5 Arial,Helvetica,sans-serif}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--fg)}
a{color:inherit;text-underline-offset:3px}a:hover{color:var(--accent)}a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.skip{position:absolute;top:-80px;background:var(--fg);color:var(--bg);padding:8px;z-index:9}.skip:focus{top:7px}
.frame{width:min(100%,1250px);min-height:100svh;padding:0 clamp(20px,4vw,52px);margin:auto;display:grid;grid-template-rows:auto 1fr auto}
.top{height:65px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}.brand{font-weight:700;text-decoration:none;font-size:14px}
.top nav,footer nav{display:flex;gap:22px;font-size:13px}.top nav a{text-decoration:none}.top nav a[aria-current="page"]{color:var(--accent)}
main{width:min(100%,860px);margin:0 auto;padding:clamp(34px,7vh,90px) 0 90px}
.eyebrow{color:var(--dim);font-size:13px;margin:0 0 9px}h1{font-size:clamp(38px,6vw,58px);letter-spacing:-.045em;line-height:1.08;margin:0 0 15px}.lead{color:var(--dim);margin:0 0 43px;font-size:15px}
.entry{border-top:1px solid var(--line);padding:24px 0 28px}.entry-head{display:flex;align-items:baseline;gap:18px;justify-content:space-between}.entry h2{font-size:20px;font-weight:700;letter-spacing:-.02em;margin:0}.entry time{color:var(--dim);font-size:13px;white-space:nowrap}
.stage{font-size:12px;color:var(--dim);margin:6px 0 0}.entry-notes{font-size:15px;line-height:1.65;max-width:70ch;margin:18px 0 0;overflow-wrap:anywhere}.empty{color:var(--dim);border-top:1px solid var(--line);padding-top:25px}
footer{border-top:1px solid var(--line);min-height:55px;display:flex;align-items:center;justify-content:space-between;color:var(--dim);font-size:12px;gap:12px}footer a{color:var(--dim)}
@media(max-width:580px){.top{height:50px}.frame{padding:0 17px}.top nav{gap:14px}main{padding:36px 0 65px}.lead{margin-bottom:32px}.entry-head{display:block}.entry time{display:block;margin-top:7px}.entry h2{font-size:18px}footer nav{gap:11px}}
</style></head><body><a class="skip" href="#main">Skip to releases</a><div class="frame"><header class="top"><a class="brand" href="https://pungentfunk.org/">Pungent Funk</a><nav aria-label="Neospector navigation"><a href="/downloads/neospector">Neospector</a><a href="/downloads/neospector/docs">Guide</a><a aria-current="page" href="/downloads/neospector/changelog">Releases</a></nav></header><main id="main"><p class="eyebrow">Neospector / Pungent Funk</p><h1>Release history</h1><p class="lead">Published versions and their release notes.</p><div class="entries">${entries}</div></main><footer><span>Neospector / Pungent Funk</span><nav><a href="/downloads/neospector">Downloads</a><a href="/downloads/neospector/docs">Documentation</a></nav></footer></div></body></html>`;
}
export async function serveNeospectorRelease(request){
 let url;try{url=new URL(request.url);}catch{return null;}
 const path=url.pathname;
 if(!isDownload(path)&&!path.startsWith(UPDATE))return null;
 if(!['GET','HEAD'].includes(request.method))return result('Method Not Allowed',405,{Allow:'GET, HEAD'});
 if(path.startsWith(ROOT+'/media/')){
  const filename=path.slice((ROOT+'/media/').length);
  if(!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.(?:webp|png|jpg|jpeg|gif|mp4|webm)$/i.test(filename)||filename.includes('..'))return result('Not Found',404);
  const type={webp:'image/webp',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',gif:'image/gif',mp4:'video/mp4',webm:'video/webm'}[filename.split('.').pop().toLowerCase()];
  const headers=new Headers();const range=request.headers.get('Range');
  if(range){if(!/^bytes=(?:\d+-\d*|-\d+)$/.test(range))return result('Invalid Range',416);headers.set('Range',range);}
  let upstreamMedia;
  try{upstreamMedia=await fetch('https://raw.githubusercontent.com/olij167/neospector/main/web/site_media/'+encodeURIComponent(filename),{method:request.method,headers,redirect:'follow'});}catch{return result('Media host unavailable',503);}
  if(!upstreamMedia.ok)return result('Media not available',upstreamMedia.status===404?404:503);
  const outputHeaders={'Content-Type':type,'Cache-Control':'public, max-age=300','X-Content-Type-Options':'nosniff'};
  for(const key of ['Content-Length','Content-Range','Accept-Ranges']){const value=upstreamMedia.headers.get(key);if(value)outputHeaders[key]=value;}
  return result(request.method==='HEAD'?null:upstreamMedia.body,upstreamMedia.status,outputHeaders);
 }
 if(path===ROOT||path===ROOT+'/')return result(request.method==='HEAD'?null:DOWNLOAD_PAGE,200,{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; media-src 'self'; base-uri 'none'; form-action 'none'"});
 if(path===ROOT+'/releases.json')return localJson(request,RELEASE_CATALOGUE);
 if(path===ROOT+'/docs'||path===ROOT+'/docs/')return result(request.method==='HEAD'?null:DOCS_PAGE,200,{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src 'self'; media-src 'self'; base-uri 'none'; form-action 'none'"});
 if(path===ROOT+'/changelog.json')return localJson(request,RELEASE_CATALOGUE.history||[]);
 if(path===ROOT+'/changelog')return result(request.method==='HEAD'?null:changelogPage(),200,{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"});
 if(path.startsWith(UPDATE)){
  const name=path.slice(UPDATE.length);
  if(name==='stable.json')return localJson(request,SIGNED_FEED); // older UX41 clients only
  if(name==='installers.json')return SIGNED_INSTALLERS?localJson(request,SIGNED_INSTALLERS):result('Native releases not yet published',404);
  if(name.startsWith('native/')){
    if(!SIGNED_INSTALLERS||!NATIVE_REPO)return result('Not Found',404);
    const filename=name.slice('native/'.length);
    if(!fileName(filename)||!['.deb','.exe','.pkg'].some(ext=>filename.endsWith(ext)))return result('Not Found',404);
    const entries=Object.values(SIGNED_INSTALLERS.payload.installers||{});
    if(!entries.some(x=>x.file===filename&&x.sha256&&x.bytes>0))return result('Not Found',404);
    return upstream(request,filename,{download:true,repo:NATIVE_REPO});
  }
  if(!fileName(name)||!name.endsWith('.zip'))return result('Not Found',404);
  const doc=catalogue();
  const record=doc?.downloads?.['linux-zip'];
  if(record?.ready!==true||!fileName(record.key?.split('/').at(-1))||record.key.split('/').at(-1)!==name)return result('Not Found',404);
  return upstream(request,name,{download:true});
 }
 const prefix=ROOT+'/files/latest/';
 if(path.startsWith(prefix)){
  const id=path.slice(prefix.length);
  if(!ALIASES.has(id))return result('Not Found',404);
  const doc=catalogue();const rec=doc?.downloads?.[id];
  if(rec?.ready!==true||!rec?.sha256||!Number.isSafeInteger(rec.bytes)||rec.bytes<=0)return result('Not Found',404);
  const name=fileName(rec.key?.split('/').at(-1));
  if(!name)return result('Not Found',404);
  if(rec?.stage==='public-test'){
    const repo=testingAssetRepo(RELEASE_CATALOGUE,id,rec);
    if(!repo)return result('Not Found',404);
    return upstream(request,name,{download:true,repo});
  }
  return upstream(request,name,{download:true,repo:NATIVE_REPO&&name.endsWith('.zip')===false&&RELEASE_CATALOGUE.version===SIGNED_INSTALLERS?.payload?.version?NATIVE_REPO:REPO});
 }
 return result('Not Found',404);
}
export default {async fetch(request){return await serveNeospectorRelease(request)??result('Not Found',404)}};
