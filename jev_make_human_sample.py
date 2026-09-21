"""Create a blinded human-labeling sample for Jev validation.

The template contains raw review text and blank human label columns, but no Jev
predictions. This avoids anchoring human annotators to model output.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


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


def data_path(name: str) -> Path:
    if DRIVE_DATA_DIR.exists() or Path("/content/drive/MyDrive").exists():
        DRIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DRIVE_DATA_DIR / name
    Path("./data").mkdir(exist_ok=True)
    return Path("./data") / name


def review_id_for(row: pd.Series) -> str:
    rid = row.get("recommendationid")
    if pd.notna(rid) and str(rid).strip():
        return str(rid).strip()
    raw = f"{row.get('appid','')}|{row.get('timestamp_created','')}|{row.get('review','')}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def stratified_sample(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    category_col = "category" if "category" in df.columns else ("genre" if "genre" in df.columns else None)
    if not category_col:
        return df.sample(n=min(n, len(df)), random_state=seed)

    groups = [g for _, g in df.groupby(category_col, dropna=False)]
    if not groups:
        return df.sample(n=min(n, len(df)), random_state=seed)

    per_group = max(1, n // len(groups))
    pieces = []
    for i, group in enumerate(groups):
        pieces.append(group.sample(n=min(per_group, len(group)), random_state=seed + i))
    sampled = pd.concat(pieces).drop_duplicates("review_id")

    remaining = min(n - len(sampled), len(df) - len(sampled))
    if remaining > 0:
        pool = df[~df["review_id"].isin(sampled["review_id"])]
        sampled = pd.concat(
            [sampled, pool.sample(n=remaining, random_state=seed + 999)],
            ignore_index=True,
        )
    return sampled.head(n)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--n", type=int, default=400)
    p.add_argument("--language", default="english")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    input_path = Path(args.input) if args.input else data_path("reviews_raw.csv")
    output_path = Path(args.output) if args.output else data_path("jev_human_labels_template.csv")

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    if "review" not in df.columns or "appid" not in df.columns:
        raise ValueError("input CSV に appid と review が必要です。")

    if "recommendationid" not in df.columns:
        df["recommendationid"] = pd.NA
    if "language" not in df.columns:
        df["language"] = pd.NA

    df = df[df["review"].notna()].copy()
    df["review"] = df["review"].astype(str).str.strip()
    df = df[df["review"].str.len() > 0]
    if args.language.lower() != "all":
        df = df[df["language"].astype(str).str.lower() == args.language.lower()].copy()

    df["review_id"] = df.apply(review_id_for, axis=1)
    df = df.drop_duplicates("review_id", keep="last")
    sample = stratified_sample(df, args.n, args.seed).copy()

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(sample))
    sample = sample.iloc[order].reset_index(drop=True)
    sample["split"] = ["calibration" if i < len(sample) // 2 else "test" for i in range(len(sample))]

    base_cols = [
        c for c in [
            "review_id", "recommendationid", "appid", "name", "category", "genre",
            "language", "voted_up", "timestamp_created", "review", "split"
        ]
        if c in sample.columns
    ]
    out = sample[base_cols].copy()
    for label in LABELS:
        out[label] = ""
    out["annotator_note"] = ""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"saved: {output_path}")
    print(f"rows: {len(out)}")
    print("Fill each label with 0 or 1 without looking at Jev predictions.")
    print("For inter-rater agreement, duplicate about 100 rows for a second annotator and add rater2_<label> columns.")


if __name__ == "__main__":
    main()
