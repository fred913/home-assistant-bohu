"""Protocol tests run inside the official HA container, without test dependencies."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import homeassistant  # noqa: F401 - initializes HA's voluptuous compatibility layer

# isort: split

import voluptuous as vol
from custom_components.bohu.config_flow import (
    UploadURLTooLong,
    suggested_base_url,
    upload_url,
    validate_base_url,
)
from custom_components.bohu.protocol import parse_update
from homeassistant.helpers.network import NoURLAvailableError

SAMPLE = {
    "method": "update",
    "did": "demo0001",
    "WeatherType": "0",
    "T": "23",
    "H": "59",
    "HCHO": "0.138",
    "VOC": "0.283",
    "C6H6": "0.043",
}


class ProtocolTests(unittest.TestCase):
    def test_bh6_url_buffer_limit(self):
        base = "http://node.example.net:8123"
        valid = validate_base_url(base)
        self.assertEqual(len(upload_url(valid, "x" * 22).encode()), 63)
        with self.assertRaises(UploadURLTooLong):
            validate_base_url("http://nodes.example.net:8123")

    def test_configured_ha_address_precedes_detected_container_address(self):
        hass = SimpleNamespace(
            config=SimpleNamespace(
                internal_url="http://192.168.1.10:9007",
                external_url="https://ha.example.com",
            )
        )
        with patch(
            "custom_components.bohu.config_flow.get_url",
            return_value="http://172.17.0.2:8123",
        ) as detect:
            self.assertEqual(suggested_base_url(hass), "http://192.168.1.10:9007")
            hass.config.internal_url = None
            self.assertEqual(suggested_base_url(hass), "https://ha.example.com")
            detect.assert_not_called()
            hass.config.external_url = None
            self.assertEqual(suggested_base_url(hass), "http://172.17.0.2:8123")
        with patch(
            "custom_components.bohu.config_flow.get_url",
            side_effect=NoURLAvailableError,
        ):
            self.assertEqual(suggested_base_url(hass), "")

    def test_observed_format(self):
        result = parse_update(json.dumps(SAMPLE).encode())
        self.assertEqual(result.did, "demo0001")
        self.assertEqual(
            result.values,
            {"T": 23, "H": 59, "HCHO": 0.138, "VOC": 0.283, "C6H6": 0.043},
        )
        self.assertEqual(result.weather_type, "0")

    def test_required_fields(self):
        for field in ("method", "did", "T", "H", "HCHO", "VOC", "C6H6"):
            with self.subTest(field=field):
                data = {k: v for k, v in SAMPLE.items() if k != field}
                with self.assertRaisesRegex(ValueError, f"Missing field: {field}"):
                    parse_update(json.dumps(data).encode())

    def test_reject_invalid_values(self):
        cases = [
            ("T", True),
            ("T", None),
            ("T", []),
            ("T", ""),
            ("T", "NaN"),
            ("VOC", "Infinity"),
            ("HCHO", -1),
            ("H", 101),
            ("H", -1),
            ("did", 123),
            ("did", ""),
            ("did", "x" * 129),
            ("did", "a/b"),
            ("method", "delete"),
            ("WeatherType", 2),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                parse_update(json.dumps({**SAMPLE, key: value}).encode())

    def test_reject_malformed_and_duplicate_fields(self):
        for body in (
            b"[]",
            b"null",
            b"{",
            b"\xff",
            b'{"did":"a","did":"b"}',
            b" " * 4097,
        ):
            with self.subTest(body=body[:30]), self.assertRaises(ValueError):
                parse_update(body)

    def test_boundary_values_and_optional_unknown_fields(self):
        for humidity in (0, 100):
            data = {**SAMPLE, "H": humidity, "T": -5, "HCHO": 0, "future": "ignored"}
            del data["WeatherType"]
            result = parse_update(json.dumps(data).encode())
            self.assertEqual(result.values["H"], humidity)
            self.assertEqual(result.values["T"], -5)
            self.assertIsNone(result.weather_type)

    def test_base_url(self):
        for url in (
            "http://192.0.2.10:9007",
            "https://ha.example.com",
            "http://[::1]:8123",
        ):
            self.assertEqual(validate_base_url(url + "/"), url)
        for url in (
            "",
            "ftp://ha",
            "http://",
            "http://ha:bad",
            "http://ha:0",
            "http://ha:65536",
            "http://ha/api",
            "http://ha?x=1",
            "http://ha/#foo",
            "http://user:secret@ha",
            " http://ha",
            "http://h a",
        ):
            with self.subTest(url=url), self.assertRaises(vol.Invalid):
                validate_base_url(url)


if __name__ == "__main__":
    unittest.main()
