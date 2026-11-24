"""Tests for analysis/evaluate.py: guard, eligibility, metrics, Rule B and the single evaluation (synthetic only)."""
import csv
import importlib.metadata as md
import json
from datetime import timedelta
import numpy as np
import pytest
from analysis import cutoffs as cut
from analysis import data, evaluate as ev, freeze, provenance as prov
from tests.cp3_synth import CONFIG, SELECTED, all_and_dev, commit_all, full_week_raw, init_repo, run
from tests.test_freeze import make_repo, make_run

ALL, DEV = all_and_dev()
TAG = "late-freeze-20261125-1030"


# ---------------------------------------------------------------- eligibility and counts
def test_maximum_pairs_follow_the_protocol_calendar():
    assert ev.max_pairs(True) == 112 and ev.max_pairs(False) == 336


def test_complete_synthetic_week_gives_the_maximum_pairs():
    nat, c = ev.test_pairs(ALL, True)
    hourly, h = ev.test_pairs(ALL, False)
    assert len(nat) == c["eligible_pairs"] == 112 and len(hourly) == h["eligible_pairs"] == 336
    assert all(ev.TEST_FIRST <= r["valid_dt"] <= ev.TEST_LAST and r["native"] for r in nat)


def test_missing_rows_and_late_lag_rows_are_counted_separately():
    raw = full_week_raw(drop=lambda city, h: city == "Nukus" and h == 150)
    for r in raw:                                              # lag t-3 received AFTER the origin's receipt
        if r["city"] == "Samarkand" and r["observation_hour_utc"] == data.iso(cut.FIRST_ORIGIN_UTC + 140 * cut.H):
            r["collected_at_utc"] = data.iso(cut.FIRST_ORIGIN_UTC + 150 * cut.H)
    rows, _ = all_and_dev(raw)
    hourly, c = ev.test_pairs(rows, False)
    assert c["no_usable_pair"] >= 1 and c["feature_row_received_after_prediction_time"] >= 1
    assert c["eligible_pairs"] == len(hourly) < 336
    assert c["eligible_pairs"] + c["no_usable_pair"] + c["feature_row_received_after_prediction_time"] == c["collected_rows_in_window"]


# ---------------------------------------------------------------- metrics and Rule B
def test_metrics_definitions():
    d = ev.metrics([1, 2, 3], [1, 2, 4])
    assert d["rmse"] == pytest.approx(np.sqrt(1 / 3)) and d["mae"] == pytest.approx(1 / 3)
    assert d["r2"] == pytest.approx(0.5)                      # against the mean of the test targets
    assert ev.metrics([2, 2], [1, 3])["r2"] is None


def _test_metrics(full, nw, pers):
    return {"full": {"rmse": full, "skill_vs_persistence": 1 - full / pers}, "noweather": {"rmse": nw},
            "persistence": {"rmse": pers}}


def test_rule_b_promising_and_weather_adds_information():
    r = ev.rule_b(_test_metrics(8.0, 9.0, 10.0), [3, 3, 3], [4, 4, 4], [5, 5, 5])
    assert r["promising"] and r["weather_adds_information"] and r["folds_full_beats_noweather"] == 3


def test_rule_b_needs_ten_percent_and_two_folds_and_strict_wins():
    assert not ev.rule_b(_test_metrics(9.2, 9.5, 10.0), [3] * 3, [4] * 3, [5] * 3)["promising"]       # only 8% better
    assert not ev.rule_b(_test_metrics(8.0, 9.0, 10.0), [5, 5, 3], [4] * 3, [5] * 3)["promising"]      # tie + 1 win
    assert ev.rule_b(_test_metrics(8.0, 9.0, 10.0), [5, 3, 3], [4] * 3, [5] * 3)["promising"]
    # promising, but weather does not beat the matched no-weather model on the test
    r = ev.rule_b(_test_metrics(8.0, 7.5, 10.0), [3] * 3, [4] * 3, [5] * 3)
    assert r["promising"] and not r["weather_adds_information"]
    # promising, beats no-weather on the test but only in 1 fold
    r = ev.rule_b(_test_metrics(8.0, 9.0, 10.0), [3, 5, 5], [4, 4, 4], [5] * 3)
    assert not r["weather_adds_information"]


# ---------------------------------------------------------------- scoring on identical origins
def test_evaluate_scores_all_models_on_the_same_origins_and_never_trains_on_test():
    bundles = freeze.fit_frozen_models(DEV, SELECTED)
    res = ev.evaluate(ALL, DEV, bundles, CONFIG, reps=199)
    p = res["primary"]
    assert p["pairs"]["eligible_pairs"] == 112
    assert {p["metrics"][k]["n"] for k in ("full", "noweather", "persistence")} == {112}
    assert p["metrics"]["persistence"]["skill_vs_persistence"] == pytest.approx(0.0)
    rows, allp = res["predictions"]
    assert len(rows) == 112 and all(len(v) == 112 for v in allp.values())
    h = res["sensitivity_hourly"]
    assert h["pairs"]["eligible_pairs"] == 336 and "SENSITIVITY" in h["label"]
    train = data.eligible(DEV, "train_final", native_only=False)
    assert h["n_train"] == len(train) and all(r["valid_dt"] < cut.TEST_START_UTC for r in train)
    assert len(res["loco"]["cities"]) == 8 and res["block_bootstrap"]["replications"] == 199
    assert set(res["error_analysis"]["events"]) == {"35", "25", "50"}

# ---------------------------------------------------------------- guard

def frozen_repo(tmp_path, tag=True, annotated=True, attrs=False, crlf_manifest=False):
    repo = make_repo(tmp_path)

    # make_repo() already creates and commits .gitattributes.
    if attrs:
        assert (repo / ".gitattributes").is_file()

    snap = repo / "snapshots" / "assessed_snapshot.db"
    snap.parent.mkdir()
    snap.write_bytes(b"snapshot bytes")
    commit_all(repo, "snapshot")

    base = tmp_path / "sel"
    runp = make_run(base, 1, repo, snap)

    freeze.write_freeze(
        repo / "results" / "freeze",
        freeze.fit_frozen_models(DEV, SELECTED),
        runp,
        {"snapshot_sha256": prov.sha256_file(snap)},
        prov.sha256_file(snap),
        repo,
    )

    if crlf_manifest:
        man = repo / "results" / "freeze" / "freeze_manifest.json"
        man.write_bytes(man.read_bytes().replace(b"\n", b"\r\n"))

    commit_all(repo, "freeze")

    if tag:
        run(
            repo,
            "tag",
            *(["-a", TAG, "-m", "late freeze"] if annotated else [TAG]),
        )

    return repo, snap



def guard(repo, snap, **kw):
    return ev.check_guard(repo, snap, **kw)


def test_guard_passes_for_a_clean_annotated_tag(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    g = guard(repo, snap)
    assert g["tag"] == TAG and g["tag_commit"] == prov.head(repo)


def test_guard_accepts_a_crlf_working_copy_of_the_manifest(tmp_path):
    """Windows regression: working manifest CRLF, committed object LF (what `git show` returns)."""
    repo, snap = frozen_repo(tmp_path, attrs=True, crlf_manifest=True)
    man = repo / "results" / "freeze" / "freeze_manifest.json"
    committed = prov.show_file(prov.tag_commit(TAG, repo), "results/freeze/freeze_manifest.json", repo)
    assert b"\r\n" in man.read_bytes() and b"\r" not in committed        # the byte-compare of the first version failed here
    assert prov.is_clean(repo)
    assert guard(repo, snap)["tag"] == TAG


def test_freeze_text_artefacts_are_written_with_lf_only(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    for p in (repo / "results" / "freeze").glob("*.json"):
        assert b"\r\n" not in p.read_bytes(), p.name


def test_guard_allows_docs_and_results_commits_after_the_tag(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    for rel in ("docs/n.md", "results/x.txt", "README.md", ".gitignore"):
        (repo / rel).parent.mkdir(exist_ok=True)
        (repo / rel).write_text("x")
    commit_all(repo, "docs")
    assert guard(repo, snap)["tag"] == TAG


@pytest.mark.parametrize("rel", ["analysis/selection.py", "monitoring/prepare.py", "tests/new_test.py", "src/x.py"])
def test_guard_rejects_code_commits_after_the_tag(tmp_path, rel):
    repo, snap = frozen_repo(tmp_path)
    p = repo / rel
    p.parent.mkdir(exist_ok=True)
    p.write_text("# changed\n")
    commit_all(repo, "code after tag")
    with pytest.raises(ev.EvaluationGuardError, match="outside results/"):
        guard(repo, snap)


def test_guard_requires_exactly_one_annotated_tag(tmp_path):
    repo, snap = frozen_repo(tmp_path, tag=False)
    with pytest.raises(ev.EvaluationGuardError, match="exactly one"):
        guard(repo, snap)
    run(repo, "tag", TAG)                                      # lightweight
    with pytest.raises(ev.EvaluationGuardError, match="not annotated"):
        guard(repo, snap)
    run(repo, "tag", "-d", TAG)
    run(repo, "tag", "-a", TAG, "-m", "m")
    run(repo, "tag", "-a", "late-freeze-20261126-0900", "-m", "m")
    with pytest.raises(ev.EvaluationGuardError, match="exactly one"):
        guard(repo, snap)


def test_guard_rejects_badly_named_tag(tmp_path):
    repo, snap = frozen_repo(tmp_path, tag=False)
    run(repo, "tag", "-a", "late-freeze-final", "-m", "m")
    with pytest.raises(ev.EvaluationGuardError, match="not named"):
        guard(repo, snap)


def test_guard_rejects_dirty_tree_tampered_artefact_manifest_snapshot_and_code(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    (repo / "scratch.txt").write_text("x")
    with pytest.raises(ev.EvaluationGuardError, match="not clean"):
        guard(repo, snap)
    (repo / "scratch.txt").unlink()
    model = repo / "results" / "freeze" / "model_full.pkl"
    good = model.read_bytes()
    model.write_bytes(good + b"x")
    commit_all(repo, "tamper artefact")                        # committed under results/ (allowed path) but hash differs
    with pytest.raises(ev.EvaluationGuardError, match="changed"):
        guard(repo, snap)
    model.write_bytes(good)
    commit_all(repo, "restore")
    man = repo / "results" / "freeze" / "freeze_manifest.json"
    original = man.read_text()
    man.write_text(original.replace("late freeze", "late  freeze", 1))
    commit_all(repo, "edit manifest")
    with pytest.raises(ev.EvaluationGuardError, match="differs from the one in the tag commit"):
        guard(repo, snap)
    man.write_text(original)
    commit_all(repo, "restore manifest")
    snap.write_bytes(b"different snapshot")
    commit_all(repo, "snapshot changed")
    with pytest.raises(ev.EvaluationGuardError, match="snapshot"):
        guard(repo, snap)


def test_guard_checks_environment_pins(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    assert guard(repo, snap, check_env=True)["tag"] == TAG
    (repo / "requirements.txt").write_text(f"numpy==0.0.1\nscikit-learn=={md.version('scikit-learn')}\n")
    commit_all(repo, "bad pin")
    with pytest.raises(ev.EvaluationGuardError, match="outside results/|pins"):
        guard(repo, snap)


def test_marker_rules(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    with pytest.raises(ev.EvaluationGuardError, match="needs an existing first evaluation"):
        guard(repo, snap, post_test=True)
    with pytest.raises(ev.EvaluationGuardError, match="has not been run"):
        ev.require_marker(repo)
    mk = ev.marker_path(repo)
    mk.parent.mkdir(parents=True)
    mk.write_text("{}")
    with pytest.raises(ev.EvaluationGuardError, match="already run"):
        guard(repo, snap)
    ev.require_marker(repo)                                    # post-test modules may now run


# ---------------------------------------------------------------- the single evaluation end to end
def test_single_evaluation_then_post_test_only(tmp_path, monkeypatch):
    repo, snap = frozen_repo(tmp_path)
    monkeypatch.setattr(ev, "load_all_rows", lambda db: (ALL, DEV))
    now = cut.FIRST_ORIGIN_UTC + timedelta(days=30)
    r = ev.run_evaluation(snap, repo, reps=199, now=now)
    out = repo / "results" / "evaluation"
    assert r["out"] == out and ev.marker_path(repo).is_file()
    for n in ("test_metrics.json", "sensitivity_hourly.json", "error_analysis.json", "block_bootstrap.json",
              "loco.json", "test_predictions.csv", "evaluation_manifest.json"):
        assert (out / n).is_file(), n

    with (out / "test_predictions.csv").open(newline="", encoding="utf-8") as fh:
        predictions = list(csv.DictReader(fh))

    expected_columns = {
        "city", "valid_utc", "valid_local", "receipt_utc",
        "target_valid_utc", "target_receipt_utc", "target",
        "pred_full", "pred_noweather", "pred_persistence"
    }
    assert set(predictions[0]) == expected_columns
    assert len(predictions) == 112

    for row in predictions:
        origin = data.parse(row["valid_utc"])
        target_valid = data.parse(row["target_valid_utc"])
        assert target_valid - origin == 6 * cut.H
        assert row["receipt_utc"]
        assert row["target_receipt_utc"]

    man = json.loads((out / "evaluation_manifest.json").read_text())
    assert man["tag"] == TAG and man["label"] == "single test evaluation"
    assert all(prov.sha256_file(out / n) == h for n, h in man["outputs_sha256"].items())
    tm = json.loads((out / "test_metrics.json").read_text())
    assert tm["pairs"]["eligible_pairs"] == 112 and "rule_b" in tm
    with pytest.raises(ev.EvaluationGuardError, match="already run"):               # marker is checked first
        ev.run_evaluation(snap, repo, reps=199)
    with pytest.raises(ev.EvaluationGuardError, match="not clean"):                 # outputs not committed yet
        ev.run_evaluation(snap, repo, post_test=True, reps=199)
    commit_all(repo, "first evaluation outputs")
    with pytest.raises(ev.EvaluationGuardError, match="already run"):               # a second run needs --post-test
        ev.run_evaluation(snap, repo, reps=199)
    p = ev.run_evaluation(snap, repo, post_test=True, reps=199, now=now + timedelta(hours=1))
    assert "POST-TEST" in p["label"] and p["out"].parent.name == "post_test"
    assert json.loads((p["out"] / "evaluation_manifest.json").read_text())["label"].startswith("POST-TEST")
    assert (out / "test_metrics.json").read_text() == (repo / "results/evaluation/test_metrics.json").read_text()


def test_failed_guard_loads_nothing_and_writes_no_marker(tmp_path, monkeypatch):
    repo, snap = frozen_repo(tmp_path, tag=False)
    monkeypatch.setattr(ev, "load_all_rows", lambda db: pytest.fail("test data must not be loaded"))
    with pytest.raises(ev.EvaluationGuardError):
        ev.run_evaluation(snap, repo, reps=99)
    assert not ev.marker_path(repo).exists()

def test_guard_rejects_missing_frozen_file_record(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    man = repo / "results" / "freeze" / freeze.MANIFEST_NAME
    manifest = json.loads(man.read_text(encoding="utf-8"))
    manifest["files"].pop("analysis/data.py")
    man.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    commit_all(repo, "remove frozen file record")
    run(repo, "tag", "-d", TAG)
    run(repo, "tag", "-a", TAG, "-m", "updated test tag")

    with pytest.raises(ev.EvaluationGuardError, match="missing or invalid provenance record"):
        guard(repo, snap)

def test_guard_rejects_missing_decision_file_record(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    man = repo / "results" / "freeze" / freeze.MANIFEST_NAME
    manifest = json.loads(man.read_text(encoding="utf-8"))

    decision = "docs/decisions/0011-snapshot-integrity-and-reproducible-freeze.md"
    assert decision in manifest["files"]

    manifest["files"].pop(decision)
    man.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    commit_all(repo, "remove decision file provenance record")

    run(repo, "tag", "-d", TAG)
    run(repo, "tag", "-a", TAG, "-m", "updated test tag")

    with pytest.raises(
        ev.EvaluationGuardError,
        match="missing or invalid provenance record",
    ):
        guard(repo, snap)

def test_guard_rejects_missing_optional_decision_file_record(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    man = repo / "results" / "freeze" / freeze.MANIFEST_NAME
    manifest = json.loads(man.read_text(encoding="utf-8"))

    decision = "docs/decisions/0012-freeze-evaluation-and-post-test-implementation.md"
    assert decision in manifest["files"]

    manifest["files"].pop(decision)
    man.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    commit_all(repo, "remove optional decision file provenance record")

    run(repo, "tag", "-d", TAG)
    run(repo, "tag", "-a", TAG, "-m", "updated test tag")

    with pytest.raises(
        ev.EvaluationGuardError,
        match="missing or invalid provenance record",
    ):
        guard(repo, snap)

def test_guard_rejects_missing_files_dictionary(tmp_path):
    repo, snap = frozen_repo(tmp_path)
    man = repo / "results" / "freeze" / freeze.MANIFEST_NAME
    manifest = json.loads(man.read_text(encoding="utf-8"))
    manifest.pop("files")
    man.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    commit_all(repo, "remove files dictionary")
    run(repo, "tag", "-d", TAG)
    run(repo, "tag", "-a", TAG, "-m", "updated test tag")

    with pytest.raises(ev.EvaluationGuardError, match="no valid 'files' provenance dictionary"):
        guard(repo, snap)
