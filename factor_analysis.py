"""Steamゲームの運用中急減に関する探索的要因分析。

主対象:
- 12か月固定主分析対象のうち、ピーク後3〜12か月で最大月次下落が
  大きい50作品（10カテゴリ×5作品）。

目的:
- 発売・ピーク直後1〜2か月の自然な反動を除外し、運用中の急減期に
  どのような出来事が観測されたかを整理する。

重要:
- Steam Community Announcementを一次資料として優先する。
- 外部ニュースは補助資料として分離する。
- 時間的一致は因果関係を証明しない。
- 自動キーワード分類は要因候補の探索用であり、最終判断は手動確認する。
"""

import os
import re

import pandas as pd


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

TARGET_FILENAME = "factor_target_games_3to12.csv"
NEWS_FILENAME = "factor_news_3to12.csv"
STATUS_FILENAME = "factor_news_collection_status_3to12.csv"

NEWS_EVENTS_FILENAME = "factor_news_events_3to12.csv"
GAME_SUMMARY_FILENAME = "factor_game_summary_3to12.csv"
CATEGORY_SUMMARY_FILENAME = "factor_category_summary_3to12.csv"
EVIDENCE_FILENAME = "factor_evidence_3to12.csv"
LABELS_TEMPLATE_FILENAME = "factor_labels_template_3to12.csv"

WINDOW_MONTHS = 2
OFFICIAL_FEEDNAME = "steam_community_announcements"

NEWS_EVENT_GROUPS = {
    "maintenance_outage": [
        "maintenance", "downtime", "outage", "service interruption",
        "emergency maintenance", "server maintenance", "temporarily unavailable",
    ],
    "server_matchmaking": [
        "server", "servers", "matchmaking", "queue", "latency", "ping",
        "connection", "disconnect", "region", "network",
    ],
    "bug_fix_performance": [
        "bug fix", "bug fixes", "fixed", "fixes", "crash", "crashes",
        "stability", "performance", "optimization", "optimisation", "stutter",
        "frame rate", "fps issue", "known issues",
    ],
    "balance_gameplay": [
        "balance", "balancing", "nerf", "nerfed", "buff", "buffed",
        "gameplay change", "gameplay changes", "weapon adjustment",
        "adjustment", "rework",
    ],
    "anti_cheat_security": [
        "anti-cheat", "anticheat", "anti cheat", "cheat", "cheater",
        "cheaters", "ban wave", "security update", "exploit fix",
    ],
    "content_release": [
        "new map", "new maps", "new mode", "new modes", "new character",
        "new characters", "new hero", "new heroes", "new weapon",
        "new weapons", "dlc", "expansion", "new content", "content update",
    ],
    "season_event": [
        "season", "seasonal", "event", "anniversary", "festival",
        "limited-time", "limited time", "holiday event",
    ],
    "monetization_sale": [
        "sale", "discount", "price", "pricing", "bundle", "store",
        "shop", "premium", "battle pass", "battlepass", "currency",
        "microtransaction", "microtransactions",
    ],
    "general_update_patch": [
        "update", "patch", "hotfix", "release notes", "patch notes",
        "changelog", "version",
    ],
}

LABEL_COLUMNS = [
    "appid",
    "name",
    "category",
    "peak_month",
    "target_drop_month",
    "months_after_peak",
    "decline_rate_12m",
    "largest_monthly_drop_rate_3to12",
    "news_count_around_drop",
    "official_news_count_around_drop",
    "external_news_count_around_drop",
    "official_evidence_valid",
    "main_official_event_group",
    "main_official_event_share",
    "evidence_1_source_type",
    "evidence_1_date",
    "evidence_1_title",
    "evidence_1_url",
    "evidence_1_groups",
    "evidence_2_source_type",
    "evidence_2_date",
    "evidence_2_title",
    "evidence_2_url",
    "evidence_2_groups",
    "evidence_3_source_type",
    "evidence_3_date",
    "evidence_3_title",
    "evidence_3_url",
    "evidence_3_groups",
    "manual_reason_label",
    "competitor_candidate",
    "manual_evidence_note",
    "confidence",
    "memo",
]


def get_data_dir():
    drive_root = "/content/drive/MyDrive"
    if os.path.exists(DRIVE_DATA_DIR) or os.path.exists(drive_root):
        os.makedirs(DRIVE_DATA_DIR, exist_ok=True)
        return DRIVE_DATA_DIR
    os.makedirs("./data", exist_ok=True)
    return "./data"


def get_path(filename):
    return os.path.join(get_data_dir(), filename)


def save_csv(df, filename):
    path = get_path(filename)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {path} ({len(df)}行)")


def require_csv(filename, required_columns=None):
    path = get_path(filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"入力CSVが見つかりません: {path}\n前段のスクリプトを実行してください。"
        )
    df = pd.read_csv(path, encoding="utf-8-sig")
    if required_columns:
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            raise ValueError(f"{filename}に必要な列がありません: {missing}")
    return df


def optional_csv(filename):
    path = get_path(filename)
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def keyword_pattern(term):
    escaped = re.escape(term.lower())
    if " " in term or "-" in term:
        return escaped
    return rf"\b{escaped}\b"


def mentions_group(text, terms):
    if pd.isna(text):
        return False
    target = str(text).lower()
    return any(re.search(keyword_pattern(term), target) for term in terms)


def clean_text(value):
    if pd.isna(value):
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def month_diff(start, end):
    if pd.isna(start) or pd.isna(end):
        return None
    return (end.year - start.year) * 12 + (end.month - start.month)


def load_targets():
    required = [
        "appid", "name", "category", "peak_month", "decline_rate_12m",
        "largest_drop_month_3to12", "largest_monthly_drop_rate_3to12",
    ]
    df = require_csv(TARGET_FILENAME, required)
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["peak_month"] = pd.to_datetime(df["peak_month"], errors="coerce")
    df["largest_drop_month_3to12"] = pd.to_datetime(
        df["largest_drop_month_3to12"], errors="coerce"
    )
    return (
        df.dropna(subset=["appid", "peak_month", "largest_drop_month_3to12"])
        .drop_duplicates("appid", keep="first")
        .reset_index(drop=True)
    )


def load_news():
    required = [
        "appid", "name", "category", "target_drop_month", "gid", "title",
        "url", "contents", "feedname", "news_date",
    ]
    df = require_csv(NEWS_FILENAME, required)
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["news_date"] = pd.to_datetime(df["news_date"], errors="coerce")
    df["feedname"] = df["feedname"].fillna("").astype(str)
    df["is_official_announcement"] = df["feedname"].eq(OFFICIAL_FEEDNAME)
    return df.drop_duplicates(["appid", "gid"], keep="last").copy()


def make_news_events(news_df, target_df):
    target_lookup = {
        int(row["appid"]): row["largest_drop_month_3to12"]
        for _, row in target_df.iterrows()
    }
    rows = []

    for _, item in news_df.iterrows():
        if pd.isna(item["appid"]) or pd.isna(item["news_date"]):
            continue
        appid = int(item["appid"])
        drop_month = target_lookup.get(appid)
        if drop_month is None or pd.isna(drop_month):
            continue

        relative_month = month_diff(drop_month, item["news_date"])
        if relative_month is None or abs(relative_month) > WINDOW_MONTHS:
            continue

        title = clean_text(item.get("title", ""))
        contents = clean_text(item.get("contents", ""))
        text = f"{title} {contents}".strip()

        matched_groups = []
        row = {
            "appid": appid,
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "target_drop_month": str(drop_month.to_period("M")),
            "news_date": item["news_date"],
            "relative_month": relative_month,
            "gid": item.get("gid"),
            "title": title,
            "url": item.get("url", ""),
            "feedname": item.get("feedname", ""),
            "is_official_announcement": bool(item.get("is_official_announcement", False)),
        }

        for group_name, terms in NEWS_EVENT_GROUPS.items():
            mentioned = int(mentions_group(text, terms))
            row[f"mention_{group_name}"] = mentioned
            if mentioned:
                matched_groups.append(group_name)

        row["matched_group_count"] = len(matched_groups)
        row["matched_groups"] = ";".join(matched_groups)
        rows.append(row)

    columns = [
        "appid", "name", "category", "target_drop_month", "news_date",
        "relative_month", "gid", "title", "url", "feedname",
        "is_official_announcement",
    ]
    columns += [f"mention_{name}" for name in NEWS_EVENT_GROUPS]
    columns += ["matched_group_count", "matched_groups"]

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns].sort_values(["appid", "news_date"])


def choose_evidence(news_part, drop_month, limit=3):
    if news_part.empty:
        return []

    part = news_part.copy()
    center = drop_month.to_period("M").start_time
    part["distance_days"] = (part["news_date"] - center).abs().dt.days
    part["source_priority"] = (~part["is_official_announcement"]).astype(int)
    part = part.sort_values(
        ["source_priority", "matched_group_count", "distance_days", "news_date"],
        ascending=[True, False, True, True],
    )
    return part.head(limit).to_dict("records")


def make_game_summary(target_df, news_events_df):
    rows = []
    evidence_rows = []

    for _, target in target_df.iterrows():
        appid = int(target["appid"])
        drop_month = target["largest_drop_month_3to12"]
        news_part = news_events_df[news_events_df["appid"] == appid].copy()
        official = news_part[news_part["is_official_announcement"]].copy()
        external = news_part[~news_part["is_official_announcement"]].copy()

        official_count = len(official)
        group_counts = {}
        group_shares = {}
        for group_name in NEWS_EVENT_GROUPS:
            column = f"mention_{group_name}"
            count = int(official[column].sum()) if official_count else 0
            group_counts[group_name] = count
            group_shares[group_name] = count / official_count if official_count else None

        if official_count and max(group_counts.values()) > 0:
            main_group = max(group_counts, key=group_counts.get)
            main_share = group_shares[main_group]
        elif official_count:
            main_group = "other_or_unclear"
            main_share = 0.0
        else:
            main_group = "no_official_announcement"
            main_share = None

        row = {
            "appid": appid,
            "name": target["name"],
            "category": target["category"],
            "peak_month": target["peak_month"],
            "target_drop_month": drop_month,
            "months_after_peak": month_diff(target["peak_month"], drop_month),
            "decline_rate_12m": target["decline_rate_12m"],
            "largest_monthly_drop_rate_3to12": target["largest_monthly_drop_rate_3to12"],
            "news_count_around_drop": len(news_part),
            "official_news_count_around_drop": official_count,
            "external_news_count_around_drop": len(external),
            "official_evidence_valid": official_count > 0,
            "main_official_event_group": main_group,
            "main_official_event_share": main_share,
        }
        for group_name in NEWS_EVENT_GROUPS:
            row[f"{group_name}_official_mentions"] = group_counts[group_name]
            row[f"{group_name}_official_share"] = group_shares[group_name]
        rows.append(row)

        evidence = {
            "appid": appid,
            "name": target["name"],
            "category": target["category"],
            "target_drop_month": str(drop_month.to_period("M")),
        }
        selected = choose_evidence(news_part, drop_month, limit=3)
        for index in range(3):
            prefix = f"evidence_{index + 1}"
            if index < len(selected):
                item = selected[index]
                evidence[f"{prefix}_source_type"] = (
                    "steam_community_announcement"
                    if item.get("is_official_announcement")
                    else "external_or_other_feed"
                )
                evidence[f"{prefix}_date"] = item.get("news_date")
                evidence[f"{prefix}_title"] = item.get("title", "")
                evidence[f"{prefix}_url"] = item.get("url", "")
                evidence[f"{prefix}_groups"] = item.get("matched_groups", "")
            else:
                evidence[f"{prefix}_source_type"] = ""
                evidence[f"{prefix}_date"] = ""
                evidence[f"{prefix}_title"] = ""
                evidence[f"{prefix}_url"] = ""
                evidence[f"{prefix}_groups"] = ""
        evidence_rows.append(evidence)

    return pd.DataFrame(rows), pd.DataFrame(evidence_rows)


def make_category_summary(game_summary_df):
    rows = []
    scopes = [("ALL", game_summary_df)] + list(game_summary_df.groupby("category"))

    for category, part in scopes:
        valid = part[part["official_evidence_valid"]].copy()
        valid_games = len(valid)
        for group_name in NEWS_EVENT_GROUPS:
            mention_column = f"{group_name}_official_mentions"
            games_with_event = int((valid[mention_column] > 0).sum()) if valid_games else 0
            rows.append(
                {
                    "category": category,
                    "event_group": group_name,
                    "target_games": len(part),
                    "official_evidence_games": valid_games,
                    "games_with_event": games_with_event,
                    "game_proportion": (
                        games_with_event / valid_games if valid_games > 0 else None
                    ),
                    "total_official_mentions": (
                        int(valid[mention_column].sum()) if valid_games else 0
                    ),
                }
            )
    return pd.DataFrame(rows)


def make_labels_template(game_summary_df, evidence_df):
    merged = game_summary_df.merge(
        evidence_df,
        on=["appid", "name", "category", "target_drop_month"],
        how="left",
        validate="one_to_one",
    )
    for column in LABEL_COLUMNS:
        if column not in merged.columns:
            merged[column] = ""
    return merged[LABEL_COLUMNS]


def print_summary(target_df, news_df, news_events_df, game_summary_df, status_df):
    print("\n===== 3〜12か月急減 要因分析サマリー =====")
    print(f"factor target games: {len(target_df)}")
    print(f"news rows collected: {len(news_df)}")
    print(f"news rows around drop (±{WINDOW_MONTHS}m): {len(news_events_df)}")

    any_news = int((game_summary_df["news_count_around_drop"] > 0).sum())
    official = int(game_summary_df["official_evidence_valid"].sum())
    print(f"any news around drop: {any_news}/{len(game_summary_df)}")
    print(f"Steam Community Announcement available: {official}/{len(game_summary_df)}")

    if not status_df.empty and "window_start_reached" in status_df.columns:
        coverage = status_df["window_start_reached"].astype(str).str.lower().isin(
            ["true", "1", "yes"]
        )
        print(f"collection window start reached: {int(coverage.sum())}/{len(status_df)}")

    print("\nmain event groups from Steam Community Announcements:")
    counts = game_summary_df["main_official_event_group"].value_counts(dropna=False)
    for group, count in counts.items():
        print(f"  {group}: {count}")

    print("\ndrop-month offsets from peak:")
    offsets = game_summary_df["months_after_peak"].value_counts().sort_index()
    for offset, count in offsets.items():
        print(f"  +{int(offset)} months: {count}")

    print("\n注意:")
    print("- 発売・ピーク直後1〜2か月は除外している。")
    print("- Steam Community Announcementを一次資料として優先する。")
    print("- 外部ニュースは補助資料であり、公式発表と混同しない。")
    print("- 時間的一致は人口減少の因果関係を証明しない。")
    print("- 自動分類後、factor_labels_template_3to12.csvを手動確認する。")


def main():
    print(f"保存先: {get_data_dir()}")
    print("対象: ピーク後3〜12か月の最大月次下落")
    print("証拠: Steam Community Announcement優先、外部ニュースは補助")

    target_df = load_targets()
    news_df = load_news()
    status_df = optional_csv(STATUS_FILENAME)

    news_events_df = make_news_events(news_df, target_df)
    save_csv(news_events_df, NEWS_EVENTS_FILENAME)

    game_summary_df, evidence_df = make_game_summary(target_df, news_events_df)
    save_csv(game_summary_df, GAME_SUMMARY_FILENAME)
    save_csv(evidence_df, EVIDENCE_FILENAME)

    category_summary_df = make_category_summary(game_summary_df)
    save_csv(category_summary_df, CATEGORY_SUMMARY_FILENAME)

    labels_df = make_labels_template(game_summary_df, evidence_df)
    save_csv(labels_df, LABELS_TEMPLATE_FILENAME)

    print_summary(target_df, news_df, news_events_df, game_summary_df, status_df)


if __name__ == "__main__":
    main()
