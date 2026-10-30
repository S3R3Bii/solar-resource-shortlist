"""Boundary fixtures for the fixed missing-day perturbation."""

import sys, unittest
from datetime import date, timedelta
from fractions import Fraction as Q
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from stress import block, summarize


class MissingDay(unittest.TestCase):
    def test_leap_month(self):
        self.assertIn(date(2020, 2, 29), block(2020, 2, 30))

    def test_year_end_no_wrap(self):
        self.assertEqual(len(block(2020, 12, 40)), 31)
        self.assertNotIn(date(2021, 1, 1), block(2020, 12, 40))

    def test_daily_mean_denominator(self):
        values = {date(2020, 1, i): Q(i) for i in range(1, 4)}
        self.assertEqual(summarize(values, {date(2020, 1, 3)}), (Q(2), Q(3, 2), 2))

    def test_missing_not_zero(self):
        values = {date(2020, 1, 1): Q(0), date(2020, 1, 2): Q(10)}
        self.assertEqual(summarize(values, {date(2020, 1, 1)}), (Q(5), Q(10), 1))

    def test_empty_remainder_rejected(self):
        with self.assertRaises(AssertionError):
            summarize({date(2020, 1, 1): Q(1)}, {date(2020, 1, 1)})

    def test_unknown_day_rejected(self):
        with self.assertRaises(AssertionError):
            summarize({date(2020, 1, 1): Q(1)}, {date(2020, 1, 2)})


if __name__ == "__main__":
    unittest.main()
