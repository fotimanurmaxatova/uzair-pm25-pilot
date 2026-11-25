"""End-to-end rehearsal of the stage order selection -> commit -> freeze -> commit -> annotated tag -> guard
(decision 0011 sections 3, 5, 7 and 8).  Synthetic data and a temporary Git repository only."""
import pytest

from analysis import evaluate as ev, freeze, provenance as prov
from tests.cp3_synth import commit_all, run
from tests.test_freeze import make_repo, make_run

TAG = "late-freeze-20261125-1030"


def _patch_development_rows(monkeypatch):
    from tests.test_freeze import DEV as dev_rows
    class _Conn:
        def close(self):
            pass
    monkeypatch.setattr(freeze, "open_ro", lambda db: _Conn())
    monkeypatch.setattr(freeze.data, "load_development", lambda conn: dev_rows)


def test_selection_commit_then_freeze_commit_then_tag_passes_the_evaluation_guard(tmp_path, monkeypatch):
    _patch_development_rows(monkeypatch)
    repo = make_repo(tmp_path)
    snap = repo / "snapshots" / "assessed_snapshot.db"
    snap.parent.mkdir()
    snap.write_bytes(b"snapshot bytes")
    commit_all(repo, "snapshot")

    base = repo / "results" / "selection"
    make_run(base, 1, repo, snap)
    out = repo / "results" / "freeze"

    # the selection outputs are not committed yet: the freeze must refuse (0011 section 3) and write nothing
    with pytest.raises(freeze.FreezeError, match="not clean"):
        freeze.build_freeze(snap, base, out, repo_root=repo)
    assert not out.exists()

    selection_commit = commit_all(repo, "selection run-001")
    result = freeze.build_freeze(snap, base, out, repo_root=repo)
    assert result["run"] == "run-001"
    assert not prov.is_clean(repo)                      # freeze outputs wait for their own commit
    freeze_commit = commit_all(repo, "freeze")
    run(repo, "tag", "-a", TAG, "-m", f"late freeze {freeze_commit}")

    # the tagged commit contains the selection run (an ancestor) and every freeze artefact, byte for byte
    assert prov.is_ancestor(selection_commit, freeze_commit, repo)
    assert prov.tag_commit(TAG, repo) == freeze_commit == prov.head(repo)
    tracked = set(run(repo, "ls-tree", "-r", "--name-only", "HEAD", "results").splitlines())
    for name in ("cv_table.csv", "selected_configurations.json", "selection_manifest.json"):
        assert f"results/selection/run-001/{name}" in tracked
    for name in ("model_full.pkl", "model_full.json", "model_noweather.pkl", "model_noweather.json",
                 "frozen_config.json", "freeze_manifest.json"):
        rel = f"results/freeze/{name}"
        assert rel in tracked
        assert run(repo, "rev-parse", f"HEAD:{rel}") == run(repo, "hash-object", rel)

    g = ev.check_guard(repo, snap)                       # loads no test rows, writes nothing
    assert g["tag"] == TAG and g["manifest"]["selection_run"] == "run-001"
    assert not ev.marker_path(repo).exists()


def test_freeze_after_a_selection_commit_never_reuses_an_older_run(tmp_path, monkeypatch):
    _patch_development_rows(monkeypatch)
    repo = make_repo(tmp_path)
    snap = repo / "snapshots" / "assessed_snapshot.db"
    snap.parent.mkdir()
    snap.write_bytes(b"snapshot bytes")
    commit_all(repo, "snapshot")
    base = repo / "results" / "selection"
    make_run(base, 1, repo, snap)
    make_run(base, 2, repo, snap, complete=False)         # an unfinished later attempt
    commit_all(repo, "runs")
    with pytest.raises(freeze.FreezeError, match="incomplete"):
        freeze.build_freeze(snap, base, repo / "results" / "freeze", repo_root=repo)
