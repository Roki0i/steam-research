export const monthIndex = month => Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1;
export function withChanges(rows) {
  return rows.map((r, i) => {
    const prev = rows[i - 1];
    const adjacent = prev && monthIndex(r.month) - monthIndex(prev.month) === 1;
    return {...r, change: adjacent && prev.avg > 0 ? (r.avg / prev.avg - 1) * 100 : null};
  });
}
export function periodRows(rows, months) {
  if (!months || !rows.length) return rows;
  const cutoff = monthIndex(rows.at(-1).month) - months + 1;
  return rows.filter(r => monthIndex(r.month) >= cutoff);
}
export function largestDrop(rows) {
  return rows.filter(r => r.change !== null && r.change < 0).reduce((best, r) => !best || r.change < best.change ? r : best, null);
}
export function csvText(rows, game) {
  const quote = value => `"${String(value).replace(/^[=+@\-\t\r]/, "'$&").replaceAll('"', '""')}"`;
  const prefix = game ? 'appid,name,category,' : '';
  return '\uFEFF' + prefix + 'month,avg_players,peak_players,change_percent\r\n' + rows.map(r =>
    (game ? [game.id, quote(game.name), quote(game.category)] : []).concat([r.month, r.avg, r.peak ?? '', r.change == null ? '' : r.change.toFixed(4)]).join(',')
  ).join('\r\n');
}
