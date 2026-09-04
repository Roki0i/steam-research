"""ピーク後3〜12か月の急減要因分析用Steam News収集。

レビュー本文は収集しない。旧factor_data_collect.pyとは別系統で、
発売・ピーク直後1〜2か月を除外した要因探索専用。
"""

import os
import time
from datetime import datetime

import pandas as pd
import requests


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"
TARGET_FILENAME = "factor_target_games_3to12.csv"
NEWS_FILENAME = "factor_news_3to12.csv"
STATUS_FILENAME = "factor_news_collection_status_3to12.csv"

REQUEST_INTERVAL_SEC = 1.0
REQUEST_TIMEOUT_SEC = 20
MAX_RETRIES = 4
NEWS_COUNT = 250
WINDOW_MONTHS = 2

NEWS_COLUMNS = [
    "appid",
    "name",
    "category",
    "target_drop_month",
    "gid",
    "title",
    "url",
    "is_external_url",
    "author",
    "contents",
    "feedlabel",
    "feedname",
    "tags",
    "date",
    "news_date",
]

STATUS_COLUMNS = [
    "appid",
    "name",
    "category",
    "target_drop_month",
    "news_done",
    "news_rows",
    "window_start_reached",
    "oldest_news_date",
    "newest_news_date",
    "news_error",
    "collected_at",
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "steam-research/1.0 academic-project"})


def get_data_dir():
    drive_root = "/content/drive/MyDrive"
    if os.path.exists(DRIVE_DATA_DIR) or os.path.exists(drive_root):
        os.makedirs(DRIVE_DATA_DIR, exist_ok=True)
        return DRIVE_DATA_DIR
    os.makedirs("./data", exist_ok=True)
    return "./data"


def get_path(filename):
    return os.path.join(get_data_dir(), filename)


def save_csv(df, filename, columns=None):
    out = df.copy()
    if columns is not None:
        for column in columns:
            if column not in out.columns:
                out[column] = None
        out = out[columns]
    path = get_path(filename)
    out.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {path} ({len(out)}行)")


def load_existing(filename, columns):
    path = get_path(filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(path, encoding="utf-8-sig")
    for column in columns:
        if column not in df.columns:
            df[column] = None
    return df[columns]


def request_json(url, params):
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
            if response.status_code == 429 or response.status_code >= 500:
                wait = min(30, 2 ** (attempt + 1))
                print(f"    HTTP {response.status_code}: {wait}秒待機")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt < MAX_RETRIES - 1:
                time.sleep(min(30, 2 ** (attempt + 1)))
    raise RuntimeError(f"API取得失敗: {last_error}")


def load_targets():
    path = get_path(TARGET_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} がありません。先に最新版decline_analysis.pyを実行してください。"
        )
    df = pd.read_csv(path, encoding="utf-8-sig")
    required = [
        "appid", "name", "category", "peak_month", "decline_rate_12m",
        "largest_drop_month_3to12", "largest_monthly_drop_rate_3to12",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{TARGET_FILENAME}に必要な列がありません: {missing}")
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["largest_drop_month_3to12"] = pd.to_datetime(
        df["largest_drop_month_3to12"], errors="coerce"
    )
    return (
        df.dropna(subset=["appid", "largest_drop_month_3to12"])
        .drop_duplicates("appid", keep="first")
        .reset_index(drop=True)
    )


def target_period(game):
    return game["largest_drop_month_3to12"].to_period("M")


def target_key(appid, drop_month):
    return int(appid), str(pd.Timestamp(drop_month).to_period("M"))


def fetch_news(game):
    drop_period = target_period(game)
    start_time = (drop_period - WINDOW_MONTHS).start_time
    end_time = (drop_period + WINDOW_MONTHS).end_time

    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    params = {
        "appid": int(game["appid"]),
        "count": NEWS_COUNT,
        "maxlength": 4000,
        "enddate": int(end_time.timestamp()),
        "format": "json",
    }
    data = request_json(url, params)
    items = data.get("appnews", {}).get("newsitems", [])

    rows = []
    for item in items:
        timestamp = item.get("date")
        news_date = pd.to_datetime(timestamp, unit="s", errors="coerce") if timestamp else pd.NaT
        tags = item.get("tags", [])
        if isinstance(tags, list):
            tags = ";".join(str(tag) for tag in tags)
        rows.append(
            {
                "appid": int(game["appid"]),
                "name": game["name"],
                "category": game["category"],
                "target_drop_month": str(drop_period),
                "gid": item.get("gid"),
                "title": item.get("title"),
                "url": item.get("url"),
                "is_external_url": item.get("is_external_url"),
                "author": item.get("author"),
                "contents": item.get("contents"),
                "feedlabel": item.get("feedlabel"),
                "feedname": item.get("feedname"),
                "tags": tags,
                "date": timestamp,
                "news_date": news_date,
            }
        )

    result = pd.DataFrame(rows, columns=NEWS_COLUMNS)
    valid_dates = pd.to_datetime(result["news_date"], errors="coerce").dropna()
    oldest = valid_dates.min() if not valid_dates.empty else None
    newest = valid_dates.max() if not valid_dates.empty else None
    meta = {
        "news_rows": len(result),
        "window_start_reached": bool(oldest is not None and oldest <= start_time),
        "oldest_news_date": oldest,
        "newest_news_date": newest,
    }
    return result, meta


def replace_rows(base_df, new_df, appid, drop_period):
    if base_df.empty:
        result = new_df.copy()
    else:
        keep = ~(
            (pd.to_numeric(base_df["appid"], errors="coerce") == int(appid))
            & (base_df["target_drop_month"].astype(str) == str(drop_period))
        )
        result = pd.concat([base_df.loc[keep], new_df], ignore_index=True)
    if not result.empty:
        result = result.drop_duplicates(["appid", "gid"], keep="last")
    return result


def main():
    print(f"保存先: {get_data_dir()}")
    print("factor news collection: peak +3〜+12 months acute-drop targets")

    targets = load_targets()
    news_df = load_existing(NEWS_FILENAME, NEWS_COLUMNS)
    status_df = load_existing(STATUS_FILENAME, STATUS_COLUMNS)

    done_keys = set()
    if not status_df.empty:
        done_mask = status_df["news_done"].astype(str).str.lower().isin(["true", "1", "yes"])
        for _, row in status_df.loc[done_mask].iterrows():
            try:
                done_keys.add(target_key(row["appid"], row["target_drop_month"]))
            except Exception:
                pass

    print(f"target games: {len(targets)}")
    print(f"resume done: {len(done_keys)}")

    for index, game in targets.iterrows():
        appid = int(game["appid"])
        drop_period = str(target_period(game))
        key = (appid, drop_period)
        print(f"[{index + 1}/{len(targets)}] {game['name']} ({appid}) / drop={drop_period}")

        if key in done_keys:
            print("  skip: 取得済み")
            continue

        status = {
            "appid": appid,
            "name": game["name"],
            "category": game["category"],
            "target_drop_month": drop_period,
            "news_done": False,
            "news_rows": 0,
            "window_start_reached": False,
            "oldest_news_date": None,
            "newest_news_date": None,
            "news_error": "",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
        }

        try:
            new_rows, meta = fetch_news(game)
            news_df = replace_rows(news_df, new_rows, appid, drop_period)
            status.update(meta)
            status["news_done"] = True
            print(
                f"  news={meta['news_rows']} / "
                f"window start reached={meta['window_start_reached']}"
            )
        except Exception as error:
            status["news_error"] = str(error)
            print(f"  error: {error}")

        if not status_df.empty:
            keep = ~(
                (pd.to_numeric(status_df["appid"], errors="coerce") == appid)
                & (status_df["target_drop_month"].astype(str) == drop_period)
            )
            status_df = status_df.loc[keep].copy()
        status_df = pd.concat([status_df, pd.DataFrame([status])], ignore_index=True)

        save_csv(news_df, NEWS_FILENAME, NEWS_COLUMNS)
        save_csv(status_df, STATUS_FILENAME, STATUS_COLUMNS)
        time.sleep(REQUEST_INTERVAL_SEC)

    done = status_df["news_done"].astype(str).str.lower().isin(["true", "1", "yes"])
    coverage = status_df["window_start_reached"].astype(str).str.lower().isin(["true", "1", "yes"])
    errors = status_df["news_error"].fillna("").astype(str).str.len() > 0

    print("\n===== 収集サマリー =====")
    print(f"target games: {len(targets)}")
    print(f"news rows: {len(news_df)}")
    print(f"news done: {int(done.sum())}/{len(targets)}")
    print(f"window start reached: {int(coverage.sum())}/{len(targets)}")
    print(f"news errors: {int(errors.sum())}")


if __name__ == "__main__":
    main()
