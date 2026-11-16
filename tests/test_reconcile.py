"""Tests for monitoring/reconcile.py. Synthetic rows only."""
import sqlite3

from monitoring import coverage as cov
from monitoring import reconcile as rc
from tests.test_coverage import make_db


def add_bodies(path, failed_bodies=0):
    """The fixture stores no raw responses: add one per successful run and `failed_bodies` per failed run."""
    c = sqlite3.connect(path)
    ok = [r[0] for r in c.execute("SELECT run_id FROM collection_runs WHERE status = 'success'")]
    bad = [r[0] for r in c.execute("SELECT run_id FROM collection_runs WHERE status <> 'success' ORDER BY run_id")][:failed_bodies]
    c.executemany("INSERT INTO raw_responses (run_id, received_at_utc, response_sha256, body) VALUES (?,?,?,?)",
                  [(rid, "2026-11-02T00:06:00Z", "0" * 64, "{}") for rid in ok + bad])
    c.commit()
    c.close()
    return path


def counts(path):
    conn = cov.open_ro(path)
    try:
        return rc.reconcile(conn)
    finally:
        conn.close()


def test_clean_week_reconciles(tmp_path):
    o = counts(add_bodies(make_db(tmp_path)))
    assert o["logical"] == 168 * 8 * 2 and o["failed"] == 0 and o["retries_total"] == 0
    assert o["attempts"] == o["logical"]
    assert o["observations"] == 1344
    assert all(ok for _, ok in rc.checks(o))


def test_failed_poll_is_separated_from_retained_responses(tmp_path):
    slot = cov.START + 20 * cov.H
    o = counts(add_bodies(make_db(tmp_path, fail_slots=(slot,)), failed_bodies=5))
    assert o["failed"] == 8 and o["failed_with_body"] == 5 and o["failed_no_body"] == 3
    assert o["retained"] == o["logical"] - 3
    assert o["aq_without_observation"] == 8          # air-quality half of the failed poll has no weather pair
    assert o["observations"] == 1344 - 8
    assert all(ok for _, ok in rc.checks(o))


def test_retries_add_attempts_but_not_logical_requests(tmp_path):
    path = add_bodies(make_db(tmp_path))
    c = sqlite3.connect(path)
    c.execute("UPDATE collection_runs SET retry_count = 3 WHERE run_id IN (1, 2)")
    c.commit()
    c.close()
    o = counts(path)
    assert o["retries_total"] == 6 and o["attempts"] == o["logical"] + 6 and o["success_retried"] == 2
    assert all(ok for _, ok in rc.checks(o))


def test_a_broken_identity_is_reported_and_exit_code_is_nonzero(tmp_path, capsys):
    o = counts(add_bodies(make_db(tmp_path)))
    o["retained"] += 1
    assert not all(ok for _, ok in rc.checks(o))
    assert "[FAIL]" in rc.report(o)


def test_main_runs_read_only_and_exits_zero(tmp_path, capsys):
    assert rc.main(["--db", str(add_bodies(make_db(tmp_path)))]) == 0
    assert "HTTP attempts" in capsys.readouterr().out