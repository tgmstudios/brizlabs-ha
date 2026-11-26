"""Service registration and the persistent BLE connection."""

import asyncio
import logging
import time
import uuid

import voluptuous as vol
from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
from bleak.backends.device import BLEDevice
from bleak.backends.bluezdbus.scanner import BleakScannerBlueZDBus
from bleak.exc import BleakError
from homeassistant.core import HomeAssistant

from . import scenes
from .const import DOMAIN, NOTIFY_UUID, WRITE_UUID
from .protocol import Decoder, encode

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["light", "number", "select"]

SET_SCENE_SCHEMA = vol.Schema({
    vol.Required("address"): str,
    vol.Required("effect"): vol.In(scenes.EFFECT_LIST),
    vol.Optional("brightness"): vol.All(vol.Coerce(int), vol.Range(min=0, max=scenes.MAX_LEVEL)),
    vol.Optional("mix"): vol.All(vol.Coerce(int), vol.Range(min=0, max=scenes.MAX_LEVEL)),
    vol.Optional("speed"): vol.All(vol.Coerce(int), vol.Range(min=0, max=scenes.MAX_SPEED)),
    vol.Optional("combine"): vol.All(str, vol.Length(min=2, max=28)),
})
SCAN_LOCK = asyncio.Lock()


async def async_setup(hass, config):
    def _device(call):
        address = call.data["address"].upper()
        device = next((d for d in hass.data.get(DOMAIN, {}).values() if d.address == address), None)
        if device is None:
            raise ValueError(f"No BrizLabs device configured at {address}")
        return device

    async def set_properties(call):
        await _device(call).send(call.data["properties"])

    async def set_scene(call):
        props = scenes.scene_properties(call.data["effect"], call.data.get("brightness"),
                                        call.data.get("mix"), call.data.get("speed"))
        if "combine" in call.data:
            props["scene_combine"] = call.data["combine"]
        await _device(call).send(props)

    hass.services.async_register(DOMAIN, "set_scene", set_scene, schema=SET_SCENE_SCHEMA)
    hass.services.async_register(DOMAIN, "set_properties", set_properties,
        schema=vol.Schema({vol.Required("address"): str, vol.Required("properties"): dict}))
    return True


class BrizlabsDevice:
    def __init__(self, hass: HomeAssistant, address: str):
        self.hass = hass
        self.address = address
        self.values = {}
        self.available = False
        self.listeners = set()
        self.client = None
        self.write_char = None
        self.decoder = Decoder()
        self.lock = asyncio.Lock()
        self.task = None
        self.stop = asyncio.Event()

    def subscribe(self, callback):
        self.listeners.add(callback)
        return lambda: self.listeners.discard(callback)

    def update(self):
        for callback in tuple(self.listeners):
            callback()

    def notification(self, _sender, data):
        message = self.decoder.feed(bytes(data))
        if not isinstance(message, dict):
            return
        if message.get("type") not in ("thing.property.report", "thing.property.get.response"):
            return
        changed = False
        for key, value in message.get("data", {}).items():
            if isinstance(value, dict):
                if "value" not in value:
                    continue  # valueless set-ack; keep last known value
                value = value["value"]
            if self.values.get(key) != value:
                self.values[key] = value
                changed = True
        if changed:
            self.update()

    async def run(self):
        while not self.stop.is_set():
            client = None
            scanner = None
            try:
                path = "/org/bluez/hci0/dev_" + self.address.replace(":", "_")
                known = BLEDevice(self.address, "RY", {"path": path, "props": {}})
                client = BleakClientBlueZDBus(known, bluez={}, timeout=25)
                try:
                    await client.connect(pair=False)
                except BleakError as exc:
                    if "not found" not in str(exc):
                        raise
                    async with SCAN_LOCK:
                        found = asyncio.Event()
                        discovered = None

                        def on_advertisement(ble_device, _advertisement):
                            nonlocal discovered
                            if ble_device.address.upper() == self.address:
                                discovered = ble_device
                                found.set()

                        scanner = BleakScannerBlueZDBus(on_advertisement, None, "active", bluez={})
                        await scanner.start()
                        await asyncio.wait_for(found.wait(), timeout=20)
                        client = BleakClientBlueZDBus(discovered, bluez={}, timeout=25)
                        await client.connect(pair=False)
                        await scanner.stop()
                        scanner = None
                self.client = client
                self.decoder = Decoder()
                self.write_char = client.services.get_characteristic(WRITE_UUID)
                notify_char = client.services.get_characteristic(NOTIFY_UUID)
                if not self.write_char or not notify_char:
                    raise RuntimeError("BrizLabs GATT characteristics are missing")
                await client.start_notify(notify_char, lambda data: self.notification(None, data), bluez={})
                self.available = True
                self.update()
                await self.get()
                while client.is_connected and not self.stop.is_set():
                    try:
                        await asyncio.wait_for(self.stop.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOGGER.warning("BrizLabs %s connection: %s", self.address, exc, exc_info=True)
            finally:
                if scanner:
                    try:
                        await scanner.stop()
                    except Exception:
                        pass
                self.available = False
                self.client = None
                self.write_char = None
                self.update()
                if client and client.is_connected:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
            if not self.stop.is_set():
                try:
                    await asyncio.wait_for(self.stop.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass

    async def send(self, properties=None):
        if not self.client or not self.client.is_connected:
            raise ConnectionError(f"BrizLabs {self.address} is disconnected")
        message = {
            "ts": int(time.time()),
            "data": properties if properties is not None else [],
            "type": "thing.property.set" if properties is not None else "thing.property.get",
        }
        if properties is not None:
            message["msgId"] = uuid.uuid4().hex[:16]
        async with self.lock:
            for packet in encode(message):
                await self.client.write_gatt_char(self.write_char, packet, response=True)
                await asyncio.sleep(0.03)
            if properties is not None:
                # The device echoes some sets without a value and never reports
                # its true render state, so track what we set ourselves.
                changed = False
                for key, value in properties.items():
                    if self.values.get(key) != value:
                        self.values[key] = value
                        changed = True
                if changed:
                    self.update()

    async def get(self):
        await self.send()


async def async_setup_entry(hass, entry):
    device = BrizlabsDevice(hass, entry.data["address"])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = device
    device.task = hass.async_create_background_task(device.run(), f"brizlabs_{entry.entry_id}")
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    device = hass.data[DOMAIN].pop(entry.entry_id)
    device.stop.set()
    if device.task:
        await device.task
    return ok
