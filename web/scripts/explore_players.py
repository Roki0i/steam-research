"""Explore published SteamCharts monthly averages without network or data writes.

Compares the same calendar month one year apart to reduce seasonality effects.
The selected titles are not a random Steam sample; trends are descriptive only.
"""

import argparse
import json
import math
from pathlib import Path
import re
from statistics import median

PART_PATTERN = re.compile(r"data/players-(?:\d{2}|auto-\d{2}-[a-f0-9]{16})\.json\Z")
MONTH_PATTERN = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")
CHANGE_THRESHOLD = 20.0
EXAMPLE_MIN_BASELINE = 100.0


def read_published_data(root):
    """Load only shards referenced by the published catalogue."""
    catalogue = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
    entries = catalogue["games"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("Catalogue must contain games")

    shards = {}
    games = []
    seen = set()
    for entry in entries:
        game_id = entry["id"]
        part = entry["part"]
        if not isinstance(part, str) or not PART_PATTERN.fullmatch(part):
            raise ValueError("Unsafe shard path")
        if game_id in seen:
            raise ValueError("Duplicate catalogue game ID")
        seen.add(game_id)
        if part not in shards:
            data = json.loads((root / part).read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise ValueError("Shard must contain a list")
            ids = [game["id"] for game in data]
            if len(set(ids)) != len(ids):
                raise ValueError("Duplicate game ID in shard")
            shards[part] = {game["id"]: game for game in data}
        game = shards[part].get(game_id)
        if game is None or game["name"] != entry["name"]:
            raise ValueError("Catalogue and shard disagree")
        games.append(game)
    return catalogue, games


def previous_year(month):
    if not MONTH_PATTERN.fullmatch(month):
        raise ValueError("Month must be YYYY-MM")
    if int(month[:4]) <= 1:
        raise ValueError("Year must be after 0001")
    return f"{int(month[:4]) - 1:04d}{month[4:]}"


def analyze(games, end_month, minimum_baseline=10):
    """Classify exact year-over-year changes, excluding missing/low baselines."""
    start_month = previous_year(end_month)
    if not math.isfinite(minimum_baseline) or minimum_baseline <= 0:
        raise ValueError("Minimum baseline must be positive and finite")
    categories = {}
    excluded = {"missing_start": 0, "missing_end": 0, "low_baseline": 0}
    examples = []
    seen = set()

    for game in games:
        if game["id"] in seen:
            raise ValueError("Duplicate game ID")
        seen.add(game["id"])
        category = game["category"]
        categories.setdefault(category, {"selected": 0, "changes": []})
        categories[category]["selected"] += 1
        series = {}
        for point in game["monthly"]:
            month = point["month"]
            avg = point["avg"]
            if not MONTH_PATTERN.fullmatch(month) or not isinstance(avg, (int, float)) or not math.isfinite(avg) or avg < 0:
                raise ValueError("Invalid month or average")
            if month in series:
                raise ValueError("Duplicate month for game")
            series[month] = avg
        if start_month not in series:
            excluded["missing_start"] += 1
            continue
        if end_month not in series:
            excluded["missing_end"] += 1
            continue
        start = series[start_month]
        if start < minimum_baseline:
            excluded["low_baseline"] += 1
            continue
        pct = round(100 * (series[end_month] / start - 1), 8)
        categories[category]["changes"].append(pct)
        if start >= EXAMPLE_MIN_BASELINE:
            examples.append({"id": game["id"], "name": game["name"],
                             "category": category, "start_average": round(start, 2),
                             "end_average": round(series[end_month], 2),
                             "change_pct": round(pct, 2)})

    all_changes = [pct for group in categories.values() for pct in group["changes"]]

    def summarize(changes):
        return {"eligible": len(changes),
                "increased_20pct_or_more": sum(p >= CHANGE_THRESHOLD for p in changes),
                "decreased_20pct_or_more": sum(p <= -CHANGE_THRESHOLD for p in changes),
                "within_20pct": sum(-CHANGE_THRESHOLD < p < CHANGE_THRESHOLD for p in changes),
                "median_change_pct": round(median(changes), 2) if changes else None}

    category_summary = []
    for name, group in sorted(categories.items()):
        category_summary.append({"name": name, "selected": group["selected"],
                                 **summarize(group["changes"])})
    return {"source": "published SteamCharts monthly average concurrent players",
            "start_month": start_month, "end_month": end_month,
            "min_start_average": minimum_baseline,
            "selected_games": len(games), "excluded": excluded,
            "overall": summarize(all_changes), "by_category": category_summary,
            "examples": {
                "increases": sorted(examples, key=lambda row: (-row["change_pct"], row["id"]))[:5],
                "decreases": sorted(examples, key=lambda row: (row["change_pct"], row["id"]))[:5],
            },
            "limitations": [
                "The selected 1,000 games are not a random sample of Steam.",
                "Monthly average concurrent players are not unique users or churn.",
                "Missing months and low baselines are excluded; categories have unequal coverage.",
                "A year-over-year change alone cannot establish its cause.",
            ]}


def print_report(report):
    totals = report["overall"]
    print(f"Comparison: {report['start_month']} -> {report['end_month']} (same calendar month)")
    print(f"Selected: {report['selected_games']}; comparable: {totals['eligible']}; "
          f"excluded: {sum(report['excluded'].values())}")
    print(f"Excluded by reason: {report['excluded']}")
    print(f">=20% increase: {totals['increased_20pct_or_more']}; "
          f">=20% decrease: {totals['decreased_20pct_or_more']}; "
          f"within +/-20%: {totals['within_20pct']}; "
          f"median: {totals['median_change_pct']}%")
    print("By category (selected / comparable / median YoY change):")
    for c in report["by_category"]:
        print(f"  {c['name']}: {c['selected']} / {c['eligible']} / {c['median_change_pct']}%")
    for label, key in (("Largest increases", "increases"), ("Largest decreases", "decreases")):
        print(label + " (baseline >=100 average concurrent players):")
        for game in report["examples"][key]:
            print(f"  {game['name']} [{game['id']}]: {game['change_pct']:+.2f}%")
    print("Note: selected games are not representative; concurrent players are not churn; no causality inferred.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="Published web directory containing snapshot.json and data/")
    parser.add_argument("--end-month", help="YYYY-MM; default is latest catalogue month")
    parser.add_argument("--min-start-average", type=float, default=10,
                        help="Exclude games with a smaller first-month average (default: 10)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable report")
    args = parser.parse_args()
    catalogue, games = read_published_data(args.root)
    end_month = args.end_month or max(game["lastMonth"] for game in catalogue["games"])
    report = analyze(games, end_month, args.min_start_average)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
