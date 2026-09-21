"""Evaluate Jev multi-label review classification against human labels.

Human-label CSV requirements:
- review_id
- one binary 0/1 column for every label in LABELS
Optional:
- split column: calibration / test
- rater2_<label> columns for inter-rater agreement

Thresholds are selected on calibration data only, then frozen for held-out test data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    cohen_kappa_score,
    f1_score,
    hamming_loss,
    jaccard_score,
    precision_score,
    recall_score,
)


DRIVE_DATA_DIR = Path("/content/drive/MyDrive/卒業研究/steam_research/data")
LABELS = [
    "bug_crash",
    "performance",
    "cheater",
    "server_connection",
    "matchmaking",
    "balance",
    "bad_update",
    "content_lack",
    "monetization",
    "management_liveops",
    "other",
]


def data_path(name: str) -> Path:
    if DRIVE_DATA_DIR.exists() or Path("/content/drive/MyDrive").exists():
        DRIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DRIVE_DATA_DIR / name
    Path("./data").mkdir(exist_ok=True)
    return Path("./data") / name


def deterministic_split(review_id: str) -> str:
    value = int(hashlib.sha256(str(review_id).encode()).hexdigest()[:8], 16)
    return "calibration" if value % 2 == 0 else "test"


def choose_threshold(y_true: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    if len(y_true) == 0 or np.sum(y_true == 1) == 0:
        return 0.5, np.nan
    best_t, best_f1 = 0.5, -1.0
    for t in np.arange(0.05, 0.951, 0.05):
        pred = (scores >= t).astype(int)
        value = f1_score(y_true, pred, zero_division=0)
        if value > best_f1:
            best_t, best_f1 = float(round(t, 2)), float(value)
    return best_t, best_f1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--classified", default=None)
    p.add_argument("--human", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    classified_path = Path(args.classified) if args.classified else data_path("review_classified.csv")
    human_path = Path(args.human)

    pred = pd.read_csv(classified_path, encoding="utf-8-sig")
    human = pd.read_csv(human_path, encoding="utf-8-sig")

    missing = {"review_id", *LABELS} - set(human.columns)
    if missing:
        raise ValueError(f"human label CSV に必要な列がありません: {sorted(missing)}")

    keep = ["review_id", *LABELS]
    merged = human.merge(
        pred[keep],
        on="review_id",
        how="inner",
        suffixes=("_human", "_jev"),
        validate="one_to_one",
    )
    if len(merged) < 50:
        raise ValueError(f"評価対象が少なすぎます: n={len(merged)}")

    if "split" in human.columns:
        split_map = human.set_index("review_id")["split"].astype(str).str.lower()
        merged["split"] = merged["review_id"].map(split_map)
    else:
        merged["split"] = merged["review_id"].astype(str).apply(deterministic_split)

    calibration = merged[merged["split"] == "calibration"].copy()
    test = merged[merged["split"] == "test"].copy()
    if calibration.empty or test.empty:
        raise ValueError("calibration/test の両方にデータが必要です。")

    thresholds: dict[str, float] = {}
    calibration_rows = []
    for label in LABELS:
        y = pd.to_numeric(calibration[f"{label}_human"], errors="coerce")
        s = pd.to_numeric(calibration[f"{label}_jev"], errors="coerce")
        valid = y.notna() & s.notna()
        threshold, cal_f1 = choose_threshold(
            y[valid].astype(int).to_numpy(),
            s[valid].astype(float).to_numpy(),
        )
        thresholds[label] = threshold
        calibration_rows.append(
            {
                "label": label,
                "threshold": threshold,
                "calibration_f1": cal_f1,
                "calibration_n": int(valid.sum()),
                "calibration_positive": int(y[valid].sum()),
            }
        )

    with open(data_path("jev_thresholds.json"), "w", encoding="utf-8") as f:
        json.dump(thresholds, f, ensure_ascii=False, indent=2)

    metric_rows = []
    matrix_true = pd.DataFrame(index=test.index)
    matrix_pred = pd.DataFrame(index=test.index)

    for label in LABELS:
        y = pd.to_numeric(test[f"{label}_human"], errors="coerce")
        s = pd.to_numeric(test[f"{label}_jev"], errors="coerce")
        valid = y.notna() & s.notna()
        yt = y[valid].astype(int).to_numpy()
        score = s[valid].astype(float).to_numpy()
        yp = (score >= thresholds[label]).astype(int)

        metric_rows.append(
            {
                "label": label,
                "threshold": thresholds[label],
                "test_n": len(yt),
                "positive_support": int(yt.sum()),
                "precision": precision_score(yt, yp, zero_division=0),
                "recall": recall_score(yt, yp, zero_division=0),
                "f1": f1_score(yt, yp, zero_division=0),
                "accuracy": accuracy_score(yt, yp),
                "brier_score": brier_score_loss(yt, score),
                "tp": int(((yt == 1) & (yp == 1)).sum()),
                "fp": int(((yt == 0) & (yp == 1)).sum()),
                "fn": int(((yt == 1) & (yp == 0)).sum()),
                "tn": int(((yt == 0) & (yp == 0)).sum()),
            }
        )
        matrix_true.loc[valid, label] = yt
        matrix_pred.loc[valid, label] = yp

    pd.DataFrame(calibration_rows).to_csv(
        data_path("jev_threshold_calibration.csv"), index=False, encoding="utf-8-sig"
    )
    metrics = pd.DataFrame(metric_rows)
    metrics.to_csv(data_path("jev_validation_metrics.csv"), index=False, encoding="utf-8-sig")

    complete = matrix_true.dropna().index.intersection(matrix_pred.dropna().index)
    yt_all = matrix_true.loc[complete].astype(int).to_numpy()
    yp_all = matrix_pred.loc[complete].astype(int).to_numpy()

    overall = {
        "test_complete_cases": len(complete),
        "micro_f1": f1_score(yt_all, yp_all, average="micro", zero_division=0),
        "macro_f1": f1_score(yt_all, yp_all, average="macro", zero_division=0),
        "hamming_loss": hamming_loss(yt_all, yp_all),
        "jaccard_samples": jaccard_score(yt_all, yp_all, average="samples", zero_division=0),
        "subset_accuracy": accuracy_score(yt_all, yp_all),
    }
    pd.DataFrame([overall]).to_csv(
        data_path("jev_validation_overall.csv"), index=False, encoding="utf-8-sig"
    )

    agreement_rows = []
    for label in LABELS:
        rater2 = f"rater2_{label}"
        if rater2 not in human.columns:
            continue
        pair = human[[label, rater2]].apply(pd.to_numeric, errors="coerce").dropna()
        kappa = (
            cohen_kappa_score(pair[label].astype(int), pair[rater2].astype(int))
            if len(pair) > 0
            else np.nan
        )
        agreement_rows.append(
            {
                "label": label,
                "n_double_coded": len(pair),
                "cohen_kappa": kappa,
            }
        )
    if agreement_rows:
        pd.DataFrame(agreement_rows).to_csv(
            data_path("jev_human_agreement.csv"), index=False, encoding="utf-8-sig"
        )

    print(f"merged labeled reviews: {len(merged)}")
    print(f"calibration: {len(calibration)}")
    print(f"test: {len(test)}")
    print("thresholds:", thresholds)
    print("overall:", overall)
    print("Primary reporting: per-label Precision/Recall/F1 + micro/macro F1.")
    print("Accuracy/subset accuracy is secondary because multi-label classes are imbalanced.")


if __name__ == "__main__":
    main()
