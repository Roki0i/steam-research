import os
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup


CATEGORY_TAGS = {
    "FPS / Shooter": ["FPS", "Shooter", "Third-Person Shooter"],
    "Action": ["Action", "Hack and Slash", "Fighting"],
    "RPG": ["RPG", "Action RPG", "JRPG", "Roguelike", "Turn-Based RPG"],
    "Strategy": ["Strategy", "Turn-Based Strategy", "RTS", "4X", "Tower Defense"],
    "Simulation": ["Simulation", "Building", "Automation", "Farming Sim", "Life Sim"],
    "Survival / Open World": ["Survival", "Open World", "Sandbox", "Space", "Sci-fi"],
    "Horror / Mystery": ["Horror", "Mystery", "Detective"],
    "Sports / Racing": ["Racing", "Sports", "Sports Management"],
    "Casual / Puzzle": ["Casual", "Puzzle", "Visual Novel", "Story Rich"],
    "Co-op / Multiplayer": ["Co-op", "Multiplayer", "Party", "Card Game", "Board Game"],
}

# 一部カテゴリだけ集めたい場合は、例: ["RPG", "Strategy"] のように変更する。
TARGET_CATEGORIES = list(CATEGORY_TAGS.keys())

MAX_GAMES_PER_CATEGORY = 100

# Steam Storeに過度なアクセスをしないため、タグごとに間隔を空ける。
REQUEST_INTERVAL_SEC = 2.0
REQUEST_TIMEOUT_SEC = 30
STORE_SEARCH_COUNT = 50

DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"
STEAM_STORE_SEARCH_RESULTS_URL = "https://store.steampowered.com/search/results/"

# Steam Storeのタグ検索では、タグ名ではなくタグIDをtags=に指定する。
# CATEGORY_TAGSは分析カテゴリの定義として維持し、検索時だけこの対応表を使う。
STEAM_TAG_IDS = {
    "FPS": 1663,
    "Shooter": 1774,
    "Third-Person Shooter": 3814,
    "Action": 19,
    "Hack and Slash": 1646,
    "Fighting": 1743,
    "RPG": 122,
    "Action RPG": 4231,
    "JRPG": 4434,
    "Roguelike": 1716,
    "Turn-Based RPG": 21725,
    "Strategy": 9,
    "Turn-Based Strategy": 1741,
    "RTS": 1676,
    "4X": 1670,
    "Tower Defense": 1645,
    "Simulation": 599,
    "Building": 1643,
    "Automation": 255534,
    "Farming Sim": 87918,
    "Life Sim": 10235,
    "Survival": 1662,
    "Open World": 1695,
    "Sandbox": 3810,
    "Space": 1755,
    "Sci-fi": 3942,
    "Horror": 1667,
    "Mystery": 5716,
    "Detective": 5611,
    "Racing": 699,
    "Sports": 701,
    "Sports Management": 12472,
    "Casual": 597,
    "Puzzle": 1664,
    "Visual Novel": 3799,
    "Story Rich": 1742,
    "Co-op": 1685,
    "Multiplayer": 3859,
    "Party": 7108,
    "Card Game": 1666,
    "Board Game": 1770,
}

GAME_CANDIDATE_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "category",
    "matched_tag",
    "owners",
    "positive",
    "negative",
    "ccu",
    "source",
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


def save_csv_dedup(df, filename, subset_cols):
    """今回収集した候補を重複削除してCSVへ保存する。"""
    if df.empty:
        print(f"保存対象なし: {filename}")
        return 0

    data_dir = get_data_dir()
    file_path = os.path.join(data_dir, filename)

    combined_df = df.copy()
    combined_df = combined_df.drop_duplicates(subset=subset_cols, keep="last")
    combined_df = combined_df[GAME_CANDIDATE_COLUMNS]
    combined_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {file_path} ({len(combined_df)}行)")
    return len(combined_df)


def print_candidate_summary(df):
    """候補CSVの重複状態を確認できるよう、最終集計を出力する。"""
    total_rows = len(df)
    unique_appids = df["appid"].nunique() if not df.empty else 0
    duplicate_appid_count = total_rows - unique_appids

    print(f"total rows: {total_rows}")
    print(f"unique appids: {unique_appids}")
    print("category counts:")

    if df.empty:
        print("  (none)")
    else:
        category_counts = df["category"].value_counts(sort=False)
        for category, count in category_counts.items():
            print(f"  {category}: {count}")

    print(f"duplicate appid count: {duplicate_appid_count}")


def to_int(value):
    """appidなどの値を整数にする。変換できない場合はNoneを返す。"""
    if value is None:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def request_store_search(tag, start=0, count=STORE_SEARCH_COUNT, use_tag_id=True):
    tag_id = STEAM_TAG_IDS.get(tag)
    params = {
        "query": "",
        "start": start,
        "count": count,
        "dynamic_data": "",
        "sort_by": "_ASC",
        "category1": 998,
        "supportedlang": "english",
        "snr": "1_7_7_230_7",
        "infinite": 1,
        "cc": "us",
        "l": "english",
    }
    if use_tag_id and tag_id is not None:
        params["tags"] = tag_id
    else:
        # 対応表にないタグが追加された場合も、全体を止めずタグ名検索で試す。
        params["term"] = tag

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; steam-research/1.0; "
            "+https://github.com/Roki0i/steam-research)"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
    response = requests.get(
        STEAM_STORE_SEARCH_RESULTS_URL,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except ValueError:
        return {"results_html": response.text}

    if not isinstance(data, dict) or "results_html" not in data:
        raise ValueError("Steam Store検索結果のレスポンス形式が想定外です")

    return data


def parse_store_results(results_html):
    soup = BeautifulSoup(results_html, "html.parser")
    rows = []

    for result in soup.select("a.search_result_row"):
        appid = to_int(
            result.get("data-ds-appid")
            or result.get("data-ds-itemkey", "").replace("App_", "")
        )
        title = result.select_one(".title")
        name = title.get_text(" ", strip=True) if title is not None else None

        if appid and name:
            rows.append({"appid": appid, "name": name})

    return rows


def make_candidate_row(game_data, category, matched_tag, collected_at):
    return {
        "collected_at": collected_at,
        "appid": game_data.get("appid"),
        "name": game_data.get("name"),
        "category": category,
        "matched_tag": matched_tag,
        "owners": None,
        "positive": None,
        "negative": None,
        "ccu": None,
        "source": "Steam Store",
    }


def fetch_candidates_by_tag(category, tag, excluded_appids, max_rows):
    collected_at = get_collected_at()
    rows = []
    start = 0
    selected_appids = set()

    while len(rows) < max_rows:
        data = request_store_search(tag, start=start)
        games = parse_store_results(data.get("results_html", ""))

        if not games and start == 0 and STEAM_TAG_IDS.get(tag) is not None:
            data = request_store_search(tag, start=start, use_tag_id=False)
            games = parse_store_results(data.get("results_html", ""))

        if not games:
            break

        for game_data in games:
            appid = game_data.get("appid")
            if appid in excluded_appids or appid in selected_appids:
                continue

            row = make_candidate_row(game_data, category, tag, collected_at)
            rows.append(row)
            selected_appids.add(appid)

            if len(rows) >= max_rows:
                break

        if len(games) < STORE_SEARCH_COUNT:
            break

        start += STORE_SEARCH_COUNT
        time.sleep(REQUEST_INTERVAL_SEC)

    return pd.DataFrame(rows, columns=GAME_CANDIDATE_COLUMNS)


def collect_candidates_for_category(category, tags, used_appids):
    print(f"カテゴリ収集中: {category}")
    tag_dfs = []
    category_appids = set()

    for tag_index, tag in enumerate(tags, start=1):
        remaining_count = MAX_GAMES_PER_CATEGORY - len(category_appids)
        if remaining_count <= 0:
            break

        print(f"  タグ取得({tag_index}/{len(tags)}): {tag}")

        try:
            excluded_appids = used_appids | category_appids
            tag_df = fetch_candidates_by_tag(
                category,
                tag,
                excluded_appids,
                remaining_count,
            )

            if not tag_df.empty:
                category_appids.update(tag_df["appid"].dropna().tolist())

            tag_dfs.append(tag_df)
            print(f"  取得件数: {tag} {len(tag_df)}行")
        except Exception as error:
            print(f"  Steam Store取得エラー: {category} / {tag} / {error}")

        if tag_index < len(tags):
            time.sleep(REQUEST_INTERVAL_SEC)

    if not tag_dfs:
        return pd.DataFrame(columns=GAME_CANDIDATE_COLUMNS)

    selected_df = pd.concat(tag_dfs, ignore_index=True)
    selected_df = selected_df.drop_duplicates(subset=["appid"], keep="first")
    selected_df = selected_df.head(MAX_GAMES_PER_CATEGORY)

    print(f"カテゴリ候補数: {category} {len(selected_df)}本")
    return selected_df


def collect_all_candidates():
    all_rows = []
    used_appids = set()
    target_categories = [
        category for category in TARGET_CATEGORIES if category in CATEGORY_TAGS
    ]

    print(f"対象カテゴリ数: {len(target_categories)}")
    print(f"カテゴリごとの最大候補数: {MAX_GAMES_PER_CATEGORY}")
    print(f"保存先: {get_data_dir()}")

    for category_index, category in enumerate(target_categories, start=1):
        print(f"処理中({category_index}/{len(target_categories)}): {category}")

        try:
            category_df = collect_candidates_for_category(
                category,
                CATEGORY_TAGS[category],
                used_appids,
            )
            used_appids.update(category_df["appid"].dropna().tolist())
            all_rows.append(category_df)
        except Exception as error:
            # 1カテゴリで失敗しても、他カテゴリの収集は続ける。
            print(f"カテゴリ処理エラー: {category} / {error}")

        if category_index < len(target_categories):
            time.sleep(REQUEST_INTERVAL_SEC)

    if all_rows:
        result_df = pd.concat(all_rows, ignore_index=True)
    else:
        result_df = pd.DataFrame(columns=GAME_CANDIDATE_COLUMNS)

    result_df = result_df.dropna(subset=["appid"])
    result_df = result_df.drop_duplicates(subset=["appid"], keep="first")
    print_candidate_summary(result_df)

    saved_rows = save_csv_dedup(
        result_df,
        "game_candidates.csv",
        ["appid"],
    )
    print(f"最終保存件数: {saved_rows}行")


def main():
    collect_all_candidates()
    print("ゲーム候補収集完了")


if __name__ == "__main__":
    main()
