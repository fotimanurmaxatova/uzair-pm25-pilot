"""Shared synthetic fixtures for the CP3 freeze / evaluation tests.  Synthetic rows only (never analysed)."""
import subprocess
from pathlib import Path

from analysis import cutoffs as cut
from analysis import data
from tests.test_selection import synthetic_raw

SELECTED = {
    "full": {"candidate": "ridge_alpha10", "spec": {"model": "ridge", "alpha": 10}, "fold_rmse": [3.0, 3.0, 3.0]},
    "noweather": {"candidate": "hgb_depth3_lr0.1", "spec": {"model": "hgb", "max_depth": 3, "learning_rate": 0.1},
                  "fold_rmse": [4.0, 4.0, 4.0]}}
CONFIG = {"selected": SELECTED, "persistence_fold_rmse": [5.0, 5.0, 5.0]}


def full_week_raw(**kw):
    return synthetic_raw(hours=168, **kw)


def all_and_dev(raw=None):
    """(all_rows incl. test period, dev_rows through the guarded loader path)."""
    raw = raw if raw is not None else full_week_raw()
    dev_raw = [r for r in raw if r["collected_at_utc"] < data.iso(cut.FINAL_CUTOFF_UTC)]
    return data.derive_rows(raw), data.build(dev_raw)


def run(path, *args):
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "tag.gpgsign=false", *args], cwd=str(path), capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def init_repo(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    run(path, "init", "-q", "-b", "main")
    return path


def commit_all(path, msg="c"):
    run(path, "add", "-A")
    run(path, "commit", "-q", "-m", msg)
    return run(path, "rev-parse", "HEAD")
