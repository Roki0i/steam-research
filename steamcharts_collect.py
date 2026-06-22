import os
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

from games import GAMES


# 本採用ゲームだけ集める。予備ゲームも集める場合は ["core", "reserve"] に変更する。
TARGET_TYPES = ["core"]

# SteamChartsに過度なアクセスをしないため、ゲームごとに間隔を空ける。
REQUEST_INTERVAL_SEC = 3.0
REQUEST_TIMEOUT_SEC = 20

DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"
GAME_CANDIDATES_FILENAME = "game_candidates.csv"

STEAMCHARTS_MONTHLY_COLUMNS = [
    "appid",
    "name",
    "category",
    "genre",
    "type",
    "month",
    "avg_players",
    "gain",
    "gain_percent",
    "peak_players",
    "source_url",
    "collected_at",
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


def get_game_candidates_path():
    return os.path.join(get_data_dir(), GAME_CANDIDATES_FILENAME)


def save_csv_append_dedup(df, filename, subset_cols):
    """既存CSVに追記し、指定列が同じ行を重複削除して保存する。"""
    if df.empty:
        print(f"保存対象なし: {filename}")
        return 0

    data_dir = get_data_dir()
    file_path = os.path.join(data_dir, filename)

    if os.path.exists(file_path):
        existing_df = pd.read_csv(file_path, encoding="utf-8-sig")
        combined_df = pd.concat([existing_df, df], ignore_index=True)
    else:
        combined_df = df.copy()

    combined_df = combined_df.drop_duplicates(subset=subset_cols, keep="last")
    ordered_columns = [
        column for column in STEAMCHARTS_MONTHLY_COLUMNS if column in combined_df.columns
    ]
    other_columns = [
        column for column in combined_df.columns if column not in ordered_columns
    ]
    combined_df = combined_df[ordered_columns + other_columns]
    combined_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {file_path} ({len(combined_df)}行)")
    return len(combined_df)


def clean_number(value):
    """カンマ、%記号、空白などを取り除いて数値化する。"""
    if value is None:
        return None

    text = str(value).strip()
    if text in ["", "-", "N/A"]:
        return None

    cleaned_text = (
        text.replace(",", "")
        .replace("%", "")
        .replace("+", "")
        .replace("\xa0", "")
        .strip()
    )

    try:
        return float(cleaned_text)
    except ValueError:
        return None


def request_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; steam-research/1.0; "
            "+https://github.com/Roki0i/steam-research)"
        )
    }
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    return response.text


def load_games_from_candidates():
    """本分析用の候補CSVからSteamCharts収集対象を読む。"""
    candidates_path = get_game_candidates_path()
    candidates_df = pd.read_csv(candidates_path, encoding="utf-8-sig")
    required_columns = ["appid", "name", "category"]
    missing_columns = [
        column for column in required_columns if column not in candidates_df.columns
    ]
    if missing_columns:
        raise ValueError(
            f"{GAME_CANDIDATES_FILENAME}に必要な列がありません: {missing_columns}"
        )

    candidates_df = candidates_df.dropna(subset=required_columns)
    candidates_df = candidates_df.drop_duplicates(
        subset=["appid", "category"],
        keep="last",
    )

    games = []
    for _, row in candidates_df.iterrows():
        category = str(row["category"])
        games.append(
            {
                "appid": int(row["appid"]),
                "name": str(row["name"]),
                "category": category,
                # 後方互換用。旧分析コードがgenreを見る場合にも同じカテゴリ名を入れる。
                "genre": category,
                "type": "candidate",
            }
        )

    return games


def load_games_from_games_py():
    """試作用のgames.pyからSteamCharts収集対象を読む。"""
    target_games = []
    for game in GAMES:
        if game["type"] not in TARGET_TYPES:
            continue

        game_copy = game.copy()
        game_copy["category"] = game_copy.get("category", game_copy.get("genre"))
        target_games.append(game_copy)

    return target_games


def load_target_games():
    candidates_path = get_game_candidates_path()
    if os.path.exists(candidates_path):
        print(f"収集対象: {candidates_path} を使用")
        return load_games_from_candidates(), ["appid", "category", "month"]

    print("収集対象: games.py の GAMES を使用")
    return load_games_from_games_py(), ["appid", "month"]


def make_base_row(game, collected_at):
    return {
        "appid": game["appid"],
        "name": game["name"],
        "category": game.get("category", game.get("genre")),
        "genre": game["genre"],
        "type": game["type"],
        "collected_at": collected_at,
    }


def find_monthly_table(soup):
    """SteamChartsの月次データ表を探す。"""
    table = soup.find("table", id="app-monthly")
    if table is not None:
        return table

    for candidate in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in candidate.find_all("th")]
        if "Month" in headers and "Avg. Players" in headers and "Peak Players" in headers:
            return candidate

    return None


def fetch_steamcharts_monthly(game):
    source_url = f"https://steamcharts.com/app/{game['appid']}"
    html = request_html(source_url)
    soup = BeautifulSoup(html, "html.parser")
    table = find_monthly_table(soup)

    if table is None:
        raise ValueError("SteamChartsの月次表が見つかりません")

    collected_at = get_collected_at()
    rows = []

    # tbodyがない場合にも備えて、表内のtrを直接読む。
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        values = [cell.get_text(" ", strip=True) for cell in cells[:5]]
        if values[0] == "Month":
            continue

        row = make_base_row(game, collected_at)
        row.update(
            {
                "month": values[0],
                "avg_players": clean_number(values[1]),
                "gain": clean_number(values[2]),
                "gain_percent": clean_number(values[3]),
                "peak_players": clean_number(values[4]),
                "source_url": source_url,
            }
        )
        rows.append(row)

    return pd.DataFrame(rows, columns=STEAMCHARTS_MONTHLY_COLUMNS)


def collect_steamcharts_monthly():
    target_games, dedup_cols = load_target_games()
    all_rows = []

    print(f"対象ゲーム数: {len(target_games)}")
    print(f"保存先: {get_data_dir()}")

    for game_index, game in enumerate(target_games, start=1):
        print(f"収集中({game_index}/{len(target_games)}): {game['name']} ({game['appid']})")

        try:
            monthly_df = fetch_steamcharts_monthly(game)
            all_rows.append(monthly_df)
            print(f"取得件数: {game['name']} {len(monthly_df)}行")
        except Exception as error:
            print(f"SteamCharts取得エラー: {game['name']} / {error}")

        if game_index < len(target_games):
            time.sleep(REQUEST_INTERVAL_SEC)

    if all_rows:
        result_df = pd.concat(all_rows, ignore_index=True)
    else:
        result_df = pd.DataFrame(columns=STEAMCHARTS_MONTHLY_COLUMNS)

    saved_rows = save_csv_append_dedup(
        result_df,
        "steamcharts_monthly.csv",
        dedup_cols,
    )
    print(f"最終保存件数: {saved_rows}行")


def main():
    collect_steamcharts_monthly()
    print("SteamCharts月次データ収集完了")


if __name__ == "__main__":
    main()
