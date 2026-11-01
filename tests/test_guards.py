from datetime import datetime, timezone

import pytest

from uzair import cli, collector, guards

OK = "0.1.0+abc1234"
T0 = datetime(2026, 11, 1, 19, 5, tzinfo=timezone.utc)   # Mon 2 Nov 00:05 Asia/Tashkent


def at(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_allowed_inside_window():
    guards.check_assessed_allowed(T0, True, OK)
    guards.check_assessed_allowed(at(2026, 11, 8, 18, 5), True, OK)   # last poll, Sun 8 Nov 23:05 local


def test_refused_before_start_boundary():
    with pytest.raises(guards.GuardError):
        guards.check_assessed_allowed(at(2026, 11, 1, 18, 59), True, OK)   # 23:59 local on 1 Nov


def test_refused_at_and_after_end_boundary():
    with pytest.raises(guards.GuardError):
        guards.check_assessed_allowed(guards.ASSESSED_END_UTC, True, OK)


def test_refused_when_manual_dirty_or_no_git():
    with pytest.raises(guards.GuardError):
        guards.check_assessed_allowed(T0, False, OK)
    with pytest.raises(guards.GuardError):
        guards.check_assessed_allowed(T0, True, "0.1.0+abc1234-dirty")
    with pytest.raises(guards.GuardError):
        guards.check_assessed_allowed(T0, True, "0.1.0+nogit")


def test_cli_refuses_assessed_outside_window_and_writes_nothing(tmp_path, monkeypatch, capsys):
    called = []
    monkeypatch.setattr(collector, "collect_all", lambda *a, **k: called.append(1) or {})
    db_path = tmp_path / "x.db"
    early = at(2026, 10, 30, 12, 0)
    assert cli.main(["--db", str(db_path), "collect", "--assessed", "--scheduled"], now=early) == 2
    assert not called and not db_path.exists()
    assert "REFUSED" in capsys.readouterr().err


def test_cli_assessed_runs_inside_window(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(collector, "current_version", lambda: ("0.1.0+abc1234", "abc1234"))
    monkeypatch.setattr(collector, "collect_all",
                        lambda conn, is_pilot=1, mode="scheduled", **k: seen.update(p=is_pilot, m=mode) or {})
    assert cli.main(["--db", str(tmp_path / "a.db"), "collect", "--assessed", "--scheduled"], now=T0) == 0
    assert seen == {"p": 0, "m": "scheduled"}
