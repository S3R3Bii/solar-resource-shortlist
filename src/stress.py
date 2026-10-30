"""Fixed common-calendar removals;not a model of actual satellite missingness."""

import argparse, csv, gzip, hashlib, json, subprocess
from datetime import date, timedelta
from fractions import Fraction as Q
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def exact(x):
    return f"{x.numerator}/{x.denominator}"


def pack(row, name, x):
    row[name + "_exact"] = exact(x)
    row[name] = f"{float(x):.9f}"


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def block(year, month, duration):
    start = date(year, month, 1)
    return {
        start + timedelta(days=i)
        for i in range(duration)
        if (start + timedelta(days=i)).year == year
    }


def summarize(values, removed):
    assert values and not (set(removed) - set(values))
    remaining = [v for d, v in values.items() if d not in removed]
    assert remaining
    full = sum(values.values(), Q()) / len(values)
    partial = sum(remaining, Q()) / len(remaining)
    return full, partial, len(remaining)


def verify_freeze():
    from freeze_proof import verify

    verify()
    name = "results/stress_dependencies.json"
    manifest = json.loads((ROOT / name).read_text(encoding="utf-8"))
    commit = subprocess.check_output(
        ["git", "log", "-1", "--format=%H", "--", name], cwd=ROOT, text=True
    ).strip()
    assert commit
    assert (
        json.loads(
            subprocess.check_output(["git", "show", commit + ":" + name], cwd=ROOT)
        )
        == manifest
    )
    for item, digest in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / item).read_bytes()).hexdigest() == digest, item
        assert (
            hashlib.sha256(
                subprocess.check_output(["git", "show", commit + ":" + item], cwd=ROOT)
            ).hexdigest()
            == digest
        ), item
    return commit


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=ROOT / "results")
    a = p.parse_args()
    a.output_dir.mkdir(exist_ok=True)
    verify_freeze()
    with (ROOT / "results/annual_inputs.csv").open(encoding="utf-8", newline="") as f:
        annual = [
            r
            for r in csv.DictReader(f)
            if r["point_eligible"] == "True"
            and r["complete"] == "True"
            and int(r["year"]) >= 2017
        ]
    valid = {(r["point_id"], int(r["year"])) for r in annual}
    cohorts = {r["point_id"]: r["cohort"] for r in annual}
    values = {key: {} for key in valid}
    with gzip.open(
        ROOT / "data/records.csv.gz", "rt", encoding="utf-8", newline=""
    ) as f:
        for r in csv.DictReader(f):
            key = (r["point_id"], int(r["date"][:4]))
            if key in valid:
                assert r["valid"] == "True"
                values[key][date.fromisoformat(r["date"])] = Q(
                    r["irradiation_kwh_m2_day_exact"]
                )
    point_rows = []
    rank_rows = []
    metrics = []
    for cohort in ["west", "east"]:
        ids = sorted(k for k, v in cohorts.items() if v == cohort)
        for year in range(2017, 2024):
            if not all((i, year) in valid for i in ids):
                continue
            for duration in [1, 7, 30]:
                for month in range(1, 13):
                    removed = block(year, month, duration)
                    full = {}
                    partial = {}
                    for ident in ids:
                        base, estimated, n = summarize(values[ident, year], removed)
                        full[ident] = base
                        partial[ident] = estimated
                        row = dict(
                            cohort=cohort,
                            point_id=ident,
                            year=year,
                            start_month=month,
                            duration_requested=duration,
                            removed_days=len(removed),
                            remaining_days=n,
                            full_days=len(values[ident, year]),
                        )
                        for field, v in [
                            ("intact_mean", base),
                            ("remaining_mean", estimated),
                            ("signed_bias", estimated - base),
                            ("absolute_bias", abs(estimated - base)),
                        ]:
                            pack(row, field, v)
                        point_rows.append(row)
                    first = sorted(ids, key=lambda i: (-full[i], i))[:2]
                    second = sorted(ids, key=lambda i: (-partial[i], i))[:2]
                    ties0 = sorted(i for i in ids if full[i] == full[first[-1]])
                    ties1 = sorted(i for i in ids if partial[i] == partial[second[-1]])
                    row = dict(
                        cohort=cohort,
                        year=year,
                        start_month=month,
                        duration_requested=duration,
                        removed_days=len(removed),
                        intact_shortlist=";".join(first),
                        remaining_shortlist=";".join(second),
                        intact_boundary_ties=";".join(ties0),
                        remaining_boundary_ties=";".join(ties1),
                        boundary_tie_intact=sum(full[i] >= full[first[-1]] for i in ids)
                        > 2,
                        boundary_tie_remaining=sum(
                            partial[i] >= partial[second[-1]] for i in ids
                        )
                        > 2,
                        shortlist_changed=set(first) != set(second),
                        overlap_count=len(set(first) & set(second)),
                    )
                    pack(
                        row,
                        "intact_mean_regret",
                        (
                            sum((full[i] for i in first), Q())
                            - sum((full[i] for i in second), Q())
                        )
                        / 2,
                    )
                    rank_rows.append(row)
        for duration in [1, 7, 30]:
            ps = [
                r
                for r in point_rows
                if r["cohort"] == cohort and r["duration_requested"] == duration
            ]
            rs = [
                r
                for r in rank_rows
                if r["cohort"] == cohort and r["duration_requested"] == duration
            ]
            metric = dict(
                cohort=cohort,
                duration=duration,
                point_cases=len(ps),
                shortlist_cases=len(rs),
                shortlist_changes=sum(r["shortlist_changed"] for r in rs),
            )
            for field, v in [
                (
                    "mean_absolute_bias",
                    sum((Q(r["absolute_bias_exact"]) for r in ps), Q()) / len(ps),
                ),
                ("max_absolute_bias", max(Q(r["absolute_bias_exact"]) for r in ps)),
                (
                    "mean_intact_regret",
                    sum((Q(r["intact_mean_regret_exact"]) for r in rs), Q()) / len(rs),
                ),
            ]:
                pack(metric, field, v)
            metrics.append(metric)
    for name, rows in [
        ("stress_point_cases", point_rows),
        ("stress_shortlists", rank_rows),
        ("stress_metrics", metrics),
    ]:
        write(a.output_dir / (name + ".csv"), rows)
    print(
        json.dumps(
            dict(
                state="EXECUTED_FIXED_ARTIFICIAL_REMOVALS",
                point_cases=len(point_rows),
                shortlist_cases=len(rank_rows),
                metric_rows=len(metrics),
            )
        )
    )


if __name__ == "__main__":
    main()
