import os
import time
from datetime import datetime

import pandas as pd
import requests


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

TARGET_FILENAME = "factor_target_games.csv"
REVIEWS_RAW_FILENAME = "factor_reviews_raw.csv"
REVIEW_SUMMARY_FILENAME = "factor_review_summary.csv"
NEWS_FILENAME = "factor_news.csv"

MAX_REVIEWS_PER_GAME = 500
REQUEST_INTERVAL_SEC = 1.5
REQUEST_TIMEOUT_SEC = 20
NEWS_COUNT = 100

REVIEWS_RAW_COLUMNS = [
    "appid",
    "name",
    "category",
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
    "review_count",
    "positive_count",
    "negative_count",
    "negative_rate",
    "avg_playtime_forever",
]

NEWS_COLUMNS = [
    "appid",
    "name",
    "category",
    "gid",
    "title",
    "url",
    "author",
    "contents",
    "date",
    "news_date",
]


def get_collected_at():
    return datetime.now().isoformat(timespec="seconds")


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


def save_csv(df, filename, columns):
    output_df = df.copy()
    for column in columns:
        if column not in output_df.columns:
            output_df[column] = None
    output_df = output_df[columns]

    file_path = get_path(filename)
    output_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {file_path} ({len(output_df)}行)")


def request_json(url, params):
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    return response.json()


def load_target_games():
    df = pd.read_csv(get_path(TARGET_FILENAME), encoding="utf-8-sig")
    required_columns = ["appid", "name", "category"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"{TARGET_FILENAME}に必要な列がありません: {missing_columns}")

    df = df.dropna(subset=required_columns).copy()
    df["appid"] = df["appid"].astype(int)
    return df.drop_duplicates(subset=["appid"], keep="first")


def fetch_reviews(game):
    url = f"https://store.steampowered.com/appreviews/{game['appid']}"
    cursor = "*"
    rows = []

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

        for review in reviews:
            author = review.get("author", {})
            timestamp_created = review.get("timestamp_created")
            review_date = None
            if timestamp_created:
                review_date = pd.to_datetime(timestamp_created, unit="s", errors="coerce")

            rows.append(
                {
                    "appid": game["appid"],
                    "name": game["name"],
                    "category": game["category"],
                    "recommendationid": review.get("recommendationid"),
                    "language": review.get("language"),
                    "review": review.get("review"),
                    "timestamp_created": timestamp_created,
                    "review_date": review_date,
                    "voted_up": review.get("voted_up"),
                    "playtime_forever": author.get("playtime_forever"),
                    "steam_purchase": review.get("steam_purchase"),
                    "received_for_free": review.get("received_for_free"),
                    "written_during_early_access": review.get(
                        "written_during_early_access"
                    ),
                }
            )

        next_cursor = data.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break

        cursor = next_cursor
        time.sleep(REQUEST_INTERVAL_SEC)

    return pd.DataFrame(rows, columns=REVIEWS_RAW_COLUMNS)


def fetch_news(game):
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    params = {
        "appid": game["appid"],
        "count": NEWS_COUNT,
        "maxlength": 1000,
        "format": "json",
    }
    data = request_json(url, params)
    news_items = data.get("appnews", {}).get("newsitems", [])

    rows = []
    for item in news_items:
        date = item.get("date")
        news_date = None
        if date:
            news_date = pd.to_datetime(date, unit="s", errors="coerce")

        rows.append(
            {
                "appid": game["appid"],
                "name": game["name"],
                "category": game["category"],
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
    if reviews_df.empty:
        return pd.DataFrame(columns=REVIEW_SUMMARY_COLUMNS)

    summary_df = (
        reviews_df.groupby(["appid", "name", "category"], as_index=False)
        .agg(
            review_count=("recommendationid", "count"),
            positive_count=("voted_up", "sum"),
            avg_playtime_forever=("playtime_forever", "mean"),
        )
    )
    summary_df["negative_count"] = summary_df["review_count"] - summary_df["positive_count"]
    summary_df["negative_rate"] = summary_df["negative_count"] / summary_df["review_count"]

    summary_df = target_df[["appid", "name", "category"]].merge(
        summary_df,
        on=["appid", "name", "category"],
        how="left",
    )
    summary_df[["review_count", "positive_count", "negative_count"]] = summary_df[
        ["review_count", "positive_count", "negative_count"]
    ].fillna(0)

    return summary_df[REVIEW_SUMMARY_COLUMNS]


def print_summary(target_df, reviews_df, news_df, review_summary_df):
    print(f"target games: {len(target_df)}")
    print(f"reviews rows: {len(reviews_df)}")
    print(f"news rows: {len(news_df)}")
    print(f"review summary rows: {len(review_summary_df)}")
    print("category target game counts:")

    for category, count in target_df["category"].value_counts(sort=False).items():
        print(f"  {category}: {count}")


def main():
    print(f"保存先: {get_data_dir()}")
    target_df = load_target_games()
    all_reviews = []
    all_news = []

    for _, game in target_df.iterrows():
        game_info = {
            "appid": int(game["appid"]),
            "name": game["name"],
            "category": game["category"],
        }
        print(f"収集中: {game_info['name']} ({game_info['appid']})")

        try:
            reviews_df = fetch_reviews(game_info)
            all_reviews.append(reviews_df)
            print(f"  reviews: {len(reviews_df)}")
        except Exception as error:
            print(f"  レビュー取得エラー: {error}")
        time.sleep(REQUEST_INTERVAL_SEC)

        try:
            news_df = fetch_news(game_info)
            all_news.append(news_df)
            print(f"  news: {len(news_df)}")
        except Exception as error:
            print(f"  ニュース取得エラー: {error}")
        time.sleep(REQUEST_INTERVAL_SEC)

    if all_reviews:
        reviews_df = pd.concat(all_reviews, ignore_index=True)
        reviews_df = reviews_df.drop_duplicates(subset=["recommendationid"], keep="last")
    else:
        reviews_df = pd.DataFrame(columns=REVIEWS_RAW_COLUMNS)

    if all_news:
        news_df = pd.concat(all_news, ignore_index=True)
        news_df = news_df.drop_duplicates(subset=["appid", "gid"], keep="last")
    else:
        news_df = pd.DataFrame(columns=NEWS_COLUMNS)

    review_summary_df = make_review_summary(reviews_df, target_df)

    save_csv(reviews_df, REVIEWS_RAW_FILENAME, REVIEWS_RAW_COLUMNS)
    save_csv(review_summary_df, REVIEW_SUMMARY_FILENAME, REVIEW_SUMMARY_COLUMNS)
    save_csv(news_df, NEWS_FILENAME, NEWS_COLUMNS)
    print_summary(target_df, reviews_df, news_df, review_summary_df)


if __name__ == "__main__":
    main()
