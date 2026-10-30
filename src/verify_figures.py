"""Recompute plotted values from individual exports and inspect actual SVG geometry/colors."""

import csv, hashlib, json, re, xml.etree.ElementTree as ET
from fractions import Fraction as Q
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(n):
    with (ROOT / "results" / n).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    expected = {}
    colors = {}
    annual = read("annual_inputs.csv")
    scores = read("held_annual_scores.csv")
    predictions = read("held_predictions.csv")
    points = read("stress_point_cases.csv")
    shortlists = read("stress_shortlists.csv")
    palette = ["#e5eeee", "#c4dada", "#91bbbb", "#559396", "#246b73"]
    for ident in sorted({r["point_id"] for r in annual}):
        sample = [
            Q(r["mean_available_daily_kwh_m2_exact"])
            for r in annual
            if r["point_id"] == ident and int(r["year"]) <= 2010
        ]
        v = sum(sample, Q()) / len(sample)
        gid = "map-" + ident
        expected[gid] = float(v)
        colors[gid] = palette[
            sum(v >= edge for edge in map(Q, ["5", "5.5", "6", "6.5"]))
        ]
    for j, cohort in enumerate(["west", "east"]):
        for i, config in enumerate(
            ["persistence", "mean3", "mean5", "mean10", "median10", "q20_10"]
        ):
            rows = [
                r for r in scores if r["cohort"] == cohort and r["config"] == config
            ]
            expected[f"forecast-0-{j}-{i}"] = float(
                sum((Q(r["regret_exact"]) for r in rows), Q()) / len(rows)
            )
            rows = [
                r
                for r in predictions
                if r["cohort"] == cohort and r["config"] == config
            ]
            expected[f"forecast-1-{j}-{i}"] = float(
                sum((Q(r["absolute_error_exact"]) for r in rows), Q()) / len(rows)
            )
        for i, duration in enumerate([1, 7, 30]):
            rows = [
                r
                for r in points
                if r["cohort"] == cohort and r["duration_requested"] == str(duration)
            ]
            expected[f"missing-0-{j}-{i}"] = float(
                sum(
                    (
                        abs(Q(r["remaining_mean_exact"]) - Q(r["intact_mean_exact"]))
                        for r in rows
                    ),
                    Q(),
                )
                / len(rows)
            )
            rows = [
                r
                for r in shortlists
                if r["cohort"] == cohort and r["duration_requested"] == str(duration)
            ]
            expected[f"missing-1-{j}-{i}"] = (
                100
                * sum(
                    set(r["intact_shortlist"].split(";"))
                    != set(r["remaining_shortlist"].split(";"))
                    for r in rows
                )
                / len(rows)
            )
    read_json = lambda n: json.loads((ROOT / n).read_text(encoding="utf-8"))
    records = read_json("figures/artist_geometry.json")
    assert len(records) == len(expected) == 48
    checks = 0
    trees = {}
    for r in records:
        assert r["value"] == expected[r["gid"]]
        checks += 1
        name = r["figure"]
        if name not in trees:
            trees[name] = ET.parse(ROOT / "figures" / (name + ".svg"))
        group = trees[name].find('.//*[@id="' + r["gid"] + '"]')
        assert group is not None
        path = group.find("{http://www.w3.org/2000/svg}path")
        values = [
            float(v)
            for v in re.findall(
                r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", path.attrib["d"]
            )
        ]
        assert len(values) >= 8
        for a, b in zip(values[:8], [v for point in r["points"] for v in point]):
            assert abs(a - b) < 1e-5
            checks += 1
        if r["gid"] in colors:
            assert (
                "fill: " + colors[r["gid"]] in path.attrib["style"]
                and r["facecolor"] == colors[r["gid"]]
            )
            checks += 1
    for name, digest in read_json("figures/manifest.json").items():
        assert (
            hashlib.sha256((ROOT / "figures" / name).read_bytes()).hexdigest() == digest
        )
        checks += 1
    result = dict(
        status="PASS",
        checks=checks,
        source_values=48,
        svg_coordinates=384,
        map_color_values=12,
        hashes=9,
        scope="Individual-export arithmetic,actual SVG rectangles,map color bins and artifact hashes;nominal source cells are not physical parcels",
    )
    (ROOT / "results/figure_verification.json").write_bytes(
        (json.dumps(result, indent=2) + "\n").encode()
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
