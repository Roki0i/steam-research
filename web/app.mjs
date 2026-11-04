import {withChanges, periodRows, largestDrop, nearbyNews, csvText, monthIndex} from './model.mjs';
import {importMonthly, importNews} from './csv.mjs';
const $ = id => document.getElementById(id);
const number = n => n === null ? '—' : new Intl.NumberFormat('ja-JP', {maximumFractionDigits:0}).format(n);
const percent = n => n === null ? '計算なし' : `${n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toFixed(1)}%`;
const monthLabel = m => `${m.slice(0,4)}年${Number(m.slice(5,7))}月`;
const shortMonth = m => `${m.slice(0,4)}/${m.slice(5,7)}`;
const colors = [['#e2ebff','#b4c6ed'],['#f4e6e0','#d7b4a4'],['#f0e8d6','#d8bf85'],['#e4e1f9','#bcb0e1'],['#e5efe0','#b2cba1'],['#e1ecee','#9fc5cd']];
const marks = {1091500:'C',2054970:'D',2358720:'W',1272080:'P',2198150:'T',646910:'2'};
let sample, data, game, rows = [], selected, period = 0, newsLimit = 5, local = false, localSummary = '', monthlyName = '', newsName = '', toastTimer;
const sourceInfo = {newsOnly:false};
function el(tag, text, cls) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(cls)node.className=cls; return node; }
function notify(message) { clearTimeout(toastTimer); $('toast').textContent=message;$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,4200); }
function dialog(id) { $(id).showModal(); }
function syncUrl() {
  const url=new URL(location.href);
  if(local) { for(const key of ['game','period','month','window'])url.searchParams.delete(key); }
  else { url.searchParams.set('game',game.id);url.searchParams.set('period',period);url.searchParams.set('month',selected);url.searchParams.set('window',$('window').value); }
  history.replaceState(null,'',url);
}
function renderDataset() {
  $('dataset-title').textContent=local?'自分のCSV':'研究サンプル';
  $('dataset-detail').textContent=local?`${data.games.length}タイトル / このタブ内だけで使用`:`${sample.games.length}タイトル / 2026-08-25収集`;
  $('footer-data').textContent=local?'自分のCSV · 再読み込みでサンプルに戻ります':'研究サンプル · 2026-08-25収集 · 自動更新なし';
  $('reset-data').hidden=!local;$('footer-reset').hidden=!local;
  $('share').disabled=local;
  $('share').title=local?'CSVの内容は共有リンクに含められません。':'';
  $('welcome').hidden=local;
  const categories=[...new Set(data.games.map(g=>g.category))].sort();
  $('genre').replaceChildren(el('option','すべてのジャンル'));
  $('genre').firstChild.value='';
  for(const category of categories){const option=el('option',category);option.value=category;$('genre').append(option);}
  $('game-count').textContent=data.games.length;
}
function renderGames() {
  const query=$('search').value.trim().toLocaleLowerCase(), category=$('genre').value;
  const filtered=data.games.filter(g=>(!category||g.category===category)&&`${g.name} ${g.id}`.toLocaleLowerCase().includes(query));
  $('list-count').textContent=`${filtered.length} / ${data.games.length} タイトル`;
  $('games').replaceChildren();
  for(const g of filtered){
    const button=el('button',undefined,'game-button');button.type='button';button.setAttribute('aria-pressed',String(g.id===game.id));
    const tile=el('span',marks[g.id]||g.name.slice(0,1),'game-mark');tile.setAttribute('aria-hidden','true');
    const color=colors[data.games.indexOf(g)%colors.length];tile.style.setProperty('--tile-a',color[0]);tile.style.setProperty('--tile-b',color[1]);
    const label=el('span');label.append(el('b',g.name),el('small',g.category));button.append(tile,label);
    if(g.id===game.id){const check=el('span','✓','selected-check');check.setAttribute('aria-hidden','true');button.append(check);}
    button.onclick=()=>selectGame(g);$('games').append(button);
  }
  $('clear-search').hidden=!query&&!category;
  if(!filtered.length)$('games').append(el('p','一致するゲームがありません。検索語やジャンルを変えてください。','no-results'));
}
function selectGame(g, requestedMonth) {
  game=g;rows=periodRows(withChanges(g.monthly),period);
  const drop=largestDrop(rows);
  selected=rows.some(r=>r.month===requestedMonth)?requestedMonth:(drop?.month??rows.at(-1).month);newsLimit=5;
  $('game-title').textContent=g.name;$('category').textContent=g.category;$('appid').textContent=`App ID: ${g.id}`;
  $('observation').textContent=`${monthLabel(rows[0].month)}〜${monthLabel(rows.at(-1).month)} · ${rows.length}か月分${local?' · 自分のCSV':''}`;
  $('source').href=g.source;
  document.querySelectorAll('[data-period]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.period)===period)));
  const peak=rows.reduce((a,b)=>b.avg>a.avg?b:a);
  $('peak').textContent=number(peak.avg);$('peak-month').textContent=monthLabel(peak.month);
  $('jump').disabled=!drop;
  $('drop-title').textContent=drop?`最も減った月：${monthLabel(drop.month)}`:'この期間に減少した月はありません';
  $('drop-detail').textContent=drop?`前月比 ${percent(drop.change)} · 表示期間内で比較`:'比較できる前月がない場合も含みます';
  $('month').replaceChildren(...rows.map(r=>{const option=el('option',monthLabel(r.month));option.value=r.month;return option;}));
  $('month-slider').max=rows.length-1;$('month-slider').disabled=rows.length===1;
  $('range-start').textContent=shortMonth(rows[0].month);$('range-end').textContent=shortMonth(rows.at(-1).month);
  const prior=withChanges(g.monthly).find(r=>r.month===rows[0].month);
  $('baseline-note').textContent=prior.change!==null?'前月比は表示範囲の直前月とも比較します。人数は平均同時接続数で、利用者数や個人の離脱率ではありません。':'人数は平均同時接続数です。前月が未収集・0人の場合は、前月比を計算しません。';
  renderGames();renderMonth();
}
function changeMonth(month) { selected=month;newsLimit=5;renderMonth(); }
function renderMonth() {
  const index=rows.findIndex(r=>r.month===selected), row=rows[index];
  $('month').value=selected;$('month-slider').value=index;$('month-slider').setAttribute('aria-valuetext',`${monthLabel(selected)}、平均${number(row.avg)}人、前月比${percent(row.change)}`);
  $('previous').disabled=index===0;$('next').disabled=index===rows.length-1;$('month-position').textContent=`${index+1} / ${rows.length}か月`;
  $('stat-date').textContent=`${monthLabel(selected)}の平均`;$('selected-avg').textContent=number(row.avg);
  $('selected-change').textContent=percent(row.change);$('selected-change').className=row.change===null?'':row.change<0?'negative':row.change>0?'positive':'';
  const previous=game.monthly[game.monthly.findIndex(r=>r.month===selected)-1];
  $('selected-diff').textContent=row.change===null?'連続する前月の値が必要です':`${row.avg-previous.avg>0?'+':row.avg-previous.avg<0?'−':''}${number(Math.abs(row.avg-previous.avg))}人 / 前月との比較`;
  $('selected-heading').textContent=monthLabel(selected);
  renderChart();renderNews();renderTable();syncUrl();
}
function svgNode(tag, attrs={}, text) { const node=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v);if(text!==undefined)node.textContent=text;return node; }
function axisNumber(value){if(value>=100000)return `${Number((value/10000).toFixed(0))}万`;if(value>=10000)return `${Number((value/10000).toFixed(1))}万`;return number(value);}
function renderChart(){
  if(!rows.length||$('explorer').hidden)return;
  const width=Math.max($('chart').clientWidth,250),height=$('chart').clientHeight,left=width<400?40:49,right=12,top=22,bottom=30,w=width-left-right,h=height-top-bottom;
  const first=monthIndex(rows[0].month),span=monthIndex(rows.at(-1).month)-first;
  const x=i=>left+(span?(monthIndex(rows[i].month)-first)/span*w:w/2);
  const largest=Math.max(...rows.map(r=>r.avg),1);const power=10**Math.floor(Math.log10(largest));const max=Math.ceil(largest/power*1.08)*power;
  const y=value=>top+h-value/max*h;
  const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-labelledby':'chart-title chart-description'});
  svg.append(svgNode('title',{id:'chart-title'},`${game.name}の平均同時接続数`),svgNode('desc',{id:'chart-description'},`${rows.length}か月の推移。${monthLabel(selected)}を選択中。下の月選択やスライダーでも操作できます。`));
  const defs=svgNode('defs'),gradient=svgNode('linearGradient',{id:'chart-area',x1:0,x2:0,y1:0,y2:1});gradient.append(svgNode('stop',{offset:'0%','stop-color':'#5978ed','stop-opacity':'.18'}),svgNode('stop',{offset:'100%','stop-color':'#5978ed','stop-opacity':'.01'}));defs.append(gradient);svg.append(defs);
  for(let i=0;i<=4;i++){const value=max*i/4,py=y(value);svg.append(svgNode('line',{x1:left,x2:width-right,y1:py,y2:py,stroke:'#e8edf6','stroke-dasharray':i?'3 4':'0'}),svgNode('text',{x:left-9,y:py+4,'text-anchor':'end'},axisNumber(value)));}
  const paths=[];let current=[];
  rows.forEach((r,i)=>{if(i&&monthIndex(r.month)-monthIndex(rows[i-1].month)!==1){if(current.length)paths.push(current);current=[];}current.push([x(i),y(r.avg)]);});if(current.length)paths.push(current);
  for(const points of paths){const line=points.map((p,i)=>`${i?'L':'M'}${p.join(',')}`).join(' ');svg.append(svgNode('path',{d:`${line} L${points.at(-1)[0]},${top+h} L${points[0][0]},${top+h} Z`,fill:'url(#chart-area)'}),svgNode('path',{d:line,fill:'none',stroke:'#5272ed','stroke-width':2.5,'stroke-linecap':'round','stroke-linejoin':'round'}));}
  const chosen=rows.findIndex(r=>r.month===selected);svg.append(svgNode('line',{x1:x(chosen),x2:x(chosen),y1:top,y2:top+h,stroke:'#98aaf5','stroke-dasharray':'4 4'}));
  for(let i=0;i<rows.length;i++)if(rows.length<=36||i===chosen)svg.append(svgNode('circle',{cx:x(i),cy:y(rows[i].avg),r:i===chosen?5:2.2,fill:i===chosen?'#4263eb':'#a8b9fa',stroke:'#fff','stroke-width':i===chosen?2:1}));
  const tickCount=width<400?3:4;for(const i of [...new Set(Array.from({length:tickCount},(_,n)=>Math.round((rows.length-1)*n/(tickCount-1))))])svg.append(svgNode('text',{x:x(i),y:height-6,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle'},shortMonth(rows[i].month)));
  $('chart').replaceChildren(svg);
  const nearest=event=>{const bounds=$('chart').getBoundingClientRect(),value=event.clientX-bounds.left;return rows.reduce((best,r,i)=>Math.abs(x(i)-value)<Math.abs(x(best)-value)?i:best,0);};
  svg.onpointermove=event=>{const r=rows[nearest(event)];$('chart-hover').textContent=`${shortMonth(r.month)} · ${number(r.avg)}人`;};
  svg.onpointerleave=()=>$('chart-hover').textContent='グラフを押して月を選択';
  svg.onclick=event=>changeMonth(rows[nearest(event)].month);
}
function official(n){return n.url.includes('/steam_community_announcements/')||/^https:\/\/steamcommunity\.com\//.test(n.url);}
function renderNews(){
  const window=Number($('window').value),news=nearbyNews(game.news,selected,window);
  $('news-count').textContent=`${news.length}件`;
  const start=monthIndex(selected)-window,end=monthIndex(selected)+window;
  const label=i=>`${Math.floor(i/12)}年${i%12+1}月`;
  $('news-window').textContent=window?`${label(start)}〜${label(end)}`:`${monthLabel(selected)}の記事`;
  $('news').replaceChildren();
  if(!news.length){const empty=el('div',undefined,'empty');empty.append(el('b',game.news.length?'この範囲に保存済み記事はありません':'このゲームのニュースは未読込です'),el('p',game.news.length?'時期を変えるか、記事のある月から調べてみましょう。':'ニュースCSVを追加すると、人数の変化と記事を照合できます。'));
    if(game.news.length){const button=el('button','記事がある月へ移動','button secondary');button.onclick=goToNews;empty.append(button);}
    else if(local){const button=el('button','ニュースCSVを追加する','button secondary');button.onclick=()=>{sourceInfo.newsOnly=true;openImport();};empty.append(button);}
    $('news').append(empty);
  }
  for(const n of news.slice(0,newsLimit)){const article=el('article',undefined,'news-item'),meta=el('div',undefined,'news-date'),time=el('time',n.date);time.dateTime=n.date;meta.append(time,el('span',official(n)?'運営のお知らせ':'記事','article-type'));const link=el('a',n.title);link.href=n.url;link.target='_blank';link.rel='noreferrer';article.append(meta,link);$('news').append(article);}
  if(news.length>newsLimit){const more=el('button',`さらに表示（残り${news.length-newsLimit}件）`,'button secondary more');more.onclick=()=>{newsLimit+=10;renderNews();};$('news').append(more);}
  const dates=game.news.map(n=>n.date);
  $('news-coverage').textContent=dates.length?`保存済み記事：${dates[0]}〜${dates.at(-1)}（${dates.length}件）。記事は原文です。全ニュースを網羅していません。`:'記事がないことは、出来事がなかったことを意味しません。';
}
function goToNews(){
  const all=withChanges(game.monthly),matches=all.filter(r=>nearbyNews(game.news,r.month,0).length);
  if(!matches.length){notify('プレイヤー数の観測期間と記事の期間が重なっていません。');return;}
  const nearest=matches.reduce((best,r)=>Math.abs(monthIndex(r.month)-monthIndex(selected))<Math.abs(monthIndex(best.month)-monthIndex(selected))?r:best);
  if(!rows.some(r=>r.month===nearest.month))period=0;
  selectGame(game,nearest.month);notify(`${monthLabel(nearest.month)}の記事を表示しました。`);
}
function renderTable(){
  $('table-count').textContent=`${rows.length}か月分 · 元の値から画面表示は小数点以下を四捨五入`;
  $('rows').replaceChildren(...[...rows].reverse().map(r=>{const tr=el('tr');tr.dataset.selected=String(r.month===selected);const first=el('td'),button=el('button',shortMonth(r.month));button.setAttribute('aria-label',`${monthLabel(r.month)}を調べる`);button.onclick=()=>changeMonth(r.month);first.append(button);tr.append(first);for(const value of [number(r.avg),number(r.peak),percent(r.change)])tr.append(el('td',value));return tr;}));
}
function download(text,name){const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})),a=el('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function dataDialog(){
  const content=$('data-content');content.replaceChildren();
  const entries=local?[
    ['読み込んだデータ',`${monthlyName}${newsName?` / ${newsName}`:''}。${localSummary}`],
    ['保存と共有','読み込んだファイルは、このタブのメモリー内だけで処理します。サーバーへの送信・ブラウザへの永続保存は行いません。再読み込みすると研究サンプルに戻ります。共有リンクにCSVの内容は含まれません。'],
    ['出典の確認','CSVを作成した方が、収集日・取得元・対象の選び方を確認してください。「元データ」はappidに対応するSteamChartsページを開きます。']
  ]:[
    ['研究用の実データ','既存の研究CSVから選んだ6タイトル、276か月分の平均・最大同時接続数と589件のニュース情報です。Steam全体を代表する標本ではありません。'],
    ['プレイヤー数','出典：SteamCharts。2026-08-25に収集した保存値です。観測期間はゲームごとに異なります。現在の人数は表示していません。'],
    ['ニュース','出典：Steamニュース経由の公開記事。研究時に収集した一部で、全ニュースを網羅しません。表示するのは原文タイトル・日付・記事URLです。'],
    ['計算方法','前月比＝（当月平均÷前月平均−1）×100。連続する暦月があり、前月平均が0より大きい場合のみ計算します。表示期間の先頭月も、元データに直前月があれば比較します。'],
    ['研究との違い','画面の「最も減った月」は表示期間内で探索します。研究スクリプトの「ピーク後3〜12か月」とは別の条件です。']
  ];
  for(const [heading,body] of entries)content.append(el('h3',heading),el('p',body));
  content.append(el('h3','読み方の注意'),el('p','平均同時接続数は月間の利用者数・個人単位の離脱率ではありません。ニュースの時期が重なるだけでは、原因と判断できません。'));
  dialog('data-dialog');
}
function example(){
  if(local){notify('自分のCSVを表示中です。研究サンプルに戻すと例を開けます。');return;}
  $('search').value='';$('genre').value='';period=0;selectGame(data.games.find(g=>g.id===2054970)??data.games[0],'2024-05');$('window').value='1';renderNews();syncUrl();
  $('guide-dialog').close();$('explorer').scrollIntoView({behavior:'smooth',block:'start'});notify('例：2024年5月の減少と、前後のニュースを見てみましょう。');
}
function openImport(){
  $('import-error').hidden=true;
  $('monthly-file').required=!sourceInfo.newsOnly;
  $('monthly-badge').textContent=sourceInfo.newsOnly?'読込済み':'必須';$('monthly-badge').className=sourceInfo.newsOnly?'optional':'';
  $('news-badge').textContent=sourceInfo.newsOnly?'必須':'任意';$('news-badge').className=sourceInfo.newsOnly?'':'optional';
  $('import-title').textContent=sourceInfo.newsOnly?'ニュースCSVを追加する':'自分のCSVで分析する';
  $('import-submit').textContent=sourceInfo.newsOnly?'ニュースを追加する →':'読み込んで分析する →';
  if(sourceInfo.newsOnly)notify('プレイヤー数は選び直さず、ニュースCSVだけ追加できます。');
  dialog('import-dialog');
}
async function readFile(file){if(file.size>20*1024*1024)throw new Error(`${file.name}は20MBを超えています。`);return file.text();}
async function submitImport(event){
  event.preventDefault();$('import-error').hidden=true;const button=$('import-submit');button.disabled=true;button.textContent='読み込み中…';
  try{
    const monthlyFile=$('monthly-file').files[0],newsFile=$('news-file').files[0];
    if(sourceInfo.newsOnly&&!newsFile)throw new Error('ニュースCSVを選んでください。');
    if(!monthlyFile&&!sourceInfo.newsOnly)throw new Error('プレイヤー数のCSVを選んでください。');
    let result=monthlyFile?importMonthly(await readFile(monthlyFile)):{games:data.games,duplicateCount:0};
    let newsResult=newsFile?importNews(await readFile(newsFile),result.games):null;
    if(newsResult&&newsResult.count===0)throw new Error('プレイヤー数とappidが一致するニュースがありません。ファイルとappidを確認してください。');
    const summary=[`${result.games.length}タイトル、${result.games.reduce((n,g)=>n+g.monthly.length,0)}か月分`,result.duplicateCount?`同値の重複${result.duplicateCount}行を統合`:null,newsResult?`ニュース${newsResult.count}件`:null,newsResult?.unmatched?`対象外appidのニュース${newsResult.unmatched}行を除外`:null].filter(Boolean).join(' / ');
    const previousId=game.id,previousMonth=selected;
    data={schemaVersion:1,games:newsResult?newsResult.games:result.games};local=true;localSummary=summary;
    if(monthlyFile)monthlyName=monthlyFile.name;
    if(monthlyFile&&!newsFile)newsName='';if(newsFile)newsName=newsFile.name;
    sourceInfo.newsOnly=false;$('search').value='';period=0;renderDataset();selectGame(data.games.find(g=>g.id===previousId)??data.games[0],previousMonth);
    $('import-dialog').close();$('import-form').reset();notify(`${summary}を読み込みました。`);
  }catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false;}
  finally{button.disabled=false;button.textContent=sourceInfo.newsOnly?'ニュースを追加する →':'読み込んで分析する →';}
}
function resetData(){data=sample;local=false;monthlyName='';newsName='';$('search').value='';period=0;renderDataset();selectGame(data.games[0]);notify('研究サンプルに戻しました。');}
function sampleCSV(){
  const lines=sample.games.map(g=>csvText(g.monthly,g).replace(/^\uFEFF/,''));
  download('\uFEFF'+lines.map((s,i)=>i?s.split('\r\n').slice(1).join('\r\n'):s).join('\r\n'),'steam-research-sample.csv');
}
async function start(){
  try{
    const response=await fetch('./snapshot.json');if(!response.ok)throw new Error('Snapshot unavailable');
    sample=await response.json();if(sample.schemaVersion!==1||!sample.games?.length)throw new Error('Invalid snapshot');data=sample;
    const params=new URLSearchParams(location.search);if(['0','12','36'].includes(params.get('period')))period=Number(params.get('period'));if(['0','1','2'].includes(params.get('window')))$('window').value=params.get('window');
    $('explorer').hidden=false;$('status').hidden=true;renderDataset();selectGame(data.games.find(g=>String(g.id)===params.get('game'))??data.games[0],params.get('month'));
    $('search').oninput=renderGames;$('genre').onchange=renderGames;
    $('clear-search').onclick=()=>{$('search').value='';$('genre').value='';renderGames();};
    document.querySelectorAll('[data-period]').forEach(button=>button.onclick=()=>{period=Number(button.dataset.period);selectGame(game,selected);});
    $('month').onchange=()=>changeMonth($('month').value);$('month-slider').oninput=()=>changeMonth(rows[Number($('month-slider').value)].month);
    $('previous').onclick=()=>changeMonth(rows[rows.findIndex(r=>r.month===selected)-1].month);$('next').onclick=()=>changeMonth(rows[rows.findIndex(r=>r.month===selected)+1].month);
    $('jump').onclick=()=>{const drop=largestDrop(rows);if(drop)changeMonth(drop.month);};
    $('window').onchange=()=>{newsLimit=5;renderNews();syncUrl();};
    $('share').onclick=async()=>{try{await navigator.clipboard.writeText(location.href);notify('このゲーム・月を開くリンクをコピーしました。');}catch{notify('アドレスバーのURLをコピーして共有してください。');}};
    $('download').onclick=()=>download(csvText(rows,game),`steam-${game.id}-${rows[0].month}-${rows.at(-1).month}.csv`);
    $('open-guide').onclick=$('footer-guide').onclick=()=>dialog('guide-dialog');
    document.querySelectorAll('[data-help]').forEach(b=>b.onclick=()=>dialog('guide-dialog'));
    $('open-import').onclick=()=>{sourceInfo.newsOnly=false;openImport();};$('import-form').onsubmit=submitImport;
    $('try-example').onclick=$('guide-example').onclick=example;
    $('dismiss-welcome').onclick=()=>$('welcome').hidden=true;
    $('dataset-info').onclick=$('footer-data-info').onclick=dataDialog;$('reset-data').onclick=$('footer-reset').onclick=resetData;
    $('sample-csv').onclick=sampleCSV;
    document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
    for(const d of document.querySelectorAll('dialog'))d.addEventListener('click',event=>{if(event.target===d){const r=d.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)d.close();}});
    document.querySelectorAll('[data-boot]').forEach(control=>control.disabled=false);$('main').setAttribute('aria-busy','false');
    let frame;new ResizeObserver(()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(renderChart);}).observe($('chart'));
  }catch(error){$('explorer').hidden=true;$('status').hidden=false;$('status').replaceChildren(el('p','データを読み込めませんでした。ページを再読み込みしてください。'));const retry=el('button','再読み込み','button secondary');retry.onclick=()=>location.reload();$('status').append(retry);console.error(error);}
}
start();
