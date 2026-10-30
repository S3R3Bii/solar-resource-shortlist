"""Reconstruct all controlled removals directly from native daily source values."""

import calendar, csv, gzip, json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    with (ROOT / "results" / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    with gzip.open(
        ROOT / "data/records.csv.gz", "rt", encoding="utf-8", newline=""
    ) as f:
        raw = list(csv.DictReader(f))
    eligible = {
        r["point_id"]: r["cohort"]
        for r in read("point_eligibility.csv")
        if r["eligible"] == "True"
    }
    series = defaultdict(dict)
    for r in raw:
        if r["point_id"] in eligible and int(r["date"][:4]) >= 2017:
            assert r["valid"] == "True"
            series[r["point_id"], int(r["date"][:4])][
                date.fromisoformat(r["date"]).toordinal()
            ] = F(Decimal(r["native_w_m2"])) * F(24, 1000)
    expected = {}
    checks = 0

    def check(x, y, label):
        nonlocal checks
        assert x == str(y), (label, x, y)
        checks += 1

    def number(r, col, v):
        check(r[col + "_exact"], f"{v.numerator}/{v.denominator}", col)
        check(r[col], format(float(v), ".9f"), col + " display")

    for ident, year in series:
        values = series[ident, year]
        assert len(values) == 365 + calendar.isleap(year)
        full = sum(values.values(), F()) / len(values)
        for month in range(1, 13):
            for duration in [1, 7, 30]:
                start = date(year, month, 1).toordinal()
                end = min(start + duration, date(year + 1, 1, 1).toordinal())
                kept = [v for d, v in values.items() if d < start or d >= end]
                remaining = sum(kept, F()) / len(kept)
                expected[ident, year, month, duration] = dict(
                    cohort=eligible[ident],
                    removed_days=end - start,
                    remaining_days=len(kept),
                    full_days=len(values),
                    intact_mean=full,
                    remaining_mean=remaining,
                    signed_bias=remaining - full,
                    absolute_bias=abs(remaining - full),
                )
    rows = read("stress_point_cases.csv")
    assert len(rows) == len(expected) == 3024
    seen = set()
    for r in rows:
        key = (
            r["point_id"],
            int(r["year"]),
            int(r["start_month"]),
            int(r["duration_requested"]),
        )
        assert key not in seen
        seen.add(key)
        e = expected[key]
        for col in ["cohort", "removed_days", "remaining_days", "full_days"]:
            check(r[col], e[col], col)
        for col in ["intact_mean", "remaining_mean", "signed_bias", "absolute_bias"]:
            number(r, col, e[col])
    rank_expected = {}
    for cohort in ["west", "east"]:
        ids = sorted(i for i, c in eligible.items() if c == cohort)
        for year in range(2017, 2024):
            for month in range(1, 13):
                for duration in [1, 7, 30]:
                    full = {
                        i: expected[i, year, month, duration]["intact_mean"]
                        for i in ids
                    }
                    remaining = {
                        i: expected[i, year, month, duration]["remaining_mean"]
                        for i in ids
                    }
                    first = sorted(ids, key=lambda i: (-full[i], i))[:2]
                    second = sorted(ids, key=lambda i: (-remaining[i], i))[:2]
                    ties0 = sorted(i for i in ids if full[i] == full[first[-1]])
                    ties1 = sorted(
                        i for i in ids if remaining[i] == remaining[second[-1]]
                    )
                    regret = (
                        sum((full[i] for i in first), F())
                        - sum((full[i] for i in second), F())
                    ) / 2
                    rank_expected[cohort, year, month, duration] = dict(
                        removed_days=expected[ids[0], year, month, duration][
                            "removed_days"
                        ],
                        intact_shortlist=";".join(first),
                        remaining_shortlist=";".join(second),
                        intact_boundary_ties=";".join(ties0),
                        remaining_boundary_ties=";".join(ties1),
                        boundary_tie_intact=sum(
                            v >= full[first[-1]] for v in full.values()
                        )
                        > 2,
                        boundary_tie_remaining=sum(
                            v >= remaining[second[-1]] for v in remaining.values()
                        )
                        > 2,
                        shortlist_changed=set(first) != set(second),
                        overlap_count=len(set(first) & set(second)),
                        intact_mean_regret=regret,
                    )
    rows = read("stress_shortlists.csv")
    assert len(rows) == len(rank_expected) == 504
    seen = set()
    for r in rows:
        key = (
            r["cohort"],
            int(r["year"]),
            int(r["start_month"]),
            int(r["duration_requested"]),
        )
        assert key not in seen
        seen.add(key)
        e = rank_expected[key]
        for col in e:
            if col != "intact_mean_regret":
                check(r[col], e[col], col)
        number(r, "intact_mean_regret", e["intact_mean_regret"])
    rows = read("stress_metrics.csv")
    assert len(rows) == 6
    seen = set()
    for r in rows:
        key = (r["cohort"], int(r["duration"]))
        assert key not in seen
        seen.add(key)
        cohort, duration = key
        ps = [
            e
            for (i, y, m, d), e in expected.items()
            if e["cohort"] == cohort and d == duration
        ]
        rs = [
            e
            for (c, y, m, d), e in rank_expected.items()
            if c == cohort and d == duration
        ]
        for col, v in [
            ("point_cases", len(ps)),
            ("shortlist_cases", len(rs)),
            ("shortlist_changes", sum(e["shortlist_changed"] for e in rs)),
        ]:
            check(r[col], v, col)
        for col, v in [
            (
                "mean_absolute_bias",
                sum((e["absolute_bias"] for e in ps), F()) / len(ps),
            ),
            ("max_absolute_bias", max(e["absolute_bias"] for e in ps)),
            (
                "mean_intact_regret",
                sum((e["intact_mean_regret"] for e in rs), F()) / len(rs),
            ),
        ]:
            number(r, col, v)
    result = dict(
        status="PASS",
        checks=checks,
        point_cases=len(expected),
        shortlist_cases=len(rank_expected),
        metric_rows=len(rows),
        independence="Separate native-flux/ordinal-date removals and exact point,shortlist and metric reconstruction;no analysis-helper imports",
        limits="Fixed artificial common-calendar removals,not a calibrated source-missingness probability",
    )
    (ROOT / "results/independent_stress.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
