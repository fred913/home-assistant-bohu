"""Five measurements and a diagnostic last-report timestamp."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DID, CONF_GAS_UNIT, DOMAIN

PARALLEL_UPDATES = 0
DESCRIPTIONS = (
    SensorEntityDescription(
        key="T",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="H",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="HCHO",
        translation_key="formaldehyde",
        icon="mdi:molecule",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="VOC",
        translation_key="voc",
        icon="mdi:air-filter",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="C6H6",
        translation_key="benzene",
        icon="mdi:molecule",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="last_seen",
        translation_key="last_seen",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(BohuSensor(entry, description) for description in DESCRIPTIONS)


class BohuSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, entry, description):
        super().__init__(entry.runtime_data)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Bohu",
            model="HTTP air quality sensor",
            serial_number=entry.data.get(CONF_DID),
        )
        if description.key in ("HCHO", "VOC", "C6H6"):
            unit = entry.options[CONF_GAS_UNIT]
            self._attr_native_unit_of_measurement = None if unit == "unknown" else unit

    @property
    def available(self):
        if self.entity_description.key == "last_seen":
            return self.coordinator.last_seen is not None
        return self.coordinator.data is not None and super().available

    @property
    def native_value(self):
        if self.entity_description.key == "last_seen":
            return self.coordinator.last_seen
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.values[self.entity_description.key]

    @property
    def extra_state_attributes(self):
        if (
            self.entity_description.key == "last_seen"
            and self.coordinator.data is not None
        ):
            return {"weather_type": self.coordinator.data.weather_type}
        return None
