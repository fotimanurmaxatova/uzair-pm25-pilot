"""Tests for analysis/eda.py.  Synthetic rows only."""
import json

import pytest

from analysis import data, eda, evaluate as ev
from tests.cp3_synth import all_and_dev

ALL, DEV = all_and_dev()
PNG = b"\x89PNG\r\n\x1a\n"


def test_six_labelled_charts_are_written(tmp_path):
    files = eda.make_charts(DEV, tmp_path, "pre_freeze")
    assert len(files) == 6
    for f in files:
        assert (tmp_path / f).read_bytes()[:8] == PNG and (tmp_path / f).stat().st_size > 2000
    eda.write_manifest(tmp_path, "pre_freeze", len(DEV))
    man = json.loads((tmp_path / "eda_manifest.json").read_text())
    assert man["mode"] == "pre_freeze" and "before 6 Nov 22:00" in man["label"] and len(man["files_sha256"]) == 6


def test_unknown_mode_and_empty_data_are_errors(tmp_path):
    with pytest.raises(ValueError):
        eda.make_charts(DEV, tmp_path, "whatever")
    with pytest.raises(ValueError, match="no native rows"):
        eda.make_charts([], tmp_path, "full")


def test_full_mode_needs_the_marker(tmp_path):
    with pytest.raises(ev.EvaluationGuardError, match="has not been run"):
        eda.main(["--db", "nope.db", "--mode", "full", "--repo", str(tmp_path)])


def test_pre_freeze_mode_never_loads_the_test_period(tmp_path, monkeypatch):
    class Conn:
        def close(self):
            pass
    monkeypatch.setattr(eda, "open_ro", lambda p: Conn())
    monkeypatch.setattr(eda.data, "load_development", lambda conn: DEV)
    monkeypatch.setattr(eda.evaluate, "load_all_rows", lambda db: pytest.fail("test period must not be loaded"))
    eda.main(["--db", "x.db", "--mode", "pre_freeze", "--repo", str(tmp_path)])
    assert (tmp_path / "results" / "eda" / "pre_freeze" / "eda_manifest.json").is_file()
    assert all(r["valid_dt"] < data.cut.TEST_START_UTC for r in DEV)
