
"""Post-test annotated EDA copies; original results/eda/full remains unchanged.

Run only after the first held-out test evaluation:
    python tools/eda_post_test.py --db snapshots/assessed_snapshot.db
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis import evaluate, modelling as m, provenance as prov
from monitoring.prepare import FEATURES

LABEL = "post-test annotated copies; original charts in results/eda/full unchanged"
SOURCE = (
    "Weather data by Open-Meteo.com; air quality from CAMS Global via "
    "the Open-Meteo Air Quality API; derived values are labelled derived."
)
OUT_REL = Path("results/post_test/eda")
ORIGINAL_REL = Path("results/eda/full")

CHARTS = (
    "01_pm25_time_series.png",
    "02_pm25_by_city.png",
    "03_diurnal_profile.png",
    "04_pm25_vs_wind.png",
    "05_pm25_vs_humidity.png",
    "06_coverage_by_city_day.png",
    "07_weather_pollutant_missingness.png",
)

CAPTIONS = (
    "Native three-hourly modelled PM2.5 observations over the assessed week by city.",
    "Distribution of native three-hourly modelled PM2.5 values differs across the eight cities.",
    "Mean modelled PM2.5 is summarised by local hour across all cities.",
    "Wind-speed values are plotted against modelled PM2.5 for native rows with both fields present.",
    "Relative-humidity values are plotted against modelled PM2.5 for native rows with both fields present.",
    "The heatmap counts collected rows for each city and local day.",
    "Null counts for weather and pollutant variables across all assessed rows; zero means complete coverage.",
)

# Okabe-Ito colour-blind-friendly palette.
PALETTE = (
    "#E69F00", "#56B4E9", "#009E73", "#F0E442",
    "#0072B2", "#D55E00", "#CC79A7", "#000000",
)
CITY_COLORS = dict(zip(m.CITIES, PALETTE))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()



EXPECTED_ORIGINAL_HASHES = {
    "01_pm25_time_series.png":
        "8a2f450c7027b3741ccee2107048d52fe00e7aae120623b211d07a316e01c99d",
    "02_pm25_by_city.png":
        "f277545cd925afe61413700781347d877b343890c24a77a9d316311487aa1d52",
    "03_diurnal_profile.png":
        "ad2ccd51596feefc478f37b4a5d5fea9b9d82c101df7818ac0ff3a0c899667ad",
    "04_pm25_vs_wind.png":
        "67b348af080d0490f04ea4c566dda1a84c6718dcd018fd71782e39660aacd7a0",
    "05_pm25_vs_humidity.png":
        "6d2660418cc873abbb63515d640646ac63113127d91960a3cb13899cadd0e797",
    "06_coverage_by_city_day.png":
        "adb715a9ec11980cf97c0b0f192755287f0985d266c281f0b8881b40f9f2555c",
    "eda_manifest.json":
        "6df06e0637311ac3dd3e8931749f72cef719e4538573c318808d5f42fa116918",
}


def original_hashes(repo):
    folder = repo / ORIGINAL_REL
    result = {}
    for name, expected in EXPECTED_ORIGINAL_HASHES.items():
        path = folder / name
        if not path.is_file():
            raise RuntimeError(f"Original EDA file is missing: {path}")
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(
                f"Original EDA hash mismatch for {name}: "
                f"expected {expected}, got {actual}"
            )
        result[name] = actual
    return result


def annotate(fig, n, caption):
    fig.subplots_adjust(bottom=0.25)
    fig.text(
        0.01, 0.145, f"n = {n:,} | {caption}",
        ha="left", va="bottom", fontsize=8, wrap=True,
    )
    fig.text(
        0.01, 0.045, SOURCE,
        ha="left", va="bottom", fontsize=6.8, wrap=True,
    )
    fig.text(
        0.99, 0.005, LABEL,
        ha="right", va="bottom", fontsize=6, wrap=True,
    )


def save(fig, path, n, caption):
    annotate(fig, n, caption)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def native_rows(rows):
    return [
        r for r in rows
        if r["native"] and r["pm2_5"] is not None
    ]


def make_charts(rows, out):
    nat = native_rows(rows)
    if not nat:
        raise RuntimeError("No native rows with non-null PM2.5")

    cities = [
        c for c in m.CITIES
        if any(r["city"] == c for r in nat)
    ]
    counts = {}

    # 1. Native PM2.5 time series by city.
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for city in cities:
        rr = sorted(
            (r for r in nat if r["city"] == city),
            key=lambda r: r["valid_dt"],
        )
        ax.plot(
            [r["valid_dt"] for r in rr],
            [r["pm2_5"] for r in rr],
            lw=1, marker="o", markersize=2,
            color=CITY_COLORS[city], label=city,
        )
    ax.set(
        title="Modelled PM2.5 by city, native three-hourly (UTC)",
        ylabel="PM2.5 (ug/m3, modelled)",
    )
    ax.legend(ncol=4, fontsize=7)
    save(fig, out / CHARTS[0], len(nat), CAPTIONS[0])
    counts[CHARTS[0]] = len(nat)

    # 2. Distribution by city.
    fig, ax = plt.subplots(figsize=(8, 5.5))
    values = [
        [r["pm2_5"] for r in nat if r["city"] == city]
        for city in cities
    ]
    bp = ax.boxplot(values, tick_labels=cities, patch_artist=True)
    for patch, city in zip(bp["boxes"], cities):
        patch.set_facecolor(CITY_COLORS[city])
    ax.set(
        title="Distribution of modelled PM2.5 by city",
        ylabel="PM2.5 (ug/m3, modelled)",
    )
    ax.tick_params(axis="x", labelrotation=30)
    save(fig, out / CHARTS[1], len(nat), CAPTIONS[1])
    counts[CHARTS[1]] = len(nat)

    # 3. Mean PM2.5 by local hour.
    hours = sorted({int(r["valid_local"][11:13]) for r in nat})
    means = [
        np.mean([
            r["pm2_5"] for r in nat
            if int(r["valid_local"][11:13]) == hour
        ])
        for hour in hours
    ]
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.plot(hours, means, marker="o", color="#0072B2")
    ax.set(
        title="Mean modelled PM2.5 by local hour (all cities)",
        xlabel="Local hour (Asia/Tashkent)",
        ylabel="PM2.5 (ug/m3, modelled)",
    )
    save(fig, out / CHARTS[2], len(nat), CAPTIONS[2])
    counts[CHARTS[2]] = len(nat)

    # 4 and 5. Weather relationships; n is the plotted complete-case count.
    for fname, key, xlabel, title, caption in (
        (
            CHARTS[3], "wind_speed_ms", "Wind speed (m/s)",
            "PM2.5 vs wind speed, native rows", CAPTIONS[3],
        ),
        (
            CHARTS[4], "relative_humidity_2m", "Relative humidity (%)",
            "PM2.5 vs relative humidity, native rows", CAPTIONS[4],
        ),
    ):
        fig, ax = plt.subplots(figsize=(7, 5.5))
        plotted = [
            r for r in nat
            if r[key] is not None
        ]
        for city in cities:
            pts = [
                r for r in plotted
                if r["city"] == city
            ]
            if pts:
                ax.scatter(
                    [r[key] for r in pts],
                    [r["pm2_5"] for r in pts],
                    s=10, alpha=0.7,
                    color=CITY_COLORS[city], label=city,
                )
        ax.set(
            title=title,
            xlabel=xlabel,
            ylabel="PM2.5 (ug/m3, modelled)",
        )
        ax.legend(ncol=2, fontsize=6)
        save(fig, out / fname, len(plotted), caption)
        counts[fname] = len(plotted)

    # 6. Collected rows per city and local day.
    days = sorted({r["valid_local"][:10] for r in rows})
    grid = np.array([
        [
            sum(
                1 for r in rows
                if r["city"] == city and r["valid_local"][:10] == day
            )
            for day in days
        ]
        for city in cities
    ])
    fig, ax = plt.subplots(figsize=(8, 5.5))
    im = ax.imshow(grid, aspect="auto", cmap="viridis")
    ax.set_xticks(range(len(days)), [day[5:] for day in days])
    ax.set_yticks(range(len(cities)), cities)
    ax.set(title="Collected rows per city and local day")
    fig.colorbar(im, ax=ax, label="Collected rows")
    save(fig, out / CHARTS[5], len(rows), CAPTIONS[5])
    counts[CHARTS[5]] = len(rows)

    # 7. Null counts across all ten weather and pollutant variables.
    missing = {
        feature: sum(1 for r in rows if r[feature] is None)
        for feature in FEATURES
    }
    fig, ax = plt.subplots(figsize=(9, 5.5))
    labels = [
        f"{name}\n(weather)" if i < 6 else f"{name}\n(pollutant)"
        for i, name in enumerate(FEATURES)
    ]
    bars = ax.bar(
        range(len(FEATURES)),
        [missing[name] for name in FEATURES],
        color=[
            "#56B4E9" if i < 6 else "#D55E00"
            for i in range(len(FEATURES))
        ],
    )
    ax.set_xticks(range(len(FEATURES)), labels, rotation=30, ha="right")
    ax.set_ylabel("Null count")
    ax.set_title("Weather and pollutant missingness")
    ax.set_ylim(bottom=0)
    for bar, name in zip(bars, FEATURES):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(missing[name]),
            ha="center", va="bottom", fontsize=7,
        )
    save(fig, out / CHARTS[6], len(rows), CAPTIONS[6])
    counts[CHARTS[6]] = len(rows)

    return counts, missing


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="snapshots/assessed_snapshot.db")
    parser.add_argument("--repo", default=str(prov.ROOT))
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = repo / db_path

        # Capture original hashes before any post-test output is written.
    before = original_hashes(repo)

    # Never overwrite an earlier post-test result.
    out = repo / OUT_REL
    targets = [out / name for name in (*CHARTS, "eda_post_test_manifest.json")]
    existing = [p.name for p in targets if p.exists()]
    if existing:
        raise FileExistsError(
            "Refusing to overwrite existing post-test outputs: "
            + ", ".join(existing)
        )

    # This guard must pass before test-period rows are loaded.
    guard = evaluate.check_guard(
        repo, db_path, post_test=True,
    )

    # Only after the guard succeeds may the held-out rows be loaded.
    rows, _dev_rows = evaluate.load_all_rows(db_path)

    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    counts, missing = make_charts(rows, out)

    after = original_hashes(repo)
    if before != after:
        raise RuntimeError(
            "Original EDA files changed during post-test chart generation"
        )

    manifest = {
        "label": LABEL,
        "mode": "post_test",
        "rows_used": len(rows),
        "tag": guard["tag"],
        "tag_commit": guard["tag_commit"],
        "guard_head": guard["head"],
        "original_eda_files_sha256_before_and_after": before,
        "original_eda_unchanged": True,
        "charts": {
            name: {
                "sha256": sha256(out / name),
                "n": counts[name],
                "caption": CAPTIONS[i],
                "source": SOURCE,
            }
            for i, name in enumerate(CHARTS)
        },
        "missing_counts": missing,
        "weather_features": FEATURES[:6],
        "pollutant_features": FEATURES[6:],
    }
    prov.write_text_lf(
        out / "eda_post_test_manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )

    print(f"{len(CHARTS)} post-test charts written to {out}")
    print(f"Rows used: {len(rows)}")
    print(f"Original EDA files unchanged: {before == after}")
    print(f"Manifest: {out / 'eda_post_test_manifest.json'}")


if __name__ == "__main__":
    main()
