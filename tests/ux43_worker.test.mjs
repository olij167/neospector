import test from 'node:test';
import assert from 'node:assert/strict';
import {serveNeospectorRelease} from '../web/worker.mjs';
import {DOWNLOAD_PAGE} from '../web/download_page.mjs';
const req=(path)=>new Request('https://omne.space'+path);
test('new native feed does not falsely advertise an unpublished release',async()=>{
 const r=await serveNeospectorRelease(req('/neospector/updates/installers.json'));
 assert.equal(r.status,404);
});
test('update log is available as website HTML and machine-readable JSON',async()=>{
 const html=await serveNeospectorRelease(req('/downloads/neospector/changelog'));
 const json=await serveNeospectorRelease(req('/downloads/neospector/changelog.json'));
 assert.equal(html.status,200);assert.match(await html.text(),/Neospector.*Update log/);
 assert.equal(json.status,200);assert.ok(Array.isArray(await json.json()));
});
test('public downloads do not advertise source ZIPs or portable ZIPs',()=>{
 assert.doesNotMatch(DOWNLOAD_PAGE,/Download source ZIP|Portable ZIP \(advanced\)|Verified source archive/);
 assert.match(DOWNLOAD_PAGE,/changelog/);
});
test('native path is not accessible before a signed release',async()=>{
 assert.equal((await serveNeospectorRelease(req('/neospector/updates/native/Neospector_not_published_linux-x64.deb'))).status,404);
});
