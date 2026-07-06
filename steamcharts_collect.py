import os
import time
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup


# SteamChartsに過度なアクセスをしないため、ゲームごとに間隔を空ける。
REQUEST_INTERVAL_SEC = 3.0
REQUEST_TIMEOUT_SEC = 20
HTTP_500_RETRY_COUNT = 3
VALID_GAMES_PER_CATEGORY = 100

DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"
GAME_CANDIDATES_POOL_FILENAME = "game_candidates_pool.csv"
GAME_CANDIDATES_VALID_FILENAME = "game_candidates_valid.csv"
STEAMCHARTS_MONTHLY_FILENAME = "steamcharts_monthly.csv"

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
    return os.path.join(get_data_dir(), GAME_CANDIDATES_POOL_FILENAME)


def save_csv(df, filename, columns=None):
    """今回の収集結果をCSVへ保存する。"""
    data_dir = get_data_dir()
    file_path = os.path.join(data_dir, filename)

    if columns is not None:
        output_df = df.copy()
        for column in columns:
            if column not in output_df.columns:
                output_df[column] = None
        output_df = output_df[columns]
    else:
        output_df = df.copy()

    output_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {file_path} ({len(output_df)}行)")
    return len(output_df)


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
    last_error = None

    for attempt in range(1, HTTP_500_RETRY_COUNT + 1):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
            response.raise_for_status()
            return response.text
        except requests.HTTPError as error:
            last_error = error
            status_code = error.response.status_code if error.response is not None else None
            if status_code != 500 or attempt >= HTTP_500_RETRY_COUNT:
                raise

            print(f"  SteamCharts 500 retry {attempt}/{HTTP_500_RETRY_COUNT}: {url}")
            time.sleep(REQUEST_INTERVAL_SEC)

    raise last_error


def load_candidate_pool():
    """本分析用の候補プールCSVからSteamCharts収集対象を読む。"""
    candidates_path = get_game_candidates_path()
    candidates_df = pd.read_csv(candidates_path, encoding="utf-8-sig")
    required_columns = ["appid", "name", "category"]
    missing_columns = [
        column for column in required_columns if column not in candidates_df.columns
    ]
    if missing_columns:
        raise ValueError(
            f"{GAME_CANDIDATES_POOL_FILENAME}に必要な列がありません: {missing_columns}"
        )

    candidates_df = candidates_df.dropna(subset=required_columns)
    candidates_df = candidates_df.drop_duplicates(
        subset=["appid"],
        keep="last",
    )
    candidates_df["appid"] = candidates_df["appid"].astype(int)
    candidates_df["category"] = candidates_df["category"].astype(str)
    candidates_df["name"] = candidates_df["name"].astype(str)
    return candidates_df


def make_game_from_candidate(row):
    category = str(row["category"])
    return {
        "appid": int(row["appid"]),
        "name": str(row["name"]),
        "category": category,
        # 後方互換用。旧分析コードがgenreを見る場合にも同じカテゴリ名を入れる。
        "genre": category,
        "type": "candidate",
    }


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

    if not rows:
        raise ValueError("SteamChartsの月次データがありません")

    has_monthly_history = False
    for row in rows:
        if row["month"] != "Last 30 Days":
            has_monthly_history = True
            break

    if not has_monthly_history:
        raise ValueError("SteamChartsの月次履歴データがありません")

    return pd.DataFrame(rows, columns=STEAMCHARTS_MONTHLY_COLUMNS)


def print_result_summary(category_stats, valid_df):
    print("category candidate counts:")
    for category, stats in category_stats.items():
        print(f"  {category}: {stats['candidates']}")

    print("category success counts:")
    for category, stats in category_stats.items():
        print(f"  {category}: {stats['success']}")

    print("category skip counts:")
    for category, stats in category_stats.items():
        print(f"  {category}: {stats['skip']}")

    total_valid_games = len(valid_df)
    unique_valid_appids = valid_df["appid"].nunique() if not valid_df.empty else 0
    duplicate_appid_count = total_valid_games - unique_valid_appids

    print(f"total valid games: {total_valid_games}")
    print(f"unique valid appids: {unique_valid_appids}")
    print(f"duplicate appid count: {duplicate_appid_count}")


def collect_steamcharts_monthly():
    candidates_df = load_candidate_pool()
    all_monthly_rows = []
    valid_candidate_rows = []
    category_stats = {}
    total_candidates = len(candidates_df)

    print(f"収集対象: {get_game_candidates_path()} を使用")
    print(f"候補ゲーム数: {total_candidates}")
    print(f"保存先: {get_data_dir()}")

    for category, category_df in candidates_df.groupby("category", sort=False):
        success_count = 0
        skip_count = 0
        candidate_count = len(category_df)
        category_stats[category] = {
            "candidates": candidate_count,
            "success": 0,
            "skip": 0,
        }

        print(f"カテゴリ処理: {category} 候補{candidate_count}本")

        for game_index, (_, candidate_row) in enumerate(category_df.iterrows(), start=1):
            if success_count >= VALID_GAMES_PER_CATEGORY:
                break

            game = make_game_from_candidate(candidate_row)
            print(
                f"収集中({game_index}/{candidate_count}): "
                f"{game['name']} ({game['appid']})"
            )

            try:
                monthly_df = fetch_steamcharts_monthly(game)
                all_monthly_rows.append(monthly_df)
                valid_candidate_rows.append(candidate_row.to_dict())
                success_count += 1
                category_stats[category]["success"] = success_count
                print(f"取得成功: {game['name']} {len(monthly_df)}行")
            except Exception as error:
                skip_count += 1
                category_stats[category]["skip"] = skip_count
                print(f"スキップ: {game['name']} / {error}")

            time.sleep(REQUEST_INTERVAL_SEC)

        print(
            f"カテゴリ終了: {category} "
            f"成功{success_count}本 / スキップ{skip_count}本"
        )

    if all_monthly_rows:
        monthly_df = pd.concat(all_monthly_rows, ignore_index=True)
    else:
        monthly_df = pd.DataFrame(columns=STEAMCHARTS_MONTHLY_COLUMNS)

    if valid_candidate_rows:
        valid_df = pd.DataFrame(valid_candidate_rows)
        valid_df = valid_df.drop_duplicates(subset=["appid"], keep="first")
    else:
        valid_df = pd.DataFrame(columns=candidates_df.columns)

    save_csv(
        valid_df,
        GAME_CANDIDATES_VALID_FILENAME,
        list(candidates_df.columns),
    )
    save_csv(
        monthly_df,
        STEAMCHARTS_MONTHLY_FILENAME,
        STEAMCHARTS_MONTHLY_COLUMNS,
    )
    print_result_summary(category_stats, valid_df)


def main():
    collect_steamcharts_monthly()
    print("SteamCharts月次データ収集完了")


if __name__ == "__main__":
    main()
