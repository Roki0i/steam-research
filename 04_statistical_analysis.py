"""Steamゲームのプレイヤー衰退に関する統計分析（Google Colab実行用）。"""

from itertools import combinations
from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05
DRIVE_DATA_DIR = Path("/content/drive/MyDrive/卒業研究/steam_research/data")
DATA_DIR = DRIVE_DATA_DIR if DRIVE_DATA_DIR.exists() else Path("./data")

plt.rcParams["font.family"] = [
    "Noto Sans CJK JP", "IPAexGothic", "Yu Gothic", "Hiragino Sans", "sans-serif"
]
plt.rcParams["figure.figsize"] = (10, 6)
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.25

DECLINE_COLUMNS = [
    "appid", "name", "category", "first_month", "latest_month", "peak_month",
    "months_observed", "peak_avg_players", "latest_avg_players", "decline_rate",
    "largest_monthly_drop_rate", "peak_to_latest_months",
]
REVIEW_COLUMNS = [
    "appid", "total_positive", "total_negative", "total_reviews", "negative_rate"
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
    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"{filename}に必要な列がありません: {missing}")
    return df


def holm_adjust(p_values):
    values = np.asarray(p_values, dtype=float)
    adjusted = np.full(len(values), np.nan)
    valid = np.flatnonzero(np.isfinite(values))
    if len(valid) == 0:
        return adjusted
    order = valid[np.argsort(values[valid])]
    running_max = 0.0
    m = len(order)
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

    for df in (decline_df, review_df):
        df["appid"] = pd.to_numeric(df["appid"], errors="coerce").astype("Int64")

    decline_dupes = int(decline_df["appid"].duplicated(keep=False).sum())
    review_dupes = int(review_df["appid"].duplicated(keep=False).sum())

    decline_df = decline_df.drop_duplicates("appid", keep="last")
    review_df = review_df.drop_duplicates("appid", keep="last")[REVIEW_COLUMNS]

    analysis_df = decline_df.merge(
        review_df, on="appid", how="left", validate="one_to_one"
    )

    numeric = [
        "months_observed", "peak_avg_players", "latest_avg_players", "decline_rate",
        "largest_monthly_drop_rate", "peak_to_latest_months", "total_positive",
        "total_negative", "total_reviews", "negative_rate",
    ]
    for column in numeric:
        analysis_df[column] = pd.to_numeric(analysis_df[column], errors="coerce")
    for column in ["first_month", "latest_month", "peak_month"]:
        analysis_df[column] = pd.to_datetime(analysis_df[column], errors="coerce")

    analysis_df = (
        analysis_df[ANALYSIS_COLUMNS]
        .sort_values(["category", "appid"])
        .reset_index(drop=True)
    )
    if analysis_df.empty:
        raise ValueError("結合後のanalysis_dfが空です。入力CSVを確認してください。")

    output = DATA_DIR / "analysis_dataset.csv"
    analysis_df.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"分析対象ゲーム数: {analysis_df['appid'].nunique()}")
    print(f"カテゴリ数: {analysis_df['category'].nunique(dropna=True)}")
    print("\nカテゴリ別作品数:")
    for category, count in analysis_df["category"].value_counts(dropna=False).items():
        print(f"  {category}: {count}")
    matched = int(analysis_df["total_reviews"].notna().sum())
    print(f"\nレビュー結合成功数: {matched}")
    print(f"レビュー欠損数: {len(analysis_df) - matched}")
    print(f"分析データ保存完了: {output}")
    return analysis_df, decline_dupes, review_dupes


def quality_check(df, decline_dupes, review_dupes):
    checks = {
        "decline入力のappid重複行数": decline_dupes,
        "review入力のappid重複行数": review_dupes,
        "analysis_dfのappid重複数": int(df["appid"].duplicated().sum()),
        "decline_rate欠損数": int(df["decline_rate"].isna().sum()),
        "negative_rate欠損数": int(df["negative_rate"].isna().sum()),
        "peak_avg_players欠損数": int(df["peak_avg_players"].isna().sum()),
        "category欠損数": int(df["category"].isna().sum()),
    }
    print_table("データ品質チェック", pd.DataFrame({
        "check": checks.keys(), "count": checks.values()
    }))
    print_table(
        "各カテゴリ作品数",
        df["category"].value_counts(dropna=False).rename("n").to_frame(),
    )
    print_table("months_observedの要約統計", df["months_observed"].describe().to_frame().T)
    print_table("total_reviewsの要約統計", df["total_reviews"].describe().to_frame().T)

    for name, count in checks.items():
        if count > 0:
            warnings.warn(f"データ品質警告: {name} = {count}")
    for category, count in df["category"].value_counts(dropna=False).items():
        if count < 5:
            warnings.warn(f"標本数警告: カテゴリ「{category}」はn={count}（5未満）です。")


def analyze_genres(df):
    data = df.dropna(subset=["category", "decline_rate"]).copy()
    summary = data.groupby("category")["decline_rate"].agg(
        n="count", median="median", mean="mean"
    )
    summary["IQR"] = (
        data.groupby("category")["decline_rate"].quantile(0.75)
        - data.groupby("category")["decline_rate"].quantile(0.25)
    )
    summary = summary.sort_values("median")
    print_table("カテゴリ別衰退率の要約", summary)

    groups = [
        (category, group["decline_rate"].to_numpy())
        for category, group in data.groupby("category")
        if len(group) > 0
    ]
    if len(groups) < 2:
        raise ValueError("Kruskal-Wallis検定には有効なカテゴリが2つ以上必要です。")

    h, p = stats.kruskal(*(values for _, values in groups))
    k = len(groups)
    n = sum(len(values) for _, values in groups)
    epsilon_sq = max(0.0, (h - k + 1) / (n - k)) if n > k else np.nan

    print("\n" + "=" * 72)
    print("分析1: カテゴリ間の衰退率差（Kruskal-Wallis検定）")
    print("帰無仮説: すべてのカテゴリで衰退率の分布は同じである。")
    print(f"H({k - 1}) = {h:.4f}, p = {p:.6g}, n = {n}")
    print(f"効果量 epsilon squared = {epsilon_sq:.4f}")
    print(
        "解釈: "
        + ("5%水準で統計的に有意であった。" if p < ALPHA
           else "5%水準で統計的に有意ではなかった。")
    )
    print("注意: 有意でなくても『差がない』とは断定できず、因果関係も示さない。")

    order = list(summary.index)
    plot_values = [
        data.loc[data["category"] == category, "decline_rate"].to_numpy()
        for category in order
    ]
    fig, ax = plt.subplots(figsize=(max(10, len(order) * 1.1), 6))
    ax.boxplot(plot_values, tick_labels=order, showmeans=True)
    rng = np.random.default_rng(42)
    for pos, values in enumerate(plot_values, start=1):
        ax.scatter(rng.normal(pos, 0.05, len(values)), values, alpha=0.55, s=18)
    ax.set_xlabel("カテゴリ")
    ax.set_ylabel("ピークから最新月までの衰退率")
    ax.set_title("カテゴリ別の衰退率")
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout()
    plt.show()
    return {"h": h, "p": p, "k": k, "n": n, "epsilon_sq": epsilon_sq, "groups": groups}


def posthoc_genres(result):
    columns = ["category_1", "category_2", "U", "raw_p", "holm_p", "significant"]
    if not np.isfinite(result["p"]) or result["p"] >= ALPHA:
        print("\nKruskal-Wallis検定が有意でなかったため、事後比較は実施しない。")
        posthoc = pd.DataFrame(columns=columns)
    else:
        rows = []
        for (c1, v1), (c2, v2) in combinations(result["groups"], 2):
            u, p = stats.mannwhitneyu(v1, v2, alternative="two-sided", method="auto")
            rows.append({"category_1": c1, "category_2": c2, "U": u, "raw_p": p})
        posthoc = pd.DataFrame(rows)
        posthoc["holm_p"] = holm_adjust(posthoc["raw_p"])
        posthoc["significant"] = posthoc["holm_p"] < ALPHA
        posthoc = posthoc[columns].sort_values("holm_p")
        print_table("カテゴリ間の事後比較（Mann-Whitney U + Holm）", posthoc)

    output = DATA_DIR / "posthoc_genre_results.csv"
    posthoc.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"事後比較結果保存: {output}")


def spearman_analysis(df, x, title, xlabel, log_x=False):
    part = df.dropna(subset=[x, "decline_rate"]).copy()
    if len(part) < 3 or part[x].nunique() < 2 or part["decline_rate"].nunique() < 2:
        rho, p = np.nan, np.nan
        warnings.warn(f"{title}: Spearman相関に必要な標本数または変動が不足しています。")
    else:
        rho, p = stats.spearmanr(part[x], part["decline_rate"])

    print("\n" + "=" * 72)
    print(title)
    print(f"Spearman rho = {rho:.4f}, p = {p:.6g}, n = {len(part)}")
    print(f"関連の方向: {direction_text(rho)}")
    print(f"効果の大きさ: {rho_strength(rho)}（解釈の目安）")
    print("注意: 相関から因果関係は断定できない。")

    plot = part[part[x] > 0] if log_x else part
    plt.scatter(plot[x], plot["decline_rate"], alpha=0.6)
    if log_x and not plot.empty:
        plt.xscale("log")
    plt.xlabel(xlabel)
    plt.ylabel("ピークから最新月までの衰退率")
    plt.title(title)
    plt.tight_layout()
    plt.show()
    return {"rho": rho, "p": p, "n": len(part)}


def analyze_reviews(df):
    part = df.dropna(subset=["negative_rate", "decline_rate", "total_reviews"]).copy()
    part = part[part["total_reviews"] > 0]
    if len(part) < 3 or part["negative_rate"].nunique() < 2 or part["decline_rate"].nunique() < 2:
        rho, p = np.nan, np.nan
        warnings.warn("累積低評価率: Spearman相関に必要な標本数または変動が不足しています。")
    else:
        rho, p = stats.spearmanr(part["negative_rate"], part["decline_rate"])

    print("\n" + "=" * 72)
    print("分析3: 累積低評価率と衰退率（Spearman順位相関）")
    print(f"Spearman rho = {rho:.4f}, p = {p:.6g}, n = {len(part)}")
    print(f"関連の方向: {direction_text(rho)}")
    print(f"効果の大きさ: {rho_strength(rho)}（解釈の目安）")
    print("注意: 累積レビューのため時間的前後関係は不明で、因果関係は示せない。")

    plt.scatter(part["negative_rate"], part["decline_rate"], alpha=0.6)
    plt.xlabel("Steam累積レビューの低評価率")
    plt.ylabel("ピークから最新月までの衰退率")
    plt.title("累積低評価率と衰退率")
    plt.tight_layout()
    plt.show()
    return {"rho": rho, "p": p, "n": len(part)}


def save_results(kw, peak, review):
    rows = [
        {
            "analysis": "カテゴリ間の衰退率差（Kruskal-Wallis）",
            "statistic": "H", "statistic_value": kw["h"], "raw_p": kw["p"],
            "effect_size": kw["epsilon_sq"], "n": kw["n"],
        },
        {
            "analysis": "ピーク時プレイヤー規模と衰退率（Spearman）",
            "statistic": "rho", "statistic_value": peak["rho"], "raw_p": peak["p"],
            "effect_size": abs(peak["rho"]) if np.isfinite(peak["rho"]) else np.nan,
            "n": peak["n"],
        },
        {
            "analysis": "累積低評価率と衰退率（Spearman）",
            "statistic": "rho", "statistic_value": review["rho"], "raw_p": review["p"],
            "effect_size": abs(review["rho"]) if np.isfinite(review["rho"]) else np.nan,
            "n": review["n"],
        },
    ]
    results = pd.DataFrame(rows)
    results["holm_p_exploratory"] = holm_adjust(results["raw_p"])
    results["significant_raw"] = results["raw_p"] < ALPHA
    results["significant_holm"] = results["holm_p_exploratory"] < ALPHA
    results = results[
        ["analysis", "statistic", "statistic_value", "raw_p", "holm_p_exploratory",
         "effect_size", "n", "significant_raw", "significant_holm"]
    ]
    print_table("主要統計結果", results)
    output = DATA_DIR / "statistical_results.csv"
    results.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"保存完了: {output}")
    print("主要3研究質問は生のp値を基本に報告し、Holm補正値は探索的参考値とする。")


def print_thesis_summary(df, kw, peak, review):
    print("\n" + "=" * 72)
    print("## 結果に書ける内容")
    print(f"- 分析対象は{df['appid'].nunique()}作品、{df['category'].nunique(dropna=True)}カテゴリ。")
    print(f"- カテゴリ間比較: H({kw['k'] - 1})={kw['h']:.3f}, p={kw['p']:.4g}, epsilon squared={kw['epsilon_sq']:.3f}。")
    print(f"- ピーク規模と衰退率: rho={peak['rho']:.3f}, p={peak['p']:.4g}, n={peak['n']}。")
    print(f"- 累積低評価率と衰退率: rho={review['rho']:.3f}, p={review['p']:.4g}, n={review['n']}。")
    print("- 有意でない結果を『差がない』『関連がない』とは断定しない。")

    print("\n## 考察に書ける内容")
    print("- カテゴリ差にはゲーム設計、運営形態、発売時期などの交絡要因が影響し得る。")
    print("- 相関が有意でも、ピーク規模や低評価が衰退を引き起こしたとは断定できない。")
    print("- レビュー時期を衰退前後に分ける縦断的分析は今後の改善点となる。")

    print("\n## 研究上の限界")
    limitations = [
        "decline_rateは観測期間中ピークから最新月までで、ピークの事後選択によるバイアスがある。",
        "発売時期・運営期間・観測期間がゲーム間で完全には統一されていない。",
        "SteamChartsに掲載され取得可能な作品だけを対象とする選択バイアスがある。",
        "Steam Storeタグによるカテゴリ分類には重複と意味の曖昧さがある。",
        "累積レビューのため評価と衰退の時間的前後関係が不明である。",
        "観察研究のためアップデート、価格施策、競合作品などの交絡要因を完全には統制できない。",
        "Steamゲーム全体への一般化には注意が必要である。",
    ]
    for text in limitations:
        print(f"- {text}")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"データ入出力先: {DATA_DIR.resolve()}")
    print("注: Spearman rhoの強さの区分は目安であり、絶対的基準ではありません。")
    print("主要3研究質問は生のp値を基本に報告し、研究質問間のHolm補正は探索的参考値とします。")

    df, decline_dupes, review_dupes = load_analysis_data()
    quality_check(df, decline_dupes, review_dupes)

    kw = analyze_genres(df)
    posthoc_genres(kw)

    peak = spearman_analysis(
        df,
        "peak_avg_players",
        "分析2: ピーク時プレイヤー規模と衰退率（Spearman順位相関）",
        "ピーク時平均プレイヤー数（log scale）",
        log_x=True,
    )
    review = analyze_reviews(df)

    save_results(kw, peak, review)
    print_thesis_summary(df, kw, peak, review)
    print("\n統計分析完了")


if __name__ == "__main__":
    main()
