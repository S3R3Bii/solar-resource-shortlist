"""Finite decision/calendar cases complement full independent export reconstruction."""

import sys, unittest
from datetime import date, timedelta
from fractions import Fraction as Q
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from model import predict, rank, shortlist, correlation, boundary_ties
from prepare_inputs import prepare
from project_source import convert_daily_mean
from decimal import Decimal


class Rules(unittest.TestCase):
    def test_persistence(self):
        self.assertEqual(predict(list(map(Q, range(1, 11))), "persistence"), 10)

    def test_three_year_window(self):
        self.assertEqual(predict(list(map(Q, range(1, 11))), "mean3"), 9)

    def test_five_year_window(self):
        self.assertEqual(predict(list(map(Q, range(1, 11))), "mean5"), 8)

    def test_ten_year_mean(self):
        self.assertEqual(predict(list(map(Q, range(1, 11))), "mean10"), Q(11, 2))

    def test_even_median(self):
        self.assertEqual(predict(list(map(Q, range(1, 11))), "median10"), Q(11, 2))

    def test_nearest_rank_quantile(self):
        self.assertEqual(predict(list(map(Q, range(1, 11))), "q20_10"), 2)

    def test_history_required(self):
        with self.assertRaises(AssertionError):
            predict([Q(1)] * 9, "mean10")

    def test_lower_quantile_retains_low_outcome(self):
        self.assertEqual(predict([Q(0), Q(0)] + [Q(10)] * 8, "q20_10"), 0)

    def test_midrank_tie(self):
        self.assertEqual(
            rank(dict(a=Q(3), b=Q(3), c=Q(1))), dict(a=Q(3, 2), b=Q(3, 2), c=Q(3))
        )

    def test_id_tie_break(self):
        self.assertEqual(shortlist(dict(C=Q(1), A=Q(1), B=Q(1))), ["A", "B"])

    def test_boundary_tie(self):
        self.assertEqual(
            boundary_ties(dict(A=Q(3), B=Q(2), C=Q(2))), (["B", "C"], True)
        )

    def test_complete_top_set_not_boundary_crossing(self):
        self.assertEqual(
            boundary_ties(dict(A=Q(3), B=Q(3), C=Q(1))), (["A", "B"], False)
        )

    def test_exact_near_tie(self):
        self.assertEqual(
            shortlist(dict(A=Q(1), B=Q(1) + Q(1, 10**25), C=Q(0))), ["B", "A"]
        )

    def test_perfect_rank(self):
        self.assertAlmostEqual(
            correlation(dict(a=Q(1), b=Q(2), c=Q(3)), dict(a=Q(4), b=Q(6), c=Q(9))), 1
        )

    def test_reverse_rank(self):
        self.assertAlmostEqual(
            correlation(dict(a=Q(1), b=Q(2), c=Q(3)), dict(a=Q(9), b=Q(6), c=Q(4))), -1
        )

    def test_constant_unknown(self):
        self.assertIsNone(correlation(dict(a=Q(1), b=Q(1)), dict(a=Q(2), b=Q(3))))

    def test_regret_not_ranking_distance(self):
        actual = dict(a=Q(10), b=Q(9), c=Q(8))
        forecast = dict(a=Q(10), b=Q(8), c=Q(9))
        oracle = shortlist(actual)
        selected = shortlist(forecast)
        self.assertEqual(
            (sum(actual[x] for x in oracle) - sum(actual[x] for x in selected)) / 2,
            Q(1, 2),
        )


class Calendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = []
        d = date(2001, 1, 1)
        while d <= date(2023, 12, 31):
            cls.records.append(
                dict(
                    point_id="W01",
                    cohort="west",
                    date=d.isoformat(),
                    native_w_m2="100",
                    valid="True",
                    irradiation_kwh_m2_day_exact="12/5",
                )
            )
            d += timedelta(days=1)
        cls.planned = [dict(id="W01", cohort="west", latitude=32.5, longitude=-114.5)]

    def qualify(self, missing=()):
        data = [
            dict(r, valid="False" if r["date"] in missing else r["valid"])
            for r in self.records
        ]
        return prepare(data, self.planned)

    def test_complete_calendar(self):
        self.assertEqual(self.qualify()[3]["complete_point_years"], 23)

    def test_leap_day(self):
        self.assertEqual(
            next(r for r in self.qualify()[0] if r["year"] == 2004)["planned_days"], 366
        )

    def test_single_missing_allowed_not_zero(self):
        r = next(r for r in self.qualify(["2001-01-01"])[0] if r["year"] == 2001)
        self.assertTrue(r["year_qualified"])
        self.assertEqual(r["mean_available_daily_kwh_m2_exact"], "12/5")
        self.assertFalse(r["complete"])

    def test_month_gate(self):
        self.assertFalse(
            next(
                r
                for r in self.qualify(["2001-01-01", "2001-01-02"])[0]
                if r["year"] == 2001
            )["year_qualified"]
        )

    def test_annual_gate(self):
        self.assertFalse(
            next(
                r
                for r in self.qualify(
                    ["2001-01-01", "2001-03-01", "2001-05-01", "2001-07-01"]
                )[0]
                if r["year"] == 2001
            )["year_qualified"]
        )

    def test_zero_is_valid(self):
        data = [
            dict(r, native_w_m2="0", irradiation_kwh_m2_day_exact="0/1")
            for r in self.records
        ]
        self.assertEqual(
            prepare(data, self.planned)[0][0]["mean_available_daily_kwh_m2_exact"],
            "0/1",
        )

    def test_duplicate_date_rejected(self):
        with self.assertRaises(AssertionError):
            prepare(self.records + [self.records[0]], self.planned)

    def test_identical_series_alias(self):
        data = self.records + [dict(r, point_id="W02") for r in self.records]
        p = self.planned + [
            dict(id="W02", cohort="west", latitude=34.5, longitude=-114.5)
        ]
        audit = prepare(data, p)[2]
        self.assertEqual(audit[1]["alias_of"], "W01")
        self.assertFalse(audit[1]["eligible"])

    def test_minimum_not_lowered(self):
        self.assertEqual(self.qualify()[3]["status"], "FAIL_MINIMUM_FIXED_COHORT")

    def test_native_unit_integration(self):
        self.assertEqual(convert_daily_mean(Decimal(1000), "W m-2"), 24)

    def test_unit_mismatch_rejected(self):
        with self.assertRaises(AssertionError):
            convert_daily_mean(Decimal(1000), "kWh/m2/day")

    def test_fill_never_converted(self):
        with self.assertRaises(AssertionError):
            convert_daily_mean(Decimal(-999), "W m-2")


if __name__ == "__main__":
    unittest.main()
