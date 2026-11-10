import test from 'node:test';
import assert from 'node:assert/strict';
import {testingAssetRepo} from '../web/worker.mjs';

const catalogue={release_stage:'public-test',version:'1.0.0',preview_tag:'v1.0.0'};
const rec={stage:'public-test',release_tag:'v1.0.0',key:'neospector/releases/Neospector_1.0.0_windows-x64_Setup.exe'};
test('public test releases route through immutable GitHub tag',()=>{
 assert.equal(testingAssetRepo(catalogue,'windows-x64',rec),
              'https://github.com/olij167/neospector/releases/download/v1.0.0/');
});
test('public test route refuses ZIP, forged paths, missing stage and mismatched tags',()=>{
 for(const x of ['linux-zip','windows-x64-portable','macos-arm64']){
  assert.equal(testingAssetRepo(catalogue,x,rec),null);
 }
 assert.equal(testingAssetRepo({...catalogue,release_stage:'stable'},'windows-x64',rec),null);
 assert.equal(testingAssetRepo(catalogue,'windows-x64',{...rec,key:'neospector/releases/archive.zip'}),null);
 assert.equal(testingAssetRepo(catalogue,'windows-x64',{...rec,release_tag:'v1.0.1'}),null);
 assert.equal(testingAssetRepo({...catalogue,preview_tag:'v1.0.0/../../evil'},'windows-x64',rec),null);
});
