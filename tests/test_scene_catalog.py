import pytest
from custom_components.brizlabs import scenes


def test_scene_table_covers_ids_20_to_2d():
    assert sorted(scenes.SCENES) == list(range(0x20, 0x2E))


def test_steady_scenes_have_speed_zero():
    steady = [sid for sid, (_, _, speed) in scenes.SCENES.items() if speed == 0]
    assert steady == [0x20, 0x21]  # the two Steady On tiles


def test_mix_defaults_are_captured_values():
    assert scenes.SCENES[0x20][1] == 1000  # C1 tiles default full white
    assert scenes.SCENES[0x21][1] == 0     # C2 tiles default full colour
    assert scenes.SCENES[0x22][1] == 500   # Color Mixture mid balance


def test_names_match_app_grid():
    assert list(scenes.SCENES.values())[0][0] == "C1 Steady On"
    assert list(scenes.SCENES.values())[-1][0] == "In Waves"


def test_all_names_unique():
    names = [name for name, _, _ in scenes.SCENES.values()]
    assert len(set(names)) == len(names) == 14


def test_all_combine_is_sorted_ids():
    assert scenes.ALL_COMBINE == "".join(f"{i:02x}" for i in sorted(scenes.SCENES))
