"""Tests for analysis/freeze.py (final fit, artefacts, freeze manifest).  Synthetic data and temporary repos only."""
import importlib.metadata as md
import json
import re
from pathlib import Path

import pytest

from analysis import data, freeze, provenance as prov
from tests.cp3_synth import SELECTED, all_and_dev, commit_all, init_repo

ALL, DEV = all_and_dev()


def make_repo(tmp_path):
    repo = init_repo(tmp_path / "repo")
    for rel in (*prov.REQUIRED_CODE_FILES, "pyproject.toml", "pytest.ini"):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {rel}\n")
    (repo / "requirements.txt").write_text(
        f"numpy=={md.version('numpy')}\nscikit-learn=={md.version('scikit-learn')}\n")
    commit_all(repo, "base")
    return repo


def make_run(base, n, repo, snapshot, complete=True, selected=SELECTED):
    run = Path(base) / f"run-{n:03d}"
    run.mkdir(parents=True)
    (run / "cv_table.csv").write_text("feature_set,candidate\nfull,ridge_alpha10\n")
    (run / "selected_configurations.json").write_text(json.dumps(
        {"criterion": "c", "fold_counts": {}, "persistence_fold_rmse": [5.0, 5.0, 5.0], "selected": selected}))
    if complete:
        (run / "selection_manifest.json").write_text(json.dumps({
            "snapshot_sha256": prov.sha256_file(snapshot),
            "outputs_sha256": {n_: prov.sha256_file(run / n_) for n_ in ("cv_table.csv", "selected_configurations.json")},
            "files": prov.provenance_files(repo)}))
    return run


@pytest.fixture
def world(tmp_path):
    repo = make_repo(tmp_path)
    snap = tmp_path / "snap.db"
    snap.write_bytes(b"snapshot bytes")
    return repo, snap, tmp_path / "selection"


# ---------------------------------------------------------------- run directories (0011 section 5)
def test_latest_run_is_by_number_not_by_gap_or_score(world):
    repo, snap, base = world
    make_run(base, 1, repo, snap)
    r3 = make_run(base, 3, repo, snap)
    assert freeze.latest_complete_run(base) == r3


def test_incomplete_latest_run_blocks_the_freeze_and_never_falls_back(world):
    repo, snap, base = world
    make_run(base, 1, repo, snap)
    make_run(base, 2, repo, snap, complete=False)
    with pytest.raises(freeze.FreezeError, match="incomplete"):
        freeze.latest_complete_run(base)


def test_no_run_directory_is_an_error(tmp_path):
    with pytest.raises(freeze.FreezeError, match="no selection run"):
        freeze.latest_complete_run(tmp_path)


# ---------------------------------------------------------------- selection run checks (0011 sections 2 and 6)
def test_matching_run_passes(world):
    repo, snap, base = world
    run = make_run(base, 1, repo, snap)
    assert freeze.check_selection_run(run, repo, snap)["snapshot_sha256"] == prov.sha256_file(snap)


@pytest.mark.parametrize("rel", ["analysis/selection.py", "analysis/data.py", "monitoring/prepare.py"])
def test_code_changed_after_selection_refuses_the_freeze(world, rel):
    repo, snap, base = world
    run = make_run(base, 1, repo, snap)
    (repo / rel).write_text("# changed\n")
    commit_all(repo, "change after selection")                                 # committed blob is the reference
    with pytest.raises(freeze.FreezeError, match="changed after the selection run"):
        freeze.check_selection_run(run, repo, snap)


def test_snapshot_or_outputs_changed_are_refused(world):
    repo, snap, base = world
    run = make_run(base, 1, repo, snap)
    (run / "cv_table.csv").write_text("tampered")
    with pytest.raises(freeze.FreezeError, match="cv_table.csv"):
        freeze.check_selection_run(run, repo, snap)
    run2 = make_run(base, 2, repo, snap)
    snap.write_bytes(b"other bytes")
    with pytest.raises(freeze.FreezeError, match="snapshot"):
        freeze.check_selection_run(run2, repo, snap)


def test_manifest_without_files_record_or_a_required_file_is_refused(world):
    repo, snap, base = world
    run = make_run(base, 1, repo, snap)
    man = json.loads((run / "selection_manifest.json").read_text())
    del man["files"]["monitoring/coverage.py"]
    (run / "selection_manifest.json").write_text(json.dumps(man))
    with pytest.raises(freeze.FreezeError, match="does not record"):
        freeze.check_selection_run(run, repo, snap)
    del man["files"]
    (run / "selection_manifest.json").write_text(json.dumps(man))
    with pytest.raises(freeze.FreezeError, match="'files'"):
        freeze.check_selection_run(run, repo, snap)


# ---------------------------------------------------------------- fitting and artefacts
def test_final_fit_uses_all_eligible_native_train_final_pairs():
    b = freeze.fit_frozen_models(DEV, SELECTED)
    n = len(data.eligible(DEV, "train_final", native_only=True))
    assert n > 0 and b["full"]["n_train"] == b["noweather"]["n_train"] == n
    assert b["full"]["spec"] == SELECTED["full"]["spec"] and b["noweather"]["spec"] == SELECTED["noweather"]["spec"]
    assert b["full"]["train_fingerprint"] == b["noweather"]["train_fingerprint"] == \
        freeze.training_fingerprint(data.eligible(DEV, "train_final", native_only=True))


def test_final_fit_is_deterministic():
    a, b = freeze.fit_frozen_models(DEV, SELECTED), freeze.fit_frozen_models(DEV, SELECTED)
    assert a["full"]["preprocessor"].state() == b["full"]["preprocessor"].state()
    assert list(a["full"]["estimator"].coef_) == list(b["full"]["estimator"].coef_)
    rows = data.eligible(DEV, "cv3_valid")
    for fs in ("full", "noweather"):
        pa = a[fs]["estimator"].predict(a[fs]["preprocessor"].transform(rows))
        pb = b[fs]["estimator"].predict(b[fs]["preprocessor"].transform(rows))
        assert list(pa) == list(pb)


def test_write_freeze_records_hashes_and_never_overwrites(world, tmp_path):
    repo, snap, base = world
    run = make_run(base, 1, repo, snap)
    bundles = freeze.fit_frozen_models(DEV, SELECTED)
    out = tmp_path / "freeze"
    mpath = freeze.write_freeze(out, bundles, run, {"snapshot_sha256": prov.sha256_file(snap)}, prov.sha256_file(snap), repo)
    man = json.loads(mpath.read_text())
    assert man["label"] == "late freeze" and man["selection_run"] == "run-001"
    assert man["parent_commit"] == prov.head(repo) and man["snapshot_sha256"] == prov.sha256_file(snap)
    assert set(man["artefacts_sha256"]) == {"model_full.pkl", "model_full.json", "model_noweather.pkl",
                                            "model_noweather.json", "frozen_config.json"}
    assert set(man["selection_outputs_sha256"]) == set(freeze.RUN_FILES)
    assert "analysis/selection.py" in man["files"] and man["environment"]["numpy"] == md.version("numpy")
    freeze.verify_artefacts(out, man)
    cfg = json.loads((out / "frozen_config.json").read_text())
    assert cfg["selected"]["full"]["fold_rmse"] == [3.0, 3.0, 3.0] and cfg["persistence_fold_rmse"] == [5.0, 5.0, 5.0]
    with pytest.raises(freeze.FreezeError, match="never overwritten"):
        freeze.write_freeze(out, bundles, run, {}, "x", repo)


def test_tampered_artefact_is_detected_and_not_unpickled(world, tmp_path):
    repo, snap, base = world
    run = make_run(base, 1, repo, snap)
    out = tmp_path / "freeze"
    mpath = freeze.write_freeze(out, freeze.fit_frozen_models(DEV, SELECTED), run, {}, "x", repo)
    man = json.loads(mpath.read_text())
    good = freeze.load_model(out / "model_full.pkl", man["artefacts_sha256"]["model_full.pkl"])
    assert good["spec"] == SELECTED["full"]["spec"] and hasattr(good["estimator"], "predict")
    (out / "model_full.pkl").write_bytes((out / "model_full.pkl").read_bytes() + b"x")
    with pytest.raises(freeze.FreezeError, match="does not match"):
        freeze.load_model(out / "model_full.pkl", man["artefacts_sha256"]["model_full.pkl"])
    with pytest.raises(freeze.FreezeError, match="changed"):
        freeze.verify_artefacts(out, man)
    (out / "frozen_config.json").unlink()
    with pytest.raises(freeze.FreezeError, match="missing"):
        freeze.verify_artefacts(out, man)


def test_build_freeze_refuses_dirty_tree(world, tmp_path):
    repo, snap, base = world
    make_run(base, 1, repo, snap)
    (repo / "untracked.txt").write_text("x")
    with pytest.raises(freeze.FreezeError, match="not clean"):
        freeze.build_freeze(snap, base, tmp_path / "f", repo_root=repo)


def test_freeze_and_selection_code_cannot_reach_the_test_period():
    root = Path(prov.ROOT)
    for name in ("analysis/freeze.py", "analysis/selection.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "derive_rows" not in src
        assert not re.search(r"^\s*(from|import) .*\bevaluate\b", src, re.M)
