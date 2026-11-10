import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {serveNeospectorRelease} from '../web/worker.mjs';
const stable=JSON.parse(readFileSync(new URL('../web/stable.json',import.meta.url)));
const catalogue=JSON.parse(readFileSync(new URL('../web/releases.json',import.meta.url)));
const filename=stable.payload.archive;
const request=path=>new Request('https://omne.space'+path);

test('signed feed is served locally, regardless of GitHub availability', async()=>{
 const saved=globalThis.fetch;globalThis.fetch=async()=>new Response('unavailable',{status:503});
 try{const r=await serveNeospectorRelease(request('/neospector/updates/stable.json'));assert.equal(r.status,200);assert.deepEqual(await r.json(),stable);}finally{globalThis.fetch=saved;}
});
test('download catalogue is served locally, regardless of GitHub availability', async()=>{
 const saved=globalThis.fetch;globalThis.fetch=async()=>new Response('unavailable',{status:503});
 try{const r=await serveNeospectorRelease(request('/downloads/neospector/releases.json'));assert.equal(r.status,200);assert.deepEqual(await r.json(),catalogue);}finally{globalThis.fetch=saved;}
});
test('a transient GitHub 503 is retried, using the pinned version tag',async()=>{
 const saved=globalThis.fetch;let calls=[];
 globalThis.fetch=async url=>{calls.push(String(url));return calls.length===1?new Response('transient',{status:503}):new Response('good',{status:200});};
 try{const r=await serveNeospectorRelease(request('/neospector/updates/'+filename));assert.equal(r.status,200);assert.equal(await r.text(),'good');assert.equal(calls.length,2);assert.match(calls[0],/releases\/download\/v0\.7\.25-ux41\//);}finally{globalThis.fetch=saved;}
});
test('unavailable installer aliases are not exposed',async()=>{
 const r=await serveNeospectorRelease(request('/downloads/neospector/files/latest/windows-x64'));assert.equal(r.status,404);
});
