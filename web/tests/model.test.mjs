import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {withChanges,periodRows,largestDrop,csvText} from '../model.mjs';
test('month changes require adjacent months and a positive baseline',()=>{
 const rows=withChanges([{month:'2024-01',avg:100},{month:'2024-02',avg:60},{month:'2024-04',avg:0},{month:'2024-05',avg:20}]);
 assert.equal(rows[0].change,null);assert.equal(rows[1].change,-40);assert.equal(rows[2].change,null);assert.equal(rows[3].change,null);
 assert.equal(largestDrop(rows).month,'2024-02');
 assert.equal(largestDrop([{change:0},{change:20}]),null);
});
test('calendar range keeps original prior-month baseline and never fills missing months',()=>{
 const rows=withChanges([{month:'2023-12',avg:100},{month:'2024-01',avg:50},{month:'2024-12',avg:90}]);
 assert.deepEqual(periodRows(rows,12).map(r=>r.month),['2024-01','2024-12']);
 assert.equal(periodRows(rows,12)[0].change,-50);assert.equal(periodRows(rows,0).length,3);
});
test('published snapshot contains only intended public fields and valid observations',()=>{
 const snapshot=JSON.parse(readFileSync(new URL('../snapshot.json',import.meta.url),'utf8'));
 assert.equal(snapshot.schemaVersion,2);assert.equal(snapshot.games.length,1000);
 const batches=new Map([...new Set(snapshot.games.map(g=>g.part))].map(part=>[part,JSON.parse(readFileSync(new URL('../'+part,import.meta.url),'utf8'))]));
 assert.equal([...batches.values()].flat().reduce((n,g)=>n+g.monthly.length,0),snapshot.totalMonths);
 assert.ok(snapshot.totalMonths>=56096);
 for(const entry of snapshot.games){
  const g=batches.get(entry.part).find(g=>g.id===entry.id);assert.ok(g);
  assert.equal(entry.latestAvg,g.monthly.at(-1).avg);assert.equal(entry.lastMonth,g.monthly.at(-1).month);
  assert.equal(entry.months,g.monthly.length);assert.ok(!('news' in g));
  assert.ok(g.monthly.length>=1);
  assert.equal(new Set(g.monthly.map(r=>r.month)).size,g.monthly.length);
  assert.deepEqual(g.monthly.map(r=>r.month),g.monthly.map(r=>r.month).sort());
  for(const r of g.monthly){assert.ok(Number.isFinite(r.avg)&&r.avg>=0);assert.ok(Number.isFinite(r.peak)&&r.peak>=0);}
  const rows=withChanges(g.monthly);const drop=largestDrop(rows);
  assert.ok(!drop||drop.change>=-100);assert.ok(csvText(rows).startsWith('\uFEFFmonth,'));
 }
});
