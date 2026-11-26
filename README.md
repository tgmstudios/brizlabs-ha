# BrizLabs Micro String Lights (Home Assistant, local Bluetooth)

Custom integration v0.4.0, for BrizLabs RY micro string lights over BLE via BlueZ. No cloud.

**Status:** v0.4.0. The scene protocol was captured from the official iOS app over Bluetooth HCI and re-verified on real hardware: every scene, brightness level, colour/white balance, speed, loop sequence, and music mode in this integration maps to a frame the app itself sends. 61 automated tests replay the captured app traffic against a fake device. Unofficial, not affiliated with BrizLabs or Tuya.

## Installation
### HACS (custom repository)
Requires [HACS](https://www.hacs.dev/). This repository is **not** in the HACS default catalog, so add it manually:

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tgmstudios&repository=brizlabs-ha&category=integration)

1. HACS → ⋮ (top right) → **Custom repositories**, or use the badge above.
2. Repository: `https://github.com/tgmstudios/brizlabs-ha`, Type: **Integration**, then **Add**.
3. Find **BrizLabs Micro String Lights** in HACS, **Download**, and restart Home Assistant.
4. Settings → Devices & services → **Add integration** → BrizLabs Micro String Lights.
Requires a Bluetooth adapter reachable by BlueZ and `bleak`. Declared Home Assistant minimum (`hacs.json`) is 2026.8.2; tested on 2026.8.2 and 2026.11.3 (bleak 3.0.2).

### Manual
Copy `custom_components/brizlabs` into your Home Assistant `config/custom_components/` directory, restart, then add the integration.

HACS installs from the latest GitHub release if one exists, otherwise from the default branch. Packaging checks (HACS validation, hassfest, tests) run in GitHub Actions.

## What changed in v0.4.0
v0.3 controlled scenes through `dreamlight_scene_mode` / `work_mode` payloads inferred from a related product. An HCI capture of the official app proved the actual protocol is different: scenes are a single `scene_select` string, `work_mode` is never written, and brightness, colour/white balance, and speed all ride inside `scene_select`. v0.4.0 replaces the old codec end to end. The palette and direction selects, `paint_segments`, HS colour, and the pixel-count number are removed (they belong to the old codec and the device ignores them). Light unique IDs are unchanged, so existing automations keep working.

## Entities
- **Light** – on/off, brightness, and an *effect* list: the 14 app scene tiles (`C1 Steady On`, `C2 Steady On`, `Color Mixture`, `Fade`, `C1 Breath`, `C2 Breath`, `C1 Flash`, `C2 Flash`, `Chasing-Flash 1`, `Chasing-Flash 2`, `Sequential`, `Alternating Flash`, `Slow-Glow`, `In Waves`), plus `Loop` and `Music`. Choosing an effect sends the same frame the app sends when the tile is tapped. Setting brightness while a scene is active updates the brightness field inside `scene_select` (the app's own behaviour); with no scene active it falls back to `bright_value`.
- **White mix** (number, 0–100 %) – the colour↔white balance field of the active scene (0 = full colour, 100 = full white). Available while a scene is active.
- **Scene speed** (number, 1–4) – animation speed of the active scene. Available while a scene is active.
- **Music sensitivity** (number, 0–100) – microphone sensitivity for music mode.
- **Music mode** (select) – `Rock & Roll`, `Jazz`, `Classical`, `Energy`, `Roll`, `Pop`, `Rock`, `Kpop` (`device_music` 0–7, verified by ordered capture). Usable whenever the device is connected; the selection is tracked locally because the device never reports `device_music` back.

## Services
- `brizlabs.set_scene` – `address`, `effect` (scene name), optional `brightness` (0–1000), `mix` (0–1000), `speed` (0–4), and `combine` (loop sequence as concatenated scene hex ids, e.g. `2021`; defaults to all 14 scenes).
- `brizlabs.set_properties` – send raw device properties (advanced; no validation).

## Protocol notes (`scene_select`)
Every scene change is one `thing.property.set` carrying `scene_select`: 17 hex characters — `scene(2) brightness(4) white_mix(4) speed(2) reserved(5)`. Scene ids are `20`–`2d` for the grid and `1e` for loop; brightness and mix are 0–1000; speed is 0 for the steady scenes and 1–4 otherwise; the reserved tail is always `00000`. Loop additionally writes `scene_combine` (the hex-concatenated ids to cycle). Music mode is a bare `device_music` write; on/off is `switch_led`. The device's own reports are unreliable (they claim stale values and omit `device_music`), so the integration tracks what it sends.

## Known limits
- The device accepts only one Bluetooth central at a time; the official app and Home Assistant cannot both be connected.
- Scene names come from the app's tile labels in grid order; effect names could change if a firmware/app revision reorders the grid.
- Tests use a fake device replaying captured app traffic; run with `pip install pytest pytest-asyncio homeassistant bleak` then `python -m pytest`.

## License
No license file is included and none has been chosen; visibility of this repository alone does not grant reuse rights.
