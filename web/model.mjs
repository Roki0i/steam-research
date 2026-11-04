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
export const nearbyNews = (news, month, window) => news.filter(n => Math.abs(monthIndex(n.date.slice(0, 7)) - monthIndex(month)) <= window);
export function csvText(rows) {
  return '\uFEFFmonth,avg_players,peak_players,change_percent\r\n' + rows.map(r => [r.month, r.avg, r.peak, r.change === null ? '' : r.change.toFixed(4)].join(',')).join('\r\n');
}
