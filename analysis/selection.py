"""Model selection under decisions 0009 and 0010 (issue #15).  Development period only.

For each feature set (full, noweather) separately, the eight candidates (Ridge alpha 0.1, 1, 10, 100; HGB
max_depth 3, 5 x learning_rate 0.05, 0.1) are fitted on each of the three expanding training folds and scored on
the native validation origins of that fold.  Criterion: unweighted mean of the three per-fold RMSEs.  Ties
(equal when rounded to 4 decimals) go to the simpler setting: Ridge over HGB, larger alpha, smaller max_depth,
then smaller learning_rate.  Persistence is scored on the same origins and is not tuned.

Data come only from analysis.data (receipt-time guard); this module cannot see test-period rows.  A fold with no
eligible training or validation origin stops the selection (no silent skipping).

Run (writes the CV table, selected configurations and a manifest; prints the CV table):
    python -m analysis.selection --db snapshots\\assessed_snapshot.db --out results\\selection
Do not run it before this code and its synthetic tests are committed (decision 0009 record of actual times).
"""
import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

from analysis import cutoffs as cut
from analysis import data, modelling as m
from analysis.data import GuardError
from monitoring.coverage import open_ro

FOLDS = (1, 2, 3)


class SelectionError(RuntimeError):
    pass


def _check_development_rows(rows):
    for r in rows:
        if r["valid_dt"] >= cut.TEST_START_UTC:
            raise GuardError(f"test-origin row passed to selection: {r['city']} {r['valid_utc']}")


def fold_sets(rows):
    out = {}
    for k in FOLDS:
        tr = data.eligible(rows, f"cv{k}_train", native_only=True)
        va = data.eligible(rows, f"cv{k}_valid", native_only=True)
        if not tr or not va:
            raise SelectionError(f"fold {k} has no eligible training ({len(tr)}) or validation ({len(va)}) origins")
        out[k] = (tr, va)
    return out


def rank(results):
    """results: {candidate_id: {'spec':..., 'folds': [r1, r2, r3]}} -> list sorted best first (tie-break applied)."""
    rows = []
    for cid, v in results.items():
        mean = sum(v["folds"]) / len(v["folds"])
        rows.append((round(mean, 4), m.tie_key(v["spec"]), cid, mean))
    rows.sort(key=lambda t: (t[0], t[1]))
    return [(cid, mean) for _, _, cid, mean in rows]


def run_selection(rows, feature_sets=("full", "noweather")):
    _check_development_rows(rows)
    folds = fold_sets(rows)
    counts = {k: {"train": len(tr), "valid": len(va),
                  "excluded_feature_unavailable_train": len(data.unavailable(rows, f"cv{k}_train")),
                  "excluded_feature_unavailable_valid": len(data.unavailable(rows, f"cv{k}_valid"))}
              for k, (tr, va) in folds.items()}
    persistence = [m.rmse(m.targets(va), m.persistence(va)) for _, va in folds.values()]
    table, selected = [], {}
    for fs in feature_sets:
        results = {}
        for spec in m.candidates():
            fold_rmse = []
            for tr, va in folds.values():
                pre, est = m.fit_model(spec, fs, tr)
                fold_rmse.append(m.rmse(m.targets(va), m.predict(pre, est, va)))
            results[m.candidate_id(spec)] = {"spec": spec, "folds": fold_rmse}
        order = rank(results)
        best = order[0][0]
        for cid, mean in order:
            table.append({"feature_set": fs, "candidate": cid, "fold1_rmse": results[cid]["folds"][0],
                          "fold2_rmse": results[cid]["folds"][1], "fold3_rmse": results[cid]["folds"][2],
                          "mean_rmse": mean, "selected": int(cid == best)})
        selected[fs] = {"candidate": best, "spec": results[best]["spec"], "fold_rmse": results[best]["folds"],
                        "mean_rmse": dict(order)[best]}
    return {"counts": counts, "persistence_fold_rmse": persistence, "table": table, "selected": selected}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_outputs(res, out_dir, db_path=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "cv_table.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(res["table"][0]))
        w.writeheader()
        w.writerows(res["table"])
    (out / "selected_configurations.json").write_text(json.dumps({
        "criterion": "unweighted mean of per-fold RMSE on native validation origins; ties (4 decimals) to the simpler setting",
        "fold_counts": res["counts"], "persistence_fold_rmse": res["persistence_fold_rmse"],
        "selected": res["selected"]}, indent=2), encoding="utf-8")
    import numpy, sklearn
    manifest = {"python": platform.python_version(), "numpy": numpy.__version__, "scikit_learn": sklearn.__version__,
                "snapshot_sha256": sha256(db_path) if db_path else None,
                "final_cutoff_utc": data.iso(cut.FINAL_CUTOFF_UTC),
                "code_sha256": {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
                "outputs_sha256": {n: sha256(out / n) for n in ("cv_table.csv", "selected_configurations.json")}}
    (out / "selection_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Model selection (development period only).")
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    ap.add_argument("--out", default="results/selection")
    a = ap.parse_args(argv)
    conn = open_ro(a.db)
    try:
        rows = data.load_development(conn)
    finally:
        conn.close()
    res = run_selection(rows)
    write_outputs(res, a.out, a.db)
    print("fold sizes (train | validation): " + ", ".join(f"fold{k} {c['train']}|{c['valid']}" for k, c in res["counts"].items()))
    print("persistence RMSE per fold: " + ", ".join(f"{v:.4f}" for v in res["persistence_fold_rmse"]))
    for r in res["table"]:
        print(f"{r['feature_set']:9s} {r['candidate']:22s} {r['fold1_rmse']:.4f} {r['fold2_rmse']:.4f} "
              f"{r['fold3_rmse']:.4f} mean {r['mean_rmse']:.4f}{'  <- selected' if r['selected'] else ''}")
    print(f"written: {a.out}")


if __name__ == "__main__":
    main()