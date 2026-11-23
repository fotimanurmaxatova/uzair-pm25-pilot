"""Snapshot integrity, provenance and numbered run directories (decision 0011, sections 1 to 5).

Used by analysis.selection before and after a selection run.  It reads no PM2.5 value and never opens the database
for writing; it only hashes the file.  Every failed check raises IntegrityError and nothing is written.

Order inside `preflight` (cheapest and most informative first; the run directory is created LAST):
  1. rerun rule        another run needs --rerun and a non-empty --reason (section 5)
  2. snapshot          file present; SHA-256 equals MANIFEST.json entry AND the constant below (section 1)
  3. environment       NumPy and scikit-learn equal the pins in requirements.txt (section 2)
  4. working tree      clean, nothing tracked or untracked changed; ignored files not counted (section 3)
  5. remote            `git fetch` of origin/main, then HEAD must be contained in it; if the remote cannot be
                       reached the manifest records a WARNING and never claims the check passed (section 3)
  6. file records      SHA-256 of the bytes and the Git blob id of each required file at HEAD (section 2)
  7. run directory     run-NNN = highest existing number + 1, created with exist_ok=False (section 5)
`finish_run` re-hashes the snapshot (it must be byte-identical), hashes the run outputs and writes
selection_manifest.json LAST, with an exclusive create so a manifest is never overwritten.

Dry run (checks 1 to 6 only, nothing created):
    python -m analysis.integrity
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from analysis import cutoffs as cut
from analysis import data, provenance as prov

# SHA-256 of snapshots/assessed_snapshot.db fixed in decision 0010 (not read from any file at run time).
EXPECTED_SNAPSHOT_SHA256 = "9ff58bb40ffc09ed2a7ff929d7a2f6ecce85b12b9c5bcdf55ef427ae1693d6c2"
SNAPSHOT_REL = "snapshots/assessed_snapshot.db"
MANIFEST_REL = "snapshots/MANIFEST.json"
SNAPSHOT_KEY = "assessed_snapshot.db"
OUTPUT_FILES = ("cv_table.csv", "selected_configurations.json")
MANIFEST_NAME = "selection_manifest.json"
RUN_RE = re.compile(r"^run-(\d+)$")
REMOTE_TIMEOUT_S = 30
PINNED_PACKAGES = ("numpy", "scikit-learn")
OPTIONAL_FILES = ("docs/decisions/0012-freeze-evaluation-and-post-test-implementation.md",)
REQUIRED_FILES = (*prov.CONFIG_FILES, *prov.DECISION_FILES, ".gitattributes", MANIFEST_REL,
                  "monitoring/coverage.py", "monitoring/prepare.py")


class IntegrityError(RuntimeError):
    pass


# ---------------------------------------------------------------- 1. snapshot
def check_snapshot(db_path, manifest_path, expected=None):
    """Three values must agree: the file, the MANIFEST.json entry and the constant fixed in the code."""
    db, mf = Path(db_path), Path(manifest_path)
    if not db.is_file():
        raise IntegrityError(f"snapshot database not found: {db}")
    if not mf.is_file():
        raise IntegrityError(f"snapshot manifest not found: {mf}")
    try:
        man = json.loads(mf.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise IntegrityError(f"snapshot manifest is not valid JSON: {mf}") from exc
    listed = (man.get("files_sha256") or {}).get(SNAPSHOT_KEY)
    if not listed:
        raise IntegrityError(f"{mf.name} has no files_sha256 entry for {SNAPSHOT_KEY}")
    exp = EXPECTED_SNAPSHOT_SHA256 if expected is None else expected
    actual = prov.sha256_file(db)
    if not (actual.lower() == str(listed).lower() == str(exp).lower()):
        raise IntegrityError("snapshot integrity check failed (a manifest edited together with the snapshot does "
                             f"not pass): file {actual}, MANIFEST.json {listed}, fixed constant {exp}")
    return {"snapshot_sha256": actual, "snapshot_bytes": db.stat().st_size, "manifest_entry_sha256": listed,
            "expected_constant_sha256": exp, "snapshot_manifest_sha256": prov.sha256_file(mf),
            "snapshot_manifest_created_utc": man.get("created_utc")}


def verify_unchanged(db_path, sha256):
    if prov.sha256_file(db_path) != sha256:
        raise IntegrityError("the snapshot changed during the run: it must stay byte-identical")


# ---------------------------------------------------------------- 2. environment and file records
def check_environment(root):
    req = Path(root) / "requirements.txt"
    if not req.is_file():
        raise IntegrityError("requirements.txt not found")
    problems = prov.check_pins(req, PINNED_PACKAGES)
    if problems:
        raise IntegrityError("installed packages differ from the pins in requirements.txt: " + "; ".join(problems))
    return prov.environment()


def required_paths(root):
    root = Path(root)
    rels = sorted(p.relative_to(root).as_posix() for p in (root / "analysis").glob("*.py"))
    rels += [r for r in REQUIRED_FILES]
    rels += [r for r in OPTIONAL_FILES if (root / r).is_file()]
    return rels


def file_records(root, rev="HEAD"):
    """{path: {sha256 of the working bytes, git_blob of the committed object at `rev`, working_bytes_match_blob}}.
    The committed Git blob id is the reference (0011 section 2); the byte hash is supporting evidence.  They can
    differ legitimately when the working copy has CRLF line endings (Git normalises to LF), so a difference is
    recorded, not refused; the clean-working-tree check already guarantees the content is the committed content."""
    root = Path(root)
    out = {}
    for rel in required_paths(root):
        p = root / rel
        if not p.is_file():
            raise IntegrityError(f"required file missing: {rel}")
        try:
            blob = prov.committed_blob(root, rel, rev)
        except prov.ProvenanceError as exc:
            raise IntegrityError(f"{rel} is not committed at {rev}: {exc}") from exc
        rec = prov.file_record(p)
        out[rel] = {"sha256": rec["sha256"], "git_blob": blob, "working_bytes_match_blob": rec["git_blob"] == blob}
    return out


# ---------------------------------------------------------------- 3. git
def git_state(root):
    return {"head": prov.head(root), "tree": prov.tree_hash(root), "branch": prov.branch(root)}


def check_working_tree(root):
    if prov.is_clean(root):
        return
    lines = prov.git(["status", "--porcelain"], root).stdout.splitlines()
    shown = "; ".join(lines[:8]) + (" ..." if len(lines) > 8 else "")
    raise IntegrityError(f"the working tree is not clean (tracked or untracked changes): {shown}")


def _fetch_main(root):
    try:
        p = subprocess.run(["git", "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main"], cwd=str(root),
                           capture_output=True, text=True, timeout=REMOTE_TIMEOUT_S)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return False, f"git fetch did not complete: {type(exc).__name__}"
    return p.returncode == 0, p.stderr.strip()[:300]


def check_remote(root):
    """HEAD must be contained in the fetched origin/main.  An unreachable remote is a recorded warning, not a pass."""
    ok, msg = _fetch_main(root)
    if not ok:
        return {"remote_check": "not performed",
                "warning": f"origin/main could not be fetched ({msg}); the remote-containment check was NOT performed"}
    if not prov.is_ancestor("HEAD", "refs/remotes/origin/main", root):
        raise IntegrityError("HEAD is not contained in origin/main: push the committed version first (0011 section 3)")
    return {"remote_check": "passed", "origin_main": prov.git(["rev-parse", "refs/remotes/origin/main"], root).stdout.strip()}


# ---------------------------------------------------------------- 5. run directories
def existing_runs(base):
    base = Path(base)
    runs = []
    if base.is_dir():
        for p in base.iterdir():
            mt = RUN_RE.match(p.name)
            if p.is_dir() and mt:
                runs.append((int(mt.group(1)), p))
    return sorted(runs)


def plan_run(base, rerun=False, reason=None):
    """Number, previous completed run and rerun reason of the next run.  Creates nothing."""
    runs = existing_runs(base)
    reason = (reason or "").strip()
    if runs and not (rerun and reason):
        raise IntegrityError(f"run directories already exist ({', '.join(p.name for _, p in runs)}): another "
                             "selection run needs both --rerun and a non-empty --reason, and is recorded in decision 0009")
    number = (runs[-1][0] + 1) if runs else 1                     # highest + 1: gaps and incomplete runs stay used
    completed = [p for _, p in runs if (p / MANIFEST_NAME).is_file()]
    return {"number": number, "run_dir": Path(base) / f"run-{number:03d}", "rerun": bool(runs),
            "rerun_reason": reason if runs else None, "previous_run": completed[-1].name if completed else None}


def create_run_dir(plan):
    plan["run_dir"].parent.mkdir(parents=True, exist_ok=True)
    try:
        plan["run_dir"].mkdir(exist_ok=False)                     # never reuse or write into an existing directory
    except FileExistsError as exc:
        raise IntegrityError(f"{plan['run_dir']} already exists; a run directory is never reused") from exc
    return plan["run_dir"]


# ---------------------------------------------------------------- orchestration
def preflight(root, db_path, manifest_path, base, rerun=False, reason=None, now=None, expected=None,
              check_remote_state=True, create=True):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    plan = plan_run(base, rerun, reason)
    snap = check_snapshot(db_path, manifest_path, expected)
    env = check_environment(root)
    check_working_tree(root)
    git = {**git_state(root), "working_tree_clean": True,
           **(check_remote(root) if check_remote_state else {"remote_check": "skipped (dry run)"})}
    files = file_records(root)
    if create:
        create_run_dir(plan)
    return {"plan": plan, "run_dir": plan["run_dir"], "snapshot": snap, "environment": env, "git": git, "files": files,
            "started_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "started_asia_tashkent": (now + cut.TZ).strftime("%Y-%m-%d %H:%M:%S")}


def finish_run(ctx, db_path):
    """Snapshot must be unchanged; hash the outputs; write the manifest LAST (exclusive create)."""
    run_dir = Path(ctx["run_dir"])
    verify_unchanged(db_path, ctx["snapshot"]["snapshot_sha256"])
    missing = [n for n in OUTPUT_FILES if not (run_dir / n).is_file()]
    if missing:
        raise IntegrityError(f"run outputs missing, no manifest written: {missing}")
    plan, snap = ctx["plan"], ctx["snapshot"]
    manifest = {
        "run": run_dir.name, "run_number": plan["number"], "previous_run": plan["previous_run"],
        "rerun": plan["rerun"], "rerun_reason": plan["rerun_reason"],
        "started_utc": ctx["started_utc"], "started_asia_tashkent": ctx["started_asia_tashkent"],
        "git": ctx["git"], "snapshot_sha256": snap["snapshot_sha256"], "snapshot": snap,
        "environment": ctx["environment"], "pinned_packages_checked": list(PINNED_PACKAGES),
        "files": ctx["files"], "final_cutoff_utc": data.iso(cut.FINAL_CUTOFF_UTC),
        "outputs_sha256": {n: prov.sha256_file(run_dir / n) for n in OUTPUT_FILES}}
    with open(run_dir / MANIFEST_NAME, "x", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return run_dir / MANIFEST_NAME


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dry run of the pre-selection integrity checks (creates nothing).")
    ap.add_argument("--repo", default=str(prov.ROOT))
    ap.add_argument("--db", default=SNAPSHOT_REL)
    ap.add_argument("--manifest", default=MANIFEST_REL)
    ap.add_argument("--out", default="results/selection")
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--reason", default=None)
    a = ap.parse_args(argv)
    try:
        ctx = preflight(a.repo, a.db, a.manifest, a.out, a.rerun, a.reason, create=False)
    except IntegrityError as exc:
        print(f"FAILED: {exc}")
        return 1
    g = ctx["git"]
    print(f"snapshot sha256 OK: {ctx['snapshot']['snapshot_sha256']}")
    print(f"environment OK: numpy {ctx['environment']['numpy']}, scikit-learn {ctx['environment']['scikit-learn']}")
    print(f"git: HEAD {g['head'][:10]} branch {g['branch']} tree clean; remote check: {g['remote_check']}")
    if g.get("warning"):
        print("WARNING: " + g["warning"])
    print(f"files recorded: {len(ctx['files'])}; next run directory would be {ctx['plan']['run_dir'].name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
