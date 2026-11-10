/** Neospector downloads, backed by PUBLIC olij167/neospector GitHub Releases.
 * Routes: omne.space/downloads/neospector* and omne.space/neospector/updates/*
 * No Cloudflare R2, account tokens or signing secrets required.
 * Neospector verifies Ed25519 signatures and SHA-256 over downloaded updates.
 */
import { DOWNLOAD_PAGE } from './download_page.mjs';
import { SIGNED_FEED, RELEASE_CATALOGUE } from './release_data.mjs';
import { SIGNED_INSTALLERS } from './native_release.mjs';
const ROOT = '/downloads/neospector';
const UPDATE = '/neospector/updates/';
const REPO = 'https://github.com/olij167/neospector/releases/download/v'+SIGNED_FEED.payload.version+'/';
const NATIVE_REPO = SIGNED_INSTALLERS?.payload?.version ? 'https://github.com/olij167/neospector/releases/download/v'+SIGNED_INSTALLERS.payload.version+'/' : null;
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
 const entries=(RELEASE_CATALOGUE.history||[]).map(x=>`<article><h2>${esc(x.version)} — ${esc(x.title)}</h2><small>${esc(x.date)}</small><p>${esc(x.notes).replaceAll('\n','<br>')}</p></article>`).join('')||'<p>Release history will appear here after the first native installer publication.</p>';
 return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Neospector — Update log</title><style>body{background:#110f17;color:#eee7f4;font:16px system-ui;margin:auto;max-width:800px;padding:32px}a{color:#dec177}article{border-top:1px solid #514359;padding:18px 0}small{color:#bdb0c5}p{line-height:1.6;white-space:normal}</style></head><body><a href="/downloads/neospector">Neospector downloads</a><h1>Update log</h1>${entries}</body></html>`;
}
export async function serveNeospectorRelease(request){
 let url;try{url=new URL(request.url);}catch{return null;}
 const path=url.pathname;
 if(!isDownload(path)&&!path.startsWith(UPDATE))return null;
 if(!['GET','HEAD'].includes(request.method))return result('Method Not Allowed',405,{Allow:'GET, HEAD'});
 if(path===ROOT||path===ROOT+'/')return result(request.method==='HEAD'?null:DOWNLOAD_PAGE,200,{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"});
 if(path===ROOT+'/releases.json')return localJson(request,RELEASE_CATALOGUE);
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
  return upstream(request,name,{download:true,repo:NATIVE_REPO&&name.endsWith('.zip')===false&&RELEASE_CATALOGUE.version===SIGNED_INSTALLERS?.payload?.version?NATIVE_REPO:REPO});
 }
 return result('Not Found',404);
}
export default {async fetch(request){return await serveNeospectorRelease(request)??result('Not Found',404)}};
