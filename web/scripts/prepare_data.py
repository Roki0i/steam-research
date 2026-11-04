"""Create the public, allowlisted snapshot; never copy raw reviews or news bodies."""
import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

APPIDS = [1091500, 2054970, 2358720, 1272080, 2198150, 646910]


def prepare(monthly_path, news_path):
    groups = defaultdict(dict)
    names = {}
    categories = {}
    collected = defaultdict(set)
    with open(monthly_path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            appid = int(row["appid"])
            if appid not in APPIDS:
                continue
            month = row.get("month_date", "")[:7]
            datetime.strptime(month, "%Y-%m")
            avg = float(row["avg_players"])
            peak = float(row["peak_players"])
            if not all(math.isfinite(v) and v >= 0 for v in (avg, peak)):
                raise ValueError("Invalid player count")
            value = {"month": month, "avg": avg, "peak": peak}
            if month in groups[appid] and groups[appid][month] != value:
                raise ValueError(f"Conflicting duplicate: {appid} {month}")
            groups[appid][month] = value
            names[appid] = row["name"]
            categories[appid] = row["category"]
            collected[appid].add(row["collected_at"][:10])
    news = defaultdict(dict)
    with open(news_path, encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            appid = int(row["appid"])
            if appid not in APPIDS:
                continue
            # Use only public article metadata, no contents/author/user identifiers.
            url = row["url"]
            if urlparse(url).scheme != "https":
                continue
            date = row["news_date"][:10]
            datetime.strptime(date, "%Y-%m-%d")
            news[appid][row["gid"]] = {"title": row["title"], "date": date, "url": url}
    games = []
    for appid in APPIDS:
        if not groups[appid]:
            raise ValueError(f"No observations: {appid}")
        games.append({"id": appid, "name": names[appid], "category": categories[appid],
                      "collected": sorted(collected[appid]),
                      "source": f"https://steamcharts.com/app/{appid}",
                      "monthly": sorted(groups[appid].values(), key=lambda r: r["month"]),
                      "news": sorted(news[appid].values(), key=lambda r: r["date"])})
    return {"schemaVersion": 1, "preparedOn": "2026-11-05", "newsDataset": "factor_news_12m.csv",
            "monthlyDataset": "steamcharts_monthly_clean.csv",
            "inputSha256": {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                            for p in (monthly_path, news_path)}, "games": games}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("monthly_csv")
    parser.add_argument("news_csv")
    parser.add_argument("--output", default=str(Path(__file__).resolve().parents[1] / "snapshot.json"))
    args = parser.parse_args()
    result = prepare(args.monthly_csv, args.news_csv)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"games": len(result["games"]), "months": sum(len(g["monthly"]) for g in result["games"]),
                      "news": sum(len(g["news"]) for g in result["games"])}, ensure_ascii=False))
