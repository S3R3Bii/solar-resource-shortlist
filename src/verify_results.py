"""Independently reconstruct history cutoffs,finite shortlists and development choice."""

import argparse, csv, json, math
from collections import defaultdict
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = ["persistence", "mean3", "mean5", "mean10", "median10", "q20_10"]


def read(name):
    with (ROOT / "results" / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["development", "held"])
    a = p.parse_args()
    stage = a.stage
    checks = 0

    def check(x, y, label):
        nonlocal checks
        assert x == str(y), (label, x, y)
        checks += 1

    def number(row, key, v):
        check(row[key + "_exact"], f"{v.numerator}/{v.denominator}", key)
        check(row[key], format(float(v), ".9f"), key + " display")

    def ranks(values):
        ordered = sorted(values, key=values.get, reverse=True)
        result = {}
        for key in ordered:
            positions = [
                i + 1 for i, k in enumerate(ordered) if values[k] == values[key]
            ]
            result[key] = F(sum(positions), len(positions))
        return result

    def top(values):
        result = []
        for key in sorted(values):
            if not result:
                result.append(key)
                continue
            result.append(key)
            result.sort(key=lambda k: (-values[k], k))
        return result[:2]

    inputs = [r for r in read("annual_inputs.csv") if r["point_eligible"] == "True"]
    resources = {
        (r["point_id"], int(r["year"])): F(r["mean_available_daily_kwh_m2_exact"])
        for r in inputs
    }
    cohorts = {r["point_id"]: r["cohort"] for r in inputs}
    expected = {}
    forecast_expected = {}
    for cohort in ["west"] if stage == "development" else ["west", "east"]:
        ids = sorted(i for i, g in cohorts.items() if g == cohort)
        for year in range(2011, 2017) if stage == "development" else range(2017, 2024):
            actual = {i: resources[i, year] for i in ids}
            oracle = top(actual)
            best = sum((actual[i] for i in oracle), F()) / 2
            ar = ranks(actual)
            oracle_ties = sorted(i for i in ids if actual[i] == actual[oracle[-1]])
            oracle_boundary = sum(actual[i] >= actual[oracle[-1]] for i in ids) > 2
            for rule in RULES:
                window = (
                    1
                    if rule == "persistence"
                    else {"mean3": 3, "mean5": 5, "mean10": 10}.get(rule, 10)
                )
                pred = {}
                years = list(range(year - window, year))
                assert all(y < year for y in years)
                checks += 1
                for ident in ids:
                    sample = [resources[ident, y] for y in years]
                    ordered = sorted(sample)
                    if rule == "q20_10":
                        pred[ident] = ordered[(len(ordered) + 4) // 5 - 1]
                    elif rule == "median10":
                        pred[ident] = (ordered[4] + ordered[5]) / 2
                    else:
                        pred[ident] = sum(sample, F()) / len(sample)
                chosen = top(pred)
                pr = ranks(pred)
                px = sum(pr.values(), F()) / len(ids)
                ax = sum(ar.values(), F()) / len(ids)
                numerator = sum((pr[i] - px) * (ar[i] - ax) for i in ids)
                denominator = sum((pr[i] - px) ** 2 for i in ids) * sum(
                    (ar[i] - ax) ** 2 for i in ids
                )
                rho = (
                    format(float(numerator) / math.sqrt(float(denominator)), ".9f")
                    if denominator
                    else ""
                )
                selected = sum((actual[i] for i in chosen), F()) / 2
                mae = sum((abs(pred[i] - actual[i]) for i in ids), F()) / len(ids)
                ties = sorted(i for i in ids if pred[i] == pred[chosen[-1]])
                boundary = sum(pred[i] >= pred[chosen[-1]] for i in ids) > 2
                expected[cohort, year, rule] = dict(
                    selected=chosen,
                    oracle=oracle,
                    score_boundary_ties=ties,
                    boundary_tie=boundary,
                    oracle_boundary_ties=oracle_ties,
                    oracle_boundary_tie=oracle_boundary,
                    overlap_count=len(set(chosen) & set(oracle)),
                    spearman=rho,
                    selected_actual_mean=selected,
                    oracle_actual_mean=best,
                    regret=best - selected,
                    mae=mae,
                    points=len(ids),
                )
                assert best >= selected
                checks += 1
                for ident in ids:
                    forecast_expected[cohort, year, rule, ident] = dict(
                        prediction=pred[ident],
                        actual=actual[ident],
                        absolute_error=abs(pred[ident] - actual[ident]),
                        input_years=";".join(map(str, years)),
                        selected=ident in chosen,
                        oracle=ident in oracle,
                        predicted_midrank_exact=f"{pr[ident].numerator}/{pr[ident].denominator}",
                        actual_midrank_exact=f"{ar[ident].numerator}/{ar[ident].denominator}",
                    )
    rows = read(stage + "_predictions.csv")
    assert len(rows) == len(forecast_expected)
    seen = set()
    for r in rows:
        key = (r["cohort"], int(r["year"]), r["config"], r["point_id"])
        assert key not in seen
        seen.add(key)
        e = forecast_expected[key]
        check(r["stage"], stage, "stage")
        for col in [
            "input_years",
            "selected",
            "oracle",
            "predicted_midrank_exact",
            "actual_midrank_exact",
        ]:
            check(r[col], e[col], col)
        for col in ["prediction", "actual", "absolute_error"]:
            number(r, col, e[col])
    rows = read(stage + "_annual_scores.csv")
    assert len(rows) == len(expected)
    seen = set()
    for r in rows:
        key = (r["cohort"], int(r["year"]), r["config"])
        assert key not in seen
        seen.add(key)
        e = expected[key]
        check(r["stage"], stage, "stage")
        for col in [
            "selected",
            "oracle",
            "score_boundary_ties",
            "oracle_boundary_ties",
        ]:
            check(r[col], ";".join(e[col]), col)
        for col in [
            "points",
            "boundary_tie",
            "oracle_boundary_tie",
            "overlap_count",
            "spearman",
        ]:
            check(r[col], e[col], col)
        for col in ["selected_actual_mean", "oracle_actual_mean", "regret", "mae"]:
            number(r, col, e[col])
    rows = read(stage + "_metrics.csv")
    assert len(rows) == 6 * (1 if stage == "development" else 2)
    seen = set()
    dev = []
    for r in rows:
        key = (r["cohort"], r["config"])
        assert key not in seen
        seen.add(key)
        es = [e for (c, y, k), e in expected.items() if c == key[0] and k == key[1]]
        rhos = [float(e["spearman"]) for e in es if e["spearman"] != ""]
        check(r["stage"], stage, "stage")
        for col, v in [
            ("years", len(es)),
            ("points", es[0]["points"]),
            ("undefined_spearman_years", len(es) - len(rhos)),
            ("boundary_tie_years", sum(e["boundary_tie"] for e in es)),
            ("oracle_boundary_tie_years", sum(e["oracle_boundary_tie"] for e in es)),
            (
                "mean_spearman",
                format(math.fsum(rhos) / len(rhos), ".9f") if rhos else "",
            ),
        ]:
            check(r[col], v, col)
        mean_regret = sum((e["regret"] for e in es), F()) / len(es)
        mean_mae = sum((e["mae"] for e in es), F()) / len(es)
        for col, v in [
            ("mean_regret", mean_regret),
            ("mean_mae", mean_mae),
            ("mean_overlap", F(sum(e["overlap_count"] for e in es), 2 * len(es))),
        ]:
            number(r, col, v)
        dev.append(
            dict(
                config=key[1],
                regret_exact=f"{mean_regret.numerator}/{mean_regret.denominator}",
                mae_exact=f"{mean_mae.numerator}/{mean_mae.denominator}",
            )
        )
    if stage == "development":
        ordered = sorted(
            dev,
            key=lambda r: (
                F(r["regret_exact"]),
                F(r["mae_exact"]),
                RULES.index(r["config"]),
            ),
        )
        selection = json.loads(
            (ROOT / "results/selection.json").read_text(encoding="utf-8")
        )
        assert (
            selection["candidate_order"] == RULES
            and selection["all_candidates"] == ordered
            and selection["selected"] == ordered[0]["config"]
            and selection["held_tuned"] is False
        )
        checks += 4
    result = dict(
        status="PASS",
        stage=stage,
        checks=checks,
        prediction_rows=len(forecast_expected),
        annual_rows=len(expected),
        metric_rows=len(rows),
        independence="Separate history-year enumeration,order statistics,midranks,finite oracle/regret and selection reconstruction;no analysis-helper imports",
        limits="Retrospective current-source finite cohort,not original-vintage or ground-station validation",
    )
    (ROOT / "results" / f"independent_{stage}.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
