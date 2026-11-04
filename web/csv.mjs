// Strict CSV import. Inputs stay in browser memory; this module has no network calls.
export function parseCSV(text) {
  if (text.length > 20 * 1024 * 1024) throw new Error('CSVは20MB以下にしてください。');
  text = text.replace(/^\uFEFF/, '');
  const records = []; let row = [], field = '', quoted = false, closed = false;
  const endField = () => { row.push(field); field = ''; closed = false; };
  const endRow = () => { endField(); if (row.some(v => v.trim())) records.push(row); row = []; };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') { quoted = false; closed = true; }
      else field += c;
    } else if (c === '"') {
      if (field || closed) throw new Error('CSVの引用符が不正です。ダブルクォートで囲む形式を確認してください。');
      quoted = true;
    } else if (c === ',') endField();
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; endRow(); }
    else { if (closed && c.trim()) throw new Error('閉じた引用符の後に余分な文字があります。'); if (!closed) field += c; }
    if (records.length > 200000) throw new Error('CSVは20万行以内にしてください。');
  }
  if (quoted) throw new Error('CSVの引用符が閉じられていません。');
  if (field || row.length || closed) endRow();
  if (records.length < 2) throw new Error('見出し行と、1行以上のデータが必要です。');
  const headers = records.shift().map(h => h.trim());
  if (new Set(headers).size !== headers.length || headers.some(h => !h)) throw new Error('列名の重複または空の列名があります。');
  return records.map((values, i) => {
    if (values.length !== headers.length) throw new Error(`${i + 2}行目：列数が見出しと一致しません。`);
    return Object.fromEntries(headers.map((h, j) => [h, values[j].trim()]));
  });
}
const requireColumns = (row, columns) => {
  const missing = columns.filter(c => !(c in row));
  if (missing.length) throw new Error(`必要な列がありません：${missing.join(', ')}`);
};
function appId(value, line) {
  const id = Number(value);
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(id) || id < 1) throw new Error(`${line}行目：appidには正の整数を入れてください。`);
  return id;
}
function count(value, column, line, optional = false) {
  if (optional && !value) return null;
  const n = Number(value.replace(/,/g, ''));
  if (!value || !Number.isFinite(n) || n < 0) throw new Error(`${line}行目：${column}には0以上の数値を入れてください。`);
  return n;
}
export function normalizeMonth(value) {
  let match = /^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?$/.exec(value);
  if (!match) {
    const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
    const english = /^([A-Za-z]+) (\d{4})$/.exec(value);
    if (english) { const i = months.findIndex(m => m.toLowerCase() === english[1].toLowerCase()); if (i >= 0) match = [null, english[2], String(i + 1)]; }
  }
  if (!match || Number(match[2]) < 1 || Number(match[2]) > 12 || Number(match[1]) < 1900 || Number(match[1]) > 2200) throw new Error('年月はYYYY-MM形式（例：2024-05）にしてください。');
  return `${match[1]}-${match[2].padStart(2, '0')}`;
}
export function importMonthly(text) {
  const records = parseCSV(text);
  requireColumns(records[0], ['appid', 'name', 'avg_players']);
  if (!('month' in records[0]) && !('month_date' in records[0])) throw new Error('month または month_date 列が必要です。');
  const groups = new Map(); let duplicateCount = 0;
  records.forEach((r, i) => {
    const line = i + 2, id = appId(r.appid, line);
    if (!r.name || r.name.length > 256) throw new Error(`${line}行目：nameには256文字以内のゲーム名を入れてください。`);
    let month;
    try { month = normalizeMonth(r.month_date || r.month); } catch(e) { throw new Error(`${line}行目：${e.message}`); }
    const point = {month, avg: count(r.avg_players, 'avg_players', line), peak: count(r.peak_players || '', 'peak_players', line, true)};
    if (point.peak !== null && point.peak < point.avg) throw new Error(`${line}行目：最大同時接続数が平均より小さくなっています。`);
    if (!groups.has(id)) groups.set(id, {id, name:r.name, category:r.category || r.genre || '未分類', collected:[], source:`https://steamcharts.com/app/${id}`, monthly:[], map:new Map()});
    const g = groups.get(id);
    if (g.name !== r.name) throw new Error(`${line}行目：同じappidに異なるゲーム名があります。`);
    if (g.map.has(month)) {
      const prev = g.map.get(month);
      if (prev.avg !== point.avg || prev.peak !== point.peak) throw new Error(`${line}行目：${g.name}の${month}に異なる値が重複しています。`);
      duplicateCount++;
    } else g.map.set(month, point);
    if (/^\d{4}-\d{2}-\d{2}/.test(r.collected_at || '')) g.collected.push(r.collected_at.slice(0,10));
  });
  const games = [...groups.values()].map(g => {
    g.monthly = [...g.map.values()].sort((a,b) => a.month.localeCompare(b.month));
    g.collected = [...new Set(g.collected)].sort(); delete g.map; return g;
  });
  return {games, duplicateCount};
}