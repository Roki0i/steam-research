"""Refresh published monthly player counts; never edit the research CSV baseline."""
import argparse
import copy
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

USER_AGENT = 'steam-research/1.1 (+https://github.com/Roki0i/steam-research)'
ORIGIN = 'https://steamcharts.com'
PART_RE = re.compile(r'data/players-(?:\d{2}|auto-\d{2}-[a-f0-9]{16})\.json\Z')


class AccessBlocked(RuntimeError):
    """Stop the entire run on access refusal or rate limiting."""


class MonthlyTable(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.table, self.row, self.cell = [], None, None, None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.table = []
        elif self.table is not None:
            if tag == 'tr': self.row = []
            elif tag in ('td', 'th') and self.row is not None: self.cell = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.table is not None: self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_monthly(html, now):
    parser = MonthlyTable()
    parser.feed(html)
    table = next((t for t in parser.tables if t and any(
        'Month' in r and 'Avg. Players' in r and 'Peak Players' in r for r in t)), None)
    if table is None: raise ValueError('Monthly table missing')
    points = {}
    cutoff = now.astimezone(timezone.utc).strftime('%Y-%m')
    for cells in table:
        if not cells or cells[0] in ('Month', 'Last 30 Days'): continue
        if len(cells) < 5: raise ValueError('Incomplete monthly row')
        try: month = datetime.strptime(cells[0], '%B %Y').strftime('%Y-%m')
        except ValueError as error: raise ValueError('Unknown monthly row') from error
        # Never mix an unfinished month or a rolling 30-day value into calendar history.
        if month >= cutoff: continue
        try: avg, peak = (float(cells[i].replace(',', '')) for i in (1, 4))
        except ValueError as error: raise ValueError('Invalid player count') from error
        if not all(math.isfinite(n) and n >= 0 for n in (avg, peak)) or peak < avg:
            raise ValueError('Invalid player count')
        point = {'month': month, 'avg': avg, 'peak': peak}
        if month in points and points[month] != point: raise ValueError('Conflicting month')
        points[month] = point
    if not points: raise ValueError('No completed calendar months')
    return sorted(points.values(), key=lambda r: r['month'])


def get_html(url, *, robots=False):
    for attempt in range(2):
        try:
            with urlopen(Request(url, headers={'User-Agent': USER_AGENT}), timeout=20) as response:
                if response.geturl().split('/')[2] != 'steamcharts.com':
                    raise AccessBlocked('Unexpected redirect host')
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024: raise ValueError('Response too large')
                text = data.decode('utf-8')
                if any(marker in text.lower() for marker in ('verify you are human', 'cf-chl-', 'just a moment...')):
                    raise AccessBlocked('Human verification requested')
                return text
        except HTTPError as error:
            if robots and error.code in (404, 410): return None
            if error.code in (401, 403, 429): raise AccessBlocked(f'HTTP {error.code}') from error
            if error.code < 500 or attempt: raise
        except (URLError, TimeoutError):
            if attempt: raise
        time.sleep(3)
    raise RuntimeError('Request failed')


def check_robots(fetch=get_html):
    text = fetch(ORIGIN + '/robots.txt', robots=True)
    policy = RobotFileParser()
    if text is None:
        policy.parse(['User-agent: *', 'Allow: /'])
    else: policy.parse(text.splitlines())
    return policy


def load_games(root):
    catalogue = json.loads((root / 'snapshot.json').read_text(encoding='utf-8'))
    if catalogue.get('schemaVersion') != 2: raise ValueError('Unsupported catalogue')
    parts, games, seen = {}, [], set()
    for entry in catalogue['games']:
        part = entry['part']
        if not PART_RE.fullmatch(part): raise ValueError('Unsafe data path')
        if part not in parts:
            parts[part] = {g['id']: g for g in json.loads((root / part).read_text(encoding='utf-8'))}
        game = parts[part][entry['id']]
        if game['id'] in seen: raise ValueError('Duplicate game')
        seen.add(game['id'])
        games.append(copy.deepcopy(game))
    if not games: raise ValueError('Empty catalogue')
    return catalogue, games


def refresh_games(games, now, fetch, allowed, limit=0, pause=time.sleep, interval=3):
    result = copy.deepcopy(games)
    target = len(games) if limit == 0 else min(limit, len(games))
    report = {'attempted': 0, 'successful': 0, 'failed': 0, 'total': len(games),
              'scope': 'full' if target == len(games) else 'sample', 'errors': [], 'stopped': False}
    consecutive = 0
    stamp = now.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    for index in range(target):
        game = result[index]
        url = f"{ORIGIN}/app/{game['id']}"
        if not allowed(url):
            report['stopped'] = True
            report['stopReason'] = 'robots.txt does not allow collection'
            break
        if index: pause(max(3, interval))
        report['attempted'] += 1
        try:
            fresh = parse_monthly(fetch(url), now)
            merged = {point['month']: point for point in game['monthly']}
            merged.update({point['month']: point for point in fresh})
            game['monthly'] = sorted(merged.values(), key=lambda r: r['month'])
            game['collected'] = sorted(set(game.get('collected', []) + [stamp[:10]]))
            game['lastCheckedAt'] = stamp
            report['successful'] += 1
            consecutive = 0
        except Exception as error:
            report['failed'] += 1
            consecutive += 1
            # No page body, token, or account information is included in the report.
            report['errors'].append({'appid': game['id'], 'error': type(error).__name__ + ': ' + str(error)[:180]})
            if isinstance(error, AccessBlocked) or consecutive >= 5:
                report['stopped'] = True
                report['stopReason'] = 'Access blocked' if isinstance(error, AccessBlocked) else 'Five consecutive failures'
                break
    report['lastAttemptAt'] = stamp
    report['status'] = ('failed' if report['successful'] == 0 else
                        'partial' if report['failed'] or report['stopped'] else
                        'sample_verified' if report['scope'] == 'sample' else 'success')
    return result, report


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as file:
        file.write(body)
        temporary = file.name
    os.replace(temporary, path)


def write_snapshot(root, previous, games, report):
    games.sort(key=lambda g: (-g['monthly'][-1]['avg'], g['name']))
    catalogue, keep = [], {entry['part'] for entry in previous['games']}
    for offset in range(0, len(games), 40):
        batch = games[offset:offset + 40]
        body = json.dumps(batch, ensure_ascii=False, separators=(',', ':'))
        digest = hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]
        part = f'data/players-auto-{offset // 40:02}-{digest}.json'
        atomic_json(root / part, batch)
        keep.add(part)
        for game in batch:
            points = game['monthly']
            catalogue.append({k: v for k, v in game.items() if k != 'monthly'} | {
                'part': part, 'firstMonth': points[0]['month'], 'lastMonth': points[-1]['month'],
                'latestAvg': points[-1]['avg'], 'months': len(points)})
    refresh = report | {'schedule': 'monthly-day-2',
                        'lastFullSuccessAt': report['lastAttemptAt'] if report['status'] == 'success'
                        else previous.get('refresh', {}).get('lastFullSuccessAt')}
    snapshot = {'schemaVersion': 2, 'preparedOn': report['lastAttemptAt'][:10],
                'source': 'SteamCharts monthly tables',
                'baselineDataset': previous.get('baselineDataset', previous.get('monthlyDataset')),
                'baselineInputSha256': previous.get('baselineInputSha256', previous.get('inputSha256', {})),
                'totalMonths': sum(len(g['monthly']) for g in games), 'refresh': refresh, 'games': catalogue}
    # Commit the catalogue last, after every immutable part is present.
    atomic_json(root / 'snapshot.json', snapshot)
    # Preserve the previous generation and the original bundled baseline for cached readers.
    for path in (root / 'data').glob('players-auto-*.json'):
        if path.relative_to(root).as_posix() not in keep: path.unlink()
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--limit', type=int, default=0, help='0 means all titles; a smaller run is explicitly labelled sample')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.limit < 0: parser.error('limit must be non-negative')
    previous, games = load_games(args.root)
    now = datetime.now(timezone.utc)
    try:
        policy = check_robots()
        delay = policy.crawl_delay(USER_AGENT) or 3
        rate = policy.request_rate(USER_AGENT)
        if rate: delay = max(delay, rate.seconds / rate.requests)
        updated, report = refresh_games(games, now, get_html, lambda url: policy.can_fetch(USER_AGENT, url), args.limit, interval=delay)
    except Exception as error:
        updated = games
        report = {'attempted': 0, 'successful': 0, 'failed': 0, 'total': len(games), 'scope': 'full',
                  'status': 'failed', 'stopped': True, 'stopReason': type(error).__name__,
                  'errors': [], 'lastAttemptAt': now.isoformat(timespec='seconds').replace('+00:00', 'Z')}
    if not args.dry_run: write_snapshot(args.root, previous, updated, report)
    if args.report: atomic_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))
    # A sample probe is not a successful full refresh. Partial/failed runs are visible as failed jobs.
    if report['status'] in ('failed', 'partial'): raise SystemExit(1)


if __name__ == '__main__':
    main()
