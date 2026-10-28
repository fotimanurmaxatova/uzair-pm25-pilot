"""Validation of Open-Meteo `current` responses.

Pure functions: no network, no database. A bad response raises
ValidationError(reason_code, detail); the collector sends it to quarantine.
Ranges mirror the CHECK constraints in migrations/0001_schema.sql.
"""
import json
import math
from datetime import datetime, timezone

NATIVE_STEP_S = 3 * 3600  # CAMS global native resolution: 3 hours


class ValidationError(Exception):
    def __init__(self, reason_code, detail=""):
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail


def utc_iso(unix_seconds):
    return datetime.fromtimestamp(unix_seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_current(body_text):
    try:
        payload = json.loads(body_text)
    except (TypeError, ValueError) as exc:
        raise ValidationError("invalid_json", str(exc))
    if not isinstance(payload, dict) or not isinstance(payload.get("current"), dict):
        raise ValidationError("missing_current", "no 'current' object")
    units = payload.get("current_units")
    return payload["current"], units if isinstance(units, dict) else {}


def _time_and_interval(cur):
    t, interval = cur.get("time"), cur.get("interval")
    if isinstance(t, bool) or not isinstance(t, int):
        raise ValidationError("bad_time", f"time={t!r} (expected unix seconds)")
    if isinstance(interval, bool) or not isinstance(interval, int) or interval <= 0:
        raise ValidationError("bad_interval", f"interval={interval!r}")
    return t, interval


def _number(cur, key, lo=None, hi=None, required=False):
    value = cur.get(key)
    if value is None:
        if required:
            raise ValidationError("missing_value", key)
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError("not_a_number", f"{key}={value!r}")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ValidationError("out_of_range", f"{key}={value} not in [{lo}, {hi}]")
    return float(value)


def _unit(units, key, expected, reason):
    allowed = expected if isinstance(expected, tuple) else (expected,)
    if units.get(key) not in allowed:
        raise ValidationError(reason, f"{key} unit is {units.get(key)!r}, expected one of {allowed!r}")


def validate_weather(body_text):
    cur, units = _load_current(body_text)
    _unit(units, "wind_speed_10m", "m/s", "wrong_wind_unit")  # km/h default would corrupt the study
    _unit(units, "surface_pressure", "hPa", "wrong_pressure_unit")
    t, interval = _time_and_interval(cur)
    return {
        "weather_time_utc": utc_iso(t),
        "weather_interval_s": interval,
        "temperature_2m": _number(cur, "temperature_2m", -60, 60),
        "relative_humidity_2m": _number(cur, "relative_humidity_2m", 0, 100),
        "precipitation_mm": _number(cur, "precipitation", 0, None),
        "wind_speed_ms": _number(cur, "wind_speed_10m", 0, None, required=True),
        "wind_direction_deg": _number(cur, "wind_direction_10m", 0, 360),
        "surface_pressure_hpa": _number(cur, "surface_pressure", 700, 1100),
        "wind_speed_unit": "m/s",
    }


def validate_air_quality(body_text):
    cur, units = _load_current(body_text)
    _unit(units, "pm2_5", ("\u03bcg/m\u00b3", "\u00b5g/m\u00b3"), "wrong_pm_unit")  # Greek mu or micro sign
    t, interval = _time_and_interval(cur)
    pm25 = _number(cur, "pm2_5", 0, 1000, required=True)
    pm10 = _number(cur, "pm10", 0, 1000)
    if pm10 is not None and pm25 > pm10:
        raise ValidationError("pm_inconsistent", f"pm2_5={pm25} > pm10={pm10}")
    return {
        "observation_hour_utc": utc_iso(t),
        "aq_interval_s": interval,
        "pm2_5": pm25,
        "pm10": pm10,
        "nitrogen_dioxide": _number(cur, "nitrogen_dioxide", 0, None),
        "ozone": _number(cur, "ozone", 0, None),
        # native = valid time sits on a 3-hourly boundary (00,03,06... UTC)
        "is_native_step": 1 if t % NATIVE_STEP_S == 0 else 0,
    }


MAX_TIME_GAP_S = 3600  # decision 0002: weather and air-quality valid times must be within 1 h


def _ts(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def check_time_alignment(weather, air, max_gap_s=MAX_TIME_GAP_S):
    gap = abs((_ts(weather["weather_time_utc"]) - _ts(air["observation_hour_utc"])).total_seconds())
    if gap > max_gap_s:
        raise ValidationError("time_mismatch", f"weather/air-quality valid times differ by {gap:.0f}s (max {max_gap_s}s)")
