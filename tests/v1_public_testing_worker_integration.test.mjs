import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,copyFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const src=fileURLToPath(new URL('../web/',import.meta.url));
const names=['linux','windows-x64','macos-arm64-pkg','macos-x64-pkg'];
const aliases={linux:['linux-x64','.deb'],'windows-x64':['windows-x64','_Setup.exe'],
  'macos-arm64-pkg':['macos-arm64','.pkg'],'macos-x64-pkg':['macos-x64','.pkg']};

test('public testing catalogue routes all four installers to one immutable GitHub prerelease and never serves ZIP',async()=>{
 const temp=mkdtempSync(join(tmpdir(),'neospector-v1-worker-'));
 const oldFetch=globalThis.fetch;
 try{
   for(const name of ['worker.mjs','download_page.mjs','native_release.mjs'])
     copyFileSync(join(src,name),join(temp,name));
   const downloads={ 'linux-zip':{ready:false,key:null,sha256:null,bytes:null} };
   for(const [id,[alias,ext]] of Object.entries(aliases)){
     downloads[id]={ready:true,key:'neospector/releases/Neospector_1.0.0_'+alias+ext,
       sha256:'a'.repeat(64),bytes:1024,stage:'public-test',release_tag:'v1.0.0'};
   }
   const catalog={schema:1,product:'Neospector',version:'1.0.0',
     release_stage:'public-test',preview_tag:'v1.0.0',downloads,history:[]};
   const legacy={payload:{version:'0.7.25-ux41'}};
   writeFileSync(join(temp,'release_data.mjs'),
     'export const RELEASE_CATALOGUE='+JSON.stringify(catalog)+';\n'+
     'export const SIGNED_FEED='+JSON.stringify(legacy)+';\n');
   const {serveNeospectorRelease}=await import(pathToFileURL(join(temp,'worker.mjs')).href);
   const seen=[];
   globalThis.fetch=async (url,opts)=>{
     seen.push(String(url));
     return new Response('mock native installer',{status:200,headers:{'Content-Type':'application/octet-stream'}});
   };
   for(const id of names){
     const response=await serveNeospectorRelease(new Request('https://omne.space/downloads/neospector/files/latest/'+id));
     assert.equal(response.status,200,id);
     assert.match(seen.at(-1),/^https:\/\/github\.com\/olij167\/neospector\/releases\/download\/v1\.0\.0\/Neospector_1\.0\.0_/);
     assert(!seen.at(-1).endsWith('.zip'));
   }
   assert.equal(seen.length,4);
   for(const id of ['linux-zip','windows-x64-portable','macos-arm64']){
     const response=await serveNeospectorRelease(new Request('https://omne.space/downloads/neospector/files/latest/'+id));
     assert.equal(response.status,404,id);
   }
   const signed=await serveNeospectorRelease(new Request('https://omne.space/neospector/updates/installers.json'));
   assert.equal(signed.status,404,'public test must not enable signed auto-install');
   const stable=await serveNeospectorRelease(new Request('https://omne.space/neospector/updates/stable.json'));
   assert.equal((await stable.json()).payload.version,'0.7.25-ux41','legacy feed stays pinned');
   const ver=await serveNeospectorRelease(new Request('https://omne.space/downloads/neospector/releases.json'));
   assert.equal((await ver.json()).version,'1.0.0');
 } finally {globalThis.fetch=oldFetch;rmSync(temp,{recursive:true,force:true});}
});
