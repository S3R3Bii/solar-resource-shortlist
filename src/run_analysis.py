"""Select on western development years,then apply the frozen rule to later cases."""

import argparse, csv, json, math
from collections import defaultdict
from fractions import Fraction as Q
from pathlib import Path
from model import CONFIGS, predict, rank, shortlist, correlation, boundary_ties

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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["development", "held"])
    p.add_argument("--output-dir", type=Path, default=ROOT / "results")
    a = p.parse_args()
    a.output_dir.mkdir(exist_ok=True)
    if a.stage == "held":
        from freeze_proof import verify

        verify()
    with (ROOT / "results/annual_inputs.csv").open(encoding="utf-8", newline="") as f:
        inputs = [r for r in csv.DictReader(f) if r["point_eligible"] == "True"]
        values = {
            (r["point_id"], int(r["year"])): Q(r["mean_available_daily_kwh_m2_exact"])
            for r in inputs
        }
        cohorts = {r["point_id"]: r["cohort"] for r in inputs}
        predictions = []
        outcomes = []
    for cohort in ["west"] if a.stage == "development" else ["west", "east"]:
        points = sorted(k for k, v in cohorts.items() if v == cohort)
        for year in (
            range(2011, 2017) if a.stage == "development" else range(2017, 2024)
        ):
            actual = {k: values[k, year] for k in points}
            oracle = shortlist(actual)
            oracle_mean = sum((actual[k] for k in oracle), Q()) / 2
            oracle_ties, oracle_boundary = boundary_ties(actual)
            for config in CONFIGS:
                histories = {
                    k: [values[k, y] for y in range(year - 10, year)] for k in points
                }
                forecast = {k: predict(histories[k], config) for k in points}
                selected = shortlist(forecast)
                pred_rank = rank(forecast)
                actual_rank = rank(actual)
                ties, boundary = boundary_ties(forecast)
                chosen_mean = sum((actual[k] for k in selected), Q()) / 2
                mae = sum((abs(forecast[k] - actual[k]) for k in points), Q()) / len(
                    points
                )
                rho = correlation(forecast, actual)
                row = dict(
                    stage=a.stage,
                    cohort=cohort,
                    year=year,
                    config=config,
                    points=len(points),
                    selected=";".join(selected),
                    oracle=";".join(oracle),
                    score_boundary_ties=";".join(ties),
                    boundary_tie=boundary,
                    oracle_boundary_ties=";".join(oracle_ties),
                    oracle_boundary_tie=oracle_boundary,
                    overlap_count=len(set(selected) & set(oracle)),
                    spearman="" if rho is None else f"{rho:.9f}",
                )
                for field, x in [
                    ("selected_actual_mean", chosen_mean),
                    ("oracle_actual_mean", oracle_mean),
                    ("regret", oracle_mean - chosen_mean),
                    ("mae", mae),
                ]:
                    pack(row, field, x)
                outcomes.append(row)
                window = (
                    1
                    if config == "persistence"
                    else int(config[4:]) if config.startswith("mean") else 10
                )
                for k in points:
                    row = dict(
                        stage=a.stage,
                        cohort=cohort,
                        year=year,
                        config=config,
                        point_id=k,
                        input_years=";".join(map(str, range(year - window, year))),
                        selected=k in selected,
                        oracle=k in oracle,
                        predicted_midrank_exact=exact(pred_rank[k]),
                        actual_midrank_exact=exact(actual_rank[k]),
                    )
                    for field, x in [
                        ("prediction", forecast[k]),
                        ("actual", actual[k]),
                        ("absolute_error", abs(forecast[k] - actual[k])),
                    ]:
                        pack(row, field, x)
                    predictions.append(row)
    metrics = []
    for cohort in ["west"] if a.stage == "development" else ["west", "east"]:
        for config in CONFIGS:
            rows = [
                r for r in outcomes if r["cohort"] == cohort and r["config"] == config
            ]
            rhos = [float(r["spearman"]) for r in rows if r["spearman"] != ""]
            metric = dict(
                stage=a.stage,
                cohort=cohort,
                config=config,
                years=len(rows),
                points=rows[0]["points"],
                mean_spearman="" if not rhos else f"{math.fsum(rhos)/len(rhos):.9f}",
                undefined_spearman_years=len(rows) - len(rhos),
                boundary_tie_years=sum(r["boundary_tie"] for r in rows),
                oracle_boundary_tie_years=sum(r["oracle_boundary_tie"] for r in rows),
            )
            for field, col, divisor in [
                ("mean_regret", "regret_exact", 1),
                ("mean_mae", "mae_exact", 1),
                ("mean_overlap", "overlap_count", 2),
            ]:
                pack(
                    metric,
                    field,
                    sum((Q(r[col]) for r in rows), Q()) / len(rows) / divisor,
                )
            metrics.append(metric)
    for name, rows in [
        ("predictions", predictions),
        ("annual_scores", outcomes),
        ("metrics", metrics),
    ]:
        write(a.output_dir / f"{a.stage}_{name}.csv", rows)
    if a.stage == "development":
        ordered = sorted(
            metrics,
            key=lambda r: (
                Q(r["mean_regret_exact"]),
                Q(r["mean_mae_exact"]),
                CONFIGS.index(r["config"]),
            ),
        )
        selection = dict(
            selected=ordered[0]["config"],
            criterion="Mean annual western 2011–2016 shortlist regret,then all-point MAE,then fixed candidate order",
            candidate_order=CONFIGS,
            all_candidates=[
                dict(
                    config=r["config"],
                    regret_exact=r["mean_regret_exact"],
                    mae_exact=r["mean_mae_exact"],
                )
                for r in ordered
            ],
            held_tuned=False,
        )
        (a.output_dir / "selection.json").write_bytes(
            (json.dumps(selection, indent=2) + "\n").encode()
        )
    print(
        json.dumps(
            dict(
                stage=a.stage,
                prediction_rows=len(predictions),
                annual_rows=len(outcomes),
                metric_rows=len(metrics),
                selected=(
                    selection["selected"]
                    if a.stage == "development"
                    else json.loads(
                        (ROOT / "results/selection.json").read_text(encoding="utf-8")
                    )["selected"]
                ),
            )
        )
    )


if __name__ == "__main__":
    main()
