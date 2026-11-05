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
