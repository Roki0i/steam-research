import os
import time
from datetime import datetime

import pandas as pd
import requests


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

TARGET_FILENAME = "factor_target_games.csv"
REVIEWS_RAW_FILENAME = "factor_reviews_raw_12m.csv"
REVIEW_SUMMARY_FILENAME = "factor_review_summary_12m.csv"
NEWS_FILENAME = "factor_news_12m.csv"
STATUS_FILENAME = "factor_collection_status_12m.csv"

MAX_REVIEWS_PER_GAME = 10000
REQUEST_INTERVAL_SEC = 1.5
REQUEST_TIMEOUT_SEC = 20
MAX_RETRIES = 4
NEWS_COUNT = 100
WINDOW_MONTHS = 2

REVIEWS_RAW_COLUMNS = [
    "appid",
    "name",
    "category",
    "target_drop_month",
    "recommendationid",
    "language",
    "review",
    "timestamp_created",
    "review_date",
    "voted_up",
    "playtime_forever",
    "steam_purchase",
    "received_for_free",
    "written_during_early_access",
]

REVIEW_SUMMARY_COLUMNS = [
    "appid",
    "name",
    "category",
    "target_drop_month",
    "review_count_around_drop",
    "positive_count_around_drop",
    "negative_count_around_drop",
    "negative_rate_around_drop",
]

NEWS_COLUMNS = [
    "appid",
    "name",
    "category",
    "target_drop_month",
    "gid",
    "title",
    "url",
    "author",
    "contents",
    "date",
    "news_date",
]

STATUS_COLUMNS = [
    "appid",
    "name",
    "category",
    "target_drop_month",
    "review_done",
    "review_target_reached",
    "review_hit_cap",
    "review_rows",
    "review_oldest_date",
    "review_newest_date",
    "news_done",
    "news_rows",
    "review_error",
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
    local_data_dir = "./data"
    os.makedirs(local_data_dir, exist_ok=True)
    return local_data_dir


def get_path(filename):
    return os.path.join(get_data_dir(), filename)


def save_csv(df, filename, columns=None):
    output_df = df.copy()
    if columns is not None:
        for column in columns:
            if column not in output_df.columns:
                output_df[column] = None
        output_df = output_df[columns]
    path = get_path(filename)
    output_df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {path} ({len(output_df)}行)")


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
                print(f"    HTTP {response.status_code}: {wait}秒待機して再試行")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            last_error = error
            if attempt < MAX_RETRIES - 1:
                time.sleep(min(30, 2 ** (attempt + 1)))
    raise RuntimeError(f"API取得失敗: {last_error}")


def load_target_games():
    df = pd.read_csv(get_path(TARGET_FILENAME), encoding="utf-8-sig")
    required = [
        "appid",
        "name",
        "category",
        "peak_month",
        "decline_rate_12m",
        "largest_drop_month_12m",
        "largest_monthly_drop_rate_12m",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(
            f"{TARGET_FILENAME}に必要な列がありません: {missing}\n"
            "最新版のdecline_analysis.pyを先に実行してください。"
        )

    df = df.dropna(subset=["appid", "largest_drop_month_12m", "decline_rate_12m"]).copy()
    df["appid"] = df["appid"].astype(int)
    for column in ["peak_month", "largest_drop_month_12m"]:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    df = df.dropna(subset=["largest_drop_month_12m"])
    return df.drop_duplicates("appid", keep="first").reset_index(drop=True)


def target_key(appid, target_drop_month):
    period = pd.Timestamp(target_drop_month).to_period("M")
    return int(appid), str(period)


def fetch_reviews(game):
    url = f"https://store.steampowered.com/appreviews/{game['appid']}"
    cursor = "*"
    rows = []

    drop_period = game["target_drop_month"].to_period("M")
    target_start = (drop_period - WINDOW_MONTHS).start_time
    target_reached = False

    while len(rows) < MAX_REVIEWS_PER_GAME:
        params = {
            "json": 1,
            "language": "all",
            "filter": "recent",
            "purchase_type": "all",
            "num_per_page": min(100, MAX_REVIEWS_PER_GAME - len(rows)),
            "cursor": cursor,
        }
        data = request_json(url, params)
        reviews = data.get("reviews", [])
        if not reviews:
            break

        page_dates = []
        for review in reviews:
            author = review.get("author", {})
            timestamp_created = review.get("timestamp_created")
            review_date = pd.NaT
            if timestamp_created:
                review_date = pd.to_datetime(timestamp_created, unit="s", errors="coerce")
                if not pd.isna(review_date):
                    page_dates.append(review_date)

            rows.append(
                {
                    "appid": game["appid"],
                    "name": game["name"],
                    "category": game["category"],
                    "target_drop_month": str(drop_period),
                    "recommendationid": review.get("recommendationid"),
                    "language": review.get("language"),
                    "review": review.get("review"),
                    "timestamp_created": timestamp_created,
                    "review_date": review_date,
                    "voted_up": review.get("voted_up"),
                    "playtime_forever": author.get("playtime_forever"),
                    "steam_purchase": review.get("steam_purchase"),
                    "received_for_free": review.get("received_for_free"),
                    "written_during_early_access": review.get("written_during_early_access"),
                }
            )

        if page_dates and min(page_dates) <= target_start:
            target_reached = True
            break

        next_cursor = data.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        time.sleep(REQUEST_INTERVAL_SEC)

    result = pd.DataFrame(rows, columns=REVIEWS_RAW_COLUMNS)
    valid_dates = pd.to_datetime(result["review_date"], errors="coerce").dropna()
    meta = {
        "review_target_reached": bool(target_reached),
        "review_hit_cap": len(result) >= MAX_REVIEWS_PER_GAME and not target_reached,
        "review_rows": len(result),
        "review_oldest_date": valid_dates.min() if not valid_dates.empty else None,
        "review_newest_date": valid_dates.max() if not valid_dates.empty else None,
    }
    return result, meta


def fetch_news(game):
    drop_period = game["target_drop_month"].to_period("M")
    end_time = (drop_period + WINDOW_MONTHS).end_time
    end_timestamp = int(end_time.timestamp())

    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    params = {
        "appid": game["appid"],
        "count": NEWS_COUNT,
        "maxlength": 2000,
        "enddate": end_timestamp,
        "format": "json",
    }
    data = request_json(url, params)
    news_items = data.get("appnews", {}).get("newsitems", [])

    rows = []
    for item in news_items:
        date = item.get("date")
        news_date = pd.NaT
        if date:
            news_date = pd.to_datetime(date, unit="s", errors="coerce")
        rows.append(
            {
                "appid": game["appid"],
                "name": game["name"],
                "category": game["category"],
                "target_drop_month": str(drop_period),
                "gid": item.get("gid"),
                "title": item.get("title"),
                "url": item.get("url"),
                "author": item.get("author"),
                "contents": item.get("contents"),
                "date": date,
                "news_date": news_date,
            }
        )
    return pd.DataFrame(rows, columns=NEWS_COLUMNS)


def make_review_summary(reviews_df, target_df):
    rows = []
    for _, target in target_df.iterrows():
        appid = int(target["appid"])
        drop_period = target["largest_drop_month_12m"].to_period("M")
        months = [drop_period + offset for offset in range(-WINDOW_MONTHS, WINDOW_MONTHS + 1)]

        part = reviews_df[reviews_df["appid"] == appid].copy()
        dates = pd.to_datetime(part["review_date"], errors="coerce")
        part = part[dates.dt.to_period("M").isin(months)]
        voted = part["voted_up"].astype(str).str.lower().isin(["true", "1", "yes"])
        review_count = len(part)
        positive_count = int(voted.sum())
        negative_count = review_count - positive_count
        rows.append(
            {
                "appid": appid,
                "name": target["name"],
                "category": target["category"],
                "target_drop_month": str(drop_period),
                "review_count_around_drop": review_count,
                "positive_count_around_drop": positive_count,
                "negative_count_around_drop": negative_count,
                "negative_rate_around_drop": (
                    negative_count / review_count if review_count > 0 else None
                ),
            }
        )
    return pd.DataFrame(rows, columns=REVIEW_SUMMARY_COLUMNS)


def latest_status_map(status_df):
    result = {}
    if status_df.empty:
        return result
    for _, row in status_df.iterrows():
        try:
            key = target_key(row["appid"], row["target_drop_month"])
            result[key] = row
        except Exception:
            continue
    return result


def replace_game_rows(base_df, new_df, appid, drop_period, id_columns):
    if base_df.empty:
        result = new_df.copy()
    else:
        keep = ~(
            (pd.to_numeric(base_df["appid"], errors="coerce") == int(appid))
            & (base_df["target_drop_month"].astype(str) == str(drop_period))
        )
        result = pd.concat([base_df.loc[keep], new_df], ignore_index=True)
    if result.empty:
        return result
    return result.drop_duplicates(subset=id_columns, keep="last")


def main():
    print(f"保存先: {get_data_dir()}")
    print("要因分析対象: 12か月固定衰退率のカテゴリ別上位5作品")
    target_df = load_target_games()

    reviews_all = load_existing(REVIEWS_RAW_FILENAME, REVIEWS_RAW_COLUMNS)
    news_all = load_existing(NEWS_FILENAME, NEWS_COLUMNS)
    status_df = load_existing(STATUS_FILENAME, STATUS_COLUMNS)
    status_map = latest_status_map(status_df)

    current_keys = {
        target_key(row["appid"], row["largest_drop_month_12m"])
        for _, row in target_df.iterrows()
    }
    if not reviews_all.empty:
        reviews_all = reviews_all[
            reviews_all.apply(
                lambda row: target_key(row["appid"], row["target_drop_month"]) in current_keys,
                axis=1,
            )
        ].copy()
    if not news_all.empty:
        news_all = news_all[
            news_all.apply(
                lambda row: target_key(row["appid"], row["target_drop_month"]) in current_keys,
                axis=1,
            )
        ].copy()

    status_rows = []

    for index, target in target_df.iterrows():
        drop_month = target["largest_drop_month_12m"]
        drop_period = str(drop_month.to_period("M"))
        key = target_key(target["appid"], drop_month)
        previous = status_map.get(key)

        game = {
            "appid": int(target["appid"]),
            "name": target["name"],
            "category": target["category"],
            "target_drop_month": drop_month,
        }
        print(f"[{index + 1}/{len(target_df)}] {game['name']} ({game['appid']}) / {drop_period}")

        review_done = bool(previous is not None and str(previous.get("review_done")).lower() == "true")
        news_done = bool(previous is not None and str(previous.get("news_done")).lower() == "true")

        status = {
            "appid": game["appid"],
            "name": game["name"],
            "category": game["category"],
            "target_drop_month": drop_period,
            "review_done": review_done,
            "review_target_reached": previous.get("review_target_reached") if previous is not None else False,
            "review_hit_cap": previous.get("review_hit_cap") if previous is not None else False,
            "review_rows": previous.get("review_rows") if previous is not None else 0,
            "review_oldest_date": previous.get("review_oldest_date") if previous is not None else None,
            "review_newest_date": previous.get("review_newest_date") if previous is not None else None,
            "news_done": news_done,
            "news_rows": previous.get("news_rows") if previous is not None else 0,
            "review_error": "",
            "news_error": "",
            "collected_at": datetime.now().isoformat(timespec="seconds"),
        }

        if not review_done:
            try:
                reviews_df, review_meta = fetch_reviews(game)
                reviews_all = replace_game_rows(
                    reviews_all,
                    reviews_df,
                    game["appid"],
                    drop_period,
                    ["appid", "target_drop_month", "recommendationid"],
                )
                status.update(review_meta)
                status["review_done"] = True
                print(
                    f"  reviews: {len(reviews_df)} / target reached: "
                    f"{review_meta['review_target_reached']}"
                )
            except Exception as error:
                status["review_error"] = str(error)
                print(f"  レビュー取得エラー: {error}")
            save_csv(reviews_all, REVIEWS_RAW_FILENAME, REVIEWS_RAW_COLUMNS)
            time.sleep(REQUEST_INTERVAL_SEC)
        else:
            print("  reviews: 取得済みのためスキップ")

        if not news_done:
            try:
                news_df = fetch_news(game)
                news_all = replace_game_rows(
                    news_all,
                    news_df,
                    game["appid"],
                    drop_period,
                    ["appid", "target_drop_month", "gid"],
                )
                status["news_done"] = True
                status["news_rows"] = len(news_df)
                print(f"  news: {len(news_df)}")
            except Exception as error:
                status["news_error"] = str(error)
                print(f"  ニュース取得エラー: {error}")
            save_csv(news_all, NEWS_FILENAME, NEWS_COLUMNS)
            time.sleep(REQUEST_INTERVAL_SEC)
        else:
            print("  news: 取得済みのためスキップ")

        status_rows.append(status)
        current_status = pd.DataFrame(status_rows, columns=STATUS_COLUMNS)
        save_csv(current_status, STATUS_FILENAME, STATUS_COLUMNS)
        status_map[key] = pd.Series(status)

    review_summary_df = make_review_summary(reviews_all, target_df)
    save_csv(review_summary_df, REVIEW_SUMMARY_FILENAME, REVIEW_SUMMARY_COLUMNS)

    final_status = pd.DataFrame(status_rows, columns=STATUS_COLUMNS)
    save_csv(final_status, STATUS_FILENAME, STATUS_COLUMNS)

    print("\n===== 収集サマリー =====")
    print(f"target games: {len(target_df)}")
    print(f"reviews rows: {len(reviews_all)}")
    print(f"news rows: {len(news_all)}")
    print(f"review target reached: {final_status['review_target_reached'].astype(str).str.lower().eq('true').sum()}/{len(final_status)}")
    print(f"review hit cap: {final_status['review_hit_cap'].astype(str).str.lower().eq('true').sum()}")
    print(f"review errors: {(final_status['review_error'].fillna('') != '').sum()}")
    print(f"news errors: {(final_status['news_error'].fillna('') != '').sum()}")


if __name__ == "__main__":
    main()
