"""Single source of truth for the model-selection cut-offs (decisions 0009 and 0010). All values UTC.

Local time is Asia/Tashkent (UTC+5, no DST).  Day numbers are November 2026.

  fold k = 1, 2, 3 validates on Wed 4, Thu 5, Fri 6 Nov.
  Fold training: outcomes received STRICTLY before 00:00 local of the validation day
                 (3 Nov 19:00Z, 4 Nov 19:00Z, 5 Nov 19:00Z).
  Final fit and selection outcomes: received STRICTLY before 6 Nov 22:00 local = 17:00Z.
  Test origins: 7 Nov 00:00 to 8 Nov 17:00 local.  They must never be loaded before the freeze tag.

A partition is (first origin, last origin, outcome-receipt cut-off).  Origins are valid times of the
forecast origin t; the target is the same city at t + 6 h.  The comparison on receipt time is always `<`.
"""
from collections import namedtuple
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
TZ = timedelta(hours=5)
H = timedelta(hours=1)

Window = namedtuple("Window", "first last cutoff")


def local_to_utc(day, hour=0):
    """Local (Asia/Tashkent) time on `day` November 2026 -> aware UTC datetime."""
    return datetime(2026, 11, day, hour, tzinfo=UTC) - TZ


FIRST_ORIGIN_UTC = local_to_utc(2, 0)                 # first scheduled slot, Mon 2 Nov 00:00 local
VALID_DAYS = (4, 5, 6)
FOLD_CUTOFF_UTC = {k: local_to_utc(day, 0) for k, day in enumerate(VALID_DAYS, 1)}
FINAL_CUTOFF_UTC = local_to_utc(6, 22)                # 6 Nov 22:00 local = 17:00Z
TEST_START_UTC = local_to_utc(7, 0)                   # first test origin
TEST_END_UTC = local_to_utc(8, 17)                    # last test origin


def partitions():
    """Development partitions only.  The test partition is deliberately not defined here."""
    p = {"train_final": Window(FIRST_ORIGIN_UTC, local_to_utc(6, 15), FINAL_CUTOFF_UTC)}
    for k, day in enumerate(VALID_DAYS, 1):
        v0 = local_to_utc(day, 0)
        p[f"cv{k}_train"] = Window(FIRST_ORIGIN_UTC, v0 - 7 * H, FOLD_CUTOFF_UTC[k])
        p[f"cv{k}_valid"] = Window(v0, local_to_utc(day, 15), FINAL_CUTOFF_UTC)
    return p