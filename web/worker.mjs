/** Neospector downloads, backed by PUBLIC olij167/neospector GitHub Releases.
 * Routes: omne.space/downloads/neospector* and omne.space/neospector/updates/*
 * No Cloudflare R2, account tokens or signing secrets required.
 * Neospector verifies Ed25519 signatures and SHA-256 over downloaded updates.
 */
import { DOWNLOAD_PAGE } from './download_page.mjs';
const ROOT = '/downloads/neospector';
const UPDATE = '/neospector/updates/';
const REPO = 'https://github.com/olij167/neospector/releases/latest/download/';
const ALIASES = new Set(['linux','linux-zip','windows-x64','macos-arm64','macos-x64','windows-x64-portable','macos-arm64-pkg','macos-x64-pkg']);
const FILENAME = /^Neospector_[A-Za-z0-9_.-]+\.(?:zip|deb|exe|dmg|pkg)$/;
const SECURITY = {'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'};
const CONTENT = {zip:'application/zip',deb:'application/vnd.debian.binary-package',exe:'application/octet-stream',dmg:'application/x-apple-diskimage',pkg:'application/octet-stream'};
const result=(body,status=200,headers={})=>new Response(body,{status,headers:{...SECURITY,...headers}});
const fileName=(name)=>typeof name==='string'&&FILENAME.test(name)&&!name.includes('..')&&!name.includes('/')?name:null;
const isDownload=(path)=>path===ROOT||path===ROOT+'/'||path.startsWith(ROOT+'/');
const assetUrl=(name)=>REPO+encodeURIComponent(name);
async function upstream(request,name,{isJson=false,download=false}={}){
  const headers=new Headers();
  const range=request.headers.get('range');
  if(range){if(isJson||!/^bytes=(?:\d+-\d*|-\d+)$/.test(range))return result('Invalid Range',416);headers.set('Range',range);}
  let fetched;
  try {fetched=await fetch(assetUrl(name),{method:request.method,headers,redirect:'follow'});}catch{return result('Release host unavailable',503);}
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
async function catalogue(){
 let response;
 try{response=await fetch(assetUrl('releases.json'),{redirect:'follow',headers:{Accept:'application/json'}});}catch{return null;}
 if(!response.ok)return null;
 const length=Number(response.headers.get('content-length')||0);if(length>32768)return null;
 const raw=await response.text();if(raw.length>32768)return null;
 let d;try{d=JSON.parse(raw);}catch{return null;}
 if(d?.schema!==1||d?.product!=='Neospector'||!d?.downloads||typeof d.downloads!=='object')return null;
 return d;
}
export async function serveNeospectorRelease(request){
 let url;try{url=new URL(request.url);}catch{return null;}
 const path=url.pathname;
 if(!isDownload(path)&&!path.startsWith(UPDATE))return null;
 if(!['GET','HEAD'].includes(request.method))return result('Method Not Allowed',405,{Allow:'GET, HEAD'});
 if(path===ROOT||path===ROOT+'/')return result(request.method==='HEAD'?null:DOWNLOAD_PAGE,200,{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'"});
 if(path===ROOT+'/releases.json')return upstream(request,'releases.json',{isJson:true});
 if(path.startsWith(UPDATE)){
  const name=path.slice(UPDATE.length);
  if(name==='stable.json')return upstream(request,'stable.json',{isJson:true});
  if(!fileName(name)||!name.endsWith('.zip'))return result('Not Found',404);
  const doc=await catalogue();
  const record=doc?.downloads?.['linux-zip'];
  if(record?.ready!==true||!fileName(record.key?.split('/').at(-1))||record.key.split('/').at(-1)!==name)return result('Not Found',404);
  return upstream(request,name,{download:true});
 }
 const prefix=ROOT+'/files/latest/';
 if(path.startsWith(prefix)){
  const id=path.slice(prefix.length);
  if(!ALIASES.has(id))return result('Not Found',404);
  const doc=await catalogue();const rec=doc?.downloads?.[id];
  if(rec?.ready!==true||!rec?.sha256||!Number.isSafeInteger(rec.bytes)||rec.bytes<=0)return result('Not Found',404);
  const name=fileName(rec.key?.split('/').at(-1));
  if(!name)return result('Not Found',404);
  return upstream(request,name,{download:true});
 }
 return result('Not Found',404);
}
export default {async fetch(request){return await serveNeospectorRelease(request)??result('Not Found',404)}};
