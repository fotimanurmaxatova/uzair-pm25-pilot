"""Hashes, Git state and environment checks shared by the freeze and the evaluation guard
(decision 0010 item 16, decision 0011 sections 2, 3 and 8).

Standard library only.  Nothing here reads assessed data.
"""
import hashlib
import platform
import re
import subprocess
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProvenanceError(RuntimeError):
    pass


# ---------------------------------------------------------------- hashes
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text_lf(path, text):
    """Write text with LF line endings on every platform.  Every text file whose bytes are hashed (manifests, CSV,
    JSON) is written this way, so a hash recorded on Windows still matches a fresh LF checkout elsewhere."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def git_blob_hash(data):
    """Git object id of a blob with these bytes (what `git hash-object` prints).  Cross-platform reference (0011)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def file_record(path):
    b = Path(path).read_bytes()
    return {"sha256": sha256_bytes(b), "git_blob": git_blob_hash(b)}


# Code whose hashes must be identical in the selection manifest and in the freeze (0011 section 6).
REQUIRED_CODE_FILES = ("analysis/cutoffs.py", "analysis/data.py", "analysis/modelling.py", "analysis/selection.py",
                       "monitoring/coverage.py", "monitoring/prepare.py")
CONFIG_FILES = ("requirements.txt", "pyproject.toml", "pytest.ini")
DECISION_FILES = ("docs/decisions/0009-late-model-freeze.md",
                  "docs/decisions/0010-analysis-implementation-choices.md",
                  "docs/decisions/0011-snapshot-integrity-and-reproducible-freeze.md")
# Paths whose content is verified after the freeze tag (docs/ and results/ may change legitimately).
FROZEN_PREFIXES = ("analysis/", "monitoring/", "requirements.txt", "pyproject.toml", "pytest.ini")


def committed_blob(root, rel, rev="HEAD"):
    """Git blob id of the COMMITTED object `rev:rel`.  This is the cross-platform reference (0011 section 2): it is
    the same on Windows and Linux even if the working copy has CRLF line endings, because Git normalises on add."""
    return git(["rev-parse", f"{rev}:{rel}"], root).stdout.strip()


def provenance_files(root=ROOT, rev="HEAD"):
    """{relative path: {sha256 of the working bytes, git_blob of the committed object}} for every analysis/*.py, the
    monitoring code, configuration and decisions.  Outside a Git repository the blob id is computed from the bytes."""
    root = Path(root)
    rels = sorted(p.relative_to(root).as_posix() for p in (root / "analysis").glob("*.py"))
    rels += ["monitoring/coverage.py", "monitoring/prepare.py", *CONFIG_FILES, *DECISION_FILES]
    out = {}
    for rel in rels:
        if not (root / rel).is_file():
            continue
        rec = file_record(root / rel)
        try:
            rec["git_blob"] = committed_blob(root, rel, rev)
        except ProvenanceError:
            pass
        out[rel] = rec
    return out


# ---------------------------------------------------------------- environment
def installed(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def environment():
    out = {"python": platform.python_version()}
    for pkg in ("numpy", "pandas", "scikit-learn", "matplotlib", "pytest", "setuptools"):
        out[pkg] = installed(pkg)
    return out


def parse_pins(requirements_path):
    pins = {}
    for line in Path(requirements_path).read_text(encoding="utf-8").splitlines():
        mt = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;#]+)", line.strip())
        if mt:
            pins[mt.group(1).lower().replace("_", "-")] = mt.group(2)
    return pins


def check_pins(requirements_path, packages=("numpy", "scikit-learn")):
    """List of problems (empty = fine).  A different Python version is recorded elsewhere, not blocked."""
    pins = parse_pins(requirements_path)
    problems = []
    for pkg in packages:
        want, got = pins.get(pkg), installed(pkg)
        if want is None:
            problems.append(f"{pkg} is not pinned in requirements.txt")
        elif got != want:
            problems.append(f"{pkg}: installed {got}, pinned {want}")
    return problems


# ---------------------------------------------------------------- git
def git(args, cwd=ROOT, check=True, text=True):
    try:
        p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=text)
    except FileNotFoundError as exc:
        raise ProvenanceError("git is not installed or not on PATH") from exc
    if check and p.returncode != 0:
        err = p.stderr.strip() if text else p.stderr.decode("utf-8", "replace").strip()
        raise ProvenanceError(f"git {' '.join(args)} failed: {err}")
    return p


def head(cwd=ROOT):
    return git(["rev-parse", "HEAD"], cwd).stdout.strip()


def tree_hash(cwd=ROOT):
    return git(["rev-parse", "HEAD^{tree}"], cwd).stdout.strip()


def branch(cwd=ROOT):
    return git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()


def is_clean(cwd=ROOT):
    """True if there are no tracked or untracked changes (files ignored by .gitignore are not counted)."""
    return not git(["status", "--porcelain"], cwd).stdout.strip()


def list_tags(pattern, cwd=ROOT):
    return [t for t in git(["tag", "--list", pattern], cwd).stdout.splitlines() if t.strip()]


def tag_object_type(tag, cwd=ROOT):
    """'tag' for an annotated tag, 'commit' for a lightweight tag."""
    return git(["cat-file", "-t", f"refs/tags/{tag}"], cwd).stdout.strip()


def tag_commit(tag, cwd=ROOT):
    return git(["rev-list", "-n", "1", f"refs/tags/{tag}"], cwd).stdout.strip()


def is_ancestor(ancestor, descendant, cwd=ROOT):
    return git(["merge-base", "--is-ancestor", ancestor, descendant], cwd, check=False).returncode == 0


def files_changed_after(commit, cwd=ROOT):
    """Every path touched by any commit in commit..HEAD (per commit, so a change that is later reverted still counts)."""
    out = git(["log", "--name-only", "--no-renames", "--pretty=format:", f"{commit}..HEAD"], cwd).stdout
    return sorted({ln.strip() for ln in out.splitlines() if ln.strip()})


def show_file(rev, path, cwd=ROOT):
    return git(["show", f"{rev}:{path}"], cwd, text=False).stdout
