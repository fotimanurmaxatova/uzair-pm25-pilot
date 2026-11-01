import json
from pathlib import Path

import pytest

from uzair import validate

FIXTURES = Path(__file__).parent / "fixtures"


def weather_body(**current_overrides):
    payload = json.loads((FIXTURES / "weather_ok.json").read_text(encoding="utf-8"))
    payload["current"].update(current_overrides)
    return json.dumps(payload)


def test_null_wind_speed_is_rejected_with_reason_code():
    with pytest.raises(validate.ValidationError) as exc:
        validate.validate_weather(weather_body(wind_speed_10m=None))
    assert exc.value.reason_code == "missing_value"


@pytest.mark.parametrize("humidity", [0, 100])
def test_humidity_limits_are_accepted(humidity):
    result = validate.validate_weather(weather_body(relative_humidity_2m=humidity))
    assert result["relative_humidity_2m"] == humidity


@pytest.mark.parametrize("humidity", [-1, 101])
def test_humidity_outside_limits_is_rejected(humidity):
    with pytest.raises(validate.ValidationError) as exc:
        validate.validate_weather(weather_body(relative_humidity_2m=humidity))
    assert exc.value.reason_code == "out_of_range"


def test_wind_speed_zero_is_accepted():
    assert validate.validate_weather(weather_body(wind_speed_10m=0))["wind_speed_ms"] == 0


def test_negative_wind_speed_is_rejected():
    with pytest.raises(validate.ValidationError) as exc:
        validate.validate_weather(weather_body(wind_speed_10m=-0.1))
    assert exc.value.reason_code == "out_of_range"