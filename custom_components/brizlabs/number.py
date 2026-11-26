"""White mix, scene speed, and microphone sensitivity controls."""

from homeassistant.components.number import NumberEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from . import scenes
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    device = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BrizlabsNumber(device, "sensitivity", 0, 100, "Mic sensitivity"),
                        BrizlabsSceneField(device, "mix", "White mix", 10),
                        BrizlabsSceneField(device, "speed", "Scene speed", 1)])


class BrizlabsNumber(NumberEntity):
    _attr_has_entity_name = True
    _attr_native_step = 1

    def __init__(self, device, key, minimum, maximum, name):
        self.device = device
        self.key = key
        self._attr_name = name
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device.address)})

    async def async_added_to_hass(self):
        self.async_on_remove(self.device.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    @property
    def available(self):
        return self.device.available and self.key in self.device.values

    @property
    def native_value(self):
        return self.device.values.get(self.key)

    async def async_set_native_value(self, value):
        await self.device.send({self.key: int(value)})


class BrizlabsSceneField(NumberEntity):
    """Brightness-scaled field (white mix) or speed of the active scene."""

    _attr_has_entity_name = True
    _attr_native_step = 1

    def __init__(self, device, field, name, scale):
        self.device = device
        self.field = field  # scenes.Scene attribute written back into scene_select
        self.scale = scale  # HA unit per payload unit (10 = percent, 1 = raw)
        self._attr_name = name
        self._attr_native_min_value = 0
        self._attr_native_max_value = scenes.MAX_LEVEL // scale if scale > 1 else scenes.MAX_SPEED
        self._attr_unique_id = f"{device.address}_scene_{field}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device.address)})

    async def async_added_to_hass(self):
        self.async_on_remove(self.device.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    def _payload(self):
        return self.device.values.get("scene_select")

    @property
    def available(self):
        return self.device.available and scenes.decode(self._payload()) is not None

    @property
    def native_value(self):
        scene = scenes.decode(self._payload())
        if scene is None:
            return None
        value = getattr(scene, self.field)
        return value // self.scale if self.scale > 1 else value

    async def async_set_native_value(self, value):
        payload = self._payload()
        if scenes.decode(payload) is None:
            raise HomeAssistantError("Select a scene effect first")
        raw = int(value) * self.scale
        try:
            new = scenes.with_mix(payload, raw) if self.field == "mix" else scenes.with_speed(payload, int(value))
        except ValueError as exc:
            raise HomeAssistantError(str(exc)) from exc
        await self.device.send({"scene_select": new})
