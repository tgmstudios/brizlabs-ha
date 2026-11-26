"""Music style selector; written as a bare ``device_music`` set like the app does."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from . import scenes
from .const import DOMAIN

MUSIC_OPTIONS = ["Rock & Roll", "Jazz", "Classical", "Energy", "Roll", "Pop", "Rock", "Kpop"]
_NAME_TO_MUSIC = {name: i for i, name in enumerate(MUSIC_OPTIONS)}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BrizlabsMusicSelect(hass.data[DOMAIN][entry.entry_id], entry)])


class BrizlabsMusicSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_name = "Music mode"
    _attr_options = MUSIC_OPTIONS

    def __init__(self, device, entry):
        self.device = device
        self._attr_unique_id = f"{device.address}_music_mode"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device.address)})

    async def async_added_to_hass(self):
        self.async_on_remove(self.device.subscribe(self._changed))

    @callback
    def _changed(self):
        self.async_write_ha_state()

    @property
    def available(self):
        # device_music never appears in the device's GET response; the control
        # is usable while connected and tracks the style once one is set.
        return self.device.available

    @property
    def current_option(self):
        music = self.device.values.get("device_music")
        return MUSIC_OPTIONS[music] if isinstance(music, int) and 0 <= music < len(MUSIC_OPTIONS) else None

    async def async_select_option(self, option):
        try:
            music = _NAME_TO_MUSIC[option]
        except KeyError as exc:
            raise HomeAssistantError(f"Unknown music mode: {option}") from exc
        await self.device.send({"device_music": music})
