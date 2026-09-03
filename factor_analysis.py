"""Steamゲーム急減期の要因候補分析（12か月固定主分析対応）。

主目的:
- 12か月固定衰退率が大きい50作品について、ピーク後12か月以内の
  最大月次下落月の前後2か月に公開されたSteam公式ニュースを分析する。
- ニュース本文・タイトルからイベント候補をキーワード支援で抽出する。

重要:
- Steam公式ニュースは開発・運営側が公開した情報であり、人口減少の
  因果関係を直接証明するものではない。
- 自動分類は「要因候補の抽出」であり、最終的な理由付けは手動確認する。
- 過去レビュー本文は取得制約が大きいため、対象時期まで取得できた作品のみ
  補助証拠として利用する。
"""

import os
import re
from collections import Counter

import pandas as pd


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

TARGET_FILENAME = "factor_target_games.csv"
REVIEWS_RAW_FILENAME = "factor_reviews_raw_12m.csv"
NEWS_FILENAME = "factor_news_12m.csv"
STATUS_FILENAME = "factor_collection_status_12m.csv"

REVIEW_MONTHLY_FILENAME = "factor_review_monthly_12m.csv"
NEWS_MONTHLY_FILENAME = "factor_news_monthly_12m.csv"
NEWS_EVENTS_FILENAME = "factor_news_events_12m.csv"
GAME_SUMMARY_FILENAME = "factor_game_summary_12m.csv"
CATEGORY_SUMMARY_FILENAME = "factor_category_summary_12m.csv"
EVIDENCE_FILENAME = "factor_evidence_12m.csv"
LABELS_TEMPLATE_FILENAME = "factor_labels_template_12m.csv"

WINDOW_MONTHS = 2
MIN_ENGLISH_NEGATIVE_REVIEWS = 5

# 公式ニュースから確認できる「イベント候補」。
# 複数カテゴリへの同時該当を許す。
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
        "frame rate", "fps issue",
    ],
    "balance_gameplay": [
        "balance", "balancing", "nerf", "nerfed", "buff", "buffed",
        "gameplay change", "gameplay changes", "weapon adjustment",
        "adjustment", "rework",
    ],
    "anti_cheat_security": [
        "anti-cheat", "anticheat", "anti cheat", "cheat", "cheater",
        "cheaters", "ban wave", "banned", "security", "exploit",
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

# レビューは補助証拠のみ。対象時期まで取得できた作品に限定して使用する。
REVIEW_KEYWORD_GROUPS = {
    "bug_crash": [
        "bug", "bugs", "buggy", "crash", "crashes", "crashing",
        "broken", "glitch", "glitches", "freeze", "freezing",
    ],
    "cheater": [
        "cheater", "cheaters", "hacker", "hackers", "aimbot",
        "wallhack", "wallhacks", "cheating",
    ],
    "server_matchmaking": [
        "server", "servers", "matchmaking", "lag", "laggy", "disconnect",
        "disconnects", "queue", "queue time", "ping",
    ],
    "balance_update": [
        "balance", "unbalanced", "nerf", "nerfed", "buff", "buffed",
        "update", "patch",
    ],
    "monetization": [
        "pay to win", "pay-to-win", "p2w", "microtransaction",
        "microtransactions", "monetization", "cash shop", "battle pass",
        "overpriced",
    ],
    "content_lack": [
        "boring", "repetitive", "no content", "lack of content",
        "not enough content", "grind", "grindy", "endgame",
    ],
    "performance": [
        "fps", "stutter", "stuttering", "optimization", "optimisation",
        "performance", "frame drop", "frame drops",
    ],
}

LABEL_COLUMNS = [
    "appid",
    "name",
    "category",
    "peak_month",
    "target_drop_month",
    "decline_rate_12m",
    "largest_monthly_drop_rate_12m",
    "news_evidence_valid",
    "news_count_around_drop",
    "news_count_drop_month",
    "main_news_event_group",
    "main_news_event_share",
    "evidence_news_1_date",
    "evidence_news_1_title",
    "evidence_news_1_url",
    "evidence_news_1_groups",
    "evidence_news_2_date",
    "evidence_news_2_title",
    "evidence_news_2_url",
    "evidence_news_2_groups",
    "evidence_news_3_date",
    "evidence_news_3_title",
    "evidence_news_3_url",
    "evidence_news_3_groups",
    "review_target_reached",
    "review_support_available",
    "review_count_around_drop",
    "negative_rate_around_drop",
    "review_main_keyword_group",
    "review_main_keyword_share",
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
    local_data_dir = "./data"
    os.makedirs(local_data_dir, exist_ok=True)
    return local_data_dir


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
        missing = [column for column in required_columns if column not in df.columns]
        if missing:
            raise ValueError(f"{filename}に必要な列がありません: {missing}")
    return df


def optional_csv(filename, columns=None):
    path = get_path(filename)
    if not os.path.exists(path):
        return pd.DataFrame(columns=columns or [])
    df = pd.read_csv(path, encoding="utf-8-sig")
    if columns:
        for column in columns:
            if column not in df.columns:
                df[column] = None
    return df


def to_bool_series(series):
    if str(series.dtype) == "bool":
        return series
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


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


def clean_news_text(value):
    if pd.isna(value):
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def month_distance(start, end):
    if pd.isna(start) or pd.isna(end):
        return None
    return (end.year - start.year) * 12 + (end.month - start.month)


def target_months(center):
    period = center.to_period("M")
    return [period + offset for offset in range(-WINDOW_MONTHS, WINDOW_MONTHS + 1)]


def load_targets():
    required = [
        "appid",
        "name",
        "category",
        "peak_month",
        "decline_rate_12m",
        "largest_drop_month_12m",
        "largest_monthly_drop_rate_12m",
    ]
    df = require_csv(TARGET_FILENAME, required)
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    for column in ["peak_month", "largest_drop_month_12m"]:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    return (
        df.dropna(subset=["appid", "largest_drop_month_12m", "decline_rate_12m"])
        .drop_duplicates("appid", keep="first")
        .reset_index(drop=True)
    )


def load_status():
    df = optional_csv(
        STATUS_FILENAME,
        [
            "appid",
            "target_drop_month",
            "review_target_reached",
            "review_hit_cap",
            "review_error",
            "news_error",
        ],
    )
    if df.empty:
        return df
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["target_drop_month"] = df["target_drop_month"].astype(str)
    df["review_target_reached"] = to_bool_series(df["review_target_reached"])
    df["review_hit_cap"] = to_bool_series(df["review_hit_cap"])
    return df.drop_duplicates(["appid", "target_drop_month"], keep="last")


def load_news():
    required = [
        "appid",
        "name",
        "category",
        "target_drop_month",
        "gid",
        "title",
        "url",
        "contents",
        "news_date",
    ]
    df = require_csv(NEWS_FILENAME, required)
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["news_date"] = pd.to_datetime(df["news_date"], errors="coerce")
    df["target_drop_month"] = df["target_drop_month"].astype(str)
    return df.drop_duplicates(["appid", "gid"], keep="last").copy()


def load_reviews():
    columns = [
        "appid",
        "target_drop_month",
        "recommendationid",
        "language",
        "review",
        "review_date",
        "voted_up",
    ]
    df = optional_csv(REVIEWS_RAW_FILENAME, columns)
    if df.empty:
        return df
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["review_date"] = pd.to_datetime(df["review_date"], errors="coerce")
    df["target_drop_month"] = df["target_drop_month"].astype(str)
    df["voted_up"] = to_bool_series(df["voted_up"])
    return df.drop_duplicates("recommendationid", keep="last").copy()


def make_news_monthly(news_df):
    part = news_df.dropna(subset=["news_date"]).copy()
    if part.empty:
        return pd.DataFrame(
            columns=["appid", "name", "category", "news_month", "news_count"]
        )
    part["news_month"] = part["news_date"].dt.to_period("M").astype(str)
    return (
        part.groupby(["appid", "name", "category", "news_month"], as_index=False)
        .agg(news_count=("gid", "count"))
        .sort_values(["appid", "news_month"])
    )


def make_review_monthly(reviews_df):
    if reviews_df.empty:
        return pd.DataFrame(
            columns=[
                "appid", "review_month", "review_count", "positive_count",
                "negative_count", "negative_rate",
            ]
        )
    part = reviews_df.dropna(subset=["review_date"]).copy()
    part["review_month"] = part["review_date"].dt.to_period("M").astype(str)
    monthly = (
        part.groupby(["appid", "review_month"], as_index=False)
        .agg(
            review_count=("recommendationid", "count"),
            positive_count=("voted_up", "sum"),
        )
    )
    monthly["negative_count"] = monthly["review_count"] - monthly["positive_count"]
    monthly["negative_rate"] = monthly["negative_count"] / monthly["review_count"]
    return monthly.sort_values(["appid", "review_month"])


def make_news_events(news_df, target_df):
    target_lookup = {
        int(row["appid"]): row["largest_drop_month_12m"]
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

        relative_month = month_distance(drop_month, item["news_date"])
        if relative_month is None or abs(relative_month) > WINDOW_MONTHS:
            continue

        title = clean_news_text(item.get("title", ""))
        contents = clean_news_text(item.get("contents", ""))
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
        "relative_month", "gid", "title", "url",
    ]
    columns += [f"mention_{name}" for name in NEWS_EVENT_GROUPS]
    columns += ["matched_group_count", "matched_groups"]

    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns].sort_values(["appid", "news_date"])


def review_supplement(appid, drop_month, reviews_df, status_row):
    result = {
        "review_target_reached": False,
        "review_hit_cap": False,
        "review_support_available": False,
        "review_count_around_drop": 0,
        "negative_rate_around_drop": None,
        "english_negative_reviews_around_drop": 0,
        "review_main_keyword_group": "",
        "review_main_keyword_share": None,
    }

    if status_row is not None:
        result["review_target_reached"] = bool(status_row["review_target_reached"])
        result["review_hit_cap"] = bool(status_row["review_hit_cap"])

    if reviews_df.empty or not result["review_target_reached"]:
        return result

    months = target_months(drop_month)
    part = reviews_df[reviews_df["appid"] == appid].copy()
    part = part[part["review_date"].dt.to_period("M").isin(months)]
    result["review_count_around_drop"] = len(part)
    if part.empty:
        return result

    negative_count = int((~part["voted_up"]).sum())
    result["negative_rate_around_drop"] = negative_count / len(part)

    negative_english = part[
        (~part["voted_up"])
        & (part["language"].astype(str).str.lower() == "english")
    ].copy()
    result["english_negative_reviews_around_drop"] = len(negative_english)

    if len(negative_english) < MIN_ENGLISH_NEGATIVE_REVIEWS:
        return result

    counts = {}
    for group_name, terms in REVIEW_KEYWORD_GROUPS.items():
        counts[group_name] = int(
            negative_english["review"].apply(
                lambda text: int(mentions_group(text, terms))
            ).sum()
        )

    if counts and max(counts.values()) > 0:
        main_group = max(counts, key=counts.get)
        result["review_main_keyword_group"] = main_group
        result["review_main_keyword_share"] = (
            counts[main_group] / len(negative_english)
        )
    result["review_support_available"] = True
    return result


def choose_evidence(news_part, drop_month, limit=3):
    if news_part.empty:
        return []
    part = news_part.copy()
    center = drop_month.to_period("M").start_time
    part["distance_days"] = (part["news_date"] - center).abs().dt.days
    part = part.sort_values(
        ["matched_group_count", "distance_days", "news_date"],
        ascending=[False, True, True],
    )
    return part.head(limit).to_dict("records")


def status_lookup(status_df):
    if status_df.empty:
        return {}
    lookup = {}
    for _, row in status_df.iterrows():
        if pd.isna(row["appid"]):
            continue
        lookup[(int(row["appid"]), str(row["target_drop_month"]))] = row
    return lookup


def make_game_summary(target_df, news_events_df, reviews_df, status_df):
    rows = []
    evidence_rows = []
    statuses = status_lookup(status_df)

    for _, target in target_df.iterrows():
        appid = int(target["appid"])
        drop_month = target["largest_drop_month_12m"]
        drop_period = str(drop_month.to_period("M"))

        news_part = news_events_df[news_events_df["appid"] == appid].copy()
        news_count = len(news_part)
        news_evidence_valid = news_count > 0

        group_counts = {}
        group_shares = {}
        for group_name in NEWS_EVENT_GROUPS:
            column = f"mention_{group_name}"
            count = int(news_part[column].sum()) if news_count else 0
            group_counts[group_name] = count
            group_shares[group_name] = count / news_count if news_count else None

        if group_counts and max(group_counts.values()) > 0:
            main_news_group = max(group_counts, key=group_counts.get)
            main_news_share = group_shares[main_news_group]
        elif news_count > 0:
            main_news_group = "other_or_unclear"
            main_news_share = 0.0
        else:
            main_news_group = ""
            main_news_share = None

        supplement = review_supplement(
            appid,
            drop_month,
            reviews_df,
            statuses.get((appid, drop_period)),
        )

        row = {
            "appid": appid,
            "name": target["name"],
            "category": target["category"],
            "peak_month": target["peak_month"],
            "target_drop_month": drop_month,
            "decline_rate_12m": target["decline_rate_12m"],
            "largest_monthly_drop_rate_12m": target["largest_monthly_drop_rate_12m"],
            "news_evidence_valid": news_evidence_valid,
            "news_count_around_drop": news_count,
            "news_count_pre_2m": int((news_part["relative_month"] < 0).sum()) if news_count else 0,
            "news_count_drop_month": int((news_part["relative_month"] == 0).sum()) if news_count else 0,
            "news_count_post_2m": int((news_part["relative_month"] > 0).sum()) if news_count else 0,
            "main_news_event_group": main_news_group,
            "main_news_event_share": main_news_share,
        }
        for group_name in NEWS_EVENT_GROUPS:
            row[f"{group_name}_news_mentions"] = group_counts[group_name]
            row[f"{group_name}_news_share"] = group_shares[group_name]
        row.update(supplement)
        rows.append(row)

        evidence = {
            "appid": appid,
            "name": target["name"],
            "category": target["category"],
            "target_drop_month": drop_period,
            "news_evidence_valid": news_evidence_valid,
            "main_news_event_group": main_news_group,
            "main_news_event_share": main_news_share,
        }
        selected = choose_evidence(news_part, drop_month, limit=3)
        for index in range(3):
            prefix = f"evidence_news_{index + 1}"
            if index < len(selected):
                item = selected[index]
                evidence[f"{prefix}_date"] = item.get("news_date")
                evidence[f"{prefix}_title"] = item.get("title", "")
                evidence[f"{prefix}_url"] = item.get("url", "")
                evidence[f"{prefix}_groups"] = item.get("matched_groups", "")
            else:
                evidence[f"{prefix}_date"] = ""
                evidence[f"{prefix}_title"] = ""
                evidence[f"{prefix}_url"] = ""
                evidence[f"{prefix}_groups"] = ""
        evidence_rows.append(evidence)

    return pd.DataFrame(rows), pd.DataFrame(evidence_rows)


def make_category_summary(game_summary_df):
    rows = []
    scopes = [("ALL", game_summary_df)]
    scopes += list(game_summary_df.groupby("category"))

    for category, part in scopes:
        valid = part[part["news_evidence_valid"]].copy()
        valid_games = len(valid)
        for group_name in NEWS_EVENT_GROUPS:
            mention_column = f"{group_name}_news_mentions"
            share_column = f"{group_name}_news_share"
            games_with_event = int((valid[mention_column] > 0).sum()) if valid_games else 0
            rows.append(
                {
                    "category": category,
                    "event_group": group_name,
                    "target_games": len(part),
                    "news_valid_games": valid_games,
                    "games_with_event": games_with_event,
                    "game_proportion": (
                        games_with_event / valid_games if valid_games > 0 else None
                    ),
                    "total_news_mentions": int(valid[mention_column].sum()) if valid_games else 0,
                    "mean_game_news_share": pd.to_numeric(
                        valid[share_column], errors="coerce"
                    ).mean() if valid_games else None,
                }
            )
    return pd.DataFrame(rows)


def make_labels_template(game_summary_df, evidence_df):
    evidence_columns = ["appid"] + [
        f"evidence_news_{index}_{field}"
        for index in range(1, 4)
        for field in ["date", "title", "url", "groups"]
    ]
    merged = game_summary_df.merge(
        evidence_df[evidence_columns],
        on="appid",
        how="left",
        validate="one_to_one",
    )
    for column in LABEL_COLUMNS:
        if column not in merged.columns:
            merged[column] = ""
    return merged[LABEL_COLUMNS]


def print_summary(target_df, news_df, news_events_df, game_summary_df):
    print("\n===== 要因分析サマリー =====")
    print(f"factor target games: {len(target_df)}")
    print(f"official news rows collected: {len(news_df)}")
    print(f"official news rows around drop (±{WINDOW_MONTHS}m): {len(news_events_df)}")

    news_valid = int(game_summary_df["news_evidence_valid"].sum())
    review_reached = int(game_summary_df["review_target_reached"].sum())
    review_support = int(game_summary_df["review_support_available"].sum())
    print(f"news evidence available: {news_valid}/{len(game_summary_df)}")
    print(f"review target reached: {review_reached}/{len(game_summary_df)} (supplement only)")
    print(f"review text support usable: {review_support}/{len(game_summary_df)} (supplement only)")

    print("\nmain official-news event groups:")
    counts = game_summary_df.loc[
        game_summary_df["news_evidence_valid"], "main_news_event_group"
    ].value_counts(dropna=False)
    for group, count in counts.items():
        print(f"  {group}: {count}")

    print("\ncategory news coverage:")
    coverage = game_summary_df.groupby("category")["news_evidence_valid"].agg(["count", "sum"])
    for category, row in coverage.iterrows():
        print(f"  {category}: {int(row['sum'])}/{int(row['count'])}")

    print("\n注意:")
    print("- 公式ニュースとの時間的一致は、人口減少の因果関係を証明しない。")
    print("- 自動カテゴリは要因候補の探索用。factor_labels_template_12m.csvで手動確認する。")
    print("- 競合作品発売などSteam公式ニュース外の要因は、別途手動・Web調査が必要。")


def main():
    print(f"保存先: {get_data_dir()}")
    print("要因分析の主証拠: Steam公式ニュース")
    print("対象窓: 12か月固定衰退率上位50作品の最大下落月±2か月")
    print("過去レビュー本文: 対象時期まで取得できた作品のみ補助利用")

    target_df = load_targets()
    news_df = load_news()
    reviews_df = load_reviews()
    status_df = load_status()

    news_monthly_df = make_news_monthly(news_df)
    save_csv(news_monthly_df, NEWS_MONTHLY_FILENAME)

    review_monthly_df = make_review_monthly(reviews_df)
    save_csv(review_monthly_df, REVIEW_MONTHLY_FILENAME)

    news_events_df = make_news_events(news_df, target_df)
    save_csv(news_events_df, NEWS_EVENTS_FILENAME)

    game_summary_df, evidence_df = make_game_summary(
        target_df,
        news_events_df,
        reviews_df,
        status_df,
    )
    save_csv(game_summary_df, GAME_SUMMARY_FILENAME)
    save_csv(evidence_df, EVIDENCE_FILENAME)

    category_summary_df = make_category_summary(game_summary_df)
    save_csv(category_summary_df, CATEGORY_SUMMARY_FILENAME)

    labels_df = make_labels_template(game_summary_df, evidence_df)
    save_csv(labels_df, LABELS_TEMPLATE_FILENAME)

    print_summary(target_df, news_df, news_events_df, game_summary_df)


if __name__ == "__main__":
    main()
