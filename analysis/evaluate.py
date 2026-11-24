"""Single held-out test evaluation behind the late-freeze guard (decisions 0009 and 0010 items 13 to 16, 0011 section 8).

The ONLY module (with the post-test modules that call `require_marker`) that may load the test period.

Guard (all must hold, otherwise nothing is loaded and nothing is written):
  * exactly one tag matching `late-freeze-*`, named late-freeze-YYYYMMDD-HHMM, ANNOTATED, its commit an ancestor of HEAD;
  * working tree clean;
  * every commit after the tag touches only results/, docs/, README.md or .gitignore;
  * the freeze manifest equals the one in the tag commit; every frozen artefact, the snapshot and every frozen code
    file match the manifest hashes; NumPy and scikit-learn match the pins;
  * the first run is allowed only if no marker exists; a later run needs --post-test and an existing marker, and all
    of its output is labelled post-test work.

The first evaluation writes the marker (exclusive create) BEFORE the test rows are loaded: the test is then spent.
Models and persistence are scored on identical eligible native test origins.  The hourly sensitivity run refits the
frozen hyperparameters on all eligible hourly training pairs (no second selection) and is reported separately.

    python -m analysis.evaluate --db snapshots/assessed_snapshot.db
    python -m analysis.evaluate --db snapshots/assessed_snapshot.db --post-test
"""
import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from analysis import cutoffs as cut
from analysis import data, freeze, modelling as m, provenance as prov, q5_extras as q5
from monitoring.coverage import is_native, open_ro

MARKER = "FIRST_TEST_EVALUATION.json"
TAG_GLOB = "late-freeze-*"
TAG_RE = re.compile(r"^late-freeze-\d{8}-\d{4}$")
ALLOWED_DIRS = ("results/", "docs/")
ALLOWED_FILES = ("README.md", ".gitignore")
FREEZE_REL = "results/freeze"
OUT_REL = "results/evaluation"
POST_REL = "results/post_test"
TEST_FIRST, TEST_LAST = cut.TEST_START_UTC, cut.TEST_END_UTC


class EvaluationGuardError(RuntimeError):
    pass


# ---------------------------------------------------------------- guard
def marker_path(repo_root, out_rel=OUT_REL):
    return Path(repo_root) / out_rel / MARKER


def require_marker(repo_root, out_rel=OUT_REL):
    """For modules that may only run after the single test evaluation (Q1-Q4, full-window EDA)."""
    if not marker_path(repo_root, out_rel).is_file():
        raise EvaluationGuardError("the single test evaluation has not been run yet "
                                   f"({out_rel}/{MARKER} missing); post-test analyses are not allowed before it")



def check_guard(repo_root, snapshot_path, freeze_rel=FREEZE_REL, out_rel=OUT_REL,
                post_test=False, check_env=True):
    repo = Path(repo_root)

    mk = marker_path(repo, out_rel).is_file()

    if mk and not post_test:
        raise EvaluationGuardError(
            "the first test evaluation has already run; a second run needs "
            "--post-test and all its output is labelled post-test work")

    if post_test and not mk:
        raise EvaluationGuardError(
            "--post-test needs an existing first evaluation (marker missing)")

    tags = prov.list_tags(TAG_GLOB, repo)

    if len(tags) != 1:
        raise EvaluationGuardError(
            f"exactly one {TAG_GLOB} tag is required, found {len(tags)}: {tags}")

    tag = tags[0]

    if not TAG_RE.match(tag):
        raise EvaluationGuardError(
            f"tag {tag} is not named late-freeze-YYYYMMDD-HHMM")

    if prov.tag_object_type(tag, repo) != "tag":
        raise EvaluationGuardError(f"tag {tag} is not annotated")

    tc = prov.tag_commit(tag, repo)

    if not prov.is_ancestor(tc, "HEAD", repo):
        raise EvaluationGuardError(
            f"the commit of {tag} is not an ancestor of HEAD")

    if not prov.is_clean(repo):
        raise EvaluationGuardError(
            "the working tree is not clean (tracked or untracked changes)")

    bad = [
        f for f in prov.files_changed_after(tc, repo)
        if not (
            f.startswith(ALLOWED_DIRS)
            or f in ALLOWED_FILES
        )
    ]

    if bad:
        raise EvaluationGuardError(
            f"commits after {tag} changed files outside results/, docs/, "
            f"README.md, .gitignore: {bad}")
    man_rel = f"{freeze_rel}/{freeze.MANIFEST_NAME}"
    man_path = repo / man_rel

    if not man_path.is_file():
        raise EvaluationGuardError(f"{man_rel} is missing")

    try:
        manifest = json.loads(
            man_path.read_text(encoding="utf-8"))

        tagged_manifest = json.loads(
            prov.show_file(tc, man_rel, repo).decode("utf-8"))

    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationGuardError(
            f"the freeze manifest is missing, unreadable or invalid: {exc}") from exc

    if not isinstance(manifest, dict):
        raise EvaluationGuardError(
            "the freeze manifest must be a JSON object")

    if tagged_manifest != manifest:
        raise EvaluationGuardError(
            "the freeze manifest differs from the one in the tag commit")

    try:
        freeze.verify_artefacts(repo / freeze_rel, manifest)
    except freeze.FreezeError as exc:
        raise EvaluationGuardError(str(exc)) from exc

    expected_snapshot = manifest.get("snapshot_sha256")

    if (
        not isinstance(expected_snapshot, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_snapshot)):
        raise EvaluationGuardError(
            "the freeze manifest has a missing or invalid snapshot SHA-256")

    try:
        actual_snapshot = prov.sha256_file(snapshot_path)
    except OSError as exc:
        raise EvaluationGuardError(
            f"cannot read the assessed snapshot: {exc}") from exc

    if actual_snapshot != expected_snapshot:
        raise EvaluationGuardError(
            "the snapshot does not match the frozen snapshot hash")

    # Derive the required frozen paths from the clean repository.
    # Do not trust the manifest to tell us which files must be present.
    analysis_dir = repo / "analysis"

    expected_paths = {
        p.relative_to(repo).as_posix()
        for p in analysis_dir.glob("*.py")
        if p.is_file()}

    expected_paths.update(prov.REQUIRED_CODE_FILES)
    expected_paths.update(prov.CONFIG_FILES)
    expected_paths.update(prov.DECISION_FILES)

    optional_decision = (
        "docs/decisions/0012-freeze-evaluation-and-post-test-implementation.md")
    try:
        tree_paths = prov.git(
            ["ls-tree", "-r", "--name-only", tc, "--", optional_decision],
            repo,).stdout.splitlines()
    except prov.ProvenanceError as exc:
        raise EvaluationGuardError(
            f"cannot inspect optional decision file in freeze tag: {exc}") from exc

    if optional_decision in tree_paths:
        expected_paths.add(optional_decision)

    files = manifest.get("files")

    if not isinstance(files, dict):
        raise EvaluationGuardError(
            "the freeze manifest has no valid 'files' provenance dictionary")

    try:
        prov.verify_file_records(
            files,
            tuple(sorted(expected_paths)),
            root=repo,
            rev=tc,)
    except prov.ProvenanceError as exc:
        raise EvaluationGuardError(
            f"frozen code provenance verification failed: {exc}") from exc

    if check_env:
        problems = prov.check_pins(repo / "requirements.txt")

        if problems:
            raise EvaluationGuardError(
                "environment differs from the pins: "
                + "; ".join(problems))

    return {
        "tag": tag,
        "tag_commit": tc,
        "head": prov.head(repo),
        "manifest": manifest,
    }


# ---------------------------------------------------------------- data
def _load_raw_all(conn):
    conn.row_factory = lambda cur, r: dict(zip([d[0] for d in cur.description], r))
    sel = ", ".join(f"o.{f}" for f in data.FEATURES)
    return conn.execute(
        f"SELECT c.name AS city, o.observation_hour_utc, o.collected_at_utc, o.weather_time_utc, {sel} "
        "FROM observations o JOIN cities c USING (city_id) "
        "WHERE o.is_pilot=0 AND o.acquisition_mode='scheduled' "
        "ORDER BY c.city_id, o.observation_hour_utc").fetchall()


def load_all_rows(db_path):
    """(all_rows, dev_rows).  all_rows include the test period; dev_rows come through the receipt-time guard and
    are the only rows used for fitting, exactly as in the selection and the freeze."""
    conn = open_ro(db_path)
    try:
        raw = _load_raw_all(conn)
        dev = data.load_development(conn)
    finally:
        conn.close()
    return data.derive_rows(raw), dev


def max_pairs(native_only=True):
    n_hours = int((TEST_LAST - TEST_FIRST) / cut.H) + 1
    ok = sum(1 for k in range(n_hours) if is_native(TEST_FIRST + k * cut.H) or not native_only)
    return ok * len(m.CITIES)


def test_pairs(rows, native_only=True):
    """Eligible test pairs and the separately counted losses (collected rows are not pairs)."""
    inwin = [r for r in rows if TEST_FIRST <= r["valid_dt"] <= TEST_LAST and (r["native"] or not native_only)]
    usable = [r for r in inwin if r["usable_pair"] and r["pm2_5"] is not None]    # persistence needs the origin value
    elig = [r for r in usable if data.features_available(r)]
    return elig, {"maximum_pairs": max_pairs(native_only), "collected_rows_in_window": len(inwin),
                  "no_usable_pair": len(inwin) - len(usable),
                  "feature_row_received_after_prediction_time": len(usable) - len(elig),
                  "eligible_pairs": len(elig)}


# ---------------------------------------------------------------- scoring
def metrics(y, p):
    y, p = np.asarray(y, float), np.asarray(p, float)
    sse, sst = float(((y - p) ** 2).sum()), float(((y - y.mean()) ** 2).sum())
    return {"n": int(len(y)), "rmse": float(np.sqrt(sse / len(y))), "mae": float(np.abs(y - p).mean()),
            "r2": (1.0 - sse / sst) if sst > 0 else None}      # R2 against the mean of the test targets (0010 item 13)


def score(rows, preds):
    """preds: {'full', 'noweather'} arrays; persistence is added.  Returns per-model metrics with skill."""
    y = m.targets(rows)
    allp = {**preds, "persistence": m.persistence(rows)}
    rp = m.rmse(y, allp["persistence"])
    out = {}
    for name, p in allp.items():
        d = metrics(y, p)
        d["skill_vs_persistence"] = (1.0 - d["rmse"] / rp) if rp > 0 else None
        out[name] = d
    return out, allp


def _wins(a, b):
    return sum(1 for x, y in zip(a, b) if x < y)          # strict; ties do not count


def rule_b(test, fold_full, fold_noweather, fold_persistence):
    """Rule B and 'weather adds information' (protocol; 0010 item 15).  test: metrics from `score`."""
    skill = test["full"]["skill_vs_persistence"]
    beats_pers_test = skill is not None and skill >= 0.10
    wins_pers = _wins(fold_full, fold_persistence)
    promising = bool(beats_pers_test and wins_pers >= 2)
    beats_nw_test = test["full"]["rmse"] < test["noweather"]["rmse"]
    wins_nw = _wins(fold_full, fold_noweather)
    return {"full_skill_vs_persistence_test": skill, "full_at_least_10pct_below_persistence_test": bool(beats_pers_test),
            "folds_full_beats_persistence": wins_pers, "promising": promising,
            "full_beats_noweather_test": bool(beats_nw_test), "folds_full_beats_noweather": wins_nw,
            "weather_adds_information": bool(promising and beats_nw_test and wins_nw >= 2),
            "note": "exploratory pilot screening result (0009 item 7); not a causal or general-forecasting claim"}


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def _dump(path, obj):
    prov.write_text_lf(path, json.dumps(_jsonable(obj), indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------- the evaluation
def evaluate(all_rows, dev_rows, bundles, config, reps=q5.BOOT_REPS):
    """Pure computation (synthetic-testable).  bundles: frozen primary models; config: frozen_config.json content."""
    selected = config["selected"]
    prim, prim_counts = test_pairs(all_rows, native_only=True)
    if not prim:
        raise EvaluationGuardError("no eligible primary test pairs")
    preds = {fs: m.predict(b["preprocessor"], b["estimator"], prim) for fs, b in bundles.items()}
    test, allp = score(prim, preds)
    rb = rule_b(test, selected["full"]["fold_rmse"], selected["noweather"]["fold_rmse"],
                config["persistence_fold_rmse"])
    # hourly sensitivity: frozen hyperparameters, refitted on all eligible hourly training pairs, same cut-off
    hourly, hourly_counts = test_pairs(all_rows, native_only=False)
    train_h = data.eligible(dev_rows, "train_final", native_only=False)
    hp = {}
    for fs in ("full", "noweather"):
        pre, est = m.fit_model(selected[fs]["spec"], fs, train_h)
        hp[fs] = m.predict(pre, est, hourly)
    hscore, _ = score(hourly, hp)
    train_n = data.eligible(dev_rows, "train_final", native_only=True)
    return {
        "primary": {"label": "primary native three-hourly test evaluation (retrospective held-out; late freeze)",
                    "pairs": prim_counts, "metrics": test, "rule_b": rb},
        "sensitivity_hourly": {"label": "SENSITIVITY: all eligible hourly rows; frozen hyperparameters refitted",
                               "pairs": hourly_counts, "n_train": len(train_h), "metrics": hscore},
        "predictions": (prim, allp),
        "error_analysis": q5.error_analysis(prim, allp),
        "block_bootstrap": q5.paired_block_bootstrap(prim, allp, reps=reps),
        "loco": q5.leave_one_city_out(train_n, prim, selected)}


def write_predictions(path, rows, allp):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow([
            "city", "valid_utc", "valid_local", "receipt_utc",
            "target_valid_utc", "target_receipt_utc", "target",
            "pred_full", "pred_noweather", "pred_persistence"
        ])
        for i, r in enumerate(rows):
            target_valid_utc = (r["valid_dt"] + 6 * cut.H).strftime("%Y-%m-%dT%H:%M:%SZ")
            w.writerow([
                r["city"], r["valid_utc"], r["valid_local"], r["receipt_utc"],
                target_valid_utc, r["target_receipt_utc"], r["target_pm25_t6"],
                float(allp["full"][i]),
                float(allp["noweather"][i]),
                float(allp["persistence"][i])
            ])


def write_results(out_dir, res, label, guard, snapshot_sha256):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prim, allp = res["predictions"]
    _dump(out / "test_metrics.json", {"label": label, **res["primary"]})
    _dump(out / "sensitivity_hourly.json", {"label": label, **res["sensitivity_hourly"]})
    _dump(out / "error_analysis.json", {"label": label, **res["error_analysis"]})
    _dump(out / "block_bootstrap.json", {"label": label, **res["block_bootstrap"]})
    _dump(out / "loco.json", {"label": label, **res["loco"]})
    write_predictions(out / "test_predictions.csv", prim, allp)
    names = ["test_metrics.json", "sensitivity_hourly.json", "error_analysis.json", "block_bootstrap.json",
             "loco.json", "test_predictions.csv"]
    _dump(out / "evaluation_manifest.json", {
        "label": label, "tag": guard["tag"], "tag_commit": guard["tag_commit"], "head": guard["head"],
        "snapshot_sha256": snapshot_sha256, "outputs_sha256": {n: prov.sha256_file(out / n) for n in names},
        "environment": prov.environment()})


def run_evaluation(db_path, repo_root=prov.ROOT, post_test=False, now=None, reps=q5.BOOT_REPS):
    repo = Path(repo_root)
    guard = check_guard(repo, db_path, post_test=post_test)
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    snap = prov.sha256_file(db_path)
    if post_test:
        out, label = repo / POST_REL / stamp, "POST-TEST WORK (not the single test evaluation)"
    else:
        out, label = repo / OUT_REL, "single test evaluation"

    fdir = repo / FREEZE_REL
    manifest = guard["manifest"]
    config = json.loads((fdir / freeze.CONFIG_NAME).read_text(encoding="utf-8"))
    bundles = {fs: freeze.load_model(fdir / f"model_{fs}.pkl", manifest["artefacts_sha256"][f"model_{fs}.pkl"])
               for fs in freeze.FEATURE_SETS}

    if not post_test:
        out.mkdir(parents=True, exist_ok=True)
        with open(marker_path(repo), "x", encoding="utf-8", newline="\n") as fh:
            json.dump({"first_test_evaluation_utc": stamp, "tag": guard["tag"], "tag_commit": guard["tag_commit"],
                       "head": guard["head"], "snapshot_sha256": snap}, fh, indent=2)

    all_rows, dev_rows = load_all_rows(db_path)
    res = evaluate(all_rows, dev_rows, bundles, config, reps=reps)
    write_results(out, res, label, guard, snap)
    return {"out": out, "label": label, "primary": res["primary"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Single test evaluation behind the late-freeze guard.")
    ap.add_argument("--db", default="snapshots/assessed_snapshot.db")
    ap.add_argument("--post-test", action="store_true", help="repeat after the first evaluation; output labelled post-test")
    a = ap.parse_args(argv)
    r = run_evaluation(a.db, post_test=a.post_test)
    p = r["primary"]
    print(f"{r['label']}: output in {r['out']}")
    print("pairs (primary native): " + json.dumps(p["pairs"]))
    for name, d in p["metrics"].items():
        print(f"{name:12s} RMSE {d['rmse']:.4f}  MAE {d['mae']:.4f}  skill {d['skill_vs_persistence']:.4f}")
    print("Rule B: " + json.dumps(p["rule_b"]))


if __name__ == "__main__":
    main()
