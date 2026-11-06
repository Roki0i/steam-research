import {test} from 'node:test';
import assert from 'node:assert/strict';
import {loadCatalogue,validPart,updateSummary,PUBLIC_BASE,latestClosedMonth,isObservationOutdated} from '../dataset.mjs';
const snapshot={schemaVersion:2,games:[{part:'data/players-auto-00-0123456789abcdef.json'}]};
test('prefers public dataset and falls back when it is unavailable',async()=>{
 let calls=[];
 const loaded=await loadCatalogue(async url=>{calls.push(url);if(url.startsWith(PUBLIC_BASE))throw new Error('offline');return {ok:true,json:async()=>snapshot};});
 assert.equal(loaded.fallback,true);assert.equal(loaded.base,'./');assert.equal(calls.length,2);
 const remote=await loadCatalogue(async()=>({ok:true,json:async()=>snapshot}));assert.equal(remote.fallback,false);
});
test('rejects paths outside player parts and keeps sample status explicit',()=>{
 assert.equal(validPart('../secret.json'),false);assert.equal(validPart('https://example.com/data.json'),false);
 assert.match(updateSummary({refresh:{lastAttemptAt:'2026-11-05T00:00:00Z',status:'sample_verified',successful:3,total:1000}}),/3\/1000/);
 assert.match(updateSummary({}),/初回実行待ち/);
});

test('clearly identifies observation months older than the last closed calendar month',()=>{
 const november=new Date('2026-11-07T00:00:00Z');
 assert.equal(latestClosedMonth(november),'2026-10');
 assert.equal(isObservationOutdated('2026-07',november),true);
 assert.equal(isObservationOutdated('2026-10',november),false);
 assert.equal(latestClosedMonth(new Date('2027-01-01T00:00:00Z')),'2026-12');
 assert.equal(isObservationOutdated('2026-12',new Date('2027-01-01T00:00:00Z')),false);
});
