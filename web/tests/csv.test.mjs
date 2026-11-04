import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseCSV,importMonthly,importNews,normalizeMonth} from '../csv.mjs';
import {csvText,withChanges} from '../model.mjs';
import {readFileSync} from 'node:fs';
const header='appid,name,month,avg_players,peak_players';
const valid=header+'\n730,Test,2024-01,100,200\n730,Test,2024-02,80,150';
test('CSV supports BOM, quoted commas, escaped quotes, multiline fields and CRLF',()=>{
 const records=parseCSV('\uFEFFname,title\r\n"A,B","A ""quote""\nand line"\r\n');
 assert.deepEqual(records,[{name:'A,B',title:'A "quote"\nand line'}]);
});
test('malformed quotes, missing columns and row widths produce actionable errors',()=>{
 assert.throws(()=>parseCSV('a,b\n"unfinished,x'),/閉じ/);
 assert.throws(()=>parseCSV('a,b\n1'),/2行目/);
 assert.throws(()=>parseCSV('a,a\n1,2'),/重複/);
 assert.throws(()=>importMonthly('name,month\nTest,2024-01'),/appid/);
 assert.throws(()=>importMonthly(header+'\n1,Test,2024-01,NaN,100'),/2行目.*avg_players/);
});
test('monthly import normalizes real collector formats and optional fields',()=>{
 assert.equal(normalizeMonth('July 2012'),'2012-07');assert.equal(normalizeMonth('2024/5'),'2024-05');
 assert.throws(()=>normalizeMonth('2024-13'),/年月/);
 const result=importMonthly('appid,name,month_date,month,avg_players\n1,Test,2024-02-01,February 2024,50\n1,Test,2024-01-01,January 2024,100');
 assert.equal(result.games[0].monthly[0].month,'2024-01');assert.equal(result.games[0].monthly[0].peak,null);
 assert.equal(withChanges(result.games[0].monthly)[1].change,-50);
});
test('identical duplicates collapse while conflicting observations fail atomically',()=>{
 assert.equal(importMonthly(valid+'\n730,Test,2024-02,80,150').duplicateCount,1);
 assert.throws(()=>importMonthly(valid+'\n730,Test,2024-02,70,150'),/4行目.*重複/);
 assert.throws(()=>importMonthly(header+'\n1,Test,2024-01,-1,100'),/0以上/);
 assert.throws(()=>importMonthly(header+'\n1,Test,2024-01,100,50'),/最大/);
 assert.throws(()=>importMonthly(valid+'\n730,Other,2024-03,80,150'),/異なるゲーム名/);
});
test('news import joins by appid, counts unmatched rows, deduplicates and allows only HTTP(S)',()=>{
 const games=importMonthly(valid).games;
 const news='appid,title,url,news_date\n730,Patch,https://example.org/patch,2024-02-05\n2,Other,https://example.org/other,2024-01-01\n730,Patch,https://example.org/patch,2024-02-05';
 const result=importNews(news,games);assert.equal(result.count,1);assert.equal(result.unmatched,1);assert.equal(games[0].news.length,0);
 assert.equal(importNews('appid,title,url,news_date\n730,Old,http://example.org/old,2024-01-01',games).count,1);
 assert.throws(()=>importNews('appid,title,url,date\n730,Patch,javascript:alert(1),1704067200',games),/https/);
 assert.equal(importNews('appid,title,url,date\n730,Patch,https://example.org,1704067200',games).games[0].news[0].date,'2024-01-01');
 assert.throws(()=>importNews('appid,title,url,news_date\n730,Patch,https://example.org,2024-02-30',games),/日付/);
});
test('downloaded research data round-trips with decimals and quoted titles',()=>{
 const snapshot=JSON.parse(readFileSync(new URL('../snapshot.json',import.meta.url),'utf8'));
 for(const game of snapshot.games){const imported=importMonthly(csvText(withChanges(game.monthly),game)).games[0];assert.deepEqual(imported.monthly,game.monthly);assert.equal(imported.name,game.name);}
 const csv=csvText([{month:'2024-01',avg:1,peak:null}],{id:1,name:'=SUM(A1)',category:'Test'});
 assert.ok(csv.includes("\"'=SUM(A1)\""));
});
