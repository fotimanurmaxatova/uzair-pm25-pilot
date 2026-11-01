from uzair import cli, collector, query
from .conftest import load, make_fetch

W, A = load("weather_ok.json"), load("aq_ok.json")
no_sleep = lambda s: None


def test_provenance_links_row_to_both_requests(conn):
    collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    rows = query.provenance(conn, 8)
    assert len(rows) == 8
    r = rows[0]
    assert r["w_http"] == 200 and r["a_http"] == 200 and r["w_run"] != r["a_run"]
    assert len(r["w_sha"]) == 64 and len(r["a_sha"]) == 64
    assert r["collector_version"].startswith("0.1.0")


def test_verify_passes_then_detects_tampering(conn):
    collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    checked, bad = query.verify_raw_hashes(conn)
    assert checked == 16 and bad == []
    conn.execute("UPDATE raw_responses SET body = body || ' ' WHERE raw_id = 1")
    conn.commit()
    checked, bad = query.verify_raw_hashes(conn)
    assert len(bad) == 1


def test_cli_verify_exit_code(conn, tmp_path):
    collector.collect_all(conn, fetch=make_fetch(W, A), sleep=no_sleep)
    path = conn.execute("PRAGMA database_list").fetchone()["file"]
    assert cli.main(["--db", path, "verify"]) == 0
    conn.execute("UPDATE raw_responses SET body = 'x' WHERE raw_id = 1")
    conn.commit()
    assert cli.main(["--db", path, "verify"]) == 1
