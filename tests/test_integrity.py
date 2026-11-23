"""Acceptance tests of decision 0011 (sections 1 to 5).  Synthetic data and temporary Git repositories only."""
import importlib.metadata as md
import json
import random
from pathlib import Path

import pytest

from analysis import data, freeze, integrity as integ, provenance as prov, selection as sel
from tests.cp3_synth import commit_all, init_repo, run
from tests.test_selection import synthetic_raw

SNAP_BYTES = b"synthetic snapshot bytes"


def make_project(tmp_path, with_origin=True, eol=b"\n"):
    """A temporary repo holding every file integrity.py must record, plus a snapshot and its MANIFEST.json."""
    repo = init_repo(tmp_path / "repo")
    for rel in (*(f"analysis/{n}.py" for n in ("cutoffs", "data", "modelling", "selection", "x")),
                "monitoring/coverage.py", "monitoring/prepare.py", "pyproject.toml", "pytest.ini", *prov.DECISION_FILES):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(f"# {rel}\n# second line\n".encode().replace(b"\n", eol))
    (repo / "requirements.txt").write_text(
        f"numpy=={md.version('numpy')}\nscikit-learn=={md.version('scikit-learn')}\n")
    (repo / ".gitattributes").write_text("* text=auto eol=lf\n*.db binary\n")
    (repo / ".gitignore").write_text("ignored/\n")
    snap = repo / "snapshots" / "assessed_snapshot.db"
    snap.parent.mkdir()
    snap.write_bytes(SNAP_BYTES)
    write_manifest(repo, prov.sha256_bytes(SNAP_BYTES))
    commit_all(repo, "base")
    if with_origin:
        origin = tmp_path / "origin.git"
        run(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        run(repo, "remote", "add", "origin", str(origin))
        run(repo, "push", "-q", "origin", "main")
    return repo


def write_manifest(repo, sha):
    (repo / "snapshots" / "MANIFEST.json").write_text(json.dumps({"created_utc": "2026-11-11T11:08:40Z",
                                                                 "files_sha256": {"assessed_snapshot.db": sha}}))


def pre(repo, base=None, **kw):
    kw.setdefault("expected", prov.sha256_bytes(SNAP_BYTES))
    return integ.preflight(repo, repo / "snapshots/assessed_snapshot.db", repo / "snapshots/MANIFEST.json",
                           base or repo / "results" / "selection", **kw)


# ---------------------------------------------------------------- section 1: snapshot
def test_the_real_constant_matches_the_committed_snapshot_when_present():
    db, mf = prov.ROOT / integ.SNAPSHOT_REL, prov.ROOT / integ.MANIFEST_REL
    if not (db.is_file() and mf.is_file()):
        pytest.skip("assessed snapshot not present")
    info = integ.check_snapshot(db, mf)                      # uses the constant in the code
    assert info["snapshot_sha256"] == integ.EXPECTED_SNAPSHOT_SHA256 == info["manifest_entry_sha256"]


def test_matching_snapshot_passes_and_records_hashes(tmp_path):
    repo = make_project(tmp_path)
    info = integ.check_snapshot(repo / integ.SNAPSHOT_REL, repo / integ.MANIFEST_REL, prov.sha256_bytes(SNAP_BYTES))
    assert info["snapshot_sha256"] == prov.sha256_bytes(SNAP_BYTES)
    assert info["snapshot_manifest_sha256"] == prov.sha256_file(repo / integ.MANIFEST_REL)


def test_snapshot_differing_from_manifest_or_constant_stops(tmp_path):
    repo = make_project(tmp_path)
    db, mf = repo / integ.SNAPSHOT_REL, repo / integ.MANIFEST_REL
    good = prov.sha256_bytes(SNAP_BYTES)
    db.write_bytes(SNAP_BYTES + b"!")                         # bytes changed, manifest and constant unchanged
    with pytest.raises(integ.IntegrityError, match="integrity check failed"):
        integ.check_snapshot(db, mf, good)
    db.write_bytes(SNAP_BYTES)
    write_manifest(repo, "0" * 64)                            # manifest differs from file and constant
    with pytest.raises(integ.IntegrityError, match="integrity check failed"):
        integ.check_snapshot(db, mf, good)


def test_manifest_edited_together_with_the_snapshot_still_stops(tmp_path):
    repo = make_project(tmp_path)
    db, mf = repo / integ.SNAPSHOT_REL, repo / integ.MANIFEST_REL
    db.write_bytes(b"tampered snapshot")
    write_manifest(repo, prov.sha256_bytes(b"tampered snapshot"))        # file == manifest, but not the constant
    with pytest.raises(integ.IntegrityError, match="fixed constant"):
        integ.check_snapshot(db, mf, prov.sha256_bytes(SNAP_BYTES))


def test_missing_snapshot_manifest_or_entry_stops(tmp_path):
    repo = make_project(tmp_path)
    db, mf = repo / integ.SNAPSHOT_REL, repo / integ.MANIFEST_REL
    good = prov.sha256_bytes(SNAP_BYTES)
    with pytest.raises(integ.IntegrityError, match="database not found"):
        integ.check_snapshot(tmp_path / "nope.db", mf, good)
    with pytest.raises(integ.IntegrityError, match="manifest not found"):
        integ.check_snapshot(db, tmp_path / "nope.json", good)
    mf.write_text(json.dumps({"files_sha256": {}}))
    with pytest.raises(integ.IntegrityError, match="no files_sha256 entry"):
        integ.check_snapshot(db, mf, good)
    mf.write_text("not json")
    with pytest.raises(integ.IntegrityError, match="not valid JSON"):
        integ.check_snapshot(db, mf, good)


def test_snapshot_must_stay_byte_identical(tmp_path):
    repo = make_project(tmp_path)
    db = repo / integ.SNAPSHOT_REL
    integ.verify_unchanged(db, prov.sha256_bytes(SNAP_BYTES))
    with pytest.raises(integ.IntegrityError, match="changed during the run"):
        integ.verify_unchanged(db, "0" * 64)


# ---------------------------------------------------------------- section 3: git
def test_modified_tracked_file_and_untracked_file_each_stop_but_ignored_does_not(tmp_path):
    repo = make_project(tmp_path)
    (repo / "ignored").mkdir()
    (repo / "ignored" / "f.txt").write_text("x")
    assert pre(repo, create=False)["git"]["working_tree_clean"]
    (repo / "analysis" / "x.py").write_text("# changed\n")
    with pytest.raises(integ.IntegrityError, match="not clean"):
        pre(repo, create=False)
    run(repo, "checkout", "--", "analysis/x.py")
    (repo / "untracked.txt").write_text("x")
    with pytest.raises(integ.IntegrityError, match="not clean"):
        pre(repo, create=False)


def test_remote_containment_passes_stops_or_warns(tmp_path):
    repo = make_project(tmp_path)
    assert pre(repo, create=False)["git"]["remote_check"] == "passed"
    (repo / "docs" / "n.md").write_text("n")
    commit_all(repo, "unpushed")
    with pytest.raises(integ.IntegrityError, match="not contained in origin/main"):
        pre(repo, create=False)
    run(repo, "push", "-q", "origin", "main")
    assert pre(repo, create=False)["git"]["remote_check"] == "passed"


@pytest.mark.parametrize("break_remote", ["none", "bad_path"])
def test_unreachable_or_missing_remote_is_a_warning_never_a_pass(tmp_path, break_remote):
    repo = make_project(tmp_path, with_origin=False)
    if break_remote == "bad_path":
        run(repo, "remote", "add", "origin", str(tmp_path / "does-not-exist.git"))
    ctx = pre(repo, create=False)
    assert ctx["git"]["remote_check"] == "not performed" and "NOT performed" in ctx["git"]["warning"]


def test_git_state_and_start_times_are_recorded(tmp_path):
    from datetime import datetime, timezone
    repo = make_project(tmp_path)
    ctx = pre(repo, create=False, now=datetime(2026, 11, 25, 5, 30, 0, tzinfo=timezone.utc))
    g = ctx["git"]
    assert g["head"] == prov.head(repo) and g["tree"] == prov.tree_hash(repo) and g["branch"] == "main"
    assert ctx["started_utc"] == "2026-11-25T05:30:00Z" and ctx["started_asia_tashkent"] == "2026-11-25 10:30:00"


# ---------------------------------------------------------------- section 2: files and environment
def test_file_records_cover_every_required_file_with_both_hashes(tmp_path):
    repo = make_project(tmp_path)
    recs = pre(repo, create=False)["files"]
    expected = {"analysis/cutoffs.py", "analysis/data.py", "analysis/modelling.py", "analysis/selection.py", "analysis/x.py",
                "monitoring/coverage.py", "monitoring/prepare.py", "requirements.txt", "pyproject.toml", "pytest.ini",
                ".gitattributes", "snapshots/MANIFEST.json", *prov.DECISION_FILES}
    assert set(recs) == expected
    for rel, r in recs.items():
        assert r["sha256"] == prov.sha256_file(repo / rel) and r["git_blob"] == run(repo, "hash-object", rel)


def test_missing_or_uncommitted_required_file_stops(tmp_path):
    repo = make_project(tmp_path)
    (repo / "pytest.ini").unlink()
    run(repo, "add", "-A")
    run(repo, "commit", "-q", "-m", "remove")
    run(repo, "push", "-q", "origin", "main")
    with pytest.raises(integ.IntegrityError, match="required file missing"):
        pre(repo, create=False)


def test_numpy_or_sklearn_differing_from_the_pin_stops(tmp_path):
    repo = make_project(tmp_path)
    (repo / "requirements.txt").write_text(f"numpy==0.0.1\nscikit-learn=={md.version('scikit-learn')}\n")
    commit_all(repo, "bad pin")
    run(repo, "push", "-q", "origin", "main")
    with pytest.raises(integ.IntegrityError, match="numpy"):
        pre(repo, create=False)


# ---------------------------------------------------------------- section 5: run directories
def test_first_run_is_run_001_and_nothing_else_is_written_before_the_manifest(tmp_path):
    repo = make_project(tmp_path)
    ctx = pre(repo)
    assert ctx["run_dir"].name == "run-001" and ctx["plan"]["previous_run"] is None and not ctx["plan"]["rerun"]
    assert list(ctx["run_dir"].iterdir()) == []


def test_second_run_needs_rerun_and_reason_then_writes_run_002_and_leaves_run_001_untouched(tmp_path):
    repo = make_project(tmp_path)
    base = repo / "results" / "selection"
    c1 = pre(repo, base)
    for n in integ.OUTPUT_FILES:
        (c1["run_dir"] / n).write_text(f"output {n}")
    integ.finish_run(c1, repo / integ.SNAPSHOT_REL)
    before = {p.name: p.read_bytes() for p in c1["run_dir"].iterdir()}
    commit_all(repo, "run-001 outputs")
    run(repo, "push", "-q", "origin", "main")
    for kw in ({}, {"rerun": True}, {"reason": "why"}, {"rerun": True, "reason": "   "}):
        with pytest.raises(integ.IntegrityError, match="--rerun and a non-empty --reason"):
            pre(repo, base, **kw)
    c2 = pre(repo, base, rerun=True, reason="fold 2 had a data fix")
    assert c2["run_dir"].name == "run-002" and c2["plan"]["previous_run"] == "run-001"
    assert c2["plan"]["rerun_reason"] == "fold 2 had a data fix"
    assert {p.name: p.read_bytes() for p in c1["run_dir"].iterdir()} == before          # run-001 byte-identical


def test_run_directory_without_manifest_counts_as_used_and_is_not_a_previous_run(tmp_path):
    repo = make_project(tmp_path)
    base = repo / "results" / "selection"
    (base / "run-001").mkdir(parents=True)
    (base / "run-001" / integ.MANIFEST_NAME).write_text("{}")
    (base / "run-002").mkdir()                                # incomplete: no manifest
    commit_all(repo, "runs")
    run(repo, "push", "-q", "origin", "main")
    with pytest.raises(integ.IntegrityError, match="--rerun"):
        pre(repo, base)
    ctx = pre(repo, base, rerun=True, reason="resolving incomplete run-002")
    assert ctx["run_dir"].name == "run-003" and ctx["plan"]["previous_run"] == "run-001"


def test_gaps_are_not_reused_and_with_no_completed_run_previous_is_null(tmp_path):
    base = tmp_path / "sel"
    for n in (1, 3):
        (base / f"run-{n:03d}").mkdir(parents=True)
    plan = integ.plan_run(base, True, "reason")
    assert plan["run_dir"].name == "run-004" and plan["previous_run"] is None
    (base / "run-010").mkdir()
    (base / "not-a-run").mkdir()
    (base / "run-x").mkdir()
    assert integ.plan_run(base, True, "r")["run_dir"].name == "run-011"


def test_an_existing_run_directory_is_never_reused(tmp_path):
    plan = {"run_dir": tmp_path / "sel" / "run-001"}
    integ.create_run_dir(plan)
    with pytest.raises(integ.IntegrityError, match="never reused"):
        integ.create_run_dir(plan)


def test_failed_preflight_creates_no_run_directory(tmp_path):
    repo = make_project(tmp_path)
    (repo / "untracked.txt").write_text("x")
    with pytest.raises(integ.IntegrityError):
        pre(repo)
    assert not (repo / "results").exists()


def test_manifest_is_written_last_with_all_required_fields_and_never_overwritten(tmp_path):
    repo = make_project(tmp_path)
    ctx = pre(repo)
    with pytest.raises(integ.IntegrityError, match="outputs missing"):
        integ.finish_run(ctx, repo / integ.SNAPSHOT_REL)
    assert not (ctx["run_dir"] / integ.MANIFEST_NAME).exists()
    for n in integ.OUTPUT_FILES:
        (ctx["run_dir"] / n).write_text(n)
    path = integ.finish_run(ctx, repo / integ.SNAPSHOT_REL)
    man = json.loads(path.read_text())
    assert man["run"] == "run-001" and man["previous_run"] is None and man["rerun_reason"] is None
    assert man["snapshot_sha256"] == prov.sha256_bytes(SNAP_BYTES) == man["snapshot"]["manifest_entry_sha256"]
    assert man["snapshot"]["snapshot_manifest_sha256"] == prov.sha256_file(repo / integ.MANIFEST_REL)
    assert man["git"]["head"] == prov.head(repo) and man["git"]["remote_check"] == "passed"
    assert man["environment"]["numpy"] == md.version("numpy") and "python" in man["environment"]
    assert {"pandas", "matplotlib", "pytest", "setuptools", "scikit-learn"} <= set(man["environment"])
    assert man["outputs_sha256"] == {n: prov.sha256_file(ctx["run_dir"] / n) for n in integ.OUTPUT_FILES}
    assert man["started_utc"].endswith("Z") and "started_asia_tashkent" in man
    with pytest.raises(FileExistsError):
        integ.finish_run(ctx, repo / integ.SNAPSHOT_REL)


def test_finish_run_stops_if_the_snapshot_changed_during_the_run(tmp_path):
    repo = make_project(tmp_path)
    ctx = pre(repo)
    for n in integ.OUTPUT_FILES:
        (ctx["run_dir"] / n).write_text(n)
    (repo / integ.SNAPSHOT_REL).write_bytes(b"modified during run")
    with pytest.raises(integ.IntegrityError, match="changed during the run"):
        integ.finish_run(ctx, repo / integ.SNAPSHOT_REL)
    assert not (ctx["run_dir"] / integ.MANIFEST_NAME).exists()


# ---------------------------------------------------------------- dry-run CLI
def test_dry_run_cli_reports_and_creates_nothing(tmp_path, capsys, monkeypatch):
    repo = make_project(tmp_path)
    monkeypatch.setattr(integ, "EXPECTED_SNAPSHOT_SHA256", prov.sha256_bytes(SNAP_BYTES))
    rc = integ.main(["--repo", str(repo), "--db", str(repo / integ.SNAPSHOT_REL),
                     "--manifest", str(repo / integ.MANIFEST_REL), "--out", str(repo / "results" / "selection")])
    out = capsys.readouterr().out
    assert rc == 0 and "snapshot sha256 OK" in out and "next run directory would be run-001" in out
    assert not (repo / "results").exists()
    (repo / "untracked.txt").write_text("x")
    assert integ.main(["--repo", str(repo), "--db", str(repo / integ.SNAPSHOT_REL),
                       "--manifest", str(repo / integ.MANIFEST_REL), "--out", str(repo / "r")]) == 1
    assert "FAILED" in capsys.readouterr().out


# ---------------------------------------------------------------- selection.main end to end, then the freeze check
def test_selection_main_runs_end_to_end_and_the_freeze_accepts_its_manifest(tmp_path, monkeypatch):
    repo = make_project(tmp_path)
    db = repo / integ.SNAPSHOT_REL
    monkeypatch.setattr(integ, "EXPECTED_SNAPSHOT_SHA256", prov.sha256_bytes(SNAP_BYTES))
    dev_rows = data.build(synthetic_raw(hours=118))
    monkeypatch.setattr(sel.data, "load_development", lambda conn: dev_rows)
    base = repo / "results" / "selection"
    args = ["--repo", str(repo), "--db", str(db), "--manifest", str(repo / integ.MANIFEST_REL), "--out", str(base)]
    snap_before = db.read_bytes()
    sel.main(args)
    assert db.read_bytes() == snap_before                                    # snapshot byte-identical
    run1 = base / "run-001"
    assert {p.name for p in run1.iterdir()} == {"cv_table.csv", "selected_configurations.json", "selection_manifest.json"}
    for p in run1.iterdir():
        assert b"\r\n" not in p.read_bytes(), p.name                          # LF only: hashes are portable
    run_manifest = freeze.check_selection_run(run1, repo, db)                # the freeze accepts exactly this manifest
    assert run_manifest["snapshot_sha256"] == prov.sha256_file(db)
    assert freeze.latest_complete_run(base) == run1
    with pytest.raises(integ.IntegrityError, match="--rerun"):               # second run without --rerun --reason
        sel.main(args)
    with pytest.raises(integ.IntegrityError, match="not clean"):             # outputs of run-001 not committed yet
        sel.main(args + ["--rerun", "--reason", "test"])
    commit_all(repo, "run-001")
    run(repo, "push", "-q", "origin", "main")
    keep = {p.name: p.read_bytes() for p in run1.iterdir()}
    sel.main(args + ["--rerun", "--reason", "second look at fold sizes"])
    assert {p.name: p.read_bytes() for p in run1.iterdir()} == keep          # run-001 untouched
    m2 = json.loads((base / "run-002" / "selection_manifest.json").read_text())
    assert m2["previous_run"] == "run-001" and m2["rerun_reason"] == "second look at fold sizes" and m2["rerun"]
    assert freeze.latest_complete_run(base).name == "run-002"                # freeze uses the latest run, not the best CV


# ---------------------------------------------------------------- Windows: CRLF working copies (regression)
def test_crlf_working_files_are_accepted_and_the_committed_blob_is_the_reference(tmp_path):
    repo = make_project(tmp_path / "w", eol=b"\r\n")
    run(repo, "config", "core.autocrlf", "true")
    ctx = pre(repo, create=False)
    recs = ctx["files"]
    for rel, r in recs.items():
        assert r["git_blob"] == run(repo, "rev-parse", f"HEAD:{rel}")           # committed object
        assert r["sha256"] == prov.sha256_file(repo / rel)                      # working bytes (CRLF), supporting only
    assert recs["analysis/x.py"]["working_bytes_match_blob"] is False
    assert (repo / "analysis/x.py").read_bytes().count(b"\r\n") == 2


def test_crlf_repo_runs_selection_manifest_through_to_the_freeze_check(tmp_path):
    repo = make_project(tmp_path, eol=b"\r\n")
    ctx = pre(repo)
    for n in integ.OUTPUT_FILES:
        (ctx["run_dir"] / n).write_text(n)
    (ctx["run_dir"] / "selected_configurations.json").write_text("{}")
    integ.finish_run(ctx, repo / integ.SNAPSHOT_REL)
    man = json.loads((ctx["run_dir"] / integ.MANIFEST_NAME).read_text())
    assert man["files"]["analysis/selection.py"]["git_blob"] == prov.committed_blob(repo, "analysis/selection.py")
    for rel in prov.REQUIRED_CODE_FILES:                                         # what the freeze compares
        assert prov.committed_blob(repo, rel) == man["files"][rel]["git_blob"]
