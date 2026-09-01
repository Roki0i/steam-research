"""Steamゲームのプレイヤー衰退に関する統計分析（Google Colab実行用）。

主分析:
- ピークから12か月後の固定期間衰退率

感度分析:
- ピークから6か月後の固定期間衰退率

補助分析:
- ピークから最新月までの累積衰退率と観測期間の関連
"""

from itertools import combinations
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


ALPHA = 0.05
PRIMARY_OUTCOME = "decline_rate_12m"
SENSITIVITY_OUTCOME = "decline_rate_6m"
LEGACY_OUTCOME = "decline_rate"

DRIVE_DATA_DIR = Path("/content/drive/MyDrive/卒業研究/steam_research/data")
DATA_DIR = DRIVE_DATA_DIR if DRIVE_DATA_DIR.exists() else Path("./data")

plt.rcParams["font.family"] = [
    "Noto Sans CJK JP",
    "IPAexGothic",
    "Yu Gothic",
    "Hiragino Sans",
    "sans-serif",
]
plt.rcParams["figure.figsize"] = (10, 6)
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.25

DECLINE_COLUMNS = [
    "appid",
    "name",
    "category",
    "first_month",
    "latest_month",
    "peak_month",
    "months_observed",
    "peak_avg_players",
    "latest_avg_players",
    "players_6m_after_peak",
    "players_12m_after_peak",
    "decline_rate_6m",
    "decline_rate_12m",
    "eligible_6m",
    "eligible_12m",
    "decline_rate",
    "largest_monthly_drop_rate",
    "peak_to_latest_months",
]
REVIEW_COLUMNS = [
    "appid",
    "total_positive",
    "total_negative",
    "total_reviews",
    "negative_rate",
]
ANALYSIS_COLUMNS = DECLINE_COLUMNS + REVIEW_COLUMNS[1:]


def require_csv(filename, required_columns):
    path = DATA_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"入力CSVが見つかりません: {path}\n"
            "前段の収集・集計スクリプトを実行してください。"
        )

    df = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(
            f"{filename}に必要な列がありません: {missing}\n"
            "最新版のdecline_analysis.pyを実行して固定期間指標を再生成してください。"
        )
    return df


def holm_adjust(p_values):
    """NaNを保ったままHolm法でp値を補正する。"""
    values = np.asarray(p_values, dtype=float)
    adjusted = np.full(len(values), np.nan)
    valid_indices = np.flatnonzero(np.isfinite(values))
    if len(valid_indices) == 0:
        return adjusted

    order = valid_indices[np.argsort(values[valid_indices])]
    m = len(order)
    running_max = 0.0
    for rank, index in enumerate(order):
        running_max = max(running_max, (m - rank) * values[index])
        adjusted[index] = min(running_max, 1.0)
    return adjusted


def rho_strength(rho):
    if pd.isna(rho):
        return "判定不能"
    value = abs(rho)
    if value < 0.1:
        return "ほぼなし"
    if value < 0.3:
        return "弱い"
    if value < 0.5:
        return "中程度"
    return "強い"


def direction_text(value):
    if pd.isna(value) or value == 0:
        return "明確な方向なし"
    return "正" if value > 0 else "負"


def print_table(title, df):
    print(f"\n{title}")
    print("(データなし)" if df.empty else df.to_string())


def load_analysis_data():
    decline_df = require_csv("game_decline_summary.csv", DECLINE_COLUMNS)
    review_df = require_csv("review_summary_all.csv", REVIEW_COLUMNS)

    for frame in (decline_df, review_df):
        frame["appid"] = pd.to_numeric(frame["appid"], errors="coerce").astype("Int64")

    decline_duplicate_count = int(decline_df["appid"].duplicated(keep=False).sum())
    review_duplicate_count = int(review_df["appid"].duplicated(keep=False).sum())

    decline_unique = decline_df.drop_duplicates("appid", keep="last").copy()
    review_unique = (
        review_df.drop_duplicates("appid", keep="last")[REVIEW_COLUMNS].copy()
    )

    analysis_df = decline_unique.merge(
        review_unique,
        on="appid",
        how="left",
        validate="one_to_one",
    )

    numeric_columns = [
        "months_observed",
        "peak_avg_players",
        "latest_avg_players",
        "players_6m_after_peak",
        "players_12m_after_peak",
        "decline_rate_6m",
        "decline_rate_12m",
        "decline_rate",
        "largest_monthly_drop_rate",
        "peak_to_latest_months",
        "total_positive",
        "total_negative",
        "total_reviews",
        "negative_rate",
    ]
    for column in numeric_columns:
        analysis_df[column] = pd.to_numeric(analysis_df[column], errors="coerce")

    for column in ["first_month", "latest_month", "peak_month"]:
        analysis_df[column] = pd.to_datetime(analysis_df[column], errors="coerce")

    for column in ["eligible_6m", "eligible_12m"]:
        analysis_df[column] = analysis_df[column].astype("boolean")

    analysis_df = (
        analysis_df[ANALYSIS_COLUMNS]
        .sort_values(["category", "appid"])
        .reset_index(drop=True)
    )

    if analysis_df.empty:
        raise ValueError("結合後のanalysis_dfが空です。入力CSVを確認してください。")

    output_path = DATA_DIR / "analysis_dataset.csv"
    analysis_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"分析対象ゲーム総数: {analysis_df['appid'].nunique()}")
    print(f"カテゴリ数: {analysis_df['category'].nunique(dropna=True)}")
    print(
        f"主分析（12か月固定）対象数: "
        f"{analysis_df[PRIMARY_OUTCOME].notna().sum()}"
    )
    print(
        f"感度分析（6か月固定）対象数: "
        f"{analysis_df[SENSITIVITY_OUTCOME].notna().sum()}"
    )

    print("\nカテゴリ別の主分析対象数:")
    primary_counts = (
        analysis_df.dropna(subset=[PRIMARY_OUTCOME])
        .groupby("category")["appid"]
        .nunique()
        .sort_values()
    )
    for category, count in primary_counts.items():
        print(f"  {category}: {count}")

    review_matched = int(analysis_df["total_reviews"].notna().sum())
    print(f"\nレビュー結合成功数: {review_matched}")
    print(f"レビュー欠損数: {len(analysis_df) - review_matched}")
    print(f"分析データ保存完了: {output_path}")

    return analysis_df, decline_duplicate_count, review_duplicate_count


def quality_check(df, decline_duplicate_count, review_duplicate_count):
    checks = {
        "decline入力のappid重複行数": decline_duplicate_count,
        "review入力のappid重複行数": review_duplicate_count,
        "analysis_dfのappid重複数": int(df["appid"].duplicated().sum()),
        "12か月衰退率欠損数": int(df[PRIMARY_OUTCOME].isna().sum()),
        "6か月衰退率欠損数": int(df[SENSITIVITY_OUTCOME].isna().sum()),
        "累積衰退率欠損数": int(df[LEGACY_OUTCOME].isna().sum()),
        "negative_rate欠損数": int(df["negative_rate"].isna().sum()),
        "peak_avg_players欠損数": int(df["peak_avg_players"].isna().sum()),
        "category欠損数": int(df["category"].isna().sum()),
    }
    print_table(
        "データ品質チェック",
        pd.DataFrame({"check": checks.keys(), "count": checks.values()}),
    )

    fixed_counts = (
        df.groupby("category")
        .agg(
            total=("appid", "count"),
            eligible_6m=("decline_rate_6m", "count"),
            eligible_12m=("decline_rate_12m", "count"),
        )
        .sort_values("eligible_12m")
    )
    print_table("固定期間分析のカテゴリ別対象数", fixed_counts)
    print_table(
        "peak_to_latest_monthsの要約統計",
        df["peak_to_latest_months"].describe().to_frame().T,
    )
    print_table(
        "total_reviewsの要約統計",
        df["total_reviews"].describe().to_frame().T,
    )

    for name, count in checks.items():
        if count > 0 and "欠損" not in name:
            warnings.warn(f"データ品質警告: {name} = {count}")

    for category, count in (
        df.dropna(subset=[PRIMARY_OUTCOME])
        .groupby("category")["appid"]
        .nunique()
        .items()
    ):
        if count < 20:
            warnings.warn(
                f"主分析標本数警告: カテゴリ「{category}」はn={count}です。"
            )


def category_summary(df, outcome):
    data = df.dropna(subset=["category", outcome]).copy()
    summary = data.groupby("category")[outcome].agg(
        n="count",
        median="median",
        mean="mean",
    )
    summary["IQR"] = (
        data.groupby("category")[outcome].quantile(0.75)
        - data.groupby("category")[outcome].quantile(0.25)
    )
    return data, summary.sort_values("median")


def analyze_genres(df, outcome, analysis_label, plot_label):
    data, summary = category_summary(df, outcome)
    print_table(f"{analysis_label}: カテゴリ別要約", summary)

    valid_groups = [
        (category, group[outcome].to_numpy())
        for category, group in data.groupby("category")
        if len(group) > 0
    ]
    if len(valid_groups) < 2:
        raise ValueError(
            f"{analysis_label}: Kruskal-Wallis検定には有効なカテゴリが2つ以上必要です。"
        )

    h_stat, p_value = stats.kruskal(
        *(values for _, values in valid_groups)
    )
    k = len(valid_groups)
    n = sum(len(values) for _, values in valid_groups)
    epsilon_sq = (
        max(0.0, (h_stat - k + 1) / (n - k))
        if n > k
        else np.nan
    )

    print("\n" + "=" * 72)
    print(analysis_label)
    print("帰無仮説: すべてのカテゴリで衰退率の分布は同じである。")
    print(f"H({k - 1}) = {h_stat:.4f}, p = {p_value:.6g}, n = {n}")
    print(f"効果量 epsilon squared = {epsilon_sq:.4f}")
    print(
        "解釈: "
        + (
            "5%水準で統計的に有意であった。"
            if p_value < ALPHA
            else "5%水準で統計的に有意ではなかった。"
        )
    )
    print(
        "注意: 有意でなくても『差がない』とは断定できず、"
        "カテゴリそのものの因果効果を示すものでもない。"
    )

    order = list(summary.index)
    plot_values = [
        data.loc[data["category"] == category, outcome].to_numpy()
        for category in order
    ]
    fig, ax = plt.subplots(figsize=(max(10, len(order) * 1.1), 6))
    ax.boxplot(plot_values, tick_labels=order, showmeans=True)
    rng = np.random.default_rng(42)
    for position, values in enumerate(plot_values, start=1):
        ax.scatter(
            rng.normal(position, 0.05, len(values)),
            values,
            alpha=0.55,
            s=18,
        )
    ax.set_xlabel("カテゴリ")
    ax.set_ylabel(plot_label)
    ax.set_title(analysis_label)
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.show()

    return {
        "h": h_stat,
        "p": p_value,
        "k": k,
        "n": n,
        "epsilon_sq": epsilon_sq,
        "groups": valid_groups,
    }


def posthoc_genres(result, filename, label):
    columns = [
        "category_1",
        "category_2",
        "U",
        "raw_p",
        "holm_p",
        "significant",
    ]

    if not np.isfinite(result["p"]) or result["p"] >= ALPHA:
        print(f"\n{label}: 全体検定が有意でないため事後比較は実施しない。")
        posthoc_df = pd.DataFrame(columns=columns)
    else:
        rows = []
        for (category_1, values_1), (category_2, values_2) in combinations(
            result["groups"],
            2,
        ):
            u_stat, raw_p = stats.mannwhitneyu(
                values_1,
                values_2,
                alternative="two-sided",
                method="auto",
            )
            rows.append(
                {
                    "category_1": category_1,
                    "category_2": category_2,
                    "U": u_stat,
                    "raw_p": raw_p,
                }
            )

        posthoc_df = pd.DataFrame(rows)
        posthoc_df["holm_p"] = holm_adjust(posthoc_df["raw_p"])
        posthoc_df["significant"] = posthoc_df["holm_p"] < ALPHA
        posthoc_df = posthoc_df[columns].sort_values("holm_p")
        print_table(
            f"{label}: カテゴリ間事後比較（Mann-Whitney U + Holm）",
            posthoc_df,
        )

    output_path = DATA_DIR / filename
    posthoc_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"事後比較結果保存: {output_path}")
    return posthoc_df


def spearman_analysis(
    df,
    x,
    outcome,
    title,
    xlabel,
    ylabel,
    log_x=False,
    require_positive_reviews=False,
):
    required = [x, outcome]
    if require_positive_reviews:
        required.append("total_reviews")

    part = df.dropna(subset=required).copy()
    if require_positive_reviews:
        part = part[part["total_reviews"] > 0]

    if (
        len(part) < 3
        or part[x].nunique() < 2
        or part[outcome].nunique() < 2
    ):
        rho, p_value = np.nan, np.nan
        warnings.warn(
            f"{title}: Spearman相関に必要な標本数または変動が不足しています。"
        )
    else:
        rho, p_value = stats.spearmanr(part[x], part[outcome])

    print("\n" + "=" * 72)
    print(title)
    print(f"Spearman rho = {rho:.4f}, p = {p_value:.6g}, n = {len(part)}")
    print(f"関連の方向: {direction_text(rho)}")
    print(f"効果の大きさ: {rho_strength(rho)}（解釈の目安）")
    print("注意: 相関から因果関係は断定できない。")

    plot = part[part[x] > 0].copy() if log_x else part
    plt.scatter(plot[x], plot[outcome], alpha=0.6)
    if log_x and not plot.empty:
        plt.xscale("log")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.tight_layout()
    plt.show()

    return {
        "rho": rho,
        "p": p_value,
        "n": len(part),
    }


def observation_period_diagnostic(df):
    result = spearman_analysis(
        df=df,
        x="peak_to_latest_months",
        outcome=LEGACY_OUTCOME,
        title="補助分析: ピークから最新月までの経過月数と累積衰退率",
        xlabel="ピークから最新月までの経過月数",
        ylabel="ピークから最新月までの衰退率",
        log_x=False,
    )

    period_summary = (
        df.groupby("category")["peak_to_latest_months"]
        .agg(["count", "mean", "median"])
        .sort_values("median", ascending=False)
    )
    print_table("カテゴリ別 peak_to_latest_months", period_summary)
    return result


def build_result_rows(window, outcome, kw, peak, review):
    return [
        {
            "analysis_window": window,
            "outcome": outcome,
            "analysis": "カテゴリ間の衰退率差（Kruskal-Wallis）",
            "statistic": "H",
            "statistic_value": kw["h"],
            "raw_p": kw["p"],
            "effect_size": kw["epsilon_sq"],
            "n": kw["n"],
        },
        {
            "analysis_window": window,
            "outcome": outcome,
            "analysis": "ピーク時プレイヤー規模と衰退率（Spearman）",
            "statistic": "rho",
            "statistic_value": peak["rho"],
            "raw_p": peak["p"],
            "effect_size": (
                abs(peak["rho"])
                if np.isfinite(peak["rho"])
                else np.nan
            ),
            "n": peak["n"],
        },
        {
            "analysis_window": window,
            "outcome": outcome,
            "analysis": "累積低評価率と衰退率（Spearman）",
            "statistic": "rho",
            "statistic_value": review["rho"],
            "raw_p": review["p"],
            "effect_size": (
                abs(review["rho"])
                if np.isfinite(review["rho"])
                else np.nan
            ),
            "n": review["n"],
        },
    ]


def save_statistical_results(primary_results, sensitivity_results, diagnostic):
    primary_rows = build_result_rows("12m_primary", PRIMARY_OUTCOME, *primary_results)
    sensitivity_rows = build_result_rows(
        "6m_sensitivity",
        SENSITIVITY_OUTCOME,
        *sensitivity_results,
    )

    for rows in (primary_rows, sensitivity_rows):
        adjusted = holm_adjust([row["raw_p"] for row in rows])
        for row, adjusted_p in zip(rows, adjusted):
            row["holm_p_exploratory"] = adjusted_p
            row["significant_raw"] = (
                bool(row["raw_p"] < ALPHA)
                if np.isfinite(row["raw_p"])
                else False
            )
            row["significant_holm"] = (
                bool(adjusted_p < ALPHA)
                if np.isfinite(adjusted_p)
                else False
            )

    diagnostic_row = {
        "analysis_window": "diagnostic_latest",
        "outcome": LEGACY_OUTCOME,
        "analysis": "観測期間とピーク→最新月衰退率（Spearman）",
        "statistic": "rho",
        "statistic_value": diagnostic["rho"],
        "raw_p": diagnostic["p"],
        "holm_p_exploratory": np.nan,
        "effect_size": (
            abs(diagnostic["rho"])
            if np.isfinite(diagnostic["rho"])
            else np.nan
        ),
        "n": diagnostic["n"],
        "significant_raw": (
            bool(diagnostic["p"] < ALPHA)
            if np.isfinite(diagnostic["p"])
            else False
        ),
        "significant_holm": False,
    }

    results_df = pd.DataFrame(
        primary_rows + sensitivity_rows + [diagnostic_row]
    )
    column_order = [
        "analysis_window",
        "outcome",
        "analysis",
        "statistic",
        "statistic_value",
        "raw_p",
        "holm_p_exploratory",
        "effect_size",
        "n",
        "significant_raw",
        "significant_holm",
    ]
    results_df = results_df[column_order]

    print_table("主要統計結果・感度分析", results_df)
    output_path = DATA_DIR / "statistical_results.csv"
    results_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"保存完了: {output_path}")
    return results_df


def compare_primary_and_sensitivity(primary, sensitivity):
    rows = []
    names = [
        "カテゴリ差",
        "ピーク規模相関",
        "低評価率相関",
    ]

    for name, primary_result, sensitivity_result in zip(
        names,
        primary,
        sensitivity,
    ):
        if name == "カテゴリ差":
            primary_effect = primary_result["epsilon_sq"]
            sensitivity_effect = sensitivity_result["epsilon_sq"]
            primary_p = primary_result["p"]
            sensitivity_p = sensitivity_result["p"]
        else:
            primary_effect = primary_result["rho"]
            sensitivity_effect = sensitivity_result["rho"]
            primary_p = primary_result["p"]
            sensitivity_p = sensitivity_result["p"]

        rows.append(
            {
                "analysis": name,
                "primary_12m_effect": primary_effect,
                "primary_12m_p": primary_p,
                "sensitivity_6m_effect": sensitivity_effect,
                "sensitivity_6m_p": sensitivity_p,
                "same_significance_5pct": (
                    (primary_p < ALPHA) == (sensitivity_p < ALPHA)
                    if np.isfinite(primary_p) and np.isfinite(sensitivity_p)
                    else False
                ),
            }
        )

    comparison_df = pd.DataFrame(rows)
    print_table("12か月主分析と6か月感度分析の比較", comparison_df)
    output_path = DATA_DIR / "sensitivity_comparison.csv"
    comparison_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"感度分析比較保存: {output_path}")


def print_thesis_summary(
    df,
    primary,
    sensitivity,
    diagnostic,
):
    primary_kw, primary_peak, primary_review = primary
    sensitivity_kw, sensitivity_peak, sensitivity_review = sensitivity

    print("\n" + "=" * 72)
    print("## 分析設計")
    print(
        "- 初期指標のピーク→最新月衰退率は観測期間の影響を受けるため、"
        "主分析ではピーク12か月後の固定期間衰退率を採用した。"
    )
    print(
        f"- 観測期間とピーク→最新月衰退率の関連: "
        f"rho={diagnostic['rho']:.3f}, p={diagnostic['p']:.4g}, "
        f"n={diagnostic['n']}。"
    )
    print(
        f"- 主分析（12か月）の対象は"
        f"{df[PRIMARY_OUTCOME].notna().sum()}作品、"
        f"感度分析（6か月）は{df[SENSITIVITY_OUTCOME].notna().sum()}作品。"
    )

    print("\n## 結果に書ける内容")
    print(
        f"- 12か月固定のカテゴリ間比較: "
        f"H({primary_kw['k'] - 1})={primary_kw['h']:.3f}, "
        f"p={primary_kw['p']:.4g}, "
        f"epsilon squared={primary_kw['epsilon_sq']:.3f}, "
        f"n={primary_kw['n']}。"
    )
    print(
        f"- 12か月固定のピーク規模と衰退率: "
        f"rho={primary_peak['rho']:.3f}, "
        f"p={primary_peak['p']:.4g}, "
        f"n={primary_peak['n']}。"
    )
    print(
        f"- 12か月固定の累積低評価率と衰退率: "
        f"rho={primary_review['rho']:.3f}, "
        f"p={primary_review['p']:.4g}, "
        f"n={primary_review['n']}。"
    )
    print(
        f"- 6か月感度分析では、カテゴリ差 "
        f"p={sensitivity_kw['p']:.4g}、"
        f"ピーク規模相関 rho={sensitivity_peak['rho']:.3f}、"
        f"低評価率相関 rho={sensitivity_review['rho']:.3f} であった。"
    )
    print(
        "- 有意でない結果を『差がない』『関連がない』とは断定しない。"
    )

    print("\n## 考察に書ける内容")
    print(
        "- 固定期間化により、ゲームごとの観測期間の長さによる交絡を"
        "ピーク→最新月指標より抑えた。"
    )
    print(
        "- 12か月主分析と6か月感度分析で方向や有意性が一致するかを確認し、"
        "結果の頑健性を評価する。"
    )
    print(
        "- カテゴリ差にはゲーム設計、運営形態、発売時期などの"
        "未調整交絡要因が残り得る。"
    )
    print(
        "- 相関が有意でも、ピーク規模や低評価が衰退を引き起こしたとは"
        "断定できない。"
    )

    print("\n## 研究上の限界")
    limitations = [
        "12か月主分析ではピーク後12か月分の履歴が存在する作品のみを対象とするため、比較的新しい作品が除外される。",
        "6か月感度分析も同様に固定期間分の履歴を持つ作品に限定される。",
        "SteamChartsに掲載され、かつ月次データを取得できた作品だけを対象とする選択バイアスがある。",
        "Steam Storeタグによるカテゴリ分類には重複と意味の曖昧さがある。",
        "レビュー指標は取得時点までの累積値であり、12か月衰退期間と時間窓が一致していない。",
        "ピーク時プレイヤー規模は衰退率の分母にも用いられるため、規模との相関には指標構造上の依存が含まれる可能性がある。",
        "観察研究であり、アップデート、価格施策、競合作品、運営形態などの交絡要因を完全には統制できない。",
        "Steamゲーム全体への一般化には注意が必要である。",
    ]
    for limitation in limitations:
        print(f"- {limitation}")


def run_window_analysis(
    df,
    outcome,
    window_label,
    plot_label,
    posthoc_filename,
):
    kw_result = analyze_genres(
        df,
        outcome,
        f"{window_label}: カテゴリ間の衰退率差（Kruskal-Wallis検定）",
        plot_label,
    )
    posthoc_genres(
        kw_result,
        posthoc_filename,
        window_label,
    )

    peak_result = spearman_analysis(
        df=df,
        x="peak_avg_players",
        outcome=outcome,
        title=f"{window_label}: ピーク時プレイヤー規模と衰退率",
        xlabel="ピーク時平均プレイヤー数（log scale）",
        ylabel=plot_label,
        log_x=True,
    )

    review_result = spearman_analysis(
        df=df,
        x="negative_rate",
        outcome=outcome,
        title=f"{window_label}: 累積低評価率と衰退率",
        xlabel="Steam累積レビューの低評価率",
        ylabel=plot_label,
        log_x=False,
        require_positive_reviews=True,
    )

    return kw_result, peak_result, review_result


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"データ入出力先: {DATA_DIR.resolve()}")
    print(
        "主分析はピーク12か月後の固定期間衰退率、"
        "感度分析は6か月後の固定期間衰退率とします。"
    )
    print(
        "主要3研究質問では生のp値を基本に報告し、"
        "Holm補正値は探索的参考値として併記します。"
    )
    print(
        "Spearman rhoの強さの区分は解釈の目安であり、"
        "絶対的基準ではありません。"
    )

    df, decline_duplicate_count, review_duplicate_count = load_analysis_data()
    quality_check(df, decline_duplicate_count, review_duplicate_count)

    diagnostic = observation_period_diagnostic(df)

    primary_results = run_window_analysis(
        df=df,
        outcome=PRIMARY_OUTCOME,
        window_label="主分析（ピーク12か月後）",
        plot_label="ピークから12か月後までの衰退率",
        posthoc_filename="posthoc_genre_results.csv",
    )

    primary_posthoc_path = DATA_DIR / "posthoc_genre_results.csv"
    if primary_posthoc_path.exists():
        primary_posthoc = pd.read_csv(
            primary_posthoc_path,
            encoding="utf-8-sig",
        )
        primary_posthoc.to_csv(
            DATA_DIR / "posthoc_genre_results_12m.csv",
            index=False,
            encoding="utf-8-sig",
        )

    sensitivity_results = run_window_analysis(
        df=df,
        outcome=SENSITIVITY_OUTCOME,
        window_label="感度分析（ピーク6か月後）",
        plot_label="ピークから6か月後までの衰退率",
        posthoc_filename="posthoc_genre_results_6m.csv",
    )

    save_statistical_results(
        primary_results,
        sensitivity_results,
        diagnostic,
    )
    compare_primary_and_sensitivity(
        primary_results,
        sensitivity_results,
    )
    print_thesis_summary(
        df,
        primary_results,
        sensitivity_results,
        diagnostic,
    )

    print("\n統計分析完了")


if __name__ == "__main__":
    main()
