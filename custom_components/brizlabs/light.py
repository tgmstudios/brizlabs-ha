"""Light entity: switch, brightness, and scene effects over ``scene_select``."""

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_EFFECT, ColorMode, LightEntity, LightEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo

from . import scenes
from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BrizlabsLight(hass.data[DOMAIN][entry.entry_id], entry)])


class BrizlabsLight(LightEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_effect_list = scenes.EFFECT_LIST
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, device, entry):
        self.device = device
        self._attr_unique_id = device.address.replace(":", "").lower()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.address)},
            name=entry.title,
            manufacturer="BrizLabs",
            model="Micro String Lights",
            connections={("bluetooth", device.address)},
        )

    async def async_added_to_hass(self):
        self.async_on_remove(self.device.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    @property
    def available(self):
        return self.device.available

    @property
    def is_on(self):
        return bool(self.device.values.get("switch_led", False))

    @property
    def brightness(self):
        scene = scenes.decode(self.device.values.get("scene_select"))
        level = scene.brightness if scene else round(int(self.device.values.get("bright_value", 100)) * 10)
        return max(1, min(255, round(level * 255 / scenes.MAX_LEVEL)))

    @property
    def effect(self):
        return scenes.effect_for_values(self.device.values)

    @property
    def extra_state_attributes(self):
        scene = scenes.decode(self.device.values.get("scene_select"))
        return {"scene_select": self.device.values.get("scene_select"),
                "scene_combine": self.device.values.get("scene_combine"),
                "white_mix": None if scene is None else round(scene.mix / 10),
                "scene_speed": None if scene is None else scene.speed}

    async def async_turn_on(self, **kwargs):
        data = {"switch_led": True}
        current = self.device.values.get("scene_select")
        scene = scenes.decode(current)
        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            if effect == scenes.MUSIC_NAME:
                data["device_music"] = 0
            else:
                props = scenes.scene_properties(effect)
                if ATTR_BRIGHTNESS in kwargs:
                    level = round(kwargs[ATTR_BRIGHTNESS] * scenes.MAX_LEVEL / 255)
                    props["scene_select"] = scenes.with_brightness(props["scene_select"], level)
                data.update(props)
        elif ATTR_BRIGHTNESS in kwargs:
            level = round(kwargs[ATTR_BRIGHTNESS] * scenes.MAX_LEVEL / 255)
            if scene is not None:
                data["scene_select"] = scenes.with_brightness(current, level)
            else:
                data["bright_value"] = max(1, min(100, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255)))
        await self.device.send(data)

    async def async_turn_off(self, **kwargs):
        await self.device.send({"switch_led": False})
