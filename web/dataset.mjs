export const PUBLIC_BASE = 'https://raw.githubusercontent.com/Roki0i/steam-research/main/web/';
export const validPart = path => /^data\/players-(?:\d{2}|auto-\d{2}-[a-f0-9]{16})\.json$/.test(path);
export function validateCatalogue(value) {
 if(value?.schemaVersion!==2||!Array.isArray(value.games)||!value.games.length||value.games.some(g=>!validPart(g.part)))throw new Error('Invalid catalogue');
 return value;
}
export async function loadCatalogue(fetcher=fetch) {
 for(const base of [PUBLIC_BASE,'./']) {
  try {
   const response=await fetcher(base+'snapshot.json',{signal:AbortSignal.timeout(10000),cache:'no-cache'});
   if(!response.ok)throw new Error('Unavailable');
   return {snapshot:validateCatalogue(await response.json()),base,fallback:base==='./'};
  } catch(error) {if(base==='./')throw error;}
 }
}
export function updateSummary(snapshot) {
 const r=snapshot.refresh;
 if(!r)return '初期データ · 自動更新の初回実行待ち';
 const day=r.lastAttemptAt.slice(0,10);
 const status={success:'全件更新',sample_verified:'一部タイトルで更新動作を確認',partial:'一部取得に失敗',failed:'更新に失敗・保存値を表示'}[r.status]||'更新状況不明';
 return `${day} ${status}（${r.successful}/${r.total}件）`;
}
export function checkedDate(game) {return game.lastCheckedAt?.slice(0,10)||game.collected?.at(-1)||'不明';}
