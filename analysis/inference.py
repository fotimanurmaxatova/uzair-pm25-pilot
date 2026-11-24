"""Q1 to Q4: city fixed-effects associations with a restricted wild cluster bootstrap (decision 0010 items 17 to 19).

Descriptive associations, not predictions.  Run only AFTER the single test evaluation (the marker must exist); they
never feed back into any choice made for Q5.

  Q1  PM2.5 = a_city + b*wind (m/s)                              effect: ug/m3 per +1 m/s
  Q2  PM2.5 = a_city + b*humidity                                effect: ug/m3 per +10 percentage points
  Q3  Q1 + temperature, humidity, precipitation, hour (sin, cos) effect of wind: ug/m3 per +1 m/s
  Q4  1{PM2.5 >= 35} = a_city + d*class_hours (weekdays only)    effect: percentage points (linear probability model)

Sample: primary native rows of 2-8 Nov (Q4: weekdays 2-6 Nov), complete cases; clusters = local calendar days (all
cities in one cluster).  Inference: CR1 cluster-robust t; restricted wild cluster bootstrap with the null imposed,
Webb six-point weights, 9,999 replications, fixed seed, p = share of |t*| >= |t|.  The reported 95% interval is the
symmetric bootstrap-t interval from the UNRESTRICTED wild bootstrap (labelled as such; decision 0012 draft).  Holm
adjustment over Q1 to Q4 is shown for transparency and enters no rule.  Rule A uses Q3 with leave-one-day-out,
weekday-only and all-hourly-rows runs.

    python -m analysis.inference --db snapshots/assessed_snapshot.db
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

from analysis import evaluate, modelling as m, provenance as prov

REPS = 9999
SEED = 20261123
CHUNK = 500
WEBB = np.array([-np.sqrt(1.5), -1.0, -np.sqrt(0.5), np.sqrt(0.5), 1.0, np.sqrt(1.5)])
WEEK = ("2026-11-02", "2026-11-08")
WEEKDAYS = ("2026-11-02", "2026-11-06")
RULE_A_THRESHOLD = -2.0
OUT_REL = "results/inference"


class NotEstimable(RuntimeError):
    pass


# ---------------------------------------------------------------- regression and bootstrap
def fit_cluster_ols(X, y, cl, G, j=0):
    n, k = X.shape
    if G < 2 or n <= k or np.linalg.matrix_rank(X) < k:
        raise NotEstimable(f"not estimable (n={n}, k={k}, clusters={G})")
    xtxi = np.linalg.inv(X.T @ X)
    beta = xtxi @ X.T @ y
    u = y - X @ beta
    c = X @ xtxi[j]
    s = np.bincount(cl, weights=c * u, minlength=G)
    factor = G / (G - 1) * (n - 1) / (n - k)
    se = float(np.sqrt(factor * np.sum(s ** 2)))
    if not se > 0:
        raise NotEstimable("zero cluster-robust standard error")
    return beta, u, se


def _boot_t(X, base, resid, j, cl, G, reps, rng, center):
    """t* of coefficient j over `reps` Webb wild-cluster draws of y* = base + w_cluster * resid."""
    n, k = X.shape
    xtxi = np.linalg.inv(X.T @ X)
    A, c = xtxi @ X.T, X @ xtxi[j]
    factor = G / (G - 1) * (n - 1) / (n - k)
    ind = np.zeros((G, n))
    ind[cl, np.arange(n)] = 1.0
    out, done = [], 0
    while done < reps:
        b = min(CHUNK, reps - done)
        w = rng.choice(WEBB, size=(G, b))
        ystar = base[:, None] + w[cl, :] * resid[:, None]
        bs = A @ ystar
        u = ystar - X @ bs
        s = ind @ (c[:, None] * u)
        with np.errstate(divide="ignore", invalid="ignore"):
            out.append((bs[j] - center) / np.sqrt(factor * (s ** 2).sum(axis=0)))
        done += b
    return np.concatenate(out)


def wild_cluster_test(X, y, cl, G, j=0, reps=REPS, seed=SEED):
    """Coefficient j (tested coefficient is column 0 by convention)."""
    beta, u, se = fit_cluster_ols(X, y, cl, G, j)
    t = float(beta[j] / se)
    keep = [i for i in range(X.shape[1]) if i != j]
    xr = X[:, keep]
    fit_r = xr @ np.linalg.lstsq(xr, y, rcond=None)[0]
    t_r = _boot_t(X, fit_r, y - fit_r, j, cl, G, reps, np.random.default_rng(seed), 0.0)
    ok = np.isfinite(t_r)
    p = float(np.mean(np.abs(t_r[ok]) >= abs(t) - 1e-12)) if ok.any() else None
    t_u = _boot_t(X, X @ beta, u, j, cl, G, reps, np.random.default_rng(seed + 1), float(beta[j]))
    ok_u = np.isfinite(t_u)
    q = float(np.quantile(np.abs(t_u[ok_u]), 0.95)) if ok_u.any() else None
    combos = 6 ** G
    return {"estimate": float(beta[j]), "se_cr1": se, "t": t, "p_wcr": p,
            "ci95_bootstrap_t": [float(beta[j] - q * se), float(beta[j] + q * se)] if q is not None else None,
            "n": int(X.shape[0]), "clusters": int(G), "replications": int(reps), "seed": int(seed),
            "valid_replications_restricted": int(ok.sum()),
            "distinct_weight_combinations": int(combos),
            "weights_repeat": bool(combos < reps),
            "interval_note": "symmetric bootstrap-t interval from the unrestricted wild cluster bootstrap"}


# ---------------------------------------------------------------- samples and designs
def local_date(r):
    return r["valid_local"][:10]


def sample(rows, first=WEEK[0], last=WEEK[1], native=True, drop_dates=()):
    return [r for r in rows if first <= local_date(r) <= last and (r["native"] or not native)
            and local_date(r) not in drop_dates and r["pm2_5"] is not None]


REG = {"wind": lambda r: r["wind_speed_ms"],
       "humidity10": lambda r: None if r["relative_humidity_2m"] is None else r["relative_humidity_2m"] / 10.0,
       "humidity": lambda r: r["relative_humidity_2m"], "temperature": lambda r: r["temperature_2m"],
       "precipitation": lambda r: r["precipitation_mm"], "hour_sin": lambda r: r["hour_sin"],
       "hour_cos": lambda r: r["hour_cos"], "class_hours": lambda r: r["class_hours"]}
QUESTIONS = {"Q1": ("pm2_5", ["wind"]), "Q2": ("pm2_5", ["humidity10"]),
             "Q3": ("pm2_5", ["wind", "temperature", "humidity", "precipitation", "hour_sin", "hour_cos"]),
             "Q4": ("high_pm25_35", ["class_hours"])}


def build_design(rows, question):
    """Complete-case design; tested regressor first, then the other regressors, then one dummy per city present."""
    ycol, xs = QUESTIONS[question]
    complete = [r for r in rows if r[ycol] is not None and all(REG[x](r) is not None for x in xs)]
    if not complete:
        raise NotEstimable("no complete rows")
    cities = [c for c in m.CITIES if any(r["city"] == c for r in complete)]
    X = np.column_stack([[float(REG[x](r)) for r in complete] for x in xs]
                        + [[1.0 if r["city"] == c else 0.0 for r in complete] for c in cities])
    scale = 100.0 if question == "Q4" else 1.0                      # Q4: percentage points
    y = np.array([float(r[ycol]) * scale for r in complete])
    dates = sorted({local_date(r) for r in complete})
    cl = np.array([dates.index(local_date(r)) for r in complete])
    return X, y, cl, len(dates), {"rows_in_sample": len(rows), "complete_cases": len(complete),
                                  "dropped_incomplete": len(rows) - len(complete), "cities": len(cities)}


def estimate(rows, question, reps=REPS, seed=SEED):
    if question == "Q4":
        rows = [r for r in rows if WEEKDAYS[0] <= local_date(r) <= WEEKDAYS[1]]
    X, y, cl, G, info = build_design(rows, question)
    return {**wild_cluster_test(X, y, cl, G, 0, reps, seed), **info}


# ---------------------------------------------------------------- multiple-testing and Rule A
def holm(pvalues):
    """Holm step-down adjusted p-values for {name: p}; None stays None."""
    for k, p in pvalues.items():
        if p is None:
            continue
        if isinstance(p, bool) or not isinstance(p, (int, float, np.integer, np.floating)) \
                or not math.isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError(f"invalid p-value for {k!r}: {p!r} (must be a finite number in [0, 1] or None)")
    items = sorted(((p, k) for k, p in pvalues.items() if p is not None))
    mm, adj, run = len(items), {k: None for k in pvalues}, 0.0
    for i, (p, k) in enumerate(items):
        run = max(run, min(1.0, (mm - i) * p))
        adj[k] = run
    return adj


def rule_a(primary, sensitivity):
    """Rule A on the Q3 wind coefficient (protocol).  None = a run that cannot be estimated."""
    if primary is None or any(s is None for s in sensitivity):
        return "inconclusive"
    allb = [primary, *sensitivity]
    if not (all(b < 0 for b in allb) or all(b >= 0 for b in allb)):
        return "inconclusive"                                     # unstable sign
    if primary <= RULE_A_THRESHOLD:
        return "worth a longer study"
    if primary < 0:
        return "below practical threshold"
    return "no support"


def _try(rows, q, reps, seed):
    try:
        return estimate(rows, q, reps, seed)
    except NotEstimable as exc:
        return {"estimable": False, "reason": str(exc)}


def run_questions(rows, reps=REPS, seed=SEED):
    base = sample(rows)
    primary = {q: _try(base, q, reps, seed) for q in QUESTIONS}
    adj = holm({q: primary[q].get("p_wcr") for q in primary})
    for q in primary:
        primary[q]["p_holm"] = adj[q]
    dates = sorted({local_date(r) for r in base})
    sens = {"leave_one_day_out": {d: {q: _try(sample(rows, drop_dates=(d,)), q, reps, seed) for q in ("Q1", "Q2", "Q3")}
                                  for d in dates},
            "weekday_only": {q: _try(sample(rows, *WEEKDAYS), q, reps, seed) for q in ("Q1", "Q2", "Q3")},
            "all_eligible_hourly_rows": {q: _try(sample(rows, native=False), q, reps, seed) for q in ("Q1", "Q2", "Q3")}}
    q3_runs = [v["Q3"] for v in sens["leave_one_day_out"].values()] + [sens["weekday_only"]["Q3"],
                                                                      sens["all_eligible_hourly_rows"]["Q3"]]
    sens_b = [r["estimate"] if "estimate" in r else None for r in q3_runs]
    return {"primary_native": primary, "sensitivity": sens,
            "rule_a": {"q3_wind_estimate": primary["Q3"].get("estimate"), "sensitivity_estimates": sens_b,
                       "threshold": RULE_A_THRESHOLD, "conclusion": rule_a(primary["Q3"].get("estimate"), sens_b)},
            "notes": ["descriptive associations, not predictions or causal effects",
                      "p-values, intervals and Holm values are exploratory and conditional on their assumptions",
                      "few clusters (7; 5 for Q4): inference is unreliable; Q4 weights repeat (6^5 = 7,776 < 9,999)"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Q1-Q4 inference (after the single test evaluation).")
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    ap.add_argument("--repo", default=str(prov.ROOT))
    a = ap.parse_args(argv)
    evaluate.require_marker(a.repo)
    all_rows, _ = evaluate.load_all_rows(a.db)
    res = run_questions(all_rows)
    out = Path(a.repo) / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    prov.write_text_lf(out / "inference.json", json.dumps(evaluate._jsonable(res), indent=2, sort_keys=True) + "\n")
    for q, r in res["primary_native"].items():
            if "estimate" not in r:
                print(f"{q}: NOT ESTIMABLE ({r.get('reason')})")
                continue
            print(f"{q}: estimate {r['estimate']:.3f}  se {r['se_cr1']:.3f}  p_wcr {r['p_wcr']}  n {r['n']}  clusters {r['clusters']}")
    print("Rule A: " + res["rule_a"]["conclusion"])
    print(f"written: {out / 'inference.json'}")


if __name__ == "__main__":
    main()
