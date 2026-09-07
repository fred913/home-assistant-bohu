"""Push-only state and report expiry, with no polling or background thread."""

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import CONF_TIMEOUT
from .protocol import Reading

_LOGGER = logging.getLogger(__name__)


class BohuCoordinator(DataUpdateCoordinator[Reading]):
    """Keep each device's most recent complete report in memory."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=entry.title)
        self.options = dict(entry.options)
        self.last_seen: datetime | None = None
        self.active = True
        self._cancel_expiry: CALLBACK_TYPE | None = None

    @callback
    def accept(self, reading: Reading) -> None:
        """Publish all measurements from one report together."""
        if self._cancel_expiry:
            self._cancel_expiry()
        self.last_seen = dt_util.utcnow()
        self._cancel_expiry = async_call_later(
            self.hass, self.options[CONF_TIMEOUT], self._expire
        )
        self.async_set_updated_data(reading)

    @callback
    def _expire(self, _now: datetime) -> None:
        self._cancel_expiry = None
        self.async_set_update_error(UpdateFailed("No valid report before timeout"))

    @callback
    def close(self) -> None:
        """Invalidate in-flight handlers and cancel expiry when unloaded."""
        self.active = False
        if self._cancel_expiry:
            self._cancel_expiry()
            self._cancel_expiry = None
