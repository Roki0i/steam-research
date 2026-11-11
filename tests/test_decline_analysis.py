"""Regression tests for the monthly-decline event selection rule."""
import unittest

import pandas as pd

from decline_analysis import largest_drop_metrics, make_game_decline_summary


class LargestDropMetricsTests(unittest.TestCase):
    def test_rising_months_are_not_decline_events(self):
        dates = pd.to_datetime(["2025-04-01", "2025-05-01"])
        data = pd.DataFrame({
            "month_date": dates,
            "monthly_drop_rate": [-0.10, 0.0],
        })
        month, rate = largest_drop_metrics(
            data, pd.Timestamp("2025-01-01"), start_months=3, end_months=12
        )
        self.assertIsNone(month)
        self.assertIsNone(rate)

    def test_selects_largest_positive_drop_within_window(self):
        data = pd.DataFrame({
            "month_date": pd.to_datetime([
                "2025-02-01", "2025-04-01", "2025-05-01", "2025-06-01"
            ]),
            "monthly_drop_rate": [0.80, -0.10, 0.25, 0.15],
        })
        month, rate = largest_drop_metrics(
            data, pd.Timestamp("2025-01-01"), start_months=3, end_months=5
        )
        self.assertEqual(month, pd.Timestamp("2025-05-01"))
        self.assertAlmostEqual(rate, 0.25)

    def test_summary_marks_no_eligible_late_decline_when_only_rising(self):
        data = pd.DataFrame({
            "appid": [123] * 5,
            "name": ["Example"] * 5,
            "category": ["Action"] * 5,
            "month_date": pd.to_datetime([
                "2025-01-01", "2025-02-01", "2025-03-01",
                "2025-04-01", "2025-05-01"
            ]),
            "avg_players": [100.0, 90.0, 95.0, 98.0, 99.0],
        })
        summary = make_game_decline_summary(data).iloc[0]
        self.assertFalse(summary["eligible_factor_3to12"])
        self.assertTrue(pd.isna(summary["largest_drop_month_3to12"]))
        self.assertTrue(pd.isna(summary["largest_monthly_drop_rate_3to12"]))


if __name__ == "__main__":
    unittest.main()
