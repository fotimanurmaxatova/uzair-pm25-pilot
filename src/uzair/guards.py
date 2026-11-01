"""Safety guards for assessed collection (approval of 2026-10-28).

Assessed rows (is_pilot=0) may only be written
  * inside the approved window: Mon 2 Nov 2026 00:00 to Mon 9 Nov 2026 00:00 Asia/Tashkent
    (UTC+5, so 2026-11-01T19:00:00Z to 2026-11-08T19:00:00Z),
  * by the scheduler (acquisition_mode='scheduled'), never by a manual run,
  * by a frozen collector (no uncommitted changes in src/ or migrations/).
Pure function: easy to test, no network, no database.
"""
from datetime import datetime, timezone

ASSESSED_START_UTC = datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc)
ASSESSED_END_UTC = datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc)


class GuardError(Exception):
    pass


def check_assessed_allowed(now_utc, scheduled, version):
    if not scheduled:
        raise GuardError("assessed collection must use --scheduled (manual runs are development only)")
    if now_utc < ASSESSED_START_UTC:
        raise GuardError(f"assessed collection has not started (opens {ASSESSED_START_UTC:%Y-%m-%dT%H:%M:%SZ})")
    if now_utc >= ASSESSED_END_UTC:
        raise GuardError(f"assessed collection window closed ({ASSESSED_END_UTC:%Y-%m-%dT%H:%M:%SZ})")
    if version.endswith("-dirty"):
        raise GuardError(f"collector version {version} has uncommitted changes; commit and tag before assessed collection")
    if version.endswith("+nogit"):
        raise GuardError("collector version has no git commit; run from the cloned repository")
