"""Constants for Bohu's HTTP upload protocol."""

DOMAIN = "bohu"
CONF_BASE_URL = "base_url"
CONF_DID = "did"
CONF_GAS_UNIT = "gas_unit"
CONF_TIMEOUT = "timeout"
CONF_WEBHOOK_ID = "webhook_id"
CONF_LEGACY_WEBHOOK_ID = "legacy_webhook_id"
DEFAULT_TIMEOUT = 300
DEFAULT_GAS_UNIT = "mg/m³"
GAS_UNITS = ("unknown", "mg/m³", "μg/m³", "ppm", "ppb")
MAX_BODY_BYTES = 4096
MAX_UPLOAD_URL_BYTES = 63
MEASUREMENTS = ("T", "H", "HCHO", "VOC", "C6H6")
