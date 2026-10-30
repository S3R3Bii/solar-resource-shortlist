"""Independently reconstruct paper displays from native flux and per-point forecasts."""

import csv, gzip, hashlib, json, unicodedata, re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction as F
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def rows(name):
    with (ROOT / "results" / name).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    read = lambda n: json.loads((ROOT / n).read_text(encoding="utf-8"))
    native = defaultdict(dict)
    cohorts = {}
    with gzip.open(
        ROOT / "data/records.csv.gz", "rt", encoding="utf-8", newline=""
    ) as f:
        raw = list(csv.DictReader(f))
    for r in raw:
        assert r["valid"] == "True"
        key = (r["point_id"], int(r["date"][:4]))
        native[key][date.fromisoformat(r["date"])] = (
            F(Decimal(r["native_w_m2"])) * 24 / 1000
        )
        cohorts[r["point_id"]] = r["cohort"]
    annual = {k: sum(v.values(), F()) / len(v) for k, v in native.items()}
    prediction_groups = defaultdict(dict)
    for stage in ["development", "held"]:
        for r in rows(stage + "_predictions.csv"):
            prediction_groups[stage, r["cohort"], int(r["year"]), r["config"]][
                r["point_id"]
            ] = r
    metrics = defaultdict(list)
    for (stage, cohort, year, config), records in prediction_groups.items():
        actual = {i: annual[i, year] for i in records}
        oracle = sorted(actual, key=lambda i: (-actual[i], i))[:2]
        selected = [i for i, r in records.items() if r["selected"] == "True"]
        assert len(selected) == 2
        regret = (
            sum((actual[i] for i in oracle), F())
            - sum((actual[i] for i in selected), F())
        ) / 2
        mae = sum(
            (abs(F(r["prediction_exact"]) - actual[i]) for i, r in records.items()), F()
        ) / len(records)
        metrics[stage, cohort, config].append(
            dict(
                mean_regret=regret,
                mean_mae=mae,
                mean_overlap=F(len(set(oracle) & set(selected)), 2),
            )
        )
    stress = defaultdict(list)
    ranking = defaultdict(list)
    stress_year = defaultdict(list)
    ranking_year = defaultdict(list)
    for cohort in ["west", "east"]:
        ids = sorted(i for i, c in cohorts.items() if c == cohort)
        for year in range(2017, 2024):
            for duration in [1, 7, 30]:
                for month in range(1, 13):
                    intact = {i: annual[i, year] for i in ids}
                    partial = {}
                    start = date(year, month, 1)
                    removed = {
                        start + timedelta(days=k)
                        for k in range(duration)
                        if (start + timedelta(days=k)).year == year
                    }
                    for ident in ids:
                        source = native[ident, year]
                        values = [x for d, x in source.items() if d not in removed]
                        partial[ident] = sum(values, F()) / len(values)
                        bias = abs(partial[ident] - intact[ident])
                        stress[cohort, duration].append(bias)
                        if duration == 30:
                            stress_year[cohort, year].append(bias)
                    first = sorted(ids, key=lambda i: (-intact[i], i))[:2]
                    second = sorted(ids, key=lambda i: (-partial[i], i))[:2]
                    change = set(first) != set(second)
                    regret = (
                        sum((intact[i] for i in first), F())
                        - sum((intact[i] for i in second), F())
                    ) / 2
                    ranking[cohort, duration].append((change, regret))
                    if duration == 30:
                        ranking_year[cohort, year].append(change)
    ledger = read("paper/TABLE_VALUES.json")
    reader = PdfReader(ROOT / "paper/manuscript.pdf")
    assert len(reader.pages) == 6 and len(ledger) == 118
    texts = [
        " ".join(
            re.sub(
                r"-\s*\n\s*", "-", unicodedata.normalize("NFKC", p.extract_text())
            ).split()
        )
        for p in reader.pages
    ]
    checks = 0
    for r in ledger:
        q = r["query"]
        if q["kind"] == "metric":
            items = metrics[q["stage"], q["cohort"], q["config"]]
            v = sum((x[q["field"]] for x in items), F()) / len(items)
            v *= 100 if q["field"] == "mean_overlap" else 1
        elif q["kind"] == "stress":
            bs = stress[q["cohort"], q["duration"]]
            rs = ranking[q["cohort"], q["duration"]]
            v = {
                "shortlist_changes": F(sum(x[0] for x in rs)),
                "shortlist_cases": F(len(rs)),
                "mean_absolute_bias": sum(bs, F()) / len(bs),
                "max_absolute_bias": max(bs),
                "mean_intact_regret": sum((x[1] for x in rs), F()) / len(rs),
            }[q["field"]]
        else:
            assert q["kind"] == "stress_year"
            key = (q["cohort"], q["year"])
            v = (
                F(sum(ranking_year[key]))
                if q["field"] == "changes"
                else sum(stress_year[key], F()) / len(stress_year[key])
            )
        with localcontext() as ctx:
            ctx.prec = 80
            display = format(Decimal(v.numerator) / Decimal(v.denominator), r["fmt"])
        assert r["text"] == display and display in texts[r["page"]], r
        checks += 2
    assert (
        len(raw) == 100800
        and len(native) == 276
        and len(cohorts) == 12
        and all(len([k for k in native if k[0] == i]) == 23 for i in cohorts)
    )
    checks += 4
    gate = read("results/source_gate.json")
    assert (
        gate["complete_point_years"] == 276
        and gate["unavailable_daily_rows"] == 0
        and gate["alias_points"] == 0
    )
    checks += 3
    assert read("results/selection.json")["selected"] == "mean10"
    checks += 1
    for config in ["persistence", "mean3", "mean5", "mean10", "median10", "q20_10"]:
        assert all(x["mean_regret"] == 0 for x in metrics["held", "west", config])
        checks += 1
    mean = (
        lambda cohort, config, field: sum(
            (x[field] for x in metrics["held", cohort, config]), F()
        )
        / 7
    )
    assert mean("west", "median10", "mean_mae") < mean("west", "mean10", "mean_mae")
    assert mean("east", "q20_10", "mean_mae") > mean("east", "persistence", "mean_mae")
    assert (
        mean("east", "mean5", "mean_regret")
        == mean("east", "mean10", "mean_regret")
        == mean("east", "median10", "mean_regret")
        == mean("east", "q20_10", "mean_regret")
    )
    checks += 3
    assert sum(x[0] for x in ranking["east", 1]) == 1
    checks += 1
    expected_receipts = {
        "data/source_verification.json": 806558,
        "results/independent_inputs.json": 19451,
        "results/independent_development.json": 3394,
        "results/independent_held.json": 7884,
        "results/independent_stress.json": 41886,
    }
    for name, n in expected_receipts.items():
        assert read(name)["checks"] == n
        checks += 1
    replay = read("results/reproduction.json")
    assert (
        replay["status"] == "PASS"
        and replay["exact_csv_fields_including_headers"] == 96847
        and replay["json_documents"] == 6
        and replay["tests"] == 35
        and replay["frozen_dependencies"] == 28
        and replay["stress_dependency_hashes"] == 4
        and replay["original_files_unchanged"]
        and not replay["network_during_replay"]
    )
    checks += 8
    for phrase in [
        "no demonstrated unique decision advantage",
        "not estimated frequencies",
        "different source",
        "no spatial independence",
        "not photovoltaic modeling or an untouched",
        "No eastern ranking outcome",
        "Q20 nevertheless has a larger",
        "not independent observations",
        "No independent ground-station",
        "not peer reviewed",
        "including Azure optimization",
        "no new source requests",
    ]:
        assert phrase.casefold() in " ".join(texts).casefold(), phrase
        checks += 1
    scope = read("paper/PUBLICATION_SCOPE.json")
    assert (
        scope["scope"] == "independent-program-study"
        and scope["formal_submission_target"] is False
        and len(scope["public_files"]) == 5
    )
    for name, digest in scope["public_files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
        checks += 1
    assert all(len(t) > 1600 for t in texts) and not reader.get_fields()
    pdfroot = reader.trailer["/Root"]
    assert "/AA" not in pdfroot and "/JavaScript" not in str(pdfroot.get("/Names", ""))
    checks += 3
    result = dict(
        status="PASS",
        checks=checks,
        displayed_values=len(ledger),
        pages=6,
        scope="Independent native-flux stress reconstruction,per-point forecast arithmetic,display presence,claim qualifiers and scoped hashes;visual review is separate",
    )
    (ROOT / "results/paper_verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
