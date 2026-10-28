import json

import pytest

from uzair import validate
from .conftest import load


def test_valid_weather_and_air_quality_parse():
    w = validate.validate_weather(load("weather_ok.json"))
    a = validate.validate_air_quality(load("aq_ok.json"))
    assert w["wind_speed_ms"] == 2.4 and w["wind_speed_unit"] == "m/s"
    assert a["pm2_5"] == 31.5 and a["observation_hour_utc"].endswith("Z")


def test_wrong_wind_unit_is_rejected():
    d = json.loads(load("weather_ok.json"))
    d["current_units"]["wind_speed_10m"] = "km/h"
    with pytest.raises(validate.ValidationError) as e:
        validate.validate_weather(json.dumps(d))
    assert e.value.reason_code == "wrong_wind_unit"


@pytest.mark.parametrize("key,val,code", [
    ("pm2_5", -1, "out_of_range"),
    ("pm2_5", "abc", "not_a_number"),
    ("pm2_5", None, "missing_value"),
    ("pm10", 5.0, "pm25_exceeds_pm10"),
])
def test_invalid_air_quality_values(key, val, code):
    d = json.loads(load("aq_ok.json"))
    d["current"][key] = val
    with pytest.raises(validate.ValidationError) as e:
        validate.validate_air_quality(json.dumps(d))
    assert e.value.reason_code == code


def test_garbage_body_is_rejected():
    with pytest.raises(validate.ValidationError) as e:
        validate.validate_weather("<html>502</html>")
    assert e.value.reason_code == "invalid_json"


def test_native_step_flag():
    d = json.loads(load("aq_ok.json"))
    d["current"]["time"] = 10800 * 1000        # on a 3h boundary
    assert validate.validate_air_quality(json.dumps(d))["is_native_step"] == 1
    d["current"]["time"] = 10800 * 1000 + 3600  # off boundary
    assert validate.validate_air_quality(json.dumps(d))["is_native_step"] == 0
