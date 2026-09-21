"""Aggregate Jev review classifications monthly and compare them with SteamCharts.

Primary descriptive comparison:
- complaint prevalence in month t
- player decline from month t to t+1

This script estimates associations only; it does not identify causal effects.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


DRIVE_DATA_DIR = Path("/content/drive/MyDrive/卒業研究/steam_research/data")
LABELS = [
    "bug_crash",
    "performance",
    "cheater",
    "server_connection",
    "matchmaking",
    "balance",
    "bad_update",
    "content_lack",
    "monetization",
    "management_liveops",
    "other",
]
DEFAULT_THRESHOLD = 0.5


def data_path(name: str) -> Path:
    if DRIVE_DATA_DIR.exists() or Path("/content/drive/MyDrive").exists():
        DRIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DRIVE_DATA_DIR / name
    Path("./data").mkdir(exist_ok=True)
    return Path("./data") / name


def load_thresholds(path: str | None) -> dict[str, float]:
    thresholds = {label: DEFAULT_THRESHOLD for label in LABELS}
    thresholds["relevant_complaint"] = DEFAULT_THRESHOLD
    if path:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        for key, value in loaded.items():
            if key in thresholds:
                thresholds[key] = float(value)
    return thresholds


def month_diff(start: pd.Timestamp, end: pd.Timestamp) -> float:
    if pd.isna(start) or pd.isna(end):
        return np.nan
    return (end.year - start.year) * 12 + (end.month - start.month)


def load_classified(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    required = {"review_id", "appid", "review_date", "relevant_complaint", *LABELS}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} に必要な列がありません: {sorted(missing)}")

    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["review_date"] = pd.to_datetime(df["review_date"], errors="coerce")
    df = df.dropna(subset=["appid", "review_date"]).copy()
    df["review_month"] = df["review_date"].dt.to_period("M").dt.to_timestamp()
    for col in ["relevant_complaint", *LABELS]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates("review_id", keep="last")


def make_review_monthly(df: pd.DataFrame, thresholds: dict[str, float]) -> pd.DataFrame:
    part = df.copy()
    for key, threshold in thresholds.items():
        part[f"{key}_flag"] = (part[key] >= threshold).astype(int)

    if "voted_up" in part.columns:
        voted = part["voted_up"].astype(str).str.lower().isin(["true", "1", "yes"])
        part["negative_review_flag"] = (~voted).astype(int)
    else:
        part["negative_review_flag"] = np.nan

    group_cols = ["appid", "review_month"]
    if "name" in part.columns:
        group_cols.append("name")
    if "category" in part.columns:
        group_cols.append("category")

    aggregations = {
        "review_id": "count",
        "relevant_complaint": "mean",
        "relevant_complaint_flag": "mean",
        "negative_review_flag": "mean",
    }
    for label in LABELS:
        aggregations[label] = "mean"
        aggregations[f"{label}_flag"] = "mean"

    monthly = part.groupby(group_cols, as_index=False, dropna=False).agg(aggregations)
    rename = {
        "review_id": "classified_reviews",
        "relevant_complaint": "relevant_score_mean",
        "relevant_complaint_flag": "relevant_share",
        "negative_review_flag": "negative_review_share",
    }
    for label in LABELS:
        rename[label] = f"{label}_score_mean"
        rename[f"{label}_flag"] = f"{label}_share"
    return monthly.rename(columns=rename)


def load_steamcharts(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "month_date" in df.columns:
        df["month_date"] = pd.to_datetime(df["month_date"], errors="coerce")
    elif "month" in df.columns:
        df = df[df["month"].astype(str) != "Last 30 Days"].copy()
        df["month_date"] = pd.to_datetime(df["month"], format="%B %Y", errors="coerce")
    else:
        raise ValueError("steamcharts_monthly.csv に month または month_date 列がありません。")

    if "avg_players" not in df.columns:
        raise ValueError("steamcharts_monthly.csv に avg_players 列がありません。")

    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["avg_players"] = pd.to_numeric(
        df["avg_players"].astype(str).str.replace(",", "", regex=False),
        errors="coerce",
    )
    df = df.dropna(subset=["appid", "month_date", "avg_players"]).copy()
    df["month_date"] = df["month_date"].dt.to_period("M").dt.to_timestamp()
    return df.drop_duplicates(["appid", "month_date"], keep="last").sort_values(["appid", "month_date"])


def add_forward_decline(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, game in df.groupby("appid", sort=False):
        game = game.sort_values("month_date").copy()
        game["next_month_date"] = game["month_date"].shift(-1)
        game["next_avg_players"] = game["avg_players"].shift(-1)
        game["next_month_gap"] = [
            month_diff(start, end)
            for start, end in zip(game["month_date"], game["next_month_date"])
        ]
        game["player_decline_next_1m"] = (
            game["avg_players"] - game["next_avg_players"]
        ) / game["avg_players"]
        game.loc[
            (game["next_month_gap"] != 1) | (game["avg_players"] <= 0),
            "player_decline_next_1m",
        ] = np.nan
        frames.append(game)
    return pd.concat(frames, ignore_index=True)


def add_complaint_changes(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    share_cols = ["relevant_share"] + [f"{label}_share" for label in LABELS]
    for _, game in df.groupby("appid", sort=False):
        game = game.sort_values("review_month").copy()
        prev_month = game["review_month"].shift(1)
        gaps = pd.Series(
            [month_diff(start, end) for start, end in zip(prev_month, game["review_month"])],
            index=game.index,
        )
        for col in share_cols:
            game[f"delta_{col}"] = (game[col] - game[col].shift(1)).where(gaps == 1)
        frames.append(game)
    return pd.concat(frames, ignore_index=True)


def make_correlations(df: pd.DataFrame, min_reviews: int) -> pd.DataFrame:
    part = df[
        (df["classified_reviews"] >= min_reviews)
        & df["player_decline_next_1m"].notna()
    ].copy()

    scopes = [("ALL", part)]
    if "category" in part.columns:
        scopes += list(part.groupby("category"))

    rows = []
    for category, scope in scopes:
        for label in LABELS:
            for predictor_type, predictor in [
                ("level", f"{label}_share"),
                ("change", f"delta_{label}_share"),
            ]:
                usable = scope.dropna(subset=[predictor, "player_decline_next_1m"])
                if len(usable) >= 10 and usable[predictor].nunique() >= 2:
                    rho, p_value = stats.spearmanr(
                        usable[predictor],
                        usable["player_decline_next_1m"],
                    )
                else:
                    rho, p_value = np.nan, np.nan
                rows.append(
                    {
                        "category": category,
                        "label": label,
                        "predictor_type": predictor_type,
                        "predictor": predictor,
                        "outcome": "player_decline_next_1m",
                        "n": len(usable),
                        "spearman_rho": rho,
                        "p_value": p_value,
                        "min_reviews_per_game_month": min_reviews,
                    }
                )
    return pd.DataFrame(rows)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--classified", default=None)
    p.add_argument("--steamcharts", default=None)
    p.add_argument("--thresholds", default=None, help="jev_thresholds.json")
    p.add_argument("--min-reviews", type=int, default=10)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    classified_path = Path(args.classified) if args.classified else data_path("review_classified.csv")
    steam_path = Path(args.steamcharts) if args.steamcharts else data_path("steamcharts_monthly.csv")
    thresholds = load_thresholds(args.thresholds)

    classified = load_classified(classified_path)
    review_monthly = make_review_monthly(classified, thresholds)
    review_monthly.to_csv(data_path("jev_review_monthly.csv"), index=False, encoding="utf-8-sig")

    steam = add_forward_decline(load_steamcharts(steam_path))
    merged = review_monthly.merge(
        steam,
        left_on=["appid", "review_month"],
        right_on=["appid", "month_date"],
        how="inner",
        suffixes=("", "_steam"),
        validate="many_to_one",
    )
    merged = add_complaint_changes(merged)
    merged.to_csv(data_path("jev_merged_monthly.csv"), index=False, encoding="utf-8-sig")

    correlations = make_correlations(merged, args.min_reviews)
    correlations.to_csv(data_path("jev_category_correlations.csv"), index=False, encoding="utf-8-sig")

    print(f"classified reviews: {len(classified)}")
    print(f"review game-months: {len(review_monthly)}")
    print(f"merged game-months: {len(merged)}")
    print(f"correlation rows: {len(correlations)}")
    print("Jev probability = category membership probability, not complaint severity.")
    print("Associations do not establish causality.")


if __name__ == "__main__":
    main()
