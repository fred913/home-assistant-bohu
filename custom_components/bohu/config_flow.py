"""Create one device and one secret upload URL per config entry."""

import secrets
from urllib.parse import urlsplit

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_BASE_URL,
    CONF_DID,
    CONF_GAS_UNIT,
    CONF_TIMEOUT,
    CONF_WEBHOOK_ID,
    DEFAULT_TIMEOUT,
    DOMAIN,
    GAS_UNITS,
)


def validate_base_url(value: str) -> str:
    """Accept an HTTP(S) origin, never credentials, a path, or query parameters."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as err:
        raise vol.Invalid("Invalid URL") from err
    if (
        value != value.strip()
        or any(char.isspace() for char in value)
        or parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or (port is not None and port == 0)
    ):
        raise vol.Invalid("Enter the Home Assistant origin, including its port")
    return value.rstrip("/")


def upload_url(base_url: str, hook_id: str) -> str:
    return f"{base_url}/api/webhook/{hook_id}"


def settings_schema(values: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_BASE_URL, default=values[CONF_BASE_URL]): str,
            vol.Required(CONF_GAS_UNIT, default=values[CONF_GAS_UNIT]): SelectSelector(
                SelectSelectorConfig(
                    options=list(GAS_UNITS),
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="gas_unit",
                )
            ),
            vol.Required(CONF_TIMEOUT, default=values[CONF_TIMEOUT]): vol.All(
                vol.Coerce(int), vol.Range(min=10, max=86400)
            ),
        }
    )


class BohuConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Name the device, then display its URL before finishing setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            name = user_input[CONF_NAME]
            if not name.strip() or len(name) > 100:
                errors[CONF_NAME] = "invalid_name"
            try:
                base_url = validate_base_url(user_input[CONF_BASE_URL])
            except vol.Invalid:
                errors[CONF_BASE_URL] = "invalid_url"
            if not errors:
                self._name = name
                self._hook_id = secrets.token_hex(16)
                self._options = {
                    CONF_BASE_URL: base_url,
                    CONF_GAS_UNIT: "unknown",
                    CONF_TIMEOUT: DEFAULT_TIMEOUT,
                }
                return await self.async_step_finish()

        try:
            suggested_url = get_url(self.hass, allow_cloud=False, prefer_external=False)
        except NoURLAvailableError:
            suggested_url = ""
        values = user_input or {CONF_NAME: "Bohu", CONF_BASE_URL: suggested_url}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=values[CONF_NAME]): str,
                    vol.Required(CONF_BASE_URL, default=values[CONF_BASE_URL]): str,
                }
            ),
            errors=errors,
        )

    async def async_step_finish(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={CONF_WEBHOOK_ID: self._hook_id},
                options=self._options,
            )
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema({}),
            description_placeholders={
                "url": upload_url(self._options[CONF_BASE_URL], self._hook_id),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BohuOptionsFlow()


class BohuOptionsFlow(config_entries.OptionsFlow):
    """Show the URL again and configure units, expiry and the displayed origin."""

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                base_url = validate_base_url(user_input[CONF_BASE_URL])
            except vol.Invalid:
                errors[CONF_BASE_URL] = "invalid_url"
            if not errors:
                self._options = {**user_input, CONF_BASE_URL: base_url}
                return await self.async_step_finish()
        values = user_input or dict(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=settings_schema(values),
            errors=errors,
            description_placeholders={
                "url": upload_url(
                    self.config_entry.options[CONF_BASE_URL],
                    self.config_entry.data[CONF_WEBHOOK_ID],
                ),
                "did": self.config_entry.data.get(CONF_DID, "—"),
            },
        )

    async def async_step_finish(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=self._options)
        return self.async_show_form(
            step_id="finish",
            data_schema=vol.Schema({}),
            description_placeholders={
                "url": upload_url(
                    self._options[CONF_BASE_URL],
                    self.config_entry.data[CONF_WEBHOOK_ID],
                ),
            },
        )
