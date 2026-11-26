import asyncio
from types import SimpleNamespace

import pytest
import voluptuous as vol

import custom_components.brizlabs as integ
from custom_components.brizlabs import scenes as S
from tests.fakes import FakeDevice, entry


class FakeServices:
    def __init__(self):
        self.reg = {}

    def async_register(self, domain, name, fn, schema=None):
        self.reg[(domain, name)] = (fn, schema)


class FakeEntries:
    def __init__(self):
        self.forwarded, self.unloaded = [], []

    async def async_forward_entry_setups(self, e, platforms):
        self.forwarded.append(list(platforms))

    async def async_unload_platforms(self, e, platforms):
        self.unloaded.append(list(platforms))
        return True


def make_hass():
    def bg(coro, name):
        return asyncio.ensure_future(coro)
    return SimpleNamespace(data={}, services=FakeServices(), config_entries=FakeEntries(),
                           async_create_background_task=bg)


class RunnableDevice(FakeDevice):
    def __init__(self, hass, address):
        super().__init__(address)
        self.stop = asyncio.Event()

    async def run(self):
        await self.stop.wait()


def test_select_platform_registered():
    assert integ.PLATFORMS == ["light", "number", "select"]


async def test_services_registered_and_set_scene_sends_payload():
    hass = make_hass()
    await integ.async_setup(hass, {})
    for name in ("set_properties", "set_scene"):
        assert ("brizlabs", name) in hass.services.reg
    assert ("brizlabs", "paint_segments") not in hass.services.reg
    fn, schema = hass.services.reg[("brizlabs", "set_scene")]
    a, b = FakeDevice("00:11:22:33:44:55"), FakeDevice("00:11:22:33:44:66")
    hass.data["brizlabs"] = {"1": a, "2": b}
    data = schema({"address": "00:11:22:33:44:55", "effect": "Color Mixture",
                   "brightness": 500, "mix": 100, "speed": 3})
    await fn(SimpleNamespace(data=data))
    assert b.sent == []
    props = a.sent[0]
    assert S.decode(props["scene_select"]) == S.Scene(0x22, 500, 100, 3)


async def test_set_scene_combine_override():
    hass = make_hass()
    await integ.async_setup(hass, {})
    fn, schema = hass.services.reg[("brizlabs", "set_scene")]
    a = FakeDevice("00:11:22:33:44:55")
    hass.data["brizlabs"] = {"1": a}
    await fn(SimpleNamespace(data=schema({"address": "00:11:22:33:44:55", "effect": "Loop",
                                          "combine": "2021"})))
    assert a.sent[0]["scene_combine"] == "2021"


async def test_set_scene_rejects_out_of_range():
    hass = make_hass()
    await integ.async_setup(hass, {})
    _, schema = hass.services.reg[("brizlabs", "set_scene")]
    with pytest.raises(vol.Invalid):
        schema({"address": "00:11:22:33:44:55", "effect": "Fade", "brightness": 1001})
    with pytest.raises(vol.Invalid):
        schema({"address": "00:11:22:33:44:55", "effect": "Fade", "speed": 5})


async def test_set_scene_unknown_address():
    hass = make_hass()
    await integ.async_setup(hass, {})
    fn, schema = hass.services.reg[("brizlabs", "set_scene")]
    hass.data["brizlabs"] = {}
    with pytest.raises(ValueError):
        await fn(SimpleNamespace(data=schema({"address": "x", "effect": "Fade"})))


async def test_unload_reload_cycle(monkeypatch):
    monkeypatch.setattr(integ, "BrizlabsDevice", RunnableDevice)
    hass = make_hass()
    e = entry()
    for _ in range(2):  # setup, unload, setup again
        assert await integ.async_setup_entry(hass, e)
        assert hass.data["brizlabs"][e.entry_id].address == e.data["address"]
        assert await integ.async_unload_entry(hass, e)
        assert e.entry_id not in hass.data["brizlabs"]
    assert hass.config_entries.forwarded == [["light", "number", "select"]] * 2
    assert hass.config_entries.unloaded == [["light", "number", "select"]] * 2


async def test_entity_unsubscribes_on_remove():
    from custom_components.brizlabs.select import BrizlabsMusicSelect
    dev = FakeDevice()
    sel = BrizlabsMusicSelect(dev, entry())
    removers = []
    sel.async_on_remove = removers.append
    await sel.async_added_to_hass()
    assert len(dev.listeners) == 1
    removers[0]()
    assert not dev.listeners
