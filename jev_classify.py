"""Steam review multi-label classification with TypeSafe AI Jev.

One review = one request. All label questions are evaluated in the same System One
request. Raw probabilities are saved; final thresholds are calibrated separately
with human-labeled data.

Default paths are Google Drive paths used by this graduation-research project.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from typesafe_sdk import Noul, RetryPolicy, TypeSafeClient


DRIVE_DATA_DIR = Path("/content/drive/MyDrive/卒業研究/steam_research/data")
DEFAULT_INPUT = "reviews_raw.csv"
DEFAULT_OUTPUT = "review_classified.csv"
DEFAULT_ERRORS = "review_classify_errors.csv"

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

QUESTION_SPECS = {
    "relevant_complaint": (
        "Does this Steam review express a concrete dissatisfaction or problem that could plausibly contribute "
        "to a player reducing playtime or quitting? Judge only what the review states; do not infer from game reputation.",
        "A concrete player-retention-related complaint is expressed.",
        "No such complaint is expressed; praise, neutral description, joke, or unrelated text only.",
    ),
    "bug_crash": (
        "Does the review complain about bugs, crashes, freezes, glitches, broken features, or save/data loss?",
        "A software defect, crash, freeze, glitch, broken feature, or data-loss problem is complained about.",
        "No complaint of this kind is expressed.",
    ),
    "performance": (
        "Does the review complain about performance or optimization, such as low FPS, stutter, frame drops, or excessive hardware load?",
        "Performance or optimization is complained about.",
        "No performance/optimization complaint is expressed.",
    ),
    "cheater": (
        "Does the review complain about cheating, hackers, abusive bots/exploits, or ineffective anti-cheat?",
        "Cheating or ineffective anti-cheat is complained about.",
        "No cheating/anti-cheat complaint is expressed.",
    ),
    "server_connection": (
        "Does the review complain about servers/connectivity such as outages, lag, disconnects, ping, network errors, or inability to connect?",
        "A server or connection problem is complained about.",
        "No server/connection complaint is expressed.",
    ),
    "matchmaking": (
        "Does the review complain about matchmaking quality, queue times, rank matching, team assignment, or inability to find suitable matches?",
        "Matchmaking or queue quality is complained about.",
        "No matchmaking complaint is expressed.",
    ),
    "balance": (
        "Does the review complain that gameplay, characters, weapons, classes, difficulty, or competitive systems are unfair or badly balanced?",
        "Game balance or fairness is complained about.",
        "No balance complaint is expressed.",
    ),
    "bad_update": (
        "Does the review complain that a specific update, patch, rework, season change, or recent change made the game worse? "
        "A generic bug is not enough unless the review links it to an update/change.",
        "A specific update/patch/change is described as worsening the game.",
        "No complaint about a specific update/patch/change is expressed.",
    ),
    "content_lack": (
        "Does the review complain about insufficient, repetitive, stale, shallow, or exhausted content, including weak endgame or lack of replay value?",
        "Insufficient or repetitive content is complained about.",
        "No content-shortage complaint is expressed.",
    ),
    "monetization": (
        "Does the review complain about price, DLC pricing, microtransactions, pay-to-win, subscriptions, battle passes, "
        "premium currency, refunds, or monetization practices?",
        "Price or monetization is complained about.",
        "No price/monetization complaint is expressed.",
    ),
    "management_liveops": (
        "Does the review complain about developer/publisher management or live-service operation, such as poor communication, "
        "abandoned support, update cadence, moderation, roadmap decisions, or failure to address known issues?",
        "Management, support, communication, moderation, or live operations are complained about.",
        "No management/live-operations complaint is expressed.",
    ),
    "other": (
        "Does the review express another concrete player-retention-related dissatisfaction that is NOT substantially covered by "
        "bugs/crashes, performance, cheating, server/connectivity, matchmaking, balance, bad update, content shortage, "
        "monetization, or management/live operations?",
        "A distinct churn-relevant complaint outside the listed categories is expressed.",
        "No additional complaint outside the listed categories is expressed.",
    ),
}


def data_dir() -> Path:
    if DRIVE_DATA_DIR.exists() or Path("/content/drive/MyDrive").exists():
        DRIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DRIVE_DATA_DIR
    local = Path("./data")
    local.mkdir(parents=True, exist_ok=True)
    return local


def resolve_path(value: str | None, default_name: str) -> Path:
    return Path(value) if value else data_dir() / default_name


def review_id_for(row: pd.Series) -> str:
    rid = row.get("recommendationid")
    if pd.notna(rid) and str(rid).strip():
        return str(rid).strip()
    raw = f"{row.get('appid','')}|{row.get('timestamp_created','')}|{row.get('review','')}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:24]


def build_questions() -> dict[str, Noul]:
    return {
        key: Noul(
            instructions=instruction,
            criteria={"true": yes, "false": no},
        )
        for key, (instruction, yes, no) in QUESTION_SPECS.items()
    }


def load_reviews(path: Path, language: str, negative_only: bool) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    missing = {"appid", "review"} - set(df.columns)
    if missing:
        raise ValueError(f"{path.name} に必要な列がありません: {sorted(missing)}")

    for col in ["recommendationid", "language", "voted_up", "timestamp_created", "name", "category", "genre"]:
        if col not in df.columns:
            df[col] = pd.NA

    df = df[df["review"].notna()].copy()
    df["review"] = df["review"].astype(str).str.strip()
    df = df[df["review"].str.len() > 0].copy()

    if language.lower() != "all":
        df = df[df["language"].astype(str).str.lower() == language.lower()].copy()

    if negative_only:
        voted = df["voted_up"].astype(str).str.lower()
        df = df[voted.isin(["false", "0", "no"])].copy()

    df["review_id"] = df.apply(review_id_for, axis=1)
    return df.drop_duplicates("review_id", keep="last").reset_index(drop=True)


def processed_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        df = pd.read_csv(path, encoding="utf-8-sig", usecols=["review_id"])
        return set(df["review_id"].dropna().astype(str))
    except (ValueError, pd.errors.EmptyDataError):
        return set()


def append_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    frame = pd.DataFrame(rows)
    exists = path.exists()
    frame.to_csv(
        path,
        mode="a" if exists else "w",
        header=not exists,
        index=False,
        encoding="utf-8-sig",
    )


def make_base_output(row: pd.Series) -> dict:
    review_date = pd.NaT
    ts = pd.to_numeric(row.get("timestamp_created"), errors="coerce")
    if pd.notna(ts):
        review_date = pd.to_datetime(ts, unit="s", errors="coerce")
    if pd.isna(review_date) and pd.notna(row.get("review_date")):
        review_date = pd.to_datetime(row.get("review_date"), errors="coerce")

    category = row.get("category")
    if pd.isna(category):
        category = row.get("genre")

    return {
        "classified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "review_id": str(row["review_id"]),
        "recommendationid": row.get("recommendationid"),
        "appid": row.get("appid"),
        "name": row.get("name"),
        "category": category,
        "language": row.get("language"),
        "voted_up": row.get("voted_up"),
        "timestamp_created": row.get("timestamp_created"),
        "review_date": review_date,
        "review": row.get("review"),
    }


def classify_one(client: TypeSafeClient, row: pd.Series, questions: dict[str, Noul]) -> dict:
    # Do not send game identity, Steam user ID, or author information to the model.
    state = {
        "review_text": row["review"],
        "language": row.get("language"),
        "recommended_game": row.get("voted_up"),
    }
    response = client.system_one(state=state, questions=questions)

    out = make_base_output(row)
    out["jev_model"] = response.model
    out["jev_input_tokens"] = response.usage.input_tokens
    out["jev_output_tokens"] = response.usage.output_tokens
    out["relevant_complaint"] = response.nouls["relevant_complaint"].noul
    for label in LABELS:
        out[label] = response.nouls[label].noul
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--errors", default=None)
    p.add_argument("--language", default="english", help="english recommended; use all only after multilingual validation")
    p.add_argument("--negative-only", action="store_true")
    p.add_argument("--model", default=os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-latest"))
    p.add_argument("--limit", type=int, default=None, help="pilot limit after resume filtering")
    p.add_argument("--checkpoint-every", type=int, default=25)
    p.add_argument("--sleep", type=float, default=0.10)
    p.add_argument("--max-retries", type=int, default=4)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not os.getenv("TYPESAFE_API_KEY"):
        raise RuntimeError("TYPESAFE_API_KEY が未設定です。Colab Secrets等から環境変数に設定してください。")

    input_path = resolve_path(args.input, DEFAULT_INPUT)
    output_path = resolve_path(args.output, DEFAULT_OUTPUT)
    error_path = resolve_path(args.errors, DEFAULT_ERRORS)

    reviews = load_reviews(input_path, args.language, args.negative_only)
    done = processed_ids(output_path)
    pending = reviews[~reviews["review_id"].astype(str).isin(done)].copy()
    if args.limit is not None:
        pending = pending.head(args.limit)

    print(f"input: {input_path}")
    print(f"output: {output_path}")
    print(f"rows after filter: {len(reviews)}")
    print(f"resume processed: {len(done)}")
    print(f"pending this run: {len(pending)}")
    print(f"requested model: {args.model}")

    questions = build_questions()
    retry = RetryPolicy(
        max_retries=args.max_retries,
        backoff_initial=0.5,
        backoff_max=10.0,
        http_statuses={408, 429, *range(500, 600)},
        respect_retry_after=True,
        timeout=60.0,
    )

    success_buffer: list[dict] = []
    error_buffer: list[dict] = []
    total_input_tokens = 0

    with TypeSafeClient(model=args.model, retry=retry, timeout=20.0) as client:
        available = client.models.list()
        print("available models:", ", ".join(m.name for m in available))

        for position, (_, row) in enumerate(pending.iterrows(), start=1):
            try:
                result = classify_one(client, row, questions)
                success_buffer.append(result)
                total_input_tokens += int(result.get("jev_input_tokens") or 0)
                print(f"[{position}/{len(pending)}] OK appid={row.get('appid')} review_id={row['review_id']}")
                time.sleep(max(0.0, args.sleep))
            except Exception as error:
                error_buffer.append(
                    {
                        "failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        "review_id": str(row["review_id"]),
                        "appid": row.get("appid"),
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
                print(f"[{position}/{len(pending)}] ERROR {type(error).__name__}: {error}")

            if position % max(1, args.checkpoint_every) == 0:
                append_csv(output_path, success_buffer)
                append_csv(error_path, error_buffer)
                success_buffer.clear()
                error_buffer.clear()
                print("checkpoint saved")

    append_csv(output_path, success_buffer)
    append_csv(error_path, error_buffer)

    print("classification finished")
    print(f"input tokens this run: {total_input_tokens}")
    print("Raw probabilities saved. Final thresholds must be fixed after human validation.")


if __name__ == "__main__":
    main()
