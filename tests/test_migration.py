"""Old device identity and upload URLs survive the short-URL migration."""

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import homeassistant  # noqa: F401

# isort: split

from custom_components.bohu import async_migrate_entry


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_shorten_existing_id_without_changing_device_or_options(self):
        old_id = "00112233445566778899aabbccddeeff"
        entry = SimpleNamespace(
            version=1,
            entry_id="existing-device",
            data={"webhook_id": old_id, "did": "demo0001"},
            options={"gas_unit": "mg/m³"},
        )

        def update(target, *, data, version):
            target.data = data
            target.version = version

        updater = Mock(side_effect=update)
        hass = SimpleNamespace(
            config_entries=SimpleNamespace(async_update_entry=updater)
        )
        self.assertTrue(await async_migrate_entry(hass, entry))
        self.assertEqual(len(entry.data["webhook_id"]), 22)
        self.assertEqual(
            base64.urlsafe_b64decode(entry.data["webhook_id"] + "==").hex(), old_id
        )
        self.assertEqual(entry.data["legacy_webhook_id"], old_id)
        self.assertEqual(entry.data["did"], "demo0001")
        self.assertEqual(entry.entry_id, "existing-device")
        self.assertEqual(entry.options, {"gas_unit": "mg/m³"})
        self.assertTrue(await async_migrate_entry(hass, entry))
        updater.assert_called_once()
