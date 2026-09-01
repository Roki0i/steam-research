import os
import time
from datetime import datetime

import pandas as pd
import requests


# Steam Review APIに過度な負荷をかけないため、ゲームごとに間隔を空ける。
REQUEST_INTERVAL_SEC = 1.5
REQUEST_TIMEOUT_SEC = 20
DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"
INPUT_FILENAME = "game_candidates_valid.csv"
OUTPUT_FILENAME = "review_summary_all.csv"
OUTPUT_COLUMNS = [
    "collected_at",
    "appid",
    "name",
    "category",
    "total_positive",
    "total_negative",
    "total_reviews",
    "review_score",
    "review_score_desc",
    "negative_rate",
]


def get_data_dir():
    """Google Driveが使える場合はDrive、ない場合はローカルdataを使う。"""
    drive_root = "/content/drive/MyDrive"
    if os.path.exists(DRIVE_DATA_DIR) or os.path.exists(drive_root):
        os.makedirs(DRIVE_DATA_DIR, exist_ok=True)
        return DRIVE_DATA_DIR

    local_data_dir = "./data"
    os.makedirs(local_data_dir, exist_ok=True)
    return local_data_dir


def get_path(filename):
    return os.path.join(get_data_dir(), filename)


def load_candidates():
    input_path = get_path(INPUT_FILENAME)
    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"入力CSVが見つかりません: {input_path}\n"
            "先にsteamcharts_collect.pyを実行してgame_candidates_valid.csvを作成してください。"
        )

    candidates_df = pd.read_csv(input_path, encoding="utf-8-sig")
    required_columns = ["appid", "name", "category"]
    missing_columns = [c for c in required_columns if c not in candidates_df.columns]
    if missing_columns:
        raise ValueError(f"{INPUT_FILENAME}に必要な列がありません: {missing_columns}")

    candidates_df = candidates_df.dropna(subset=required_columns).copy()
    candidates_df["appid"] = pd.to_numeric(
        candidates_df["appid"], errors="coerce"
    ).astype("Int64")
    candidates_df = candidates_df.dropna(subset=["appid"])
    candidates_df["appid"] = candidates_df["appid"].astype(int)

    duplicate_count = int(candidates_df["appid"].duplicated().sum())
    if duplicate_count:
        print(f"警告: 入力にappid重複が{duplicate_count}件あります。先頭行を採用します。")
        candidates_df = candidates_df.drop_duplicates("appid", keep="first")

    return candidates_df.reset_index(drop=True)


def load_existing_results():
    """再開用に、必要な集計値が揃った既存行だけを有効とみなす。"""
    output_path = get_path(OUTPUT_FILENAME)
    if not os.path.exists(output_path):
        return pd.DataFrame(columns=OUTPUT_COLUMNS), set()

    try:
        existing_df = pd.read_csv(output_path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=OUTPUT_COLUMNS), set()

    for column in OUTPUT_COLUMNS:
        if column not in existing_df.columns:
            existing_df[column] = pd.NA

    existing_df["appid"] = pd.to_numeric(existing_df["appid"], errors="coerce")
    valid_mask = existing_df["appid"].notna()
    valid_mask &= existing_df[["total_positive", "total_negative", "total_reviews"]].notna().all(axis=1)
    valid_appids = set(existing_df.loc[valid_mask, "appid"].astype(int))
    existing_df = existing_df[existing_df["appid"].isin(valid_appids)].copy()
    existing_df["appid"] = existing_df["appid"].astype(int)
    existing_df = existing_df.drop_duplicates("appid", keep="last")
    return existing_df[OUTPUT_COLUMNS], valid_appids


def fetch_review_summary(session, game):
    url = f"https://store.steampowered.com/appreviews/{game['appid']}"
    params = {
        "json": 1,
        "language": "all",
        "purchase_type": "all",
        # query_summaryだけが目的なのでレビュー本文を返させない。
        "num_per_page": 0,
    }
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
    response.raise_for_status()
    payload = response.json()
    if payload.get("success") != 1:
        raise ValueError("Steam Review APIがsuccess=1を返しませんでした")
    summary = payload.get("query_summary")
    if not isinstance(summary, dict):
        raise ValueError("レスポンスにquery_summaryがありません")

    total_positive = pd.to_numeric(summary.get("total_positive"), errors="coerce")
    total_negative = pd.to_numeric(summary.get("total_negative"), errors="coerce")
    total_reviews = pd.to_numeric(summary.get("total_reviews"), errors="coerce")
    negative_rate = (
        float(total_negative) / float(total_reviews)
        if pd.notna(total_negative) and pd.notna(total_reviews) and total_reviews > 0
        else None
    )
    return {
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "appid": int(game["appid"]),
        "name": str(game["name"]),
        "category": str(game["category"]),
        "total_positive": total_positive if pd.notna(total_positive) else None,
        "total_negative": total_negative if pd.notna(total_negative) else None,
        "total_reviews": total_reviews if pd.notna(total_reviews) else None,
        "review_score": summary.get("review_score"),
        "review_score_desc": summary.get("review_score_desc"),
        "negative_rate": negative_rate,
    }


def save_results(rows):
    output_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not output_df.empty:
        output_df["appid"] = pd.to_numeric(output_df["appid"], errors="coerce").astype("Int64")
        output_df = output_df.dropna(subset=["appid"])
        output_df["appid"] = output_df["appid"].astype(int)
        output_df = output_df.drop_duplicates("appid", keep="last")

    output_path = get_path(OUTPUT_FILENAME)
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_df


def collect_review_summaries():
    candidates_df = load_candidates()
    existing_df, valid_appids = load_existing_results()
    result_rows = existing_df.to_dict("records")
    success_appids = set(valid_appids)
    failed_appids = []

    print(f"対象ゲーム数: {len(candidates_df)}")
    print(f"resume対象（取得済み）: {len(valid_appids)}")
    print(f"保存先: {get_path(OUTPUT_FILENAME)}")

    session = requests.Session()
    session.headers.update(
        {"User-Agent": "steam-research/1.0 (graduation research; review summary collection)"}
    )

    pending_df = candidates_df[~candidates_df["appid"].isin(valid_appids)]
    for position, game in enumerate(pending_df.to_dict("records"), start=1):
        print(f"取得中({position}/{len(pending_df)}): {game['name']} ({game['appid']})")
        try:
            result_rows.append(fetch_review_summary(session, game))
            success_appids.add(int(game["appid"]))
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else "不明"
            print(f"  HTTPエラー {status}: {game['name']} ({game['appid']})")
            failed_appids.append(int(game["appid"]))
        except (requests.RequestException, ValueError) as error:
            print(f"  取得失敗: {game['name']} ({game['appid']}) / {error}")
            failed_appids.append(int(game["appid"]))
        finally:
            # 中断時にも、それまでの成功分をresumeできるよう逐次保存する。
            save_results(result_rows)
            time.sleep(REQUEST_INTERVAL_SEC)

    output_df = save_results(result_rows)
    duplicate_count = int(output_df["appid"].duplicated().sum()) if not output_df.empty else 0
    if duplicate_count:
        raise RuntimeError(f"出力にappid重複が{duplicate_count}件あります")

    successful_candidates = candidates_df[candidates_df["appid"].isin(success_appids)]
    category_counts = successful_candidates["category"].value_counts(sort=False)
    print(f"対象ゲーム数: {len(candidates_df)}")
    print(f"取得成功: {len(successful_candidates)}")
    print(f"失敗: {len(failed_appids)}")
    print("カテゴリ別成功数:")
    for category, count in category_counts.items():
        print(f"  {category}: {count}")
    print(f"appid重複: {duplicate_count}")


def main():
    collect_review_summaries()


if __name__ == "__main__":
    main()
