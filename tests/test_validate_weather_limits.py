import json
from pathlib import Path

import pytest

from uzair import validate

FIXTURES = Path(__file__).parent / "fixtures"


def weather_body(**current_overrides):
    payload = json.loads((FIXTURES / "weather_ok.json").read_text(encoding="utf-8"))
    payload["current"].update(current_overrides)
    return json.dumps(payload)


@pytest.mark.parametrize(
    "field, key, accepted, rejected",
    [
        ("temperature_2m", "temperature_2m", [-60, 60], [-60.1, 60.1]),
        ("surface_pressure", "surface_pressure_hpa", [700, 1100], [699.9, 1100.1]),
        ("wind_direction_10m", "wind_direction_deg", [0, 360], [-1, 360.1]),
    ],
)
def test_limits_are_inclusive_and_outside_values_are_rejected(field, key, accepted, rejected):
    for value in accepted:
        assert validate.validate_weather(weather_body(**{field: value}))[key] == value
    for value in rejected:
        with pytest.raises(validate.ValidationError) as exc:
            validate.validate_weather(weather_body(**{field: value}))
        assert exc.value.reason_code == "out_of_range"