"""Q5 post-test analyses (decision 0010 item 20, issue #8): error analysis, paired block bootstrap, leave-one-city-out.

Pure functions on row dicts and prediction arrays.  Nothing here loads data or touches Git; analysis.evaluate calls
these after the freeze guard has passed.  Settings below are fixed before the test is opened (decision 0012 draft):
  * residual = observed - predicted; the local hour is the hour of the forecast ORIGIN (Asia/Tashkent);
  * observed-level bins are on the observed target: <15, 15-35, 35-50, >=50 ug/m3 (a descriptive grouping only);
  * event thresholds 35 (primary) and 25, 50 (sensitivity); an event is target >= threshold, a forecast event is
    prediction >= threshold; missed event = observed event, no forecast event; false alarm = the reverse;
  * bootstrap: common six-hour time blocks, resampled across all cities together, 9,999 replications, fixed seed.
"""
import math

import numpy as np

from analysis import cutoffs as cut
from analysis import modelling as m

THRESHOLDS = (35, 25, 50)
LEVEL_BINS = (("<15", 0.0, 15.0), ("15-35", 15.0, 35.0), ("35-50", 35.0, 50.0), (">=50", 50.0, math.inf))
BOOT_REPS = 9999
BOOT_SEED = 20261122
COMPARISONS = (("full", "persistence"), ("noweather", "persistence"), ("full", "noweather"))
MODELS = ("full", "noweather", "persistence")


def _summ(y, p):
    e = y - p
    return {"n": int(len(y)), "mean_residual": float(e.mean()), "mae": float(np.abs(e).mean()),
            "rmse": float(np.sqrt((e ** 2).mean()))}


def _group(rows, y, preds, keys):
    """{group: {model: summary}} for the row indices of each group."""
    out = {}
    for key in sorted(set(keys)):
        idx = np.array([i for i, k in enumerate(keys) if k == key])
        out[str(key)] = {name: _summ(y[idx], np.asarray(p)[idx]) for name, p in preds.items()}
    return out


def level_label(v):
    for name, lo, hi in LEVEL_BINS:
        if lo <= v < hi:
            return name
    raise ValueError(f"value outside every level bin: {v}")


def event_table(y, p, thr):
    obs, fc = y >= thr, np.asarray(p) >= thr
    return {"threshold": thr, "observed_events": int(obs.sum()), "forecast_events": int(fc.sum()),
            "hits": int((obs & fc).sum()), "missed_events": int((obs & ~fc).sum()),
            "false_alarms": int((~obs & fc).sum()), "correct_negatives": int((~obs & ~fc).sum())}


def error_analysis(rows, preds):
    """preds: {'full': array, 'noweather': array, 'persistence': array} on the same rows, same order."""
    if not rows:
        raise ValueError("no test rows")
    y = m.targets(rows)
    hours = [int(r["valid_local"][11:13]) for r in rows]
    return {
        "definition": "residual = observed - predicted; local hour of the forecast origin; level bins on the observed target",
        "by_city": _group(rows, y, preds, [r["city"] for r in rows]),
        "by_local_hour": _group(rows, y, preds, hours),
        "by_observed_level": _group(rows, y, preds, [level_label(v) for v in y]),
        "events": {str(thr): {name: event_table(y, p, thr) for name, p in preds.items()} for thr in THRESHOLDS}}


# ---------------------------------------------------------------- paired block bootstrap
def block_index(rows):
    """Six-hour block number of each origin, counted from the first test origin; common to all cities."""
    return np.array([int((r["valid_dt"] - cut.TEST_START_UTC) / (6 * cut.H)) for r in rows])


def paired_block_bootstrap(rows, preds, reps=BOOT_REPS, seed=BOOT_SEED):
    y = m.targets(rows)
    blocks = block_index(rows)
    ub = np.unique(blocks)
    k = len(ub)
    if k < 2:
        raise ValueError("fewer than two six-hour blocks: the block bootstrap is not defined")
    idx = np.searchsorted(ub, blocks)
    n_b = np.bincount(idx, minlength=k).astype(float)
    sse = {name: np.bincount(idx, weights=(y - np.asarray(p)) ** 2, minlength=k) for name, p in preds.items()}
    draws = np.random.default_rng(seed).integers(0, k, size=(reps, k))
    boot = {name: np.sqrt(s[draws].sum(axis=1) / n_b[draws].sum(axis=1)) for name, s in sse.items()}
    obs = {name: float(np.sqrt(s.sum() / n_b.sum())) for name, s in sse.items()}
    res = {"blocks": int(k), "replications": int(reps), "seed": int(seed),
           "note": "indicative only: the test covers two calendar days", "rmse": obs, "comparisons": {}, "skill": {}}
    for a, b in COMPARISONS:
        d = boot[a] - boot[b]
        lo, hi = np.percentile(d, [2.5, 97.5])
        res["comparisons"][f"{a}_minus_{b}"] = {
            "rmse_difference": obs[a] - obs[b], "ci95": [float(lo), float(hi)],
            "share_replications_first_lower": float((d < 0).mean())}
    for name in ("full", "noweather"):
        s = 1.0 - boot[name] / boot["persistence"]
        lo, hi = np.percentile(s, [2.5, 97.5])
        res["skill"][name] = {"skill": 1.0 - obs[name] / obs["persistence"], "ci95": [float(lo), float(hi)]}
    return res


# ---------------------------------------------------------------- leave-one-city-out
def fit_without_city(spec, feature_set, train_rows, held_out):
    others = [c for c in m.CITIES if c != held_out]
    train = [r for r in train_rows if r["city"] != held_out]
    if not train:
        raise ValueError(f"no training rows left after holding out {held_out}")
    pre = m.Preprocessor(feature_set, scale=(spec["model"] == "ridge"), cities=others).fit(train)
    est = m.make_estimator(spec).fit(pre.transform(train), m.targets(train))
    return pre, est


def leave_one_city_out(train_rows, test_rows, selected):
    """Frozen hyperparameters, no new selection.  Held-out city = all-zero city indicators (0010 item 20).
    train_rows: eligible primary pre-cut-off pairs; test_rows: eligible primary test pairs (all cities)."""
    per_city, pooled_y, pooled_p = [], [], {n: [] for n in MODELS}
    for city in m.CITIES:
        test = [r for r in test_rows if r["city"] == city]
        if not test:
            per_city.append({"city": city, "n_test": 0})
            continue
        y = m.targets(test)
        preds = {"persistence": m.persistence(test)}
        for fs in ("full", "noweather"):
            pre, est = fit_without_city(selected[fs]["spec"], fs, train_rows, city)
            preds[fs] = est.predict(pre.transform(test, allow_unknown_city=True))
        rp = m.rmse(y, preds["persistence"])
        row = {"city": city, "n_test": len(test), "training_cities": 7}
        for name in MODELS:
            row[f"rmse_{name}"] = m.rmse(y, preds[name])
            pooled_p[name].extend(float(v) for v in preds[name])
            if name != "persistence":
                row[f"skill_{name}"] = (1.0 - row[f"rmse_{name}"] / rp) if rp > 0 else None
        pooled_y.extend(float(v) for v in y)
        per_city.append(row)
    pooled = None
    if pooled_y:
        py = np.array(pooled_y)
        rp = m.rmse(py, pooled_p["persistence"])
        pooled = {"n_test": len(py), **{f"rmse_{n}": m.rmse(py, pooled_p[n]) for n in MODELS},
                  **{f"skill_{n}": (1.0 - m.rmse(py, pooled_p[n]) / rp) if rp > 0 else None
                     for n in ("full", "noweather")}}
    return {"cities": per_city, "pooled": pooled,
            "note": "post-freeze sensitivity analysis; frozen hyperparameters; not a replacement for the primary models"}
