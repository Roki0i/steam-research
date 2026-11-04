"""Build the public catalogue and lazy-loaded monthly player data from collected CSV."""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def prepare(monthly_path, output):
    groups = defaultdict(dict)
    metadata = {}
    collected = defaultdict(set)
    with open(monthly_path, encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            appid = int(row['appid'])
            month = row.get('month_date', '')[:7]
            datetime.strptime(month, '%Y-%m')
            avg, peak = float(row['avg_players']), float(row['peak_players'])
            if not all(math.isfinite(v) and v >= 0 for v in (avg, peak)) or peak < avg:
                raise ValueError(f'Invalid player count: {appid} {month}')
            value = {'month': month, 'avg': avg, 'peak': peak}
            if month in groups[appid] and groups[appid][month] != value:
                raise ValueError(f'Conflicting duplicate: {appid} {month}')
            groups[appid][month] = value
            metadata[appid] = {'id': appid, 'name': row['name'], 'category': row['category'],
                               'source': f'https://steamcharts.com/app/{appid}'}
            collected[appid].add(row['collected_at'][:10])
    games = []
    for appid, values in groups.items():
        monthly = sorted(values.values(), key=lambda r: r['month'])
        games.append({**metadata[appid], 'collected': sorted(collected[appid]), 'monthly': monthly})
    games.sort(key=lambda g: (-g['monthly'][-1]['avg'], g['name']))
    data_dir = output.parent / 'data'
    data_dir.mkdir(exist_ok=True)
    catalogue = []
    for offset in range(0, len(games), 40):
        part = f'data/players-{offset // 40:02}.json'
        batch = games[offset:offset + 40]
        (output.parent / part).write_text(json.dumps(batch, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        for game in batch:
            monthly = game['monthly']
            catalogue.append({k: v for k, v in game.items() if k != 'monthly'} | {
                'part': part, 'firstMonth': monthly[0]['month'], 'lastMonth': monthly[-1]['month'],
                'latestAvg': monthly[-1]['avg'], 'months': len(monthly)})
    result = {'schemaVersion': 2, 'preparedOn': '2026-11-05', 'monthlyDataset': Path(monthly_path).name,
              'inputSha256': {Path(monthly_path).name: hashlib.sha256(Path(monthly_path).read_bytes()).hexdigest()},
              'totalMonths': sum(len(g['monthly']) for g in games), 'games': catalogue}
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({'games': len(games), 'months': result['totalMonths'], 'parts': math.ceil(len(games) / 40)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('monthly_csv')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'snapshot.json')
    args = parser.parse_args()
    prepare(args.monthly_csv, args.output)
