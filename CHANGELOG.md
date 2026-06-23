# Changelog

All notable changes to Lumi are documented here.

## [0.3.0] — 2026-06

### Added
- **`/api/status`** runtime detail endpoint — device distribution, scene count, bridge cooldown state, WebSocket connections
- **`lumi/hermes_bridge`** — perception event → WeChat push bridge with per-event cooldown throttling and LLM fallback
- **`lumi/ha/events.py`** — HA WebSocket real-time event subscriber (replaces 5s polling, latency <100ms)
- **`lumi/perception/`** — `PerceptionEvent` model + `PerceptionAnalyzer` with full event coverage: litter_box_full/cleaned, pet_at/left_litter_box, pet_detected, person_detected, anomaly_detected, motion_detected
- **`lumi/policy.py`** — `PolicyEngine` + `PetLitterBoxEmptyGuard` (hard-blocks empty command when mode=Off or bin=Full)
- **`miloco_bridge/`** — Miloco → Hermes webhook bridge (fire-and-forget agent + notify + perception actions)
- **WebSocket broadcast** — perception event toast + incremental device state sync on frontend
- **Frontend dashboard** — HA/Miloco status cards, 30s auto-refresh, `data-device-id` attributes, CSS class sync
- **Preset scenes** (`~/.lumi/scenes.json`) — sleep_mode, away_mode, home_mode, night_light
- **`deploy/`** — `lumi.service`, `miloco-hermes-bridge.service` systemd templates
- **`scripts/install.sh`** — one-shot environment setup
- **`scripts/doctor.sh`** — environment diagnostics (Python, config, services, HTTP health, tests)
- **`~/.hermes/hermes-agent/tools/lumi_tool.py`** — Hermes tool with 9 actions: health/status/summary/search/room/scenes/run_scene/control/batch_control
- **Test suite** — 318 cases across 19 test files (0 → 318)

### Changed
- `/health` endpoint enhanced with version, HA connectivity, device count, Miloco status
- `_run_perception_async` now uses `HermesBridge` directly (HTTP gateway API) instead of LLM inference — lower latency, adds cooldown throttling
- `doctor.sh` fixed: HA token path, dynamic port detection, pytest path, `/api/status` check

### Fixed
- Policy check order in `service.py`: guard runs before `resolve_command`
- `collect_ignore` moved from `pyproject.toml` to `conftest.py` (pytest config fix)
- HA 502 retry logic in `ha_report.py` (3 retries, 5s interval)
- WS incremental update CSS class sync on device cards
- Miloco room classification: use HA room as source of truth, filter meaningless room names

---

## [0.2.0] — 2026-06

### Added
- **Miloco MIoT control channel** — set_property / call_action / toggle via Lumi API
- **Scene presets API** — GET/POST/DELETE `/api/scenes`, POST `/api/scenes/{id}/execute`
- **Batch control** — POST `/api/device_graph/batch/command`
- **CORS + static files** — frontend served from `/ui`
- **WebSocket** — `/ws/device_graph` for incremental device state updates
- **Frontend** — device cards, room filter, control panel, batch control UI

### Changed
- Miloco fusion: room inference defers to HA room data

---

## [0.1.0] — 2026-06

### Added
- **`/api/device_graph`** — unified device graph (HA + Miloco/MIoT fusion)
- **`/api/device_graph/summary`** — device count by type/room/platform
- **`/api/device_graph/search`** — keyword search (name/ID/room)
- **`/api/device_graph/rooms/{room}`** — list devices by room
- **`POST /api/device_graph/{id}/command`** — single device control (turn_on/turn_off/toggle/set_*)
- **Room inference** — heuristic room assignment from entity name/area
- **Device aliases** — manual override config in `~/.lumi/config.json`
- **`lumi serve`** CLI entry point (uvicorn on `:8810`)
- **`systemd` service** — `lumi.service` user unit

---

## [0.0.1] — 2026-06

- Initial project skeleton: FastAPI app, HA client, device graph data model, pyproject.toml
