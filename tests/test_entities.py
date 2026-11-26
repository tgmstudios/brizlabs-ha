import pytest
from homeassistant.components.light import ColorMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.brizlabs import scenes as S
from custom_components.brizlabs.light import BrizlabsLight
from custom_components.brizlabs.number import BrizlabsNumber, BrizlabsSceneField
from custom_components.brizlabs.select import BrizlabsMusicSelect
from tests.fakes import FakeDevice, entry, scene_values


def wire(ent):
    ent.written = 0

    def w():
        ent.written += 1
    ent.async_write_ha_state = w
    ent.async_on_remove = lambda f: None
    return ent


# ---- light -------------------------------------------------------------
def test_light_reports_effect_from_scene_select():
    dev = FakeDevice(values=scene_values("In Waves"))
    light = BrizlabsLight(dev, entry())
    assert light.effect == "In Waves"
    dev.values = scene_values("C2 Steady On")
    assert light.effect == "C2 Steady On"
    dev.values = {"device_music": 4}
    assert light.effect == "Music"
    dev.values = {"switch_led": True}
    assert light.effect is None


def test_light_effect_list_is_scene_grid():
    light = BrizlabsLight(FakeDevice(), entry())
    assert light.effect_list == S.EFFECT_LIST
    assert "Color Mixture" in light.effect_list and "Loop" in light.effect_list


def test_light_unique_id_unchanged():
    assert BrizlabsLight(FakeDevice("00:11:22:33:44:55"), entry()).unique_id == "001122334455"


def test_light_is_brightness_only():
    light = BrizlabsLight(FakeDevice(), entry())
    assert light.supported_color_modes == {ColorMode.BRIGHTNESS}


@pytest.mark.asyncio
async def test_turn_on_plain_sends_only_switch():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_on()
    assert dev.sent == [{"switch_led": True}]


@pytest.mark.asyncio
async def test_turn_on_scene_effect_sends_app_default():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_on(effect="Color Mixture")
    assert dev.sent == [{"switch_led": True, "scene_select": "2203e801f40100000"}]


@pytest.mark.asyncio
async def test_turn_on_loop_includes_combine():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_on(effect="Loop")
    assert dev.sent[0]["scene_select"] == "1e03e800000100000"
    assert dev.sent[0]["scene_combine"] == S.ALL_COMBINE


@pytest.mark.asyncio
async def test_turn_on_music_effect_sends_device_music():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_on(effect="Music")
    assert dev.sent == [{"switch_led": True, "device_music": 0}]


@pytest.mark.asyncio
async def test_turn_on_brightness_merges_into_active_scene():
    dev = FakeDevice(values=scene_values("C2 Breath"))
    await BrizlabsLight(dev, entry()).async_turn_on(brightness=126)  # ~49%
    payload = dev.sent[0]["scene_select"]
    assert S.decode(payload).brightness == round(126 * 1000 / 255)
    assert S.decode(payload).scene_id == 0x25


@pytest.mark.asyncio
async def test_turn_on_brightness_without_scene_falls_back_to_bright_value():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_on(brightness=128)
    assert dev.sent == [{"switch_led": True, "bright_value": 50}]


@pytest.mark.asyncio
async def test_turn_on_effect_with_brightness():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_on(effect="Fade", brightness=51)
    assert S.decode(dev.sent[0]["scene_select"]).brightness == 200


@pytest.mark.asyncio
async def test_turn_off():
    dev = FakeDevice()
    await BrizlabsLight(dev, entry()).async_turn_off()
    assert dev.sent == [{"switch_led": False}]


def test_light_brightness_tracks_scene_select():
    dev = FakeDevice(values={"scene_select": "2501ec00000100000"})  # 492/1000
    assert BrizlabsLight(dev, entry()).brightness == round(492 * 255 / 1000)


def test_light_extra_attributes_expose_scene():
    dev = FakeDevice(values=scene_values("Slow-Glow"))
    attrs = BrizlabsLight(dev, entry()).extra_state_attributes
    assert attrs["white_mix"] == 50
    assert attrs["scene_speed"] == 1
    assert attrs["scene_select"] == "2c03e801f40100000"


# ---- numbers -----------------------------------------------------------
def test_mic_sensitivity_number():
    dev = FakeDevice(values={"sensitivity": 73})
    num = wire(BrizlabsNumber(dev, "sensitivity", 0, 100, "Mic sensitivity"))
    assert num.available and num.native_value == 73


@pytest.mark.asyncio
async def test_mic_sensitivity_set():
    dev = FakeDevice(values={"sensitivity": 0})
    num = BrizlabsNumber(dev, "sensitivity", 0, 100, "Mic sensitivity")
    await num.async_set_native_value(73)
    assert dev.sent == [{"sensitivity": 73}]


def test_white_mix_reads_percent():
    dev = FakeDevice(values=scene_values("Color Mixture"))
    num = wire(BrizlabsSceneField(dev, "mix", "White mix", 10))
    assert num.available and num.native_value == 50


@pytest.mark.asyncio
async def test_white_mix_set_writes_scaled():
    dev = FakeDevice(values=scene_values("Color Mixture"))
    num = BrizlabsSceneField(dev, "mix", "White mix", 10)
    await num.async_set_native_value(14)
    assert dev.sent == [{"scene_select": "2203e8008c0100000"}]


def test_scene_speed_reads():
    dev = FakeDevice(values=scene_values("C2 Breath"))
    num = wire(BrizlabsSceneField(dev, "speed", "Scene speed", 1))
    assert num.available and num.native_value == 1


@pytest.mark.asyncio
async def test_scene_speed_set():
    dev = FakeDevice(values=scene_values("C2 Breath"))
    num = BrizlabsSceneField(dev, "speed", "Scene speed", 1)
    await num.async_set_native_value(3)
    assert dev.sent == [{"scene_select": "2503e800000300000"}]


@pytest.mark.asyncio
async def test_scene_field_without_scene_errors():
    dev = FakeDevice()
    num = BrizlabsSceneField(dev, "mix", "White mix", 10)
    with pytest.raises(HomeAssistantError):
        await num.async_set_native_value(50)


def test_scene_field_unavailable_without_scene():
    num = wire(BrizlabsSceneField(FakeDevice(), "speed", "Scene speed", 1))
    assert not num.available


# ---- music select --------------------------------------------------------
def test_music_select_available_while_connected():
    sel = wire(BrizlabsMusicSelect(FakeDevice(), entry()))
    assert sel.available  # device_music is never reported; control stays usable
    assert sel.current_option is None


def test_music_select_tracks_state():
    dev = FakeDevice(values={"device_music": 2})
    sel = wire(BrizlabsMusicSelect(dev, entry()))
    assert sel.current_option == "Classical"


@pytest.mark.asyncio
async def test_music_select_sends_bare_device_music():
    dev = FakeDevice()
    sel = BrizlabsMusicSelect(dev, entry())
    await sel.async_select_option("Energy")
    assert dev.sent == [{"device_music": 3}]


@pytest.mark.asyncio
async def test_music_select_rejects_unknown():
    dev = FakeDevice()
    sel = BrizlabsMusicSelect(dev, entry())
    with pytest.raises(HomeAssistantError):
        await sel.async_select_option("Opera")


# ---- subscription --------------------------------------------------------
@pytest.mark.asyncio
async def test_entities_resubscribe_pattern():
    dev = FakeDevice()
    for ent in (BrizlabsLight(dev, entry()), BrizlabsMusicSelect(dev, entry())):
        removers = []
        ent.async_on_remove = removers.append
        await ent.async_added_to_hass()
    assert len(dev.listeners) == 2
