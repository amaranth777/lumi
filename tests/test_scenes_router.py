"""scenes/router.py HTTP API 测试。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from lumi.scenes.router import router as scenes_router
from lumi.device_graph.router import router as device_graph_router
from lumi.scenes.store import Scene, SceneAction, SceneStore
from lumi.device_graph.service import DeviceGraphService
from lumi.device_graph.schema import Device, DeviceGraph
from lumi.deps import get_scene_store, get_device_graph_service


# ─── 测试 App 工厂 ────────────────────────────────────────────────────────────

def _make_app(store: SceneStore, device_svc: DeviceGraphService | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(scenes_router)
    app.include_router(device_graph_router)
    app.dependency_overrides[get_scene_store] = lambda: store
    if device_svc:
        app.dependency_overrides[get_device_graph_service] = lambda: device_svc
    return app


def _make_store(*scenes: Scene) -> SceneStore:
    store = SceneStore.__new__(SceneStore)
    store._path = None  # 不持久化
    store._scenes = {s.id: s for s in scenes}
    store._save = lambda: None  # 禁用文件写入
    return store


def _make_scene(sid: str = "test_scene", name: str = "测试场景") -> Scene:
    return Scene(
        id=sid,
        name=name,
        icon="mdi:home",
        actions=[
            SceneAction(device_id="light.living", command="turn_on", params={}),
        ],
    )


def _make_device_svc(*devices: Device) -> DeviceGraphService:
    svc = DeviceGraphService.__new__(DeviceGraphService)
    svc.ha_client = None
    svc.miloco_client = None
    svc.aliases = []
    from lumi.device_graph.policy import build_default_policy_engine
    svc.policy_engine = build_default_policy_engine()
    svc._cached_graph = DeviceGraph(devices=list(devices), rooms={})
    return svc


# ─── GET /api/scenes ─────────────────────────────────────────────────────────

class TestListScenes:
    def test_empty_list(self):
        app = _make_app(_make_store())
        with TestClient(app) as c:
            resp = c.get("/api/scenes")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_scenes(self):
        store = _make_store(_make_scene("s1"), _make_scene("s2"))
        app = _make_app(store)
        with TestClient(app) as c:
            resp = c.get("/api/scenes")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ─── GET /api/scenes/{id} ─────────────────────────────────────────────────────

class TestGetScene:
    def test_existing_scene(self):
        store = _make_store(_make_scene("sleep_mode", "睡眠模式"))
        app = _make_app(store)
        with TestClient(app) as c:
            resp = c.get("/api/scenes/sleep_mode")
        assert resp.status_code == 200
        assert resp.json()["name"] == "睡眠模式"

    def test_nonexistent_scene_returns_404(self):
        app = _make_app(_make_store())
        with TestClient(app) as c:
            resp = c.get("/api/scenes/ghost_scene")
        assert resp.status_code == 404


# ─── POST /api/scenes ─────────────────────────────────────────────────────────

class TestCreateScene:
    def test_create_new_scene(self):
        store = _make_store()
        app = _make_app(store)
        payload = {
            "id": "new_scene",
            "name": "新场景",
            "icon": "mdi:star",
            "actions": [
                {"device_id": "light.x", "command": "turn_on", "params": {}}
            ]
        }
        with TestClient(app) as c:
            resp = c.post("/api/scenes", json=payload)
        assert resp.status_code == 200
        assert resp.json()["id"] == "new_scene"
        assert store.get("new_scene") is not None

    def test_update_existing_scene(self):
        store = _make_store(_make_scene("s1", "原始名"))
        app = _make_app(store)
        payload = {
            "id": "s1",
            "name": "新名字",
            "actions": []
        }
        with TestClient(app) as c:
            resp = c.post("/api/scenes", json=payload)
        assert resp.status_code == 200
        assert store.get("s1").name == "新名字"


# ─── DELETE /api/scenes/{id} ─────────────────────────────────────────────────

class TestDeleteScene:
    def test_delete_existing(self):
        store = _make_store(_make_scene("to_delete"))
        app = _make_app(store)
        with TestClient(app) as c:
            resp = c.delete("/api/scenes/to_delete")
        assert resp.status_code == 200
        assert store.get("to_delete") is None

    def test_delete_nonexistent_returns_404(self):
        app = _make_app(_make_store())
        with TestClient(app) as c:
            resp = c.delete("/api/scenes/ghost")
        assert resp.status_code == 404


# ─── POST /api/scenes/{id}/execute ───────────────────────────────────────────

class TestExecuteScene:
    def test_execute_with_real_devices(self):
        store = _make_store(_make_scene("night_light"))
        device_svc = _make_device_svc(
            Device(id="light.living", name="客厅灯", type="light",
                   platform="ha", state="off", attributes={})
        )
        device_svc.ha_client = MagicMock()
        device_svc.ha_client.call_service.return_value = True

        app = _make_app(store, device_svc)
        with TestClient(app) as c:
            resp = c.post("/api/scenes/night_light/execute")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["success"] == 1

    def test_execute_nonexistent_scene_returns_404(self):
        app = _make_app(_make_store(), _make_device_svc())
        with TestClient(app) as c:
            resp = c.post("/api/scenes/nonexistent/execute")
        assert resp.status_code == 404

    def test_execute_empty_scene(self):
        store = _make_store(Scene(id="empty", name="空场景", actions=[]))
        app = _make_app(store, _make_device_svc())
        with TestClient(app) as c:
            resp = c.post("/api/scenes/empty/execute")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
