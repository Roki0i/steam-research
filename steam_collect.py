import os
import time
from datetime import datetime

import pandas as pd
import requests

from games import GAMES


# 本採用ゲームだけ集める。予備ゲームも集める場合は ["core", "reserve"] に変更する。
TARGET_TYPES = ["core"]

# レビュー取得ページ数。1ページあたり最大100件を取得する。
MAX_REVIEW_PAGES = 1

REQUEST_INTERVAL_SECONDS = 1.5
REQUEST_TIMEOUT_SECONDS = 20

DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

CURRENT_PLAYERS_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "genre",
    "type",
    "current_players",
]

REVIEW_SUMMARY_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "genre",
    "type",
    "review_score",
    "review_score_desc",
    "total_positive",
    "total_negative",
    "total_reviews",
]

REVIEWS_RAW_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "genre",
    "type",
    "recommendationid",
    "steamid",
    "language",
    "review",
    "voted_up",
    "votes_up",
    "votes_funny",
    "weighted_vote_score",
    "playtime_forever",
    "playtime_at_review",
    "timestamp_created",
    "timestamp_updated",
]

NEWS_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "genre",
    "type",
    "gid",
    "title",
    "url",
    "is_external_url",
    "author",
    "contents",
    "date",
]


def get_collected_at():
    return datetime.now().isoformat(timespec="seconds")


def get_data_dir():
    """Google Driveが使える場合はDrive、ない場合はローカルdataを使う。"""
    drive_root = "/content/drive/MyDrive"
    if os.path.exists(DRIVE_DATA_DIR) or os.path.exists(drive_root):
        os.makedirs(DRIVE_DATA_DIR, exist_ok=True)
        return DRIVE_DATA_DIR

    local_data_dir = "./data"
    os.makedirs(local_data_dir, exist_ok=True)
    return local_data_dir


def save_csv_append_dedup(df, filename, subset_cols):
    """既存CSVに追記し、指定列が同じ行を重複削除して保存する。"""
    if df.empty:
        print(f"保存対象なし: {filename}")
        return

    data_dir = get_data_dir()
    file_path = os.path.join(data_dir, filename)

    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path, encoding="utf-8-sig")
        combined_df = pd.concat([existing_df, df], ignore_index=True)
    else:
        combined_df = df.copy()

    combined_df = combined_df.drop_duplicates(subset=subset_cols, keep="last")
    combined_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {file_path} ({len(combined_df)}行)")


def request_json(url, params=None):
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def make_base_row(game, collected_at):
    return {
        "collected_at": collected_at,
        "appid": game["appid"],
        "name": game["name"],
        "genre": game["genre"],
        "type": game["type"],
    }


def fetch_current_players(game):
    url = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
    params = {"appid": game["appid"]}
    data = request_json(url, params=params)

    row = make_base_row(game, get_collected_at())
    row["current_players"] = data.get("response", {}).get("player_count")
    return pd.DataFrame([row], columns=CURRENT_PLAYERS_COLUMNS)


def fetch_review_summary(game):
    url = f"https://store.steampowered.com/appreviews/{game['appid']}"
    params = {
        "json": 1,
        "language": "all",
        "filter": "recent",
        "purchase_type": "all",
        "num_per_page": 0,
    }
    data = request_json(url, params=params)
    summary = data.get("query_summary", {})

    row = make_base_row(game, get_collected_at())
    row.update(
        {
            "review_score": summary.get("review_score"),
            "review_score_desc": summary.get("review_score_desc"),
            "total_positive": summary.get("total_positive"),
            "total_negative": summary.get("total_negative"),
            "total_reviews": summary.get("total_reviews"),
        }
    )
    return pd.DataFrame([row], columns=REVIEW_SUMMARY_COLUMNS)


def fetch_reviews_raw(game, max_pages):
    url = f"https://store.steampowered.com/appreviews/{game['appid']}"
    cursor = "*"
    rows = []

    for page in range(max_pages):
        params = {
            "json": 1,
            "language": "all",
            "filter": "recent",
            "purchase_type": "all",
            "num_per_page": 100,
            "cursor": cursor,
        }
        data = request_json(url, params=params)
        reviews = data.get("reviews", [])

        if not reviews:
            print(f"レビューなし: {game['name']} page={page + 1}")
            break

        collected_at = get_collected_at()
        for review in reviews:
            author = review.get("author", {})
            row = make_base_row(game, collected_at)
            row.update(
                {
                    "recommendationid": review.get("recommendationid"),
                    "steamid": author.get("steamid"),
                    "language": review.get("language"),
                    "review": review.get("review"),
                    "voted_up": review.get("voted_up"),
                    "votes_up": review.get("votes_up"),
                    "votes_funny": review.get("votes_funny"),
                    "weighted_vote_score": review.get("weighted_vote_score"),
                    "playtime_forever": author.get("playtime_forever"),
                    "playtime_at_review": author.get("playtime_at_review"),
                    "timestamp_created": review.get("timestamp_created"),
                    "timestamp_updated": review.get("timestamp_updated"),
                }
            )
            rows.append(row)

        next_cursor = data.get("cursor")
        if not next_cursor or next_cursor == cursor:
            break

        cursor = next_cursor
        time.sleep(REQUEST_INTERVAL_SECONDS)

    return pd.DataFrame(rows, columns=REVIEWS_RAW_COLUMNS)


def fetch_news(game):
    url = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    params = {
        "appid": game["appid"],
        "count": 5,
        "maxlength": 500,
        "format": "json",
    }
    data = request_json(url, params=params)
    news_items = data.get("appnews", {}).get("newsitems", [])

    collected_at = get_collected_at()
    rows = []
    for item in news_items:
        row = make_base_row(game, collected_at)
        row.update(
            {
                "gid": item.get("gid"),
                "title": item.get("title"),
                "url": item.get("url"),
                "is_external_url": item.get("is_external_url"),
                "author": item.get("author"),
                "contents": item.get("contents"),
                "date": item.get("date"),
            }
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=NEWS_COLUMNS)


def collect_one_game(game):
    print(f"収集中: {game['name']} ({game['appid']})")

    try:
        current_players_df = fetch_current_players(game)
        save_csv_append_dedup(
            current_players_df,
            "current_players.csv",
            ["collected_at", "appid"],
        )
        time.sleep(REQUEST_INTERVAL_SECONDS)
    except Exception as error:
        print(f"現在プレイヤー数の取得エラー: {game['name']} / {error}")

    try:
        review_summary_df = fetch_review_summary(game)
        save_csv_append_dedup(
            review_summary_df,
            "review_summary.csv",
            ["collected_at", "appid"],
        )
        time.sleep(REQUEST_INTERVAL_SECONDS)
    except Exception as error:
        print(f"レビュー概要の取得エラー: {game['name']} / {error}")

    try:
        reviews_raw_df = fetch_reviews_raw(game, MAX_REVIEW_PAGES)
        save_csv_append_dedup(
            reviews_raw_df,
            "reviews_raw.csv",
            ["recommendationid"],
        )
        time.sleep(REQUEST_INTERVAL_SECONDS)
    except Exception as error:
        print(f"生レビューの取得エラー: {game['name']} / {error}")

    try:
        news_df = fetch_news(game)
        save_csv_append_dedup(news_df, "news.csv", ["gid"])
        time.sleep(REQUEST_INTERVAL_SECONDS)
    except Exception as error:
        print(f"ニュースの取得エラー: {game['name']} / {error}")


def main():
    target_games = [game for game in GAMES if game["type"] in TARGET_TYPES]
    print(f"対象ゲーム数: {len(target_games)}")
    print(f"保存先: {get_data_dir()}")

    for game in target_games:
        try:
            collect_one_game(game)
        except Exception as error:
            print(f"ゲーム処理全体のエラー: {game['name']} / {error}")
            continue

    print("収集完了")


if __name__ == "__main__":
    main()
