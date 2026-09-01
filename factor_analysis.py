import os
import re

import pandas as pd


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

TARGET_FILENAME = "factor_target_games.csv"
REVIEWS_RAW_FILENAME = "factor_reviews_raw_12m.csv"
NEWS_FILENAME = "factor_news_12m.csv"
STATUS_FILENAME = "factor_collection_status_12m.csv"

REVIEW_MONTHLY_FILENAME = "factor_review_monthly_12m.csv"
NEWS_MONTHLY_FILENAME = "factor_news_monthly_12m.csv"
GAME_SUMMARY_FILENAME = "factor_game_summary_12m.csv"
CATEGORY_SUMMARY_FILENAME = "factor_category_summary_12m.csv"
EVIDENCE_FILENAME = "factor_evidence_12m.csv"
LABELS_TEMPLATE_FILENAME = "factor_labels_template_12m.csv"

WINDOW_MONTHS = 2
MIN_ENGLISH_NEGATIVE_REVIEWS = 5

# 「dead game」など人口減少そのものを表す語は原因候補から除外する。
KEYWORD_GROUPS = {
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
    "review_target_reached",
    "review_count_around_drop",
    "negative_rate_around_drop",
    "english_negative_reviews_around_drop",
    "factor_evidence_valid",
    "main_keyword_group",
    "main_keyword_share",
    "news_count_around_drop",
    "evidence_review",
    "evidence_news_title",
    "evidence_news_url",
    "manual_reason_label",
    "competitor_candidate",
    "manual_evidence_note",
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
            f"入力CSVが見つかりません: {path}\n"
            "前段のスクリプトを実行してください。"
        )
    df = pd.read_csv(path, encoding="utf-8-sig")
    if required_columns:
        missing = [c for c in required_columns if c not in df.columns]
        if missing:
            raise ValueError(f"{filename}に必要な列がありません: {missing}")
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


def add_keyword_mentions(reviews_df):
    result = reviews_df.copy()
    for group_name, terms in KEYWORD_GROUPS.items():
        result[f"mention_{group_name}"] = result["review"].apply(
            lambda text: int(mentions_group(text, terms))
        )
    mention_columns = [f"mention_{name}" for name in KEYWORD_GROUPS]
    result["mention_group_total"] = result[mention_columns].sum(axis=1)
    return result


def load_targets():
    required = [
        "appid", "name", "category", "peak_month", "decline_rate_12m",
        "largest_drop_month_12m", "largest_monthly_drop_rate_12m",
    ]
    df = require_csv(TARGET_FILENAME, required)
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    for column in ["peak_month", "largest_drop_month_12m"]:
        df[column] = pd.to_datetime(df[column], errors="coerce")
    return df.dropna(subset=["appid", "largest_drop_month_12m"]).copy()


def load_status():
    df = require_csv(
        STATUS_FILENAME,
        ["appid", "target_drop_month", "review_target_reached", "review_hit_cap"],
    )
    df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")
    df["target_drop_month"] = df["target_drop_month"].astype(str)
    df["review_target_reached"] = to_bool_series(df["review_target_reached"])
    df["review_hit_cap"] = to_bool_series(df["review_hit_cap"])
    return df.drop_duplicates(["appid", "target_drop_month"], keep="last")


def make_review_monthly(reviews_df):
    if reviews_df.empty:
        return pd.DataFrame()
    part = reviews_df.dropna(subset=["review_date"]).copy()
    part["review_month"] = part["review_date"].dt.to_period("M").astype(str)
    return (
        part.groupby(["appid", "name", "category", "review_month"], as_index=False)
        .agg(
            review_count=("recommendationid", "count"),
            positive_count=("voted_up", "sum"),
        )
        .assign(
            negative_count=lambda x: x["review_count"] - x["positive_count"],
            negative_rate=lambda x: x["negative_count"] / x["review_count"],
        )
        .sort_values(["appid", "review_month"])
    )


def make_news_monthly(news_df):
    if news_df.empty:
        return pd.DataFrame()
    part = news_df.dropna(subset=["news_date"]).copy()
    part["news_month"] = part["news_date"].dt.to_period("M").astype(str)
    return (
        part.groupby(["appid", "name", "category", "news_month"], as_index=False)
        .agg(news_count=("gid", "count"))
        .sort_values(["appid", "news_month"])
    )


def target_months(center):
    period = center.to_period("M")
    return [period + offset for offset in range(-WINDOW_MONTHS, WINDOW_MONTHS + 1)]


def select_evidence_review(negative_english_df, main_group):
    if negative_english_df.empty or not main_group:
        return ""
    column = f"mention_{main_group}"
    candidates = negative_english_df[negative_english_df[column] > 0].copy()
    if candidates.empty:
        return ""
    candidates = candidates.sort_values(
        ["mention_group_total", "review_date"],
        ascending=[False, True],
    )
    text = str(candidates.iloc[0]["review"]).replace("\n", " ").strip()
    return text[:800]


def select_evidence_news(news_part, drop_month):
    if news_part.empty:
        return "", ""
    part = news_part.dropna(subset=["news_date"]).copy()
    if part.empty:
        row = news_part.iloc[0]
        return str(row.get("title", "")), str(row.get("url", ""))
    center = drop_month.to_period("M").start_time
    part["distance_days"] = (part["news_date"] - center).abs().dt.days
    row = part.sort_values("distance_days").iloc[0]
    return str(row.get("title", "")), str(row.get("url", ""))


def make_game_summary(target_df, reviews_df, news_df, status_df):
    rows = []
    evidence_rows = []

    status_lookup = {
        (int(row["appid"]), str(row["target_drop_month"])): row
        for _, row in status_df.iterrows()
        if pd.notna(row["appid"])
    }

    for _, target in target_df.iterrows():
        appid = int(target["appid"])
        drop_month = target["largest_drop_month_12m"]
        drop_period = str(drop_month.to_period("M"))
        months = target_months(drop_month)

        status = status_lookup.get((appid, drop_period))
        review_target_reached = bool(
            status is not None and status["review_target_reached"]
        )
        review_hit_cap = bool(status is not None and status["review_hit_cap"])

        review_part = reviews_df[reviews_df["appid"] == appid].copy()
        review_part = review_part[
            review_part["review_date"].dt.to_period("M").isin(months)
        ]

        review_count = len(review_part)
        positive_count = int(review_part["voted_up"].sum()) if review_count else 0
        negative_count = review_count - positive_count
        negative_rate = negative_count / review_count if review_count > 0 else None

        negative_english = review_part[
            (~review_part["voted_up"])
            & (review_part["language"].astype(str).str.lower() == "english")
        ].copy()
        english_negative_count = len(negative_english)

        mention_counts = {}
        mention_rates = {}
        for group_name in KEYWORD_GROUPS:
            column = f"mention_{group_name}"
            count = int(negative_english[column].sum()) if english_negative_count else 0
            mention_counts[group_name] = count
            mention_rates[group_name] = (
                count / english_negative_count if english_negative_count > 0 else None
            )

        if mention_counts and max(mention_counts.values()) > 0:
            main_group = max(mention_counts, key=mention_counts.get)
            main_share = mention_rates[main_group]
        else:
            main_group = ""
            main_share = None

        factor_evidence_valid = (
            review_target_reached
            and english_negative_count >= MIN_ENGLISH_NEGATIVE_REVIEWS
        )

        evidence_review = select_evidence_review(negative_english, main_group)

        news_part = news_df[news_df["appid"] == appid].copy()
        news_part = news_part[
            news_part["news_date"].dt.to_period("M").isin(months)
        ]
        news_title, news_url = select_evidence_news(news_part, drop_month)

        row = {
            "appid": appid,
            "name": target["name"],
            "category": target["category"],
            "peak_month": target["peak_month"],
            "target_drop_month": drop_month,
            "decline_rate_12m": target["decline_rate_12m"],
            "largest_monthly_drop_rate_12m": target["largest_monthly_drop_rate_12m"],
            "review_target_reached": review_target_reached,
            "review_hit_cap": review_hit_cap,
            "review_count_around_drop": review_count,
            "positive_count_around_drop": positive_count,
            "negative_count_around_drop": negative_count,
            "negative_rate_around_drop": negative_rate,
            "english_negative_reviews_around_drop": english_negative_count,
            "factor_evidence_valid": factor_evidence_valid,
            "main_keyword_group": main_group,
            "main_keyword_share": main_share,
            "news_count_around_drop": len(news_part),
        }
        for group_name in KEYWORD_GROUPS:
            row[f"{group_name}_mentions"] = mention_counts[group_name]
            row[f"{group_name}_share"] = mention_rates[group_name]
        rows.append(row)

        evidence_rows.append(
            {
                "appid": appid,
                "name": target["name"],
                "category": target["category"],
                "target_drop_month": drop_period,
                "factor_evidence_valid": factor_evidence_valid,
                "main_keyword_group": main_group,
                "main_keyword_share": main_share,
                "evidence_review": evidence_review,
                "evidence_news_title": news_title,
                "evidence_news_url": news_url,
            }
        )

    return pd.DataFrame(rows), pd.DataFrame(evidence_rows)


def make_category_summary(game_summary_df):
    rows = []
    valid = game_summary_df[game_summary_df["factor_evidence_valid"]].copy()
    for category, category_df in valid.groupby("category"):
        valid_games = len(category_df)
        for group_name in KEYWORD_GROUPS:
            main_count = int((category_df["main_keyword_group"] == group_name).sum())
            share_values = pd.to_numeric(
                category_df[f"{group_name}_share"], errors="coerce"
            )
            rows.append(
                {
                    "category": category,
                    "factor_group": group_name,
                    "valid_games": valid_games,
                    "main_factor_games": main_count,
                    "main_factor_proportion": (
                        main_count / valid_games if valid_games > 0 else None
                    ),
                    "mean_negative_review_mention_share": share_values.mean(),
                    "median_negative_review_mention_share": share_values.median(),
                }
            )
    return pd.DataFrame(rows)


def make_labels_template(game_summary_df, evidence_df):
    merged = game_summary_df.merge(
        evidence_df[
            [
                "appid", "evidence_review", "evidence_news_title",
                "evidence_news_url",
            ]
        ],
        on="appid",
        how="left",
        validate="one_to_one",
    )
    for column in LABEL_COLUMNS:
        if column not in merged.columns:
            merged[column] = ""
    return merged[LABEL_COLUMNS]


def main():
    print(f"保存先: {get_data_dir()}")
    print("要因分析: 12か月固定衰退率上位50作品の最大下落月±2か月")
    print("テキスト要因判定: 英語の低評価レビューのみ")

    target_df = load_targets()
    status_df = load_status()

    reviews_df = require_csv(
        REVIEWS_RAW_FILENAME,
        [
            "appid", "language", "review", "review_date", "voted_up",
            "recommendationid",
        ],
    )
    reviews_df["appid"] = pd.to_numeric(reviews_df["appid"], errors="coerce").astype("Int64")
    reviews_df["review_date"] = pd.to_datetime(reviews_df["review_date"], errors="coerce")
    reviews_df["voted_up"] = to_bool_series(reviews_df["voted_up"])
    reviews_df = add_keyword_mentions(reviews_df)

    news_df = require_csv(NEWS_FILENAME, ["appid", "gid", "title", "url", "news_date"])
    news_df["appid"] = pd.to_numeric(news_df["appid"], errors="coerce").astype("Int64")
    news_df["news_date"] = pd.to_datetime(news_df["news_date"], errors="coerce")

    review_monthly_df = make_review_monthly(reviews_df)
    save_csv(review_monthly_df, REVIEW_MONTHLY_FILENAME)

    news_monthly_df = make_news_monthly(news_df)
    save_csv(news_monthly_df, NEWS_MONTHLY_FILENAME)

    game_summary_df, evidence_df = make_game_summary(
        target_df,
        reviews_df,
        news_df,
        status_df,
    )
    save_csv(game_summary_df, GAME_SUMMARY_FILENAME)
    save_csv(evidence_df, EVIDENCE_FILENAME)

    category_summary_df = make_category_summary(game_summary_df)
    save_csv(category_summary_df, CATEGORY_SUMMARY_FILENAME)

    labels_df = make_labels_template(game_summary_df, evidence_df)
    save_csv(labels_df, LABELS_TEMPLATE_FILENAME)

    print("\n===== 要因分析サマリー =====")
    print(f"factor target games: {len(target_df)}")
    print(f"review coverage reached: {game_summary_df['review_target_reached'].sum()}/{len(game_summary_df)}")
    print(f"factor evidence valid: {game_summary_df['factor_evidence_valid'].sum()}/{len(game_summary_df)}")
    print(f"news available around drop: {(game_summary_df['news_count_around_drop'] > 0).sum()}/{len(game_summary_df)}")

    valid = game_summary_df[game_summary_df["factor_evidence_valid"]]
    if not valid.empty:
        print("\nmain keyword groups (valid games only):")
        for factor, count in valid["main_keyword_group"].replace("", "no_keyword").value_counts().items():
            print(f"  {factor}: {count}")
    else:
        print("有効な要因判定対象がありません。収集coverageを確認してください。")

    print("\n注意:")
    print("- キーワード集計は原因の確定ではなく、要因候補を抽出する探索的分析です。")
    print("- 最終的な原因ラベルはfactor_labels_template_12m.csvでレビュー・公式ニュースを確認して手動検証してください。")


if __name__ == "__main__":
    main()
