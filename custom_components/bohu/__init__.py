"""Receive Bohu air quality reports through Home Assistant's HTTP server."""

import base64
import logging
import re

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_DID,
    CONF_LEGACY_WEBHOOK_ID,
    CONF_WEBHOOK_ID,
    DOMAIN,
    MAX_BODY_BYTES,
)
from .coordinator import BohuCoordinator
from .protocol import parse_update

type BohuConfigEntry = ConfigEntry[BohuCoordinator]
PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Shorten v1 IDs without losing entropy or breaking previously working URLs."""
    if entry.version == 1:
        old_id = entry.data[CONF_WEBHOOK_ID]
        if not isinstance(old_id, str) or re.fullmatch(r"[0-9a-f]{32}", old_id) is None:
            _LOGGER.error("Cannot migrate an invalid legacy Bohu webhook ID")
            return False
        short_id = base64.urlsafe_b64encode(bytes.fromhex(old_id)).decode().rstrip("=")
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_WEBHOOK_ID: short_id,
                CONF_LEGACY_WEBHOOK_ID: old_id,
            },
            version=2,
        )
    return entry.version == 2


async def async_setup_entry(hass: HomeAssistant, entry: BohuConfigEntry) -> bool:
    """Create a device immediately, then wait for its first valid upload."""
    coordinator = entry.runtime_data = BohuCoordinator(hass, entry)
    entry.async_on_unload(coordinator.close)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def receive(
        hass: HomeAssistant, _webhook_id: str, request: web.Request
    ) -> web.Response:
        body = bytearray()
        async for chunk in request.content.iter_chunked(MAX_BODY_BYTES + 1):
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                return web.Response(status=413, text="Request body too large\n")
        if not coordinator.active:
            return web.Response(status=503, text="Integration is unloading\n")
        try:
            reading = parse_update(bytes(body))
        except ValueError as err:
            return web.Response(status=400, text=f"{err}\n")

        bound_did = entry.data.get(CONF_DID)
        if bound_did is not None and reading.did != bound_did:
            return web.Response(status=409, text="Device ID does not match this URL\n")
        if bound_did is None:
            for other in hass.config_entries.async_entries(DOMAIN):
                if (
                    other.entry_id != entry.entry_id
                    and other.data.get(CONF_DID) == reading.did
                ):
                    return web.Response(
                        status=409, text="Device ID is already configured\n"
                    )
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_DID: reading.did}
            )
            registry = dr.async_get(hass)
            device = registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
            if device:
                registry.async_update_device(device.id, serial_number=reading.did)

        coordinator.accept(reading)
        return web.Response(text="OK\n", headers={"Cache-Control": "no-store"})

    hook_ids = [entry.data[CONF_WEBHOOK_ID]]
    if legacy_id := entry.data.get(CONF_LEGACY_WEBHOOK_ID):
        hook_ids.append(legacy_id)
    # The unguessable URL is the credential. Do not reject non-RFC1918 home/VPN LANs.
    for hook_id in hook_ids:
        webhook.async_register(
            hass,
            DOMAIN,
            entry.title,
            hook_id,
            receive,
            allowed_methods=["POST"],
            local_only=False,
        )
        entry.async_on_unload(
            lambda hook_id=hook_id: webhook.async_unregister(hass, hook_id)
        )
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: BohuConfigEntry) -> None:
    """First-report ID binding must not reload the receiving integration."""
    if entry.options != entry.runtime_data.options:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BohuConfigEntry) -> bool:
    """HA runs registered cleanup callbacks after a successful unload."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
