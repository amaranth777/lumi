# Changelog

All notable changes to Lumi are documented here.

## [0.4.0] — 2026-06

### Added
- **缓存 TTL**（默认5分钟）— 防止 HA 事件丢失时缓存永久不刷新，可通过 `LUMI_CACHE_TTL` 环境变量配置
- **`invalidate_cache()`** — HA `state_changed` 事件触发设备图缓存立即失效
- **`/api/status`** — 运行时详情端点（设备分布/场景数/bridge冷却状态/WS连接数）
- **`lumi_device(action="status")`** — Hermes 工具新增 status action
- **Miloco client 补全** — `get_home` / `get_device_status` / `set_properties` / `get_device_graph_summary`

### Changed
- **WS 端点** — 去掉 5 秒轮询，改为纯事件驱动（HA WebSocket 推入）+ ping/pong keepalive
- **`_run_perception_async`** — 改用 `HermesBridge` 直推微信，失败时 LLM 降级兜底
- **doctor.sh** — 修复 HA token 路径截断、加 `/api/status` 检查、修 systemd 状态换行
- **install.sh** — 修复 HA token 路径截断、Lumi API 端口 18788→8810
- **README** — API 表格补全所有端点

### Tests
- 350 cases（+32 vs 0.3.0）新增覆盖：invalidate_cache、HA 事件缓存失效、Miloco 控制通道、HA WS 握手/重连、main app 入口

---

## [0.3.0] — 2026-06

### Added
- **`lumi/hermes_bridge`** — perception event → WeChat push bridge, per-event cooldown throttling, LLM fallback
- **`lumi/ha/events.py`** — HA WebSocket real-time event subscriber (replaces 5s polling, <100ms latency)
- **`lumi/perception/`** — `PerceptionEvent` model + `PerceptionAnalyzer`
- **`lumi/policy.py`** — `PolicyEngine` + `PetLitterBoxEmptyGuard`
- **`miloco_bridge/`** — Miloco → Hermes webhook bridge (agent / notify / perception actions)
- **Frontend dashboard** — HA/Miloco status cards, perception toast, WebSocket incremental state sync
- **Preset scenes** (`~/.lumi/scenes.json`) — sleep_mode / away_mode / home_mode / night_light
- **`scripts/install.sh`** + **`scripts/doctor.sh`** — deployment & diagnostics
- **`lumi_tool.py`** — Hermes tool, 9 actions: health/status/summary/search/room/scenes/run_scene/control/batch_control
- **Test suite** — 318 cases across 19 test files

### Changed
- `/health` endpoint enhanced with version, HA connectivity, device count, Miloco status
- `doctor.sh` fixed: HA token path, pytest path, `/api/status` check

### Fixed
- Policy check order: guard runs before `resolve_command`
- `collect_ignore` moved from `pyproject.toml` to `conftest.py`
- HA 502 retry logic in `ha_report.py`
- WS CSS class sync on device state update

---

## [0.2.0] — 2026-06

### Added
- Miloco MIoT control channel — set_property / call_action / toggle
- Scene presets API — GET/POST/DELETE `/api/scenes`, POST `/api/scenes/{id}/execute`
- Batch control — POST `/api/device_graph/batch/command`
- CORS + static files — frontend at `/ui`
- WebSocket — `/ws/device_graph` incremental device state updates
- Frontend — device cards, room filter, control panel

### Changed
- Miloco fusion: room inference defers to HA room data

---

## [0.1.0] — 2026-06

### Added
- `/api/device_graph` — unified device graph (HA + Miloco/MIoT fusion)
- `/api/device_graph/summary` + `/search` + `/rooms/{room}`
- `POST /api/device_graph/{id}/command` — single device control
- Room inference heuristics + device aliases config
- `lumi serve` CLI entry point (uvicorn on `:8810`)
- `systemd` user service template

---

## [0.0.1] — 2026-06

- Initial project skeleton: FastAPI app, HA client, device graph data model, pyproject.toml
