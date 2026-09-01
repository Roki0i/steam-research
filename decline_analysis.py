import os

import pandas as pd


DRIVE_DATA_DIR = "/content/drive/MyDrive/卒業研究/steam_research/data"

INPUT_FILENAME = "steamcharts_monthly.csv"
CLEAN_FILENAME = "steamcharts_monthly_clean.csv"
GAME_DECLINE_FILENAME = "game_decline_summary.csv"
CATEGORY_DECLINE_FILENAME = "category_decline_summary.csv"
TOP_GAMES_FILENAME = "top_games_by_category.csv"
FACTOR_TARGET_FILENAME = "factor_target_games.csv"

FIXED_HORIZONS = (6, 12)


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


def to_number(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("+", "", regex=False)
        .str.strip(),
        errors="coerce",
    )


def month_diff(start_date, end_date):
    if pd.isna(start_date) or pd.isna(end_date):
        return None
    return (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)


def load_and_clean():
    input_path = get_path(INPUT_FILENAME)
    if not os.path.exists(input_path):
        raise FileNotFoundError(
            f"入力CSVが見つかりません: {input_path}\n"
            "先にsteamcharts_collect.pyを実行してください。"
        )

    df = pd.read_csv(input_path, encoding="utf-8-sig")
    df = df[df["month"] != "Last 30 Days"].copy()
    df["month_date"] = pd.to_datetime(df["month"], errors="coerce")

    for column in ["avg_players", "peak_players", "gain", "gain_percent"]:
        df[column] = to_number(df[column])

    required_columns = [
        "appid",
        "name",
        "category",
        "month_date",
        "avg_players",
        "peak_players",
    ]
    df = df.dropna(subset=required_columns).copy()
    df["appid"] = df["appid"].astype(int)
    df = df.sort_values(["appid", "month_date"]).reset_index(drop=True)
    return df


def get_horizon_row(game_df, peak_month, horizon_months):
    """ピーク月から正確にhorizon_months後の月次行を返す。"""
    target_period = peak_month.to_period("M") + horizon_months
    periods = game_df["month_date"].dt.to_period("M")
    matched = game_df.loc[periods == target_period]
    if matched.empty:
        return None
    return matched.iloc[-1]


def fixed_horizon_metrics(game_df, peak_row, horizon_months):
    horizon_row = get_horizon_row(
        game_df,
        peak_row["month_date"],
        horizon_months,
    )
    player_col = f"players_{horizon_months}m_after_peak"
    decline_col = f"decline_rate_{horizon_months}m"
    eligible_col = f"eligible_{horizon_months}m"

    if horizon_row is None:
        return {
            player_col: None,
            decline_col: None,
            eligible_col: False,
        }

    peak_players = peak_row["avg_players"]
    horizon_players = horizon_row["avg_players"]
    decline_rate = None
    if pd.notna(peak_players) and peak_players > 0 and pd.notna(horizon_players):
        decline_rate = (peak_players - horizon_players) / peak_players

    return {
        player_col: horizon_players,
        decline_col: decline_rate,
        eligible_col: decline_rate is not None,
    }


def make_game_decline_summary(clean_df):
    rows = []

    for appid, game_df in clean_df.groupby("appid", sort=False):
        game_df = game_df.sort_values("month_date").copy()
        first_row = game_df.iloc[0]
        latest_row = game_df.iloc[-1]
        peak_index = game_df["avg_players"].idxmax()
        peak_row = game_df.loc[peak_index]

        game_df["prev_avg_players"] = game_df["avg_players"].shift(1)
        game_df["monthly_drop_rate"] = (
            game_df["prev_avg_players"] - game_df["avg_players"]
        ) / game_df["prev_avg_players"]
        game_df.loc[game_df["prev_avg_players"] <= 0, "monthly_drop_rate"] = None

        drop_df = game_df[
            game_df["month_date"] > peak_row["month_date"]
        ].dropna(subset=["monthly_drop_rate"])
        if drop_df.empty:
            largest_drop_row = latest_row
            largest_monthly_drop_rate = None
        else:
            largest_drop_row = drop_df.loc[drop_df["monthly_drop_rate"].idxmax()]
            largest_monthly_drop_rate = largest_drop_row["monthly_drop_rate"]

        peak_avg_players = peak_row["avg_players"]
        latest_avg_players = latest_row["avg_players"]
        if peak_avg_players > 0:
            decline_rate = (peak_avg_players - latest_avg_players) / peak_avg_players
        else:
            decline_rate = None

        row = {
            "appid": int(appid),
            "name": latest_row["name"],
            "category": latest_row["category"],
            "first_month": first_row["month_date"],
            "latest_month": latest_row["month_date"],
            "peak_month": peak_row["month_date"],
            "largest_drop_month": largest_drop_row["month_date"],
            "months_observed": len(game_df),
            "peak_avg_players": peak_avg_players,
            "latest_avg_players": latest_avg_players,
            # 補助指標: ピークから最新月まで。観測期間の長さに影響される。
            "decline_rate": decline_rate,
            "largest_monthly_drop_rate": largest_monthly_drop_rate,
            "peak_to_latest_months": month_diff(
                peak_row["month_date"], latest_row["month_date"]
            ),
        }

        for horizon in FIXED_HORIZONS:
            row.update(fixed_horizon_metrics(game_df, peak_row, horizon))

        rows.append(row)

    return pd.DataFrame(rows)


def make_category_decline_summary(game_decline_df):
    summary_df = (
        game_decline_df.groupby("category", as_index=False)
        .agg(
            game_count=("appid", "count"),
            eligible_6m=("eligible_6m", "sum"),
            eligible_12m=("eligible_12m", "sum"),
            avg_decline_rate_6m=("decline_rate_6m", "mean"),
            median_decline_rate_6m=("decline_rate_6m", "median"),
            avg_decline_rate_12m=("decline_rate_12m", "mean"),
            median_decline_rate_12m=("decline_rate_12m", "median"),
            avg_decline_rate=("decline_rate", "mean"),
            median_decline_rate=("decline_rate", "median"),
            avg_largest_monthly_drop_rate=("largest_monthly_drop_rate", "mean"),
            avg_peak_players=("peak_avg_players", "mean"),
            median_peak_players=("peak_avg_players", "median"),
            avg_latest_players=("latest_avg_players", "mean"),
            median_latest_players=("latest_avg_players", "median"),
            avg_months_observed=("months_observed", "mean"),
        )
        .sort_values("category")
    )
    return summary_df


def make_top_games(game_decline_df, top_n):
    # 要因分析用の既存パイプラインを壊さないため、従来のピーク→最新月の衰退率で抽出する。
    return (
        game_decline_df.sort_values(
            ["category", "decline_rate"],
            ascending=[True, False],
        )
        .groupby("category", as_index=False)
        .head(top_n)
        .reset_index(drop=True)
    )


def print_summary(clean_df, game_decline_df, category_decline_df, top_df, target_df):
    print(f"clean rows: {len(clean_df)}")
    print(f"clean games: {clean_df['appid'].nunique()}")
    print(f"game_decline rows: {len(game_decline_df)}")
    print(f"category_decline rows: {len(category_decline_df)}")
    print(f"top_games_by_category rows: {len(top_df)}")
    print(f"factor_target_games rows: {len(target_df)}")
    print("category game counts:")

    for category, count in game_decline_df["category"].value_counts(sort=False).items():
        print(f"  {category}: {count}")

    print("fixed-horizon eligible counts:")
    for horizon in FIXED_HORIZONS:
        print(f"  {horizon} months:")
        counts = (
            game_decline_df.groupby("category")[f"eligible_{horizon}m"]
            .sum()
            .astype(int)
        )
        for category, count in counts.items():
            print(f"    {category}: {count}")


def main():
    print(f"保存先: {get_data_dir()}")

    clean_df = load_and_clean()
    save_csv(clean_df, CLEAN_FILENAME)

    game_decline_df = make_game_decline_summary(clean_df)
    save_csv(game_decline_df, GAME_DECLINE_FILENAME)

    category_decline_df = make_category_decline_summary(game_decline_df)
    save_csv(category_decline_df, CATEGORY_DECLINE_FILENAME)

    top_df = make_top_games(game_decline_df, 10)
    save_csv(top_df, TOP_GAMES_FILENAME)

    target_df = make_top_games(game_decline_df, 5)
    save_csv(target_df, FACTOR_TARGET_FILENAME)

    print_summary(clean_df, game_decline_df, category_decline_df, top_df, target_df)


if __name__ == "__main__":
    main()
