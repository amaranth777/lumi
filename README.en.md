# Lumi

<p align="center"><a href="README.md">简体中文</a> | English</p>

> A private home-agent platform — unifies Miloco perception, the Home Assistant device bus, and the Hermes Agent brain into one coherent system.

---

## What is this

Lumi is neither another Home Assistant plugin nor a replacement for Miloco. It is the glue layer that binds the three together:

```
Miloco   → Perception layer: cameras, person recognition, home events
HA       → Device layer: state read/write, automation, multi-brand access
Hermes   → Brain layer: dialogue, judgment, notification, execution policy
Lumi     → Glue layer: unified device graph, policy guards, multi-source fusion
```

End result: multi-source data → unified device graph → unified analysis → policy-gated control → multi-channel execution.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              User Interaction Layer                 │
│   WeChat / Telegram / Web Dashboard / Voice         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Hermes Agent Runtime                   │
│   Dialogue · Tool calls · Scheduling · Policy guard │
└──────────────┬────────────────────────┬─────────────┘
               │                        │
               ▼                        ▼
┌──────────────────────────┐  ┌─────────────────────────┐
│   Miloco Hermes Bridge   │  │   Home Assistant API    │
│   POST /miloco/webhook   │  │   REST / WebSocket      │
└──────────────┬───────────┘  └────────────┬────────────┘
               │                           │
               └──────────┬────────────────┘
                          ▼
┌─────────────────────────────────────────────────────┐
│              Unified Device Graph                   │
│   HA entities · MIoT devices · Miloco perception    │
│   Unified rooms · states · capabilities · policies  │
└──────────────┬────────────────────────┬─────────────┘
               │                        │
               ▼                        ▼
┌──────────────────────────┐  ┌─────────────────────────┐
│      Miloco Backend      │  │    Home Assistant       │
│   Cameras · person/pet   │  │   Device states · auto  │
│   Home events · profiles │  │   History · multi-brand │
└──────────────────────────┘  └─────────────────────────┘
```

---

## Quick Start

```bash
git clone https://github.com/amaranth777/lumi.git
cd lumi
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
lumi
```

The service listens on `http://127.0.0.1:8810` by default.

Minimal config `~/.lumi/config.json`:

```json
{
  "ha": {
    "enabled": true,
    "base_url": "http://192.168.5.184:8123",
    "token_file": "~/.hermes/ha_token"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8810,
    "token": ""
  }
}
```

---

## API

Base URL: `http://127.0.0.1:8810`

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check (version / HA / Miloco connectivity / device count) |
| `GET /api/status` | Runtime details (device distribution / scene count / bridge cooldown / WS connections) |
| `GET /api/device_graph` | Full device graph |
| `GET /api/device_graph/summary` | Device graph summary (for Hermes analysis) |
| `GET /api/device_graph/types` | Device type distribution (by_type + rooms) |
| `GET /api/device_graph/search?q=` | Search devices by keyword (name/id/room/type) |
| `GET /api/device_graph/rooms/{room}` | Query devices by room |
| `POST /api/device_graph/{id}/command` | Unified device control (policy-guarded) |
| `POST /api/device_graph/batch/command` | Batch device control (concurrent) |
| `GET /api/scenes` | List all preset scenes |
| `POST /api/scenes` | Create / update a scene |
| `POST /api/scenes/{id}/execute` | Execute a scene |
| `POST /api/perception/webhook` | Receive Miloco perception webhook → analyze → notify |
| `POST /api/perception/webhook/test` | Perception webhook dry run (analyze without pushing) |
| `GET /api/perception/events/types` | List all supported perception event types |
| `WS /ws/device_graph` | Real-time state push (HA-event driven, <100ms latency) |
| `GET /ui/` | Built-in demo page |
| `GET /docs` | Auto-generated API docs |

Control example:

```bash
curl -X POST http://127.0.0.1:8810/api/device_graph/fan.airpurifier/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "turn_on", "params": {}}'
```

WebSocket real-time subscription:

```javascript
const ws = new WebSocket('ws://127.0.0.1:8810/ws/device_graph');
ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  if (type === 'snapshot') renderDevices(data);
};
```

---

## Policy Guard

High-risk actions are intercepted by the policy layer before execution, configured in the `policies` field of `device_aliases`:

```json
{
  "canonical_id": "litter_box",
  "policies": {
    "forbidden_actions": ["empty"],
    "allowed_actions": ["clean", "off"],
    "requires_precheck": true
  }
}
```

Analysis is unrestricted; execution must obey policy.

---

## Deployment

```bash
# One-click install (systemd user service)
bash scripts/install.sh

# Check status
systemctl --user status lumi.service

# Logs
journalctl --user -u lumi.service -f

# Self-check
bash scripts/doctor.sh
```

---

## Project Structure

```
lumi/
├── lumi/               # Core service (FastAPI)
├── miloco_bridge/      # Miloco ↔ Hermes bridge
├── docs/               # Architecture, config, frontend integration
├── deploy/             # systemd service templates
├── scripts/            # install.sh / doctor.sh
└── tests/
```

---

## Implementation Phases

| Phase | Goal | Status |
|-------|------|--------|
| 1 | Read-only fusion — unified HA + MIoT device graph | ✅ |
| 2 | Hermes Bridge — Miloco events → notifications | ✅ |
| 3 | Safe control — policy guard + unified device control | ✅ |
| 4 | Perception loop — camera events + HA state joint judgment | ✅ |
| 5 | Private packaging — one-click install, doctor, systemd | ✅ |

---

## Related Projects

- [Hermes Agent](https://hermes-agent.nousresearch.com) — AI brain runtime
- [Miloco](https://github.com/idootop/mi-gpt) — Xiaomi home perception platform
- [Home Assistant](https://www.home-assistant.io) — Open-source smart home platform
