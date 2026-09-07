"""Decode the observed protocol without trusting its Content-Type header."""

import json
import math
from dataclasses import dataclass

from .const import MAX_BODY_BYTES, MEASUREMENTS


@dataclass(frozen=True)
class Reading:
    """One complete, validated update. Gas values remain in device units."""

    did: str
    values: dict[str, float]
    weather_type: str | None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate field: {key}")
        result[key] = value
    return result


def parse_update(body: bytes) -> Reading:
    """Reject partial or invalid reports before changing any entity state."""
    if len(body) > MAX_BODY_BYTES:
        raise ValueError("Request body exceeds 4096 bytes")
    data = json.loads(body.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    for key in ("method", "did", *MEASUREMENTS):
        if key not in data:
            raise ValueError(f"Missing field: {key}")
    if data["method"] != "update":
        raise ValueError("Expected method=update")
    did = data["did"]
    if not isinstance(did, str) or not did or len(did) > 128 or not did.isalnum():
        raise ValueError("did must be a nonempty alphanumeric string (max 128)")
    values = {}
    for key in MEASUREMENTS:
        value = data[key]
        if type(value) not in (str, int, float):
            raise ValueError(f"{key} must be a number or numeric string")
        try:
            number = float(value)
        except (ValueError, OverflowError) as err:
            raise ValueError(f"{key} must be a finite number") from err
        if not math.isfinite(number):
            raise ValueError(f"{key} must be a finite number")
        if key == "H" and not 0 <= number <= 100:
            raise ValueError("H must be between 0 and 100")
        if key in ("HCHO", "VOC", "C6H6") and number < 0:
            raise ValueError(f"{key} must be nonnegative")
        values[key] = number
    weather_type = data.get("WeatherType")
    if weather_type is not None and not isinstance(weather_type, str):
        raise ValueError("WeatherType must be a string when present")
    return Reading(did, values, weather_type)
