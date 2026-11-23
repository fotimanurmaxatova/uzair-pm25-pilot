"""Tests for analysis/provenance.py.  Temporary Git repositories and synthetic files only."""
import importlib.metadata as md

import pytest

from analysis import provenance as prov
from tests.cp3_synth import commit_all, init_repo, run


def test_hashes_and_git_blob_match_git(tmp_path):
    repo = init_repo(tmp_path / "r")
    f = repo / "a.txt"
    f.write_bytes(b"hello\nworld\n")
    assert prov.sha256_file(f) == prov.sha256_bytes(b"hello\nworld\n")
    assert prov.git_blob_hash(b"hello\nworld\n") == run(repo, "hash-object", "a.txt")
    rec = prov.file_record(f)
    assert set(rec) == {"sha256", "git_blob"}


def test_clean_tree_ignores_ignored_files_but_not_untracked(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / ".gitignore").write_text("junk/\n")
    (repo / "a.txt").write_text("x")
    commit_all(repo)
    assert prov.is_clean(repo)
    (repo / "junk").mkdir()
    (repo / "junk" / "f").write_text("ignored")
    assert prov.is_clean(repo)
    (repo / "new.txt").write_text("untracked")
    assert not prov.is_clean(repo)
    (repo / "new.txt").unlink()
    (repo / "a.txt").write_text("changed")
    assert not prov.is_clean(repo)


def test_tags_ancestor_and_changes_after_a_commit(tmp_path):
    repo = init_repo(tmp_path / "r")
    (repo / "a.txt").write_text("1")
    c1 = commit_all(repo, "one")
    run(repo, "tag", "-a", "late-freeze-20261125-1030", "-m", "m")
    run(repo, "tag", "late-freeze-light")
    assert prov.list_tags("late-freeze-*", repo) == ["late-freeze-20261125-1030", "late-freeze-light"]
    assert prov.tag_object_type("late-freeze-20261125-1030", repo) == "tag"
    assert prov.tag_object_type("late-freeze-light", repo) == "commit"
    assert prov.tag_commit("late-freeze-20261125-1030", repo) == c1
    (repo / "docs").mkdir()
    (repo / "docs" / "n.md").write_text("n")
    (repo / "a.txt").write_text("2")
    c2 = commit_all(repo, "two")
    (repo / "a.txt").write_text("1")                      # reverted in a later commit: still counted
    commit_all(repo, "three")
    assert prov.is_ancestor(c1, "HEAD", repo) and not prov.is_ancestor(c2, c1, repo)
    assert prov.files_changed_after(c1, repo) == ["a.txt", "docs/n.md"]
    assert prov.show_file(c1, "a.txt", repo) == b"1"


def test_check_pins(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text(f"-e .\nnumpy=={md.version('numpy')}\nscikit-learn=={md.version('scikit-learn')}\n")
    assert prov.check_pins(req) == []
    req.write_text(f"numpy==0.0.1\nscikit-learn=={md.version('scikit-learn')}\n")
    assert len(prov.check_pins(req)) == 1 and "numpy" in prov.check_pins(req)[0]
    req.write_text("numpy==%s\n" % md.version("numpy"))
    assert "scikit-learn is not pinned" in prov.check_pins(req)[0]
    assert prov.environment()["numpy"] == md.version("numpy")


def test_provenance_files_lists_code_and_config(tmp_path):
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "x.py").write_text("x=1\n")
    (tmp_path / "requirements.txt").write_text("numpy==1\n")
    files = prov.provenance_files(tmp_path)
    assert set(files) == {"analysis/x.py", "requirements.txt"}
    assert prov.provenance_files()["analysis/selection.py"]["sha256"] == prov.sha256_file(prov.ROOT / "analysis/selection.py")


def test_write_text_lf_never_writes_crlf(tmp_path):
    prov.write_text_lf(tmp_path / "a.txt", "one\ntwo\n")
    assert (tmp_path / "a.txt").read_bytes() == b"one\ntwo\n"


def test_analysis_modules_write_hashed_text_with_lf_only():
    """Windows regression: text-mode writes become CRLF, and the csv module defaults to CRLF everywhere.  A hash taken
    from the Windows working copy would then not match a fresh LF checkout."""
    import re
    for path in sorted((prov.ROOT / "analysis").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"\.write_text\(", src.replace("def write_text_lf", "")), f"{path.name}: use prov.write_text_lf"
        for call in re.findall(r"csv\.(?:writer|DictWriter)\([^\n]*", src):
            assert "lineterminator" in call, f"{path.name}: csv writer without lineterminator='\\n'"
        for call in re.findall(r"open\([^\n]*[\"'][wx][\"'][^\n]*", src):
            assert 'newline=' in call, f"{path.name}: text-mode open without newline=: {call}"
