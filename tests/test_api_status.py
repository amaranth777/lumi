"""tests/test_api_status.py — /api/status 端点测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _client(summary=None, scenes=None, bridge=None, ws_connections=0):
    """返回配好 mock 的 TestClient context manager。"""
    from lumi.main import app
    from lumi.device_graph.schema import DeviceGraphSummary

    default_summary = summary or DeviceGraphSummary(
        total_devices=10,
        by_platform={"ha": 8, "miloco": 2},
        by_type={"light": 5, "switch": 3, "sensor": 2},
        rooms=["客厅", "卧室"],
    )

    mock_svc = MagicMock()
    mock_svc.get_summary.return_value = default_summary

    mock_store = MagicMock()
    mock_store.list.return_value = scenes if scenes is not None else ["scene1", "scene2"]

    import lumi.hermes_bridge as hb_mod
    mock_bridge = bridge or MagicMock()
    mock_bridge.target = "weixin"
    mock_bridge.cooldown._last_sent = {}
    mock_bridge.cooldown.remaining.return_value = 0.0

    class _CM:
        def __enter__(self):
            self._p1 = patch("lumi.deps.get_device_graph_service", return_value=mock_svc)
            self._p2 = patch("lumi.deps.get_scene_store", return_value=mock_store)
            self._p3 = patch.object(hb_mod, "get_bridge", return_value=mock_bridge)
            self._p4 = patch("lumi.main.ws_manager")
            self._p1.__enter__()
            self._p2.__enter__()
            self._p3.__enter__()
            ws = self._p4.__enter__()
            ws.active_connections = [MagicMock()] * ws_connections
            self._tc = TestClient(app, raise_server_exceptions=False)
            return self._tc

        def __exit__(self, *a):
            self._p4.__exit__(*a)
            self._p3.__exit__(*a)
            self._p2.__exit__(*a)
            self._p1.__exit__(*a)

    return _CM()


# ─── 基本结构 ─────────────────────────────────────────────────────────────────

class TestApiStatusBasic:
    def test_returns_200(self):
        with _client() as c:
            resp = c.get("/api/status")
        assert resp.status_code == 200

    def test_status_ok(self):
        with _client() as c:
            resp = c.get("/api/status")
        assert resp.json()["status"] == "ok"

    def test_version_present(self):
        with _client() as c:
            resp = c.get("/api/status")
        assert "version" in resp.json()

    def test_all_sections_present(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert "devices" in data
        assert "scenes" in data
        assert "bridge" in data
        assert "websocket" in data


# ─── devices 节 ───────────────────────────────────────────────────────────────

class TestApiStatusDevices:
    def test_total_devices(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert data["devices"]["total"] == 10

    def test_by_platform(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert data["devices"]["by_platform"]["ha"] == 8

    def test_by_type(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert data["devices"]["by_type"]["light"] == 5

    def test_rooms(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert "客厅" in data["devices"]["rooms"]

    def test_devices_error_graceful(self):
        """设备图服务异常时，返回 error 字段而不是崩溃。"""
        from lumi.main import app
        mock_svc = MagicMock()
        mock_svc.get_summary.side_effect = RuntimeError("设备图不可用")
        with patch("lumi.deps.get_device_graph_service", return_value=mock_svc), \
             patch("lumi.deps.get_scene_store", return_value=MagicMock(list=lambda: [])):
            with TestClient(app, raise_server_exceptions=False) as c:
                data = c.get("/api/status").json()
        assert "error" in data["devices"]


# ─── scenes 节 ────────────────────────────────────────────────────────────────

class TestApiStatusScenes:
    def test_scene_count(self):
        with _client(scenes=["a", "b", "c"]) as c:
            data = c.get("/api/status").json()
        assert data["scenes"]["count"] == 3

    def test_empty_scenes(self):
        with _client(scenes=[]) as c:
            data = c.get("/api/status").json()
        assert data["scenes"]["count"] == 0


# ─── bridge 节 ────────────────────────────────────────────────────────────────

class TestApiStatusBridge:
    def test_bridge_target(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert data["bridge"]["target"] == "weixin"

    def test_bridge_no_active_cooldowns(self):
        with _client() as c:
            data = c.get("/api/status").json()
        assert data["bridge"]["active_cooldowns"] == 0

    def test_bridge_active_cooldowns(self):
        """bridge 有活跃冷却时正确统计数量。"""
        from lumi.main import app
        import lumi.hermes_bridge as hb_mod

        mock_bridge = MagicMock()
        mock_bridge.target = "weixin"
        # 模拟 2 个活跃冷却
        mock_bridge.cooldown._last_sent = {"key1": 1.0, "key2": 2.0}
        mock_bridge.cooldown.remaining.side_effect = lambda k, **_: 120.0 if k in ("key1", "key2") else 0.0

        with patch("lumi.deps.get_device_graph_service", return_value=MagicMock(
            get_summary=MagicMock(return_value=MagicMock(
                total_devices=0, by_platform={}, by_type={}, rooms=[]
            ))
        )), \
             patch("lumi.deps.get_scene_store", return_value=MagicMock(list=lambda: [])), \
             patch.object(hb_mod, "get_bridge", return_value=mock_bridge):
            with TestClient(app, raise_server_exceptions=False) as c:
                data = c.get("/api/status").json()

        assert data["bridge"]["active_cooldowns"] == 2


# ─── websocket 节 ─────────────────────────────────────────────────────────────

class TestApiStatusWebSocket:
    def test_ws_connection_count_zero(self):
        with _client(ws_connections=0) as c:
            data = c.get("/api/status").json()
        assert data["websocket"]["connections"] == 0

    def test_ws_connection_count_nonzero(self):
        with _client(ws_connections=3) as c:
            data = c.get("/api/status").json()
        assert data["websocket"]["connections"] == 3
