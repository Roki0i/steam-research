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

STEAMCHARTS_MONTHLY_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "genre",
    "type",
    "month",
    "avg_players",
    "gain",
    "gain_percent",
    "peak_players",
    "source_url",
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
        return 0

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


def make_base_row(game, collected_at):
    return {
        "collected_at": collected_at,
        "appid": game["appid"],
        "name": game["name"],
        "genre": game["genre"],
        "type": game["type"],
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
    target_games = [game for game in GAMES if game["type"] in TARGET_TYPES]
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
        ["appid", "month"],
    )
    print(f"最終保存件数: {saved_rows}行")


def main():
    collect_steamcharts_monthly()
    print("SteamCharts月次データ収集完了")


if __name__ == "__main__":
    main()
