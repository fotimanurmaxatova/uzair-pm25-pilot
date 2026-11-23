"""Final fit, model artefacts and freeze manifest (decisions 0009, 0010 items 14 and 16, 0011 sections 5 to 7).

Run once, AFTER the selection run has been committed and the working tree is clean.  This module does not commit
or tag: the person commits `results/freeze/` and then creates the annotated tag `late-freeze-YYYYMMDD-HHMM`.

What it does
  1. takes the LATEST numbered selection run and refuses an incomplete one (never falls back to an earlier run);
  2. checks the selection outputs, the six required code files and the snapshot against that run's manifest;
  3. fits the two primary models (full, no-weather) on ALL eligible native pairs of `train_final`
     (receipt cut-off 6 Nov 22:00 local, strict), using the selected configurations only;
  4. writes the artefacts, the frozen configuration and the freeze manifest (written last, never overwritten).

It reads development rows only, through the receipt-time guard in analysis.data.  It never loads the test period.
It prints counts, never PM2.5 values or errors.

    python -m analysis.freeze --db snapshots/assessed_snapshot.db --selection results/selection --out results/freeze
"""
import argparse
import json
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path

from analysis import cutoffs as cut
from analysis import data, modelling as m, provenance as prov
from monitoring.coverage import open_ro

FEATURE_SETS = ("full", "noweather")
RUN_RE = re.compile(r"^run-(\d+)$")
RUN_FILES = ("cv_table.csv", "selected_configurations.json", "selection_manifest.json")
MANIFEST_NAME = "freeze_manifest.json"
CONFIG_NAME = "frozen_config.json"


class FreezeError(RuntimeError):
    pass


# ---------------------------------------------------------------- selection run
def latest_complete_run(base):
    """The highest-numbered run-NNN directory, which must be complete (0011 section 5)."""
    runs = []
    for p in Path(base).glob("run-*"):
        mt = RUN_RE.match(p.name)
        if p.is_dir() and mt:
            runs.append((int(mt.group(1)), p))
    if not runs:
        raise FreezeError(f"no selection run directory (run-NNN) in {base}")
    runs.sort()
    run = runs[-1][1]
    missing = [f for f in RUN_FILES if not (run / f).is_file()]
    if missing:
        raise FreezeError(f"the latest selection run {run.name} is incomplete (missing {missing}); resolve and "
                          "document it first; the freeze never falls back to an earlier run (0011 section 5)")
    return run


def check_selection_run(run, repo_root, snapshot_path):
    """Verify the run against its own manifest.  Returns the parsed selection manifest."""
    run = Path(run)
    man = json.loads((run / "selection_manifest.json").read_text(encoding="utf-8"))
    outs = man.get("outputs_sha256") or {}
    for name in ("cv_table.csv", "selected_configurations.json"):
        if outs.get(name) != prov.sha256_file(run / name):
            raise FreezeError(f"{run.name}/{name} does not match the hash in its selection manifest")
    files = man.get("files")
    if not isinstance(files, dict):
        raise FreezeError("the selection manifest has no 'files' record of code hashes (0011 section 2)")
    for rel in prov.REQUIRED_CODE_FILES:
        rec = files.get(rel)
        if rec is None:
            raise FreezeError(f"the selection manifest does not record {rel}")
        if prov.committed_blob(repo_root, rel) != rec.get("git_blob"):          # committed object, not working bytes
            raise FreezeError(f"{rel} changed after the selection run; the freeze is refused (0011 section 6). "
                              "Record the cause in a decision.")
    if man.get("snapshot_sha256") != prov.sha256_file(snapshot_path):
        raise FreezeError("the snapshot does not match the hash recorded by the selection run")
    return man


# ---------------------------------------------------------------- fitting
def training_fingerprint(rows):
    """SHA-256 over the identity and target of every training pair (not the values of the features)."""
    lines = sorted(f"{r['city']}|{r['valid_utc']}|{r['receipt_utc']}|{r['target_pm25_t6']!r}" for r in rows)
    return prov.sha256_bytes("\n".join(lines).encode("utf-8"))


def fit_frozen_models(dev_rows, selected):
    """Fit both primary models on all eligible native `train_final` pairs with the selected specs."""
    train = data.eligible(dev_rows, "train_final", native_only=True)
    if not train:
        raise FreezeError("no eligible primary training pairs for the final fit")
    fp = training_fingerprint(train)
    bundles = {}
    for fs in FEATURE_SETS:
        spec = selected[fs]["spec"]
        pre, est = m.fit_model(spec, fs, train)
        bundles[fs] = {"feature_set": fs, "spec": spec, "preprocessor": pre, "estimator": est,
                       "n_train": len(train), "train_fingerprint": fp}
    return bundles


def describe_model(b):
    d = {"feature_set": b["feature_set"], "spec": b["spec"], "n_train": b["n_train"],
         "train_fingerprint": b["train_fingerprint"], "preprocessor_state": b["preprocessor"].state()}
    est = b["estimator"]
    if b["spec"]["model"] == "ridge":
        d["coef"] = [float(x) for x in est.coef_]
        d["intercept"] = float(est.intercept_)
    else:
        d["n_iter"] = int(est.n_iter_)
    return d


# ---------------------------------------------------------------- writing and verification
def _dump(path, obj):
    prov.write_text_lf(path, json.dumps(obj, indent=2, sort_keys=True) + "\n")


def write_freeze(out_dir, bundles, selection_run, run_manifest, snapshot_sha256, repo_root, now=None):
    out = Path(out_dir)
    if (out / MANIFEST_NAME).exists():
        raise FreezeError(f"{out / MANIFEST_NAME} already exists; a freeze is never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    run = Path(selection_run)
    sel = json.loads((run / "selected_configurations.json").read_text(encoding="utf-8"))
    names = []
    for fs, b in bundles.items():
        (out / f"model_{fs}.pkl").write_bytes(pickle.dumps(
            {k: b[k] for k in ("feature_set", "spec", "preprocessor", "estimator")}, protocol=4))
        _dump(out / f"model_{fs}.json", describe_model(b))
        names += [f"model_{fs}.pkl", f"model_{fs}.json"]
    _dump(out / CONFIG_NAME, {
        "label": "late freeze", "selection_run": run.name, "criterion": sel.get("criterion"),
        "selected": sel["selected"], "persistence_fold_rmse": sel["persistence_fold_rmse"],
        "fold_counts": sel.get("fold_counts"), "final_cutoff_utc": data.iso(cut.FINAL_CUTOFF_UTC)})
    names.append(CONFIG_NAME)
    now = now or datetime.now(timezone.utc)
    _dump(out / MANIFEST_NAME, {
        "label": "late freeze",
        "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "created_asia_tashkent": (now + cut.TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "parent_commit": prov.head(repo_root), "branch": prov.branch(repo_root),
        "selection_run": run.name,
        "selection_outputs_sha256": {n: prov.sha256_file(run / n) for n in RUN_FILES},
        "selection_manifest_snapshot_sha256": run_manifest.get("snapshot_sha256"),
        "snapshot_sha256": snapshot_sha256,
        "artefacts_sha256": {n: prov.sha256_file(out / n) for n in sorted(names)},
        "n_train": {fs: b["n_train"] for fs, b in bundles.items()},
        "final_cutoff_utc": data.iso(cut.FINAL_CUTOFF_UTC),
        "files": prov.provenance_files(repo_root), "environment": prov.environment()})
    return out / MANIFEST_NAME


def verify_artefacts(freeze_dir, manifest):
    """Re-hash every artefact named in the manifest.  Any difference stops the evaluation."""
    for name, sha in manifest["artefacts_sha256"].items():
        p = Path(freeze_dir) / name
        if not p.is_file():
            raise FreezeError(f"frozen artefact missing: {name}")
        if prov.sha256_file(p) != sha:
            raise FreezeError(f"frozen artefact changed: {name}")


def load_model(path, expected_sha256):
    """Unpickle a frozen model only after its SHA-256 matches the manifest."""
    b = Path(path).read_bytes()
    if prov.sha256_bytes(b) != expected_sha256:
        raise FreezeError(f"{Path(path).name} does not match the frozen hash; it is not loaded")
    return pickle.loads(b)


# ---------------------------------------------------------------- command line
def build_freeze(db, selection_base, out_dir, repo_root=prov.ROOT, now=None):
    repo_root = Path(repo_root)
    if not prov.is_clean(repo_root):
        raise FreezeError("the working tree is not clean: commit the selection outputs first (0011 section 3)")
    problems = prov.check_pins(repo_root / "requirements.txt")
    if problems:
        raise FreezeError("environment differs from the pins: " + "; ".join(problems))
    run = latest_complete_run(selection_base)
    run_manifest = check_selection_run(run, repo_root, db)
    selected = json.loads((run / "selected_configurations.json").read_text(encoding="utf-8"))["selected"]
    conn = open_ro(db)
    try:
        dev_rows = data.load_development(conn)
    finally:
        conn.close()
    bundles = fit_frozen_models(dev_rows, selected)
    path = write_freeze(out_dir, bundles, run, run_manifest, prov.sha256_file(db), repo_root, now)
    return {"run": run.name, "manifest": path, "n_train": bundles["full"]["n_train"],
            "manifest_sha256": prov.sha256_file(path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Final fit and freeze manifest (development data only).")
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    ap.add_argument("--selection", default="results/selection")
    ap.add_argument("--out", default="results/freeze")
    a = ap.parse_args(argv)
    r = build_freeze(a.db, a.selection, a.out)
    print(f"selection run used: {r['run']}")
    print(f"final fit on {r['n_train']} eligible primary pairs (both models)")
    print(f"written: {r['manifest']}  sha256 {r['manifest_sha256']}")
    print("Next: commit results/freeze/, then tag it: git tag -a late-freeze-YYYYMMDD-HHMM -m \"late freeze <hash> <time>\"")


if __name__ == "__main__":
    main()
