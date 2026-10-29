from uzair import cli, collector


def test_collect_flags_set_pilot_and_mode(monkeypatch, tmp_path):
    seen = {}

    def fake_collect_all(conn, is_pilot=1, mode="scheduled", **kwargs):
        seen.update(is_pilot=is_pilot, mode=mode)
        return {}

    monkeypatch.setattr(collector, "collect_all", fake_collect_all)
    db_path = str(tmp_path / "cli.db")

    cli.main(["--db", db_path, "collect"])
    assert seen == {"is_pilot": 1, "mode": "manual"}   # safe default

    cli.main(["--db", db_path, "collect", "--scheduled", "--assessed"])
    assert seen == {"is_pilot": 0, "mode": "scheduled"}