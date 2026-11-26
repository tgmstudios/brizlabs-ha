import pytest
from custom_components.brizlabs import scenes


def test_fixture_shape(app_writes):
    assert len(app_writes) == 37


def test_roundtrip_all_captured_scene_selects(app_writes):
    for item in app_writes:
        value = item.get("scene_select")
        if value is None:
            continue
        state = scenes.decode(value)
        assert state is not None, item
        assert scenes.encode(state) == value, item


def test_layout_fields():
    # scene 25 (C2 Breath), brightness 03e8, mix 0000, speed 1
    s = scenes.decode("2503e800000100000")
    assert (s.scene_id, s.brightness, s.mix, s.speed) == (0x25, 1000, 0, 1)
    # brightness slider mid-drag: 01ec = 492
    assert scenes.decode("2501ec00000100000").brightness == 492


@pytest.mark.parametrize("bad", ["", "zz", "2503e8", "2503e80000010000", "2503e8000001000000",
                                 "2503e80000zz00000", 17 * "g", None, 12])
def test_decode_rejects_malformed(bad):
    assert scenes.decode(bad) is None


def test_every_scene_default_matches_first_app_write(app_writes):
    first = {}
    for item in app_writes:
        value = item.get("scene_select")
        if value and value[:2] not in first:
            first[value[:2]] = value
    for scene_id, payload in first.items():
        name = scenes.scene_name(int(scene_id, 16))
        assert name is not None, scene_id
        props = scenes.scene_properties(name)
        # the app's first tap of each tile is exactly our default payload
        assert props["scene_select"] == payload, (scene_id, name, payload)


def test_effect_list_is_grid_order_plus_loop_and_music():
    assert scenes.EFFECT_LIST[:2] == ["C1 Steady On", "C2 Steady On"]
    assert scenes.EFFECT_LIST[-2:] == ["Loop", "Music"]
    assert len(scenes.EFFECT_LIST) == len(set(scenes.EFFECT_LIST)) == 16


def test_loop_default_carries_full_combine():
    props = scenes.scene_properties("Loop")
    assert props["scene_select"] == "1e03e800000100000"
    assert props["scene_combine"] == "202122232425262728292a2b2c2d"


def test_with_helpers_keep_other_fields():
    base = "2203e801f40100000"
    assert scenes.with_brightness(base, 492) == "2201ec01f40100000"
    assert scenes.with_mix(base, 140) == "2203e8008c0100000"
    assert scenes.with_speed(base, 4) == "2203e801f40400000"


def test_with_helpers_clamp_levels():
    base = "2203e801f40100000"
    assert scenes.with_brightness(base, 5000) == "2203e801f40100000"
    assert scenes.with_mix(base, -5) == "2203e800000100000"


def test_with_speed_validation():
    with pytest.raises(ValueError):
        scenes.with_speed("2203e801f40100000", 5)
    with pytest.raises(ValueError):
        scenes.with_brightness("nope", 10)


def test_scene_properties_overrides():
    props = scenes.scene_properties("Color Mixture", brightness=500, mix=100, speed=3)
    assert scenes.decode(props["scene_select"]) == scenes.Scene(0x22, 500, 100, 3)
    assert "scene_combine" not in props


def test_effect_for_values():
    assert scenes.effect_for_values({"scene_select": "2d03e801f40100000"}) == "In Waves"
    assert scenes.effect_for_values({"scene_select": "1e03e800000100000"}) == "Loop"
    assert scenes.effect_for_values({"device_music": 3}) == "Music"
    assert scenes.effect_for_values({}) is None
    assert scenes.effect_for_values({"scene_select": "ff03e800000100000"}) is None


def test_scene_id_for_name_roundtrip():
    for name in scenes.EFFECT_LIST:
        if name == scenes.MUSIC_NAME:
            continue
        assert scenes.scene_name(scenes.scene_id_for_name(name)) == name
    with pytest.raises(ValueError):
        scenes.scene_id_for_name("Nope")
