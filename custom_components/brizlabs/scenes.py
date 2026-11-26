"""Codec for the BrizLabs ``scene_select`` protocol captured from the app over HCI.

Every scene change the BrizLabs app makes is a single ``thing.property.set``
carrying ``scene_select``: 17 hex characters laid out as

    scene(2) brightness(4) white_mix(4) speed(2) reserved(5)

* ``scene``: ``1e`` = loop, ``20``-``2d`` = the fourteen grid scenes
* ``brightness`` / ``white_mix``: 0-1000 (``03e8`` = maximum)
* ``speed``: 0 for the steady scenes, 1-4 for animated scenes
* ``reserved``: always ``00000``

Loop additionally writes ``scene_combine``: the hex-concatenated scene ids the
loop cycles through.  ``device_music`` (int) and ``sensitivity`` are written on
their own; ``work_mode`` is never used by the app and is ignored.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

LOOP_SCENE = 0x1E
MAX_LEVEL = 1000  # brightness / white-mix field maximum (0x3e8)
MAX_SPEED = 4

# scene id -> (name, default white mix 0-1000, default speed 0-4)
# Names are the app's scene grid labels; defaults are the app's first-write values.
SCENES: dict[int, tuple[str, int, int]] = {
    0x20: ("C1 Steady On", 1000, 0),
    0x21: ("C2 Steady On", 0, 0),
    0x22: ("Color Mixture", 500, 1),
    0x23: ("Fade", 0, 1),
    0x24: ("C1 Breath", 1000, 1),
    0x25: ("C2 Breath", 0, 1),
    0x26: ("C1 Flash", 1000, 1),
    0x27: ("C2 Flash", 0, 1),
    0x28: ("Chasing-Flash 1", 1000, 1),
    0x29: ("Chasing-Flash 2", 0, 1),
    0x2A: ("Sequential", 0, 1),
    0x2B: ("Alternating Flash", 500, 1),
    0x2C: ("Slow-Glow", 500, 1),
    0x2D: ("In Waves", 500, 1),
}
LOOP_NAME = "Loop"
MUSIC_NAME = "Music"

EFFECT_LIST = [name for name, _, _ in SCENES.values()] + [LOOP_NAME, MUSIC_NAME]
ALL_COMBINE = "".join(f"{sid:02x}" for sid in sorted(SCENES))
_NAME_TO_ID = {name: sid for sid, (name, _, _) in SCENES.items()}


@dataclass(frozen=True)
class Scene:
    scene_id: int
    brightness: int  # 0-1000
    mix: int  # 0-1000, white balance (0 = full colour, 1000 = full white)
    speed: int  # 0 = steady, 1-4 animation speed


def decode(value) -> Scene | None:
    """Parse a ``scene_select`` string; ``None`` if absent or malformed."""
    if not isinstance(value, str) or len(value) != 17:
        return None
    try:
        return Scene(int(value[0:2], 16), int(value[2:6], 16),
                     int(value[6:10], 16), int(value[10:12], 16))
    except ValueError:
        return None


def encode(scene: Scene) -> str:
    return (f"{scene.scene_id:02x}{scene.brightness:04x}"
            f"{scene.mix:04x}{scene.speed:02x}00000")


def defaults(scene_id: int) -> Scene:
    if scene_id == LOOP_SCENE:
        return Scene(LOOP_SCENE, MAX_LEVEL, 0, 1)
    _, mix, speed = SCENES[scene_id]
    return Scene(scene_id, MAX_LEVEL, mix, speed)


def scene_id_for_name(name: str) -> int:
    if name == LOOP_NAME:
        return LOOP_SCENE
    try:
        return _NAME_TO_ID[name]
    except KeyError:
        raise ValueError(f"Unknown scene effect: {name}") from None


def scene_name(scene_id: int) -> str | None:
    if scene_id == LOOP_SCENE:
        return LOOP_NAME
    entry = SCENES.get(scene_id)
    return None if entry is None else entry[0]


def _replace(value: str, **changes) -> str:
    scene = decode(value)
    if scene is None:
        raise ValueError("No active scene to modify")
    return encode(dataclasses.replace(scene, **changes))


def with_brightness(value: str, brightness: int) -> str:
    brightness = max(0, min(MAX_LEVEL, int(brightness)))
    return _replace(value, brightness=brightness)


def with_mix(value: str, mix: int) -> str:
    mix = max(0, min(MAX_LEVEL, int(mix)))
    return _replace(value, mix=mix)


def with_speed(value: str, speed: int) -> str:
    if not 0 <= speed <= MAX_SPEED:
        raise ValueError(f"speed must be 0-{MAX_SPEED}")
    return _replace(value, speed=int(speed))


def scene_properties(effect: str, brightness: int | None = None,
                     mix: int | None = None, speed: int | None = None) -> dict:
    """Property dict that starts ``effect`` at the given 0-1000 levels."""
    scene_id = scene_id_for_name(effect)
    scene = defaults(scene_id)
    if brightness is not None:
        scene = dataclasses.replace(scene, brightness=max(0, min(MAX_LEVEL, int(brightness))))
    if mix is not None:
        scene = dataclasses.replace(scene, mix=max(0, min(MAX_LEVEL, int(mix))))
    if speed is not None:
        scene = dataclasses.replace(scene, speed=max(0, min(MAX_SPEED, int(speed))))
    props = {"scene_select": encode(scene)}
    if scene_id == LOOP_SCENE:
        props["scene_combine"] = ALL_COMBINE
    return props


def effect_for_values(values: dict) -> str | None:
    """Effect name derived purely from reported/tracked device state."""
    scene = decode(values.get("scene_select"))
    if scene is not None:
        return scene_name(scene.scene_id)
    if isinstance(values.get("device_music"), int):
        return MUSIC_NAME
    return None
