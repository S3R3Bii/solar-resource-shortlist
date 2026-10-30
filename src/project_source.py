"""Retain native solar flux,exact unit conversion and full planned daily calendars."""

import argparse, csv, gzip, hashlib, io, json
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELD = "ALLSKY_SFC_SW_DWN"


def convert_daily_mean(value, unit):
    assert unit == "W m-2" and value.is_finite() and value >= 0
    return F(value) * F(3, 125)


def token(x):
    return format(x.normalize(), "f") if x else "0"


def exact(x):
    return f"{x.numerator}/{x.denominator}"


def write_csv(path, rows):
    stream = io.StringIO(newline="")
    w = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as f:
        f.write(stream.getvalue().encode())
    path.write_bytes(buffer.getvalue())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--private-dir", type=Path, required=True)
    a = p.parse_args()
    receipts = json.loads((a.private_dir / "requests.json").read_text(encoding="utf-8"))
    assert len(receipts) == 24 and all(
        r["status"] == 200 and r["error"] is None for r in receipts
    )
    by = {(r["point"], r["format"]): r for r in receipts}
    points = json.loads((ROOT / "data/planned_points.json").read_text(encoding="utf-8"))
    rows = []
    metadata = {}
    checks = 0
    calendar = []
    day = date(2001, 1, 1)
    while day <= date(2023, 12, 31):
        calendar.append(day)
        day += timedelta(days=1)
    for point in points:
        source = {}
        for fmt in ["JSON", "CSV"]:
            receipt = by[point["id"], fmt]
            body = (a.private_dir / receipt["file"]).read_bytes()
            assert hashlib.sha256(body).hexdigest() == receipt["sha256"]
            source[fmt] = body
            checks += 1
        j = json.loads(source["JSON"], parse_float=Decimal)
        header = j["header"]
        assert (
            header["sources"] == ["SYN1DEG"]
            and header["time_standard"] == "UTC"
            and header["start"] == "20010101"
            and header["end"] == "20231231"
        )
        assert j["parameters"][FIELD]["units"] == "W m-2"
        assert j["messages"] == []
        assert list(map(Decimal, map(str, j["geometry"]["coordinates"][:2]))) == [
            Decimal(str(point["longitude"])),
            Decimal(str(point["latitude"])),
        ]
        checks += 7
        lines = source["CSV"].decode("utf-8-sig").splitlines()
        end = lines.index("-END HEADER-")
        preamble = "\n".join(lines[:end])
        assert FIELD in preamble and "(W m-2)" in preamble and "in UTC" in preamble
        checks += 3
        csv_rows = list(csv.DictReader(lines[end + 1 :]))
        assert list(csv_rows[0]) == ["YEAR", "MO", "DY", FIELD]
        c = {}
        for r in csv_rows:
            d = date(int(r["YEAR"]), int(r["MO"]), int(r["DY"]))
            key = d.strftime("%Y%m%d")
            assert key not in c
            c[key] = Decimal(r[FIELD])
        values = j["properties"]["parameter"][FIELD]
        expected = {d.strftime("%Y%m%d") for d in calendar}
        assert set(values) == set(c) == expected
        checks += 2
        fill = Decimal(str(header["fill_value"]))
        assert fill == Decimal(-999)
        checks += 1
        for d in calendar:
            key = d.strftime("%Y%m%d")
            value = Decimal(str(values[key]))
            assert value == c[key]
            checks += 1
            valid = value.is_finite() and value >= 0
            reason = (
                ""
                if valid
                else (
                    "source_fill"
                    if value == fill
                    else "invalid_nonnegative_finite_flux"
                )
            )
            rows.append(
                dict(
                    point_id=point["id"],
                    cohort=point["cohort"],
                    date=d.isoformat(),
                    native_w_m2=token(value),
                    valid=valid,
                    reason=reason,
                    irradiation_kwh_m2_day_exact=(
                        exact(
                            convert_daily_mean(value, j["parameters"][FIELD]["units"])
                        )
                        if valid
                        else ""
                    ),
                    source_json=by[point["id"], "JSON"]["file"],
                    source_csv=by[point["id"], "CSV"]["file"],
                )
            )
        metadata[point["id"]] = dict(
            api=header["api"],
            sources=header["sources"],
            time_standard=header["time_standard"],
            returned_longitude=str(j["geometry"]["coordinates"][0]),
            returned_latitude=str(j["geometry"]["coordinates"][1]),
            source_unit=j["parameters"][FIELD]["units"],
            fill=str(fill),
            rows=len(values),
        )
    write_csv(ROOT / "data/records.csv.gz", rows)
    manifest = dict(
        source="NASA Langley POWER Daily API;CERES SYN1DEG",
        field=FIELD,
        source_rows=len(rows),
        days_per_point=len(calendar),
        requests=receipts,
        metadata_by_point=metadata,
        projection_sha256=hashlib.sha256(
            (ROOT / "data/records.csv.gz").read_bytes()
        ).hexdigest(),
        unit_conversion=dict(
            native="Daily mean W m-2",
            derived="kWh/m2/day",
            factor_exact="3/125",
            rationale="24hours per UTC day/1000W per kW;UNIT_BINDING.md documents pre-score confirmation",
        ),
        attribution="NASA Langley Research Center POWER project, funded through NASA Earth Science Division;Daily API v2.10.1; accessed 30 October 2026",
        limits="Requested grid points,not independent measured stations or physical parcels;current retrospective source,not original delivery vintages;no plant output/finance/climate-causality claim",
    )
    (ROOT / "data/source_manifest.json").write_bytes(
        (json.dumps(manifest, indent=2) + "\n").encode()
    )
    print(
        json.dumps(
            dict(
                state="PROJECTED_WITH_PRE_SCORE_UNIT_BINDING",
                rows=len(rows),
                source_comparisons=checks,
                points=len(points),
            )
        )
    )


if __name__ == "__main__":
    main()
