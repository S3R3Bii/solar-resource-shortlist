"""Original spatial/resource-error/missing-day figures for the fixed solar cohort."""

import csv, hashlib, json
from fractions import Fraction as Q
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch

ROOT = Path(__file__).resolve().parents[1]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "svg.fonttype": "none",
        "svg.hashsalt": "solar29-v1",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def read(n):
    with (ROOT / "results" / n).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main():
    geometry = []
    hashes = {}
    annual = read("annual_inputs.csv")
    points = json.loads((ROOT / "data/planned_points.json").read_text(encoding="utf-8"))
    metrics = read("held_metrics.csv")
    stress = read("stress_metrics.csv")
    colors = ["#296f88", "#c38533"]
    palette = ["#e5eeee", "#c4dada", "#91bbbb", "#559396", "#246b73"]
    edges = [5, 5.5, 6, 6.5]

    def save(fig, name, artists):
        fig.canvas.draw()
        height = fig.get_figheight() * fig.dpi
        for gid, value, patch in artists:
            positions = patch.get_transform().transform(patch.get_path().vertices[:4])
            geometry.append(
                dict(
                    figure=name,
                    gid=gid,
                    value=float(value),
                    facecolor=matplotlib.colors.to_hex(patch.get_facecolor()),
                    points=[
                        [float(x * 72 / fig.dpi), float((height - y) * 72 / fig.dpi)]
                        for x, y in positions
                    ],
                )
            )
        for ext in ["pdf", "svg", "png"]:
            p = ROOT / "figures" / (name + "." + ext)
            fig.savefig(
                p,
                dpi=160,
                metadata=(
                    {"Creator": "Solar resource shortlist,Study29"}
                    if ext == "pdf"
                    else None
                ),
            )
            if ext == "svg":
                p.write_bytes(
                    (
                        "\n".join(
                            x.rstrip()
                            for x in p.read_text(encoding="utf-8").splitlines()
                        )
                        + "\n"
                    ).encode()
                )
            hashes[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    fig.subplots_adjust(left=0.1, right=0.98, top=0.78, bottom=0.26)
    artists = []
    for point in points:
        rows = [
            r
            for r in annual
            if r["point_id"] == point["id"] and 2001 <= int(r["year"]) <= 2010
        ]
        value = sum(
            (Q(r["mean_available_daily_kwh_m2_exact"]) for r in rows), Q()
        ) / len(rows)
        color = palette[sum(float(value) >= e for e in edges)]
        patch = Rectangle(
            (point["longitude"] - 0.5, point["latitude"] - 0.5),
            1,
            1,
            facecolor=color,
            edgecolor="#667777",
            linewidth=0.5,
        )
        gid = "map-" + point["id"]
        patch.set_gid(gid)
        ax.add_patch(patch)
        artists.append((gid, value, patch))
        ax.text(
            point["longitude"],
            point["latitude"],
            point["id"] + "\n" + f"{float(value):.2f}",
            ha="center",
            va="center",
            fontsize=8,
            color="#101818" if float(value) < 6.5 else "white",
        )
    ax.set_xlim(-116, -104.5)
    ax.set_ylim(31.5, 37.5)
    ax.set_xticks([-114.5, -112.5, -108.5, -106.5])
    ax.set_xlabel("Requested longitude (WGS84 degrees)")
    ax.set_ylabel("Requested latitude (degrees)")
    ax.set_aspect("equal")
    fig.suptitle("Twelve grid locations; six per cohort", x=0.1, ha="left", fontsize=12)
    ax.set_title(
        "2001–2010 mean daily irradiation; nominal 1 degree cells",
        loc="left",
        fontsize=9,
    )
    handles = [
        Patch(facecolor=c, label=t)
        for c, t in zip(palette, ["<5", "5–<5.5", "5.5–<6", "6–<6.5", "≥6.5"])
    ]
    fig.legend(
        handles=handles,
        title="kWh/m²/day (equal-year mean)",
        ncol=5,
        loc="lower center",
        frameon=False,
        fontsize=8,
        title_fontsize=8,
        bbox_to_anchor=(0.54, 0.01),
    )
    save(fig, "grid_resource", artists)
    configs = ["persistence", "mean3", "mean5", "mean10", "median10", "q20_10"]
    labels = [
        "Last\nyear",
        "Mean\n3y",
        "Mean\n5y",
        "Mean\n10y*",
        "Median\n10y",
        "Q20\n10y",
    ]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.8))
    fig.subplots_adjust(left=0.11, right=0.99, top=0.77, bottom=0.27, wspace=0.32)
    artists = []
    for panel, field in enumerate(["mean_regret", "mean_mae"]):
        ax = axes[panel]
        for j, cohort in enumerate(["west", "east"]):
            values = [
                float(
                    Q(
                        next(
                            r
                            for r in metrics
                            if r["cohort"] == cohort and r["config"] == c
                        )[field + "_exact"]
                    )
                )
                for c in configs
            ]
            bars = ax.bar(
                [i + (j - 0.5) * 0.34 for i in range(6)],
                values,
                width=0.32,
                color=colors[j],
                hatch="" if j == 0 else "//",
                label=cohort.title() + ": 6 points",
            )
            for i, (v, patch) in enumerate(zip(values, bars)):
                gid = f"forecast-{panel}-{j}-{i}"
                patch.set_gid(gid)
                artists.append((gid, v, patch))
        ax.set_xticks(range(6), labels, fontsize=7)
        ax.set_ylim(0, 0.03 if panel == 0 else 0.14)
        ax.set_ylabel("kWh/m²/day")
        ax.set_title(
            ["Mean shortlist regret", "All-point mean absolute error"][panel],
            loc="left",
            fontsize=10,
        )
    fig.suptitle(
        "Shortlist agreement does not remove resource error",
        x=0.11,
        ha="left",
        fontsize=12,
    )
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        ncol=2,
        loc="lower center",
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.54, 0.01),
    )
    save(fig, "held_resource_errors", artists)
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.8))
    fig.subplots_adjust(left=0.11, right=0.98, top=0.77, bottom=0.25, wspace=0.35)
    artists = []
    for panel in range(2):
        ax = axes[panel]
        for j, cohort in enumerate(["west", "east"]):
            selected = [
                next(
                    r
                    for r in stress
                    if r["cohort"] == cohort and r["duration"] == str(d)
                )
                for d in [1, 7, 30]
            ]
            values = [
                (
                    float(Q(r["mean_absolute_bias_exact"]))
                    if panel == 0
                    else 100 * int(r["shortlist_changes"]) / int(r["shortlist_cases"])
                )
                for r in selected
            ]
            bars = ax.bar(
                [i + (j - 0.5) * 0.34 for i in range(3)],
                values,
                width=0.32,
                color=colors[j],
                hatch="" if j == 0 else "//",
                label=cohort.title(),
            )
            ax.bar_label(
                bars,
                labels=[
                    (
                        f"{v:.3f}"
                        if panel == 0
                        else r["shortlist_changes"] + "/" + r["shortlist_cases"]
                    )
                    for v, r in zip(values, selected)
                ],
                padding=3,
                fontsize=7,
            )
            for i, (v, patch) in enumerate(zip(values, bars)):
                gid = f"missing-{panel}-{j}-{i}"
                patch.set_gid(gid)
                artists.append((gid, v, patch))
        ax.set_xticks(range(3), ["1 day", "7 days", "30 days"])
        ax.set_xlabel("Removed block at each month start")
        ax.set_ylim(0, 0.18 if panel == 0 else 10)
        ax.set_title(
            [
                "Mean absolute resource bias",
                "Shortlists changed (labels: count / cases)",
            ][panel],
            loc="left",
            fontsize=9,
        )
        ax.set_ylabel("kWh/m²/day" if panel == 0 else "Fixed stress cases (%)")
    fig.suptitle(
        "A seasonal gap can move a close resource shortlist",
        x=0.11,
        ha="left",
        fontsize=12,
    )
    fig.legend(
        *axes[0].get_legend_handles_labels(),
        ncol=2,
        loc="lower center",
        frameon=False,
        fontsize=8,
        bbox_to_anchor=(0.54, 0.01),
    )
    save(fig, "missing_day_sensitivity", artists)
    (ROOT / "figures/artist_geometry.json").write_bytes(
        (json.dumps(geometry, indent=2) + "\n").encode()
    )
    (ROOT / "figures/manifest.json").write_bytes(
        (json.dumps(hashes, indent=2, sort_keys=True) + "\n").encode()
    )
    print("FIGURES_CREATED", len(geometry), "SOURCE_VALUES")


if __name__ == "__main__":
    main()
