import {withChanges, periodRows, largestDrop, nearbyNews, csvText} from './model.mjs';
const $ = id => document.getElementById(id);
const number = n => new Intl.NumberFormat('ja-JP', {maximumFractionDigits: 0}).format(n);
const percent = n => n === null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(1)}%`;
const monthLabel = m => `${m.slice(0,4)}年${Number(m.slice(5,7))}月`;
const marks = ['C', 'D', 'W', 'P', 'T', '2'];
let data, game, rows, selected, newsLimit = 5;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function syncUrl() {
  const url = new URL(location.href);
  url.searchParams.set('game', game.id);
  url.searchParams.set('period', $('period').value);
  url.searchParams.set('month', selected);
  url.searchParams.set('window', $('window').value);
  history.replaceState(null, '', url);
}
function renderGames() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const filtered = data.games.filter(g => g.name.toLocaleLowerCase().includes(query));
  $('game-count').textContent = data.games.length;
  $('games').replaceChildren();
  for (const g of filtered) {
    const button = element('button', undefined, 'game-button');
    button.type = 'button';
    button.setAttribute('aria-pressed', String(g.id === game.id));
    const mark = element('span', marks[data.games.indexOf(g)], 'game-mark');
    mark.setAttribute('aria-hidden', 'true');
    const label = element('span');
    label.append(element('b', g.name), element('small', g.category));
    button.append(mark, label);
    button.onclick = () => selectGame(g);
    $('games').append(button);
  }
  if (!filtered.length) $('games').append(element('p', '該当するゲームがありません。検索語を変えてください。', 'empty'));
}
function selectGame(g, requestedMonth) {
  game = g;
  rows = periodRows(withChanges(g.monthly), Number($('period').value));
  const drop = largestDrop(rows);
  selected = rows.some(r => r.month === requestedMonth) ? requestedMonth : (drop?.month ?? rows.at(-1).month);
  newsLimit = 5;
  $('category').textContent = `${g.category} / APP ${g.id}`;
  $('game-title').textContent = g.name;
  $('observation').textContent = `${monthLabel(rows[0].month)} — ${monthLabel(rows.at(-1).month)} · ${rows.length}か月の観測`;
  $('source').href = g.source;
  const latest = rows.at(-1);
  const peak = rows.reduce((a,b) => b.avg > a.avg ? b : a);
  $('latest').textContent = number(latest.avg);
  $('latest-month').textContent = `${monthLabel(latest.month)} / 前月比 ${percent(latest.change)}`;
  $('drop').textContent = drop ? percent(drop.change) : '—';
  $('drop-month').textContent = drop ? `${monthLabel(drop.month)} / 前月との比較` : '計算できる減少月なし';
  $('peak').textContent = number(peak.avg);
  $('peak-month').textContent = `${monthLabel(peak.month)} / 期間内最大`;
  $('jump').disabled = !drop;
  $('month').replaceChildren(...rows.map(r => {
    const option = element('option', monthLabel(r.month)); option.value = r.month; return option;
  }));
  renderGames();
  renderMonth();
}
function renderMonth() {
  $('month').value = selected;
  const row = rows.find(r => r.month === selected);
  $('selected-heading').textContent = `${monthLabel(selected)}の観測`;
  $('selected-detail').textContent = `平均 ${number(row.avg)}人 / 前月比 ${percent(row.change)}`;
  renderChart(); renderNews(); renderTable(); syncUrl();
}
function svgNode(tag, attrs, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderChart() {
  const width = 800, height = 264, left = 65, top = 24, right = 17, bottom = 34;
  const w = width - left - right, h = height - top - bottom;
  const max = Math.max(...rows.map(r => r.avg), 1) * 1.12;
  const x = i => left + (rows.length === 1 ? w/2 : i / (rows.length - 1) * w);
  const y = value => top + h - value / max * h;
  const svg = svgNode('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-labelledby': 'chart-title chart-description'});
  svg.append(svgNode('title', {id: 'chart-title'}, `${game.name}の月間平均同時接続数`));
  svg.append(svgNode('desc', {id: 'chart-description'}, `${rows.length}か月の推移。${monthLabel(selected)}を選択中。下の月の選択欄と月次データ表でも確認できます。`));
  const defs = svgNode('defs', {}), gradient = svgNode('linearGradient', {id:'area',x1:'0',x2:'0',y1:'0',y2:'1'});
  gradient.append(svgNode('stop', {offset:'0%','stop-color':'#81a55e','stop-opacity':'.24'}),svgNode('stop', {offset:'100%','stop-color':'#81a55e','stop-opacity':'.015'}));
  defs.append(gradient); svg.append(defs);
  for (let i = 0; i <= 4; i++) {
    const value = max * i / 4, py = y(value);
    svg.append(svgNode('line', {x1:left,x2:width-right,y1:py,y2:py,stroke:'#e5eade','stroke-dasharray':i ? '3 4' : '0'}));
    svg.append(svgNode('text', {x:left-12,y:py+4,'text-anchor':'end'}, number(value)));
  }
  const paths = []; let current = [];
  rows.forEach((r,i) => {
    // Never draw a continuous line over a missing calendar month.
    if (i && r.change === null) { if (current.length) paths.push(current); current = []; }
    current.push([x(i),y(r.avg)]);
  });
  if(current.length) paths.push(current);
  for (const points of paths) {
    const line = points.map((p,i) => `${i ? 'L':'M'}${p[0]},${p[1]}`).join(' ');
    svg.append(svgNode('path',{d:`${line} L${points.at(-1)[0]},${top+h} L${points[0][0]},${top+h} Z`,fill:'url(#area)'}));
    svg.append(svgNode('path',{d:line,fill:'none',stroke:'#48734a','stroke-width':'2.3','stroke-linejoin':'round'}));
  }
  const chosen = rows.findIndex(r => r.month === selected);
  svg.append(svgNode('line',{x1:x(chosen),x2:x(chosen),y1:top,y2:top+h,stroke:'#a84732','stroke-dasharray':'4 4',opacity:'.6'}));
  const ticks = [...new Set([0,Math.round((rows.length-1)/3),Math.round((rows.length-1)*2/3),rows.length-1])];
  for (const i of ticks) svg.append(svgNode('text',{x:x(i),y:height-9,'text-anchor':i===0?'start':i===rows.length-1?'end':'middle'},rows[i].month.replace('-','.')));
  rows.forEach((r,i) => {
    const point = svgNode('circle',{cx:x(i),cy:y(r.avg),r:r.month===selected?5:Math.max(5,Math.min(10,w/rows.length/2)),class:'plot-point'});
    if(r.month===selected){point.setAttribute('style','fill:#a84732;stroke:white;stroke-width:2');}
    point.append(svgNode('title',{},`${monthLabel(r.month)} / ${number(r.avg)}人 / ${percent(r.change)}`));
    point.addEventListener('click',()=>{selected=r.month;newsLimit=5;renderMonth();});
    svg.append(point);
  });
  $('chart').replaceChildren(svg);
}
function renderNews() {
  const window = Number($('window').value);
  const news = nearbyNews(game.news, selected, window);
  $('news').replaceChildren();
  if (!news.length) {
    $('news').append(element('div', 'この範囲に保存済みの記事はありません。範囲を広げるか、別の月を選んでください。未収集の記事や出来事が存在する可能性があります。', 'empty'));
  }
  for(const n of news.slice(0, newsLimit)) {
    const article = element('article',undefined,'news-item');
    const time = element('time',n.date); time.dateTime=n.date;
    const link = element('a',n.title); link.href=n.url;link.target='_blank';link.rel='noreferrer';
    article.append(time,link,element('span','↗'));
    $('news').append(article);
  }
  if(news.length>newsLimit){
    const more=element('button',`残り${news.length-newsLimit}件を表示`,'small-button more');
    more.onclick=()=>{newsLimit=news.length;renderNews();};$('news').append(more);
  }
  const dates=game.news.map(n=>n.date);
  $('news-coverage').textContent=`範囲内 ${news.length}件 / このゲームの保存済み記事 ${game.news.length}件${dates.length ? `（${dates[0]} — ${dates.at(-1)}）`:''}。研究用に収集した一部であり、全ニュースを網羅していません。`;
}
function renderTable() {
  $('rows').replaceChildren(...[...rows].reverse().map(r=>{
    const tr=element('tr');tr.dataset.selected=String(r.month===selected);
    for(const value of [r.month,number(r.avg),number(r.peak),percent(r.change)])tr.append(element('td',value));
    return tr;
  }));
}
async function start() {
  try {
    const response=await fetch('./snapshot.json');
    if(!response.ok)throw new Error('snapshot unavailable');
    data=await response.json();
    if(data.schemaVersion!==1||!data.games?.length)throw new Error('invalid snapshot');
    const params=new URLSearchParams(location.search);
    if(['0','12','36'].includes(params.get('period')))$('period').value=params.get('period');
    if(['0','1','2'].includes(params.get('window')))$('window').value=params.get('window');
    $('explorer').hidden=false;
    selectGame(data.games.find(g=>String(g.id)===params.get('game'))??data.games[0],params.get('month'));
    const collected=[...new Set(data.games.flatMap(g=>g.collected))].sort();
    $('status').textContent=`${data.games.length}タイトルの実データ · プレイヤー数収集 ${collected[0]} — ${collected.at(-1)} · 画面作成 ${data.preparedOn}`;
    $('provenance').textContent=`出典：SteamChartsおよびSteamニュース。プレイヤー数の収集日は${collected[0]}〜${collected.at(-1)}。収集時点で保存された月次値を表示しており、現在の値とは異なる場合があります。`;
    $('search').addEventListener('input',renderGames);
    $('period').onchange=()=>selectGame(game,selected);
    $('month').onchange=()=>{selected=$('month').value;newsLimit=5;renderMonth();};
    $('window').onchange=()=>{newsLimit=5;renderNews();syncUrl();};
    $('jump').onclick=()=>{const drop=largestDrop(rows);if(drop){selected=drop.month;newsLimit=5;renderMonth();}};
    $('download').onclick=()=>{
      const url=URL.createObjectURL(new Blob([csvText(rows)],{type:'text/csv;charset=utf-8'}));
      const a=element('a');a.href=url;a.download=`steam-${game.id}-${rows[0].month}-${rows.at(-1).month}.csv`;a.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
  }catch(error){
    $('explorer').hidden=true;
    $('status').textContent='データを読み込めませんでした。ページを再読み込みしてください。';
    const retry=element('button','再読み込み','small-button');retry.onclick=()=>location.reload();$('status').append(' ',retry);
    console.error(error);
  }
}
start();
