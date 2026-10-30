"""Independent Pandas CSV and SQLite JSON decoding plus decimal unit reconstruction."""

import argparse, csv, gzip, hashlib, io, json, sqlite3
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction as Q
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD = "ALLSKY_SFC_SW_DWN"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--private-dir", type=Path)
    a = p.parse_args()
    m = json.loads((ROOT / "data/source_manifest.json").read_text(encoding="utf-8"))
    assert (
        hashlib.sha256((ROOT / "data/records.csv.gz").read_bytes()).hexdigest()
        == m["projection_sha256"]
    )
    checks = 1
    with gzip.open(
        ROOT / "data/records.csv.gz", "rt", encoding="utf-8", newline=""
    ) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == m["source_rows"] == 100800
    checks += 1
    if a.private_dir:
        import pandas as pd

        conn = sqlite3.connect(":memory:")
        receipts = {(r["point"], r["format"]): r for r in m["requests"]}
        planned = json.loads(
            (ROOT / "data/planned_points.json").read_text(encoding="utf-8")
        )
        for point in planned:
            ident = point["id"]
            texts = {}
            for fmt in ["JSON", "CSV"]:
                r = receipts[ident, fmt]
                body = (a.private_dir / r["file"]).read_bytes()
                assert hashlib.sha256(body).hexdigest() == r["sha256"]
                texts[fmt] = body.decode("utf-8-sig")
                checks += 1
            j = texts["JSON"]
            unit, standard, start, end, source, lon, lat, version = conn.execute(
                "select json_extract(?, '$.parameters.ALLSKY_SFC_SW_DWN.units'),json_extract(?, '$.header.time_standard'),json_extract(?, '$.header.start'),json_extract(?, '$.header.end'),json_extract(?, '$.header.sources[0]'),json_extract(?, '$.geometry.coordinates[0]'),json_extract(?, '$.geometry.coordinates[1]'),json_extract(?, '$.header.api.version')",
                [j] * 8,
            ).fetchone()
            assert (unit, standard, start, end, source, lon, lat, version) == (
                "W m-2",
                "UTC",
                "20010101",
                "20231231",
                "SYN1DEG",
                point["longitude"],
                point["latitude"],
                "v2.10.1",
            )
            checks += 8
            native = dict(
                conn.execute(
                    "select key,atom from json_each(?, '$.properties.parameter.ALLSKY_SFC_SW_DWN')",
                    [j],
                ).fetchall()
            )
            lines = texts["CSV"].splitlines()
            line = lines.index("-END HEADER-") + 1
            frame = pd.read_csv(
                io.StringIO(texts["CSV"]),
                skiprows=line,
                dtype=str,
                keep_default_na=False,
            )
            assert list(frame.columns) == ["YEAR", "MO", "DY", FIELD]
            cells = {}
            for r in frame.to_dict("records"):
                key = str(date(int(r["YEAR"]), int(r["MO"]), int(r["DY"]))).replace(
                    "-", ""
                )
                assert key not in cells
                cells[key] = Decimal(r[FIELD])
            selected = [r for r in rows if r["point_id"] == ident]
            assert len(selected) == len(native) == len(cells) == 8400
            checks += 2
            dates = set()
            for r in selected:
                key = r["date"].replace("-", "")
                assert key not in dates
                dates.add(key)
                x = Decimal(str(native[key]))
                assert x == cells[key] == Decimal(r["native_w_m2"])
                valid = x.is_finite() and x >= 0
                assert r["valid"] == str(valid)
                assert r["reason"] == (
                    ""
                    if valid
                    else (
                        "source_fill"
                        if x == Decimal(-999)
                        else "invalid_nonnegative_finite_flux"
                    )
                )
                assert r["cohort"] == point["cohort"]
                assert (
                    r["source_json"] == receipts[ident, "JSON"]["file"]
                    and r["source_csv"] == receipts[ident, "CSV"]["file"]
                )
                checks += 7
                expected = Q(x) * 24 / 1000 if valid else None
                assert (
                    (Q(r["irradiation_kwh_m2_day_exact"]) == expected)
                    if valid
                    else r["irradiation_kwh_m2_day_exact"] == ""
                )
                checks += 1
            day = date(2001, 1, 1)
            expected_dates = set()
            while day <= date(2023, 12, 31):
                expected_dates.add(day.strftime("%Y%m%d"))
                day += timedelta(days=1)
            assert dates == set(native) == set(cells) == expected_dates
            checks += 1
    result = dict(
        status="PASS",
        mode=(
            "PRIVATE_ORIGINALS_PANDAS_SQLITE"
            if a.private_dir
            else "PUBLIC_PROJECTION_HASH_AND_COUNT_ONLY"
        ),
        checks=checks,
        source_rows=len(rows),
        scope="All selected original values,calendar,metadata and exact conversion when originals supplied;not station accuracy or site feasibility",
    )
    if a.private_dir:
        (ROOT / "data/source_verification.json").write_bytes(
            (json.dumps(result, indent=2) + "\n").encode()
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
