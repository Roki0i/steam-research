import os
import re

import pandas as pd


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

TARGET_FILENAME = "factor_target_games.csv"
REVIEWS_RAW_FILENAME = "factor_reviews_raw.csv"
NEWS_FILENAME = "factor_news.csv"

REVIEW_MONTHLY_FILENAME = "factor_review_monthly.csv"
NEWS_MONTHLY_FILENAME = "factor_news_monthly.csv"
KEYWORD_SUMMARY_FILENAME = "factor_keyword_summary.csv"
GAME_SUMMARY_FILENAME = "factor_game_summary.csv"
LABELS_TEMPLATE_FILENAME = "factor_labels_template.csv"

KEYWORD_GROUPS = {
    "bug_crash": ["bug", "bugs", "crash", "crashes", "broken", "glitch"],
    "cheater": ["cheater", "cheaters", "hacker", "hackers", "cheat", "cheating"],
    "server_matchmaking": [
        "server",
        "servers",
        "matchmaking",
        "lag",
        "disconnect",
        "queue",
    ],
    "balance_update": ["balance", "nerf", "buff", "update", "patch"],
    "pay_to_win": ["pay to win", "p2w", "microtransaction", "monetization"],
    "dead_game": ["dead game", "no players", "empty", "queue time"],
    "content_lack": ["boring", "repetitive", "no content", "lack of content", "grind"],
    "performance": ["fps", "stutter", "optimization", "performance"],
}

LABEL_COLUMNS = [
    "appid",
    "name",
    "category",
    "peak_month",
    "largest_drop_month",
    "decline_rate",
    "largest_monthly_drop_rate",
    "review_count_around_drop",
    "negative_rate_around_drop",
    "news_count_around_drop",
    "main_keyword_group",
    "reason_candidate",
    "evidence_review",
    "evidence_news",
    "competitor_candidate",
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
    file_path = get_path(filename)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {file_path} ({len(df)}行)")


def month_text(series):
    return series.dt.to_period("M").astype(str)


def keyword_count(text, words):
    if pd.isna(text):
        return 0

    target_text = str(text).lower()
    count = 0
    for word in words:
        pattern = re.escape(word.lower())
        count += len(re.findall(pattern, target_text))
    return count


def load_targets():
    target_df = pd.read_csv(get_path(TARGET_FILENAME), encoding="utf-8-sig")
    target_df["appid"] = target_df["appid"].astype(int)
    target_df["peak_month"] = pd.to_datetime(target_df["peak_month"], errors="coerce")
    target_df["largest_drop_month"] = pd.to_datetime(
        target_df["largest_drop_month"],
        errors="coerce",
    )
    return target_df


def to_bool_series(series):
    if series.dtype == bool:
        return series

    text_series = series.astype(str).str.lower()
    return text_series.isin(["true", "1", "yes"])


def make_review_monthly(reviews_df):
    if reviews_df.empty:
        return pd.DataFrame(
            columns=[
                "appid",
                "name",
                "category",
                "review_month",
                "review_count",
                "positive_count",
                "negative_count",
                "negative_rate",
            ]
        )

    reviews_df = reviews_df.dropna(subset=["review_date"]).copy()
    reviews_df["review_month"] = month_text(reviews_df["review_date"])

    monthly_df = (
        reviews_df.groupby(["appid", "name", "category", "review_month"], as_index=False)
        .agg(
            review_count=("recommendationid", "count"),
            positive_count=("voted_up", "sum"),
        )
    )
    monthly_df["negative_count"] = monthly_df["review_count"] - monthly_df["positive_count"]
    monthly_df["negative_rate"] = monthly_df["negative_count"] / monthly_df["review_count"]
    return monthly_df


def make_news_monthly(news_df):
    if news_df.empty:
        return pd.DataFrame(
            columns=["appid", "name", "category", "news_month", "news_count"]
        )

    news_df = news_df.dropna(subset=["news_date"]).copy()
    news_df["news_month"] = month_text(news_df["news_date"])

    return (
        news_df.groupby(["appid", "name", "category", "news_month"], as_index=False)
        .agg(news_count=("gid", "count"))
        .sort_values(["appid", "news_month"])
    )


def add_keyword_columns(reviews_df):
    reviews_df = reviews_df.copy()
    for group_name, words in KEYWORD_GROUPS.items():
        reviews_df[group_name] = reviews_df["review"].apply(
            lambda text: keyword_count(text, words)
        )
    reviews_df["keyword_total"] = reviews_df[list(KEYWORD_GROUPS.keys())].sum(axis=1)
    return reviews_df


def make_keyword_summary(reviews_with_keywords):
    columns = ["appid", "name", "category"] + list(KEYWORD_GROUPS.keys())
    columns += ["keyword_total", "main_keyword_group"]

    if reviews_with_keywords.empty:
        return pd.DataFrame(columns=columns)

    summary_df = (
        reviews_with_keywords.groupby(["appid", "name", "category"], as_index=False)[
            list(KEYWORD_GROUPS.keys()) + ["keyword_total"]
        ]
        .sum()
        .copy()
    )

    def get_main_group(row):
        values = row[list(KEYWORD_GROUPS.keys())]
        if values.max() <= 0:
            return ""
        return values.idxmax()

    summary_df["main_keyword_group"] = summary_df.apply(get_main_group, axis=1)
    return summary_df[columns]


def make_game_summary(target_df, review_monthly_df, news_monthly_df, reviews_with_keywords):
    rows = []

    for _, target in target_df.iterrows():
        appid = int(target["appid"])
        largest_drop_month = target["largest_drop_month"]
        if pd.isna(largest_drop_month):
            start_month = None
            end_month = None
            target_months = []
        else:
            center_month = largest_drop_month.to_period("M")
            start_month = center_month - 2
            end_month = center_month + 2
            target_months = [
                str(center_month + offset)
                for offset in range(-2, 3)
            ]

        review_part = review_monthly_df[
            (review_monthly_df["appid"] == appid)
            & (review_monthly_df["review_month"].isin(target_months))
        ]
        review_count = review_part["review_count"].sum()
        negative_count = review_part["negative_count"].sum()
        if review_count > 0:
            negative_rate = negative_count / review_count
        else:
            negative_rate = None

        news_part = news_monthly_df[
            (news_monthly_df["appid"] == appid)
            & (news_monthly_df["news_month"].isin(target_months))
        ]
        news_count = news_part["news_count"].sum()

        review_keyword_part = reviews_with_keywords[reviews_with_keywords["appid"] == appid]
        if start_month is not None:
            review_keyword_part = review_keyword_part[
                review_keyword_part["review_date"].dt.to_period("M").isin(
                    [
                        largest_drop_month.to_period("M") + offset
                        for offset in range(-2, 3)
                    ]
                )
            ]

        keyword_counts = {}
        for group_name in KEYWORD_GROUPS.keys():
            keyword_counts[group_name] = review_keyword_part[group_name].sum()
        keyword_total = sum(keyword_counts.values())

        if keyword_counts and max(keyword_counts.values()) > 0:
            main_keyword_group = max(keyword_counts, key=keyword_counts.get)
        else:
            main_keyword_group = ""

        row = {
            "appid": appid,
            "name": target["name"],
            "category": target["category"],
            "peak_month": target["peak_month"],
            "largest_drop_month": largest_drop_month,
            "decline_rate": target.get("decline_rate"),
            "largest_monthly_drop_rate": target.get("largest_monthly_drop_rate"),
            "review_count_around_drop": review_count,
            "negative_rate_around_drop": negative_rate,
            "news_count_around_drop": news_count,
            "keyword_total_around_drop": keyword_total,
            "main_keyword_group": main_keyword_group,
        }
        row.update(keyword_counts)
        rows.append(row)

    return pd.DataFrame(rows)


def make_labels_template(game_summary_df):
    labels_df = game_summary_df.copy()
    for column in LABEL_COLUMNS:
        if column not in labels_df.columns:
            labels_df[column] = ""
    return labels_df[LABEL_COLUMNS]


def print_summary(
    target_df,
    review_monthly_df,
    news_monthly_df,
    keyword_summary_df,
    game_summary_df,
    labels_df,
):
    print(f"factor target games: {len(target_df)}")
    print(f"review monthly rows: {len(review_monthly_df)}")
    print(f"news monthly rows: {len(news_monthly_df)}")
    print(f"keyword summary rows: {len(keyword_summary_df)}")
    print(f"factor game summary rows: {len(game_summary_df)}")
    print(f"factor labels template rows: {len(labels_df)}")


def main():
    print(f"保存先: {get_data_dir()}")

    target_df = load_targets()

    reviews_df = pd.read_csv(get_path(REVIEWS_RAW_FILENAME), encoding="utf-8-sig")
    reviews_df["appid"] = reviews_df["appid"].astype(int)
    reviews_df["review_date"] = pd.to_datetime(reviews_df["review_date"], errors="coerce")
    reviews_df["voted_up"] = to_bool_series(reviews_df["voted_up"])
    reviews_with_keywords = add_keyword_columns(reviews_df)

    review_monthly_df = make_review_monthly(reviews_df)
    save_csv(review_monthly_df, REVIEW_MONTHLY_FILENAME)

    news_df = pd.read_csv(get_path(NEWS_FILENAME), encoding="utf-8-sig")
    news_df["appid"] = news_df["appid"].astype(int)
    news_df["news_date"] = pd.to_datetime(news_df["news_date"], errors="coerce")

    news_monthly_df = make_news_monthly(news_df)
    save_csv(news_monthly_df, NEWS_MONTHLY_FILENAME)

    keyword_summary_df = make_keyword_summary(reviews_with_keywords)
    save_csv(keyword_summary_df, KEYWORD_SUMMARY_FILENAME)

    game_summary_df = make_game_summary(
        target_df,
        review_monthly_df,
        news_monthly_df,
        reviews_with_keywords,
    )
    save_csv(game_summary_df, GAME_SUMMARY_FILENAME)

    labels_df = make_labels_template(game_summary_df)
    save_csv(labels_df, LABELS_TEMPLATE_FILENAME)

    print_summary(
        target_df,
        review_monthly_df,
        news_monthly_df,
        keyword_summary_df,
        game_summary_df,
        labels_df,
    )


if __name__ == "__main__":
    main()
