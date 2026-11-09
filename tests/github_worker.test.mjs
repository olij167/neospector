import test from 'node:test';
import assert from 'node:assert/strict';
import {serveNeospectorRelease} from '../web/worker.mjs';
import {readFileSync} from 'node:fs';
const catalogue=JSON.parse(readFileSync(new URL('../web/releases.json',import.meta.url)));
const payload=readFileSync(new URL('../web/stable.json',import.meta.url));
const filename=catalogue.downloads['linux-zip'].key.split('/').at(-1);
const calls=[];
const priorFetch=globalThis.fetch;
globalThis.fetch=async (url,opts={})=>{
 const dest=String(url);calls.push({dest,method:opts.method||'GET',range:opts.headers?.get?.('range')});
 assert.match(dest,/^https:\/\/github\.com\/olij167\/neospector\/releases\/latest\/download\/[^/]+$/);
 let data;
 if(dest.endsWith('releases.json'))data=JSON.stringify(catalogue);
 else if(dest.endsWith('stable.json'))data=payload;
 else if(dest.endsWith(encodeURIComponent(filename)))data='ACCEPTED_RELEASE_TEST_BYTES';
 else return new Response('missing',{status:404});
 return new Response(opts.method==='HEAD'?null:data,{status:200,headers:{'content-length':String(Buffer.byteLength(data)),'accept-ranges':'bytes'}});
};
const req=(path,method='GET',headers={})=>new Request('https://omne.space'+path,{method,headers});
test('only Neospector routes resolve',async()=>{
 assert.equal(await serveNeospectorRelease(req('/waves')),null);
 assert.equal((await serveNeospectorRelease(req('/downloads/neospector'))).status,200);
});
test('signed feed served from latest GitHub release, never redirects viewer',async()=>{
 let r=await serveNeospectorRelease(req('/neospector/updates/stable.json'));
 assert.equal(r.status,200);assert.equal((await r.json()).payload.version,'0.7.25-ux41');
 assert.equal(r.headers.get('location'),null);
});
test('update ZIP and public alias stream the exact same GitHub object',async()=>{
 calls.length=0;
 const a=await serveNeospectorRelease(req('/neospector/updates/'+filename));
 const b=await serveNeospectorRelease(req('/downloads/neospector/files/latest/linux-zip'));
 assert.equal(await a.text(),await b.text());assert.equal(a.status,200);assert.equal(b.status,200);
 assert.equal(calls[1].dest,calls.at(-1).dest);
});
test('unpublished platforms rejected',async()=>{
 for(const id of ['linux','windows-x64','macos-x64','macos-arm64','windows-x64-portable','macos-arm64-pkg','macos-x64-pkg']){
  assert.equal((await serveNeospectorRelease(req('/downloads/neospector/files/latest/'+id))).status,404);
 }
});
test('HEAD, invalid range, invalid methods, unsafe filename',async()=>{
 assert.equal((await serveNeospectorRelease(req('/downloads/neospector/files/latest/linux-zip','HEAD'))).status,200);
 assert.equal((await serveNeospectorRelease(req('/downloads/neospector/files/latest/linux-zip','GET',{'Range':'bytes=1-2,3-4'}))).status,416);
 assert.equal((await serveNeospectorRelease(req('/neospector/updates/private.key'))).status,404);
 assert.equal((await serveNeospectorRelease(req('/downloads/neospector/files/latest/linux-zip','POST'))).status,405);
});
