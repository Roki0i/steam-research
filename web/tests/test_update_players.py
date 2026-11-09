import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location('updater', Path(__file__).parents[1] / 'scripts/update_players.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
def page(month='October 2026', avg='120'):
    return f'<table><tr><th>Month</th><th>Avg. Players</th><th>Gain</th><th>% Gain</th><th>Peak Players</th></tr><tr><td>{month}</td><td>{avg}</td><td>0</td><td>0</td><td>200</td></tr></table>'
def game(i):
    return {'id':i,'name':str(i),'category':'Test','source':f'https://steamcharts.com/app/{i}', 'collected':['2026-08-25'],'monthly':[{'month':'2026-07','avg':100,'peak':200}]}
class UpdaterTests(unittest.TestCase):
    def test_completed_months_only(self):
        self.assertEqual(u.parse_monthly(page(), NOW)[0]['month'],'2026-10')
        for label in ('Last 30 Days','November 2026','December 2026'):
            with self.assertRaises(ValueError): u.parse_monthly(page(label), NOW)
        with self.assertRaises(ValueError): u.parse_monthly(page(avg='nan'),NOW)
    def test_failure_retains_values_and_merge_does_not_fill_gaps(self):
        original=[game(1),game(2)]
        def fetch(url):
            if url.endswith('/2'): raise ValueError('missing table')
            return page()
        updated, report=u.refresh_games(original,NOW,fetch,lambda _:True,pause=lambda _:None)
        self.assertEqual(report['status'],'partial')
        self.assertEqual(updated[1],original[1])
        self.assertEqual([r['month'] for r in updated[0]['monthly']],['2026-07','2026-10'])
        self.assertNotIn('lastCheckedAt',original[0])
    def test_block_stops_run_and_sample_is_labelled(self):
        def blocked(_): raise u.AccessBlocked('HTTP 429')
        _,report=u.refresh_games([game(1),game(2)],NOW,blocked,lambda _:True,pause=lambda _:None)
        self.assertEqual(report['attempted'],1)
        self.assertEqual(report['status'],'failed')
        _,report=u.refresh_games([game(1),game(2)],NOW,lambda _:page(),lambda _:True,limit=1)
        self.assertEqual(report['status'],'sample_verified')
    def test_targeted_retry_and_full_status_preservation(self):
        previous = {'games': [{'part': 'data/players-00.json'}],
                    'refresh': {'scope': 'full', 'status': 'partial',
                                'lastAttemptAt': '2026-11-06T00:00:00Z',
                                'errors': [{'appid': 2}, {'appid': 3}],
                                'lastFullSuccessAt': None}}
        games = [game(1), game(2), game(3)]
        selected = set(u.failed_app_ids(previous))
        self.assertEqual(selected, {2, 3})
        calls = []
        def fetch(url):
            calls.append(url)
            return page()
        updated, report = u.refresh_games(games, NOW, fetch, lambda _: True,
                                           selected_ids=selected, pause=lambda _: None)
        self.assertEqual(report['status'], 'retry_verified')
        self.assertEqual(report['updatedAppIds'], [2, 3])
        self.assertEqual(len(calls), 2)
        self.assertEqual(updated[0], games[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = u.write_snapshot(root, previous, updated, report)
            self.assertEqual(snapshot['refresh'], previous['refresh'])
            self.assertEqual(snapshot['retry']['resolvedAppIds'], [2, 3])
            self.assertEqual(u.failed_app_ids(snapshot), [])
            sample_update, sample_report = u.refresh_games(updated, NOW, fetch,
                lambda _: True, limit=1, pause=lambda _: None)
            sample_snapshot = u.write_snapshot(root, snapshot, sample_update, sample_report)
            self.assertEqual(sample_snapshot['refresh'], previous['refresh'])
            self.assertEqual(sample_snapshot['probe']['status'], 'sample_verified')
            self.assertEqual(sample_snapshot['retry']['resolvedAppIds'], [2, 3])

    def test_retry_honors_access_blocks_and_five_failures(self):
        games = [game(i) for i in range(10)]
        def failed(_):
            raise ValueError('HTTP 500')
        _, report = u.refresh_games(games, NOW, failed, lambda _: True,
            selected_ids=set(range(10)), pause=lambda _: None)
        self.assertEqual(report['attempted'], 5)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual(report['stopReason'], 'Five consecutive failures')
        def blocked(_):
            raise u.AccessBlocked('HTTP 429')
        _, report = u.refresh_games(games, NOW, blocked, lambda _: True,
            selected_ids={1, 2}, pause=lambda _: None)
        self.assertEqual(report['attempted'], 1)
        self.assertEqual(report['stopReason'], 'Access blocked')

    def test_immutable_parts_and_catalogue_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            previous={'games':[{'part':'data/players-00.json'}], 'inputSha256':{'monthly':'original'}}
            report={'status':'success','lastAttemptAt':'2026-11-05T00:00:00Z','successful':1,'total':1}
            first=u.write_snapshot(root,previous,[game(1)],report)
            old=first['games'][0]['part']; old_body=(root/old).read_bytes()
            changed=game(1); changed['monthly'][0]['avg']=90
            second=u.write_snapshot(root,first,[changed],report)
            self.assertNotEqual(old,second['games'][0]['part'])
            self.assertEqual((root/old).read_bytes(),old_body)
            catalogue, games=u.load_games(root)
            self.assertEqual(games[0]['monthly'][0]['avg'],90)
            self.assertEqual(catalogue['baselineInputSha256'],{'monthly':'original'})
if __name__=='__main__': unittest.main()
