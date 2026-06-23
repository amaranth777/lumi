"""device_graph/router.py HTTP API 测试——用 FastAPI TestClient。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi.device_graph.router import router
from lumi.device_graph.service import DeviceGraphService
from lumi.device_graph.schema import Device, DeviceGraph, DeviceGraphSummary
from lumi.deps import get_device_graph_service


# ─── 测试 App 工厂 ────────────────────────────────────────────────────────────

def _make_app_with_service(service: DeviceGraphService) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_device_graph_service] = lambda: service
    return app


def _make_service_with_devices(*devices: Device) -> DeviceGraphService:
    svc = DeviceGraphService.__new__(DeviceGraphService)
    svc.ha_client = None
    svc.miloco_client = None
    svc.aliases = []
    from lumi.device_graph.policy import build_default_policy_engine
    svc.policy_engine = build_default_policy_engine()
    rooms: dict[str, list[str]] = {}
    for d in devices:
        if d.room:
            rooms.setdefault(d.room, []).append(d.id)
    svc._cached_graph = DeviceGraph(devices=list(devices), rooms=rooms)
    return svc


def _make_device(
    device_id: str = "light.test",
    dtype: str = "light",
    state: str = "off",
    room: str | None = None,
) -> Device:
    return Device(id=device_id, name=device_id, type=dtype,
                  platform="ha", state=state, attributes={}, room=room)


# ─── GET /api/device_graph ────────────────────────────────────────────────────

class TestGetDeviceGraph:
    def test_empty_graph(self):
        app = _make_app_with_service(_make_service_with_devices())
        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.get("/api/device_graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["devices"] == []
        assert data["rooms"] == {}

    def test_returns_devices(self):
        svc = _make_service_with_devices(
            _make_device("light.a"), _make_device("switch.b", "switch")
        )
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph")
        assert resp.status_code == 200
        assert len(resp.json()["devices"]) == 2


# ─── GET /api/device_graph/summary ───────────────────────────────────────────

class TestGetSummary:
    def test_summary_counts(self):
        svc = _make_service_with_devices(
            _make_device("light.a", "light"),
            _make_device("light.b", "light"),
            _make_device("switch.c", "switch"),
        )
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_devices"] == 3
        assert data["by_type"]["light"] == 2
        assert data["by_type"]["switch"] == 1

    def test_summary_by_platform(self):
        svc = _make_service_with_devices(_make_device("light.x"))
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/summary")
        assert resp.json()["by_platform"]["ha"] == 1


# ─── GET /api/device_graph/search ────────────────────────────────────────────

class TestSearchDevices:
    def test_search_match(self):
        svc = _make_service_with_devices(_make_device("light.bedroom_lamp"))
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/search?q=bedroom")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_search_no_match(self):
        svc = _make_service_with_devices(_make_device("light.kitchen"))
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/search?q=nonexistent_xyz")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_missing_q_returns_422(self):
        svc = _make_service_with_devices()
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/search")
        assert resp.status_code == 422


# ─── GET /api/device_graph/rooms/{room} ──────────────────────────────────────

class TestGetDevicesByRoom:
    def test_room_with_devices(self):
        svc = _make_service_with_devices(_make_device("light.bedroom", room="卧室"))
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/rooms/卧室")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_nonexistent_room_returns_404(self):
        svc = _make_service_with_devices()
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.get("/api/device_graph/rooms/火星基地")
        assert resp.status_code == 404


# ─── POST /api/device_graph/{id}/command ─────────────────────────────────────

class TestExecuteCommand:
    def test_turn_on_success(self):
        from unittest.mock import MagicMock
        svc = _make_service_with_devices(_make_device("switch.desk"))
        svc.ha_client = MagicMock()
        svc.ha_client.call_service.return_value = True
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.post("/api/device_graph/switch.desk/command",
                         json={"command": "turn_on", "params": {}})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_device_not_found_returns_400(self):
        svc = _make_service_with_devices()
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.post("/api/device_graph/light.ghost/command",
                         json={"command": "turn_on", "params": {}})
        assert resp.status_code == 400

    def test_policy_blocks_returns_400(self):
        svc = _make_service_with_devices(
            _make_device("button.petjc_cn_821633016_pro_clean")
        )
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.post(
                "/api/device_graph/button.petjc_cn_821633016_pro_clean/command",
                json={"command": "empty", "params": {}}
            )
        assert resp.status_code == 400
        assert "策略" in resp.json()["detail"]

    def test_missing_command_returns_422(self):
        svc = _make_service_with_devices(_make_device("light.x"))
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.post("/api/device_graph/light.x/command", json={})
        assert resp.status_code == 422


# ─── POST /api/device_graph/batch/command ────────────────────────────────────

class TestBatchCommand:
    def test_batch_success(self):
        from unittest.mock import MagicMock
        svc = _make_service_with_devices(
            _make_device("light.a"), _make_device("light.b")
        )
        svc.ha_client = MagicMock()
        svc.ha_client.call_service.return_value = True
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.post("/api/device_graph/batch/command", json={
                "device_ids": ["light.a", "light.b"],
                "command": "turn_off",
                "params": {}
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["success"] == 2

    def test_batch_partial_failure(self):
        from unittest.mock import MagicMock
        svc = _make_service_with_devices(_make_device("light.a"))
        svc.ha_client = MagicMock()
        svc.ha_client.call_service.return_value = True
        app = _make_app_with_service(svc)
        with TestClient(app) as c:
            resp = c.post("/api/device_graph/batch/command", json={
                "device_ids": ["light.a", "light.nonexistent"],
                "command": "turn_off",
                "params": {}
            })
        assert resp.status_code == 200
        assert resp.json()["failed"] == 1
