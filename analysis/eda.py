"""Exploratory charts (decision 0010 item 21).  Six labelled charts, two modes:

  pre_freeze  only rows received before the final cut-off (6 Nov 22:00 local), through the receipt-time guard;
              may be run before the freeze.
  full        the whole assessed window, including the test period; allowed only after the single test evaluation
              (marker required); every chart is labelled "full window, after test evaluation".

    python -m analysis.eda --db snapshots/assessed_snapshot.db --mode pre_freeze
    python -m analysis.eda --db snapshots/assessed_snapshot.db --mode full
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402

from analysis import data, evaluate, modelling as m, provenance as prov        # noqa: E402
from monitoring.coverage import open_ro        # noqa: E402

MODES = {"pre_freeze": "pre-freeze data only (received before 6 Nov 22:00 local)",
         "full": "full window, after test evaluation"}
CHARTS = ("01_pm25_time_series.png", "02_pm25_by_city.png", "03_diurnal_profile.png", "04_pm25_vs_wind.png",
          "05_pm25_vs_humidity.png", "06_coverage_by_city_day.png")


def _native(rows):
    return [r for r in rows if r["native"] and r["pm2_5"] is not None]


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(path, dpi=120, metadata={"Software": None})
    plt.close(fig)


def make_charts(rows, out_dir, mode):
    """rows: row dicts from analysis.data.  Returns the list of files written."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"EDA - {MODES[mode]}"
    nat = _native(rows)
    if not nat:
        raise ValueError("no native rows with PM2.5")
    cities = [c for c in m.CITIES if any(r["city"] == c for r in nat)]

    fig, ax = plt.subplots(figsize=(10, 4.5))
    for c in cities:
        rr = sorted((r for r in nat if r["city"] == c), key=lambda r: r["valid_dt"])
        ax.plot([r["valid_dt"] for r in rr], [r["pm2_5"] for r in rr], lw=1, label=c)
    ax.set(title=f"Modelled PM2.5 by city, native three-hourly (UTC)\n{tag}", ylabel="PM2.5 (ug/m3, modelled)")
    ax.legend(ncol=4, fontsize=7)
    _save(fig, out / CHARTS[0])

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.boxplot([[r["pm2_5"] for r in nat if r["city"] == c] for c in cities], tick_labels=cities)
    ax.set(title=f"Distribution of modelled PM2.5 by city\n{tag}", ylabel="PM2.5 (ug/m3, modelled)")
    ax.tick_params(axis="x", labelrotation=30)
    _save(fig, out / CHARTS[1])

    fig, ax = plt.subplots(figsize=(8, 4.5))
    hours = sorted({int(r["valid_local"][11:13]) for r in nat})
    ax.plot(hours, [np.mean([r["pm2_5"] for r in nat if int(r["valid_local"][11:13]) == h]) for h in hours],
            marker="o")
    ax.set(title=f"Mean modelled PM2.5 by local hour (all cities)\n{tag}", xlabel="local hour (Asia/Tashkent)",
           ylabel="PM2.5 (ug/m3, modelled)")
    _save(fig, out / CHARTS[2])

    for fname, key, label, title in ((CHARTS[3], "wind_speed_ms", "wind speed (m/s)", "wind speed"),
                                     (CHARTS[4], "relative_humidity_2m", "relative humidity (%)", "relative humidity")):
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        for c in cities:
            pts = [(r[key], r["pm2_5"]) for r in nat if r["city"] == c and r[key] is not None]
            if pts:
                ax.scatter(*zip(*pts), s=8, label=c)
        ax.set(title=f"PM2.5 vs {title}, native rows\n{tag}", xlabel=label, ylabel="PM2.5 (ug/m3, modelled)")
        ax.legend(ncol=2, fontsize=6)
        _save(fig, out / fname)

    days = sorted({r["valid_local"][:10] for r in rows})
    grid = np.array([[sum(1 for r in rows if r["city"] == c and r["valid_local"][:10] == d) for d in days]
                     for c in cities])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    im = ax.imshow(grid, aspect="auto")
    ax.set_xticks(range(len(days)), [d[5:] for d in days])
    ax.set_yticks(range(len(cities)), cities)
    ax.set(title=f"Collected rows per city and local day\n{tag}")
    fig.colorbar(im, ax=ax)
    _save(fig, out / CHARTS[5])
    return list(CHARTS)


def write_manifest(out_dir, mode, n_rows):
    out = Path(out_dir)
    prov.write_text_lf(out / "eda_manifest.json", json.dumps({
        "mode": mode, "label": MODES[mode], "rows_used": n_rows,
        "files_sha256": {n: prov.sha256_file(out / n) for n in CHARTS}}, indent=2, sort_keys=True) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Exploratory charts.")
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    ap.add_argument("--mode", choices=sorted(MODES), required=True)
    ap.add_argument("--repo", default=str(prov.ROOT))
    a = ap.parse_args(argv)
    if a.mode == "full":
        evaluate.require_marker(a.repo)
        rows = evaluate.load_all_rows(a.db)[0]
    else:                                   # pre_freeze never loads the test period: guarded loader only
        conn = open_ro(a.db)
        try:
            rows = data.load_development(conn)
        finally:
            conn.close()
    out = Path(a.repo) / "results" / "eda" / a.mode
    make_charts(rows, out, a.mode)
    write_manifest(out, a.mode, len(rows))
    print(f"{len(CHARTS)} charts written to {out} ({MODES[a.mode]}; {len(rows)} rows)")


if __name__ == "__main__":
    main()
