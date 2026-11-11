"""Read-only Steam player exploration regression tests."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "explore_players.py"
spec = importlib.util.spec_from_file_location("explore_players", SCRIPT)
explore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(explore)


def game(id, category, points):
    return {"id": id, "name": f"Game {id}", "category": category,
            "monthly": [{"month": month, "avg": avg} for month, avg in points]}


class ExplorePlayersTests(unittest.TestCase):
    def test_same_calendar_month_and_classification(self):
        games = [game(1, "Action", [("2025-10", 100), ("2026-09", 500), ("2026-10", 121)]),
                 game(2, "Action", [("2025-10", 200), ("2026-10", 159)]),
                 game(3, "RPG", [("2025-10", 100), ("2026-10", 110)])]
        result = explore.analyze(games, "2026-10")
        self.assertEqual(result["overall"]["eligible"], 3)
        self.assertEqual(result["overall"]["increased_20pct_or_more"], 1)
        self.assertEqual(result["overall"]["decreased_20pct_or_more"], 1)
        self.assertEqual(result["overall"]["within_20pct"], 1)
        self.assertEqual(result["overall"]["median_change_pct"], 10)
        self.assertEqual(result["by_category"][0]["median_change_pct"], 0.25)
        self.assertEqual(result["start_month"], "2025-10")

    def test_exclusions_and_no_fabricated_zero(self):
        games = [game(1, "A", [("2025-10", 0), ("2026-10", 5)]),
                 game(2, "A", [("2026-10", 100)]),
                 game(3, "A", [("2025-10", 100)]),
                 game(4, "B", [("2025-10", 9), ("2026-10", 20)])]
        result = explore.analyze(games, "2026-10")
        self.assertEqual(result["overall"]["eligible"], 0)
        self.assertEqual(result["excluded"], {"missing_start": 1, "missing_end": 1, "low_baseline": 2})
        self.assertIsNone(result["by_category"][0]["median_change_pct"])

    def test_boundary_and_validation(self):
        result = explore.analyze([game(1, "A", [("2025-10", 100), ("2026-10", 120)]),
                                  game(2, "A", [("2025-10", 100), ("2026-10", 80)])], "2026-10")
        self.assertEqual(result["overall"]["increased_20pct_or_more"], 1)
        self.assertEqual(result["overall"]["decreased_20pct_or_more"], 1)
        with self.assertRaises(ValueError):
            explore.analyze([game(1, "A", [("2025-10", 100), ("2025-10", 200)])], "2026-10")
        with self.assertRaises(ValueError):
            explore.analyze([game(1, "A", [])], "2026-13")
        with self.assertRaises(ValueError):
            explore.analyze([], "2026-10", 0)

    def test_read_published_data_and_safe_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            entry = {"id": 1, "name": "Game 1", "part": "data/players-00.json"}
            (root / "snapshot.json").write_text(json.dumps({"games": [entry]}), encoding="utf-8")
            (root / "data/players-00.json").write_text(json.dumps([game(1, "A", [])]), encoding="utf-8")
            catalogue, games = explore.read_published_data(root)
            self.assertEqual(catalogue["games"][0]["id"], 1)
            self.assertEqual(len(games), 1)
            entry["part"] = "../secret.json"
            (root / "snapshot.json").write_text(json.dumps({"games": [entry]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                explore.read_published_data(root)


if __name__ == "__main__":
    unittest.main()
