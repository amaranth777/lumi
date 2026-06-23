"""tests/test_main.py — Lumi FastAPI app 入口测试。

覆盖：
  - /health 端点各种 HA/Miloco 状态组合
  - lifespan 启动/关闭（HA 事件监听器）
  - 静态文件挂载
  - CORS 中间件
  - 路由注册
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _client(ha_states=None, ha_error=False, ha_disabled=False,
            miloco_available=True, miloco_disabled=False,
            listener_fn=None):
    """返回配好 mock 的 TestClient context manager。"""
    from lumi.main import app

    ha_client = None if ha_disabled else MagicMock()
    if ha_client and ha_error:
        ha_client.get_states.side_effect = RuntimeError("HA error")
    elif ha_client:
        ha_client.get_states.return_value = ha_states or []

    miloco_client = None if miloco_disabled else MagicMock()
    if miloco_client:
        miloco_client.is_available.return_value = miloco_available

    patches = [
        patch("lumi.deps.get_ha_client", return_value=ha_client),
        patch("lumi.deps.get_miloco_client", return_value=miloco_client),
    ]
    if listener_fn is not None:
        patches.append(patch("lumi.ha.events.start_ha_event_listener", listener_fn))

    class _CM:
        def __enter__(self):
            self._stack = [p.__enter__() for p in patches]
            self._tc = TestClient(app, raise_server_exceptions=False)
            return self._tc

        def __exit__(self, *a):
            for p in reversed(patches):
                p.__exit__(*a)

    return _CM()


# ─── /health — HA ok ─────────────────────────────────────────────────────────

class TestHealthHaOk:
    def test_status_ok(self):
        with _client(ha_states=[{"entity_id": f"light.x{i}"} for i in range(10)]) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["ha"] == "ok"
        assert data["device_count"] == 10
        assert data["miloco"] == "ok"

    def test_version_present(self):
        with _client() as c:
            resp = c.get("/health")
        assert "version" in resp.json()

    def test_miloco_error(self):
        with _client(miloco_available=False) as c:
            resp = c.get("/health")
        assert resp.json()["miloco"] == "error"


# ─── /health — HA error ───────────────────────────────────────────────────────

class TestHealthHaError:
    def test_ha_error_still_returns_200(self):
        with _client(ha_error=True, miloco_available=False) as c:
            resp = c.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ha"] == "error"
        assert data["miloco"] == "error"

    def test_status_still_ok_on_ha_error(self):
        with _client(ha_error=True) as c:
            resp = c.get("/health")
        assert resp.json()["status"] == "ok"


# ─── /health — disabled ───────────────────────────────────────────────────────

class TestHealthDisabled:
    def test_both_disabled(self):
        with _client(ha_disabled=True, miloco_disabled=True) as c:
            resp = c.get("/health")
        data = resp.json()
        assert data["ha"] == "disabled"
        assert data["miloco"] == "disabled"

    def test_miloco_disabled_ha_ok(self):
        with _client(ha_states=[], miloco_disabled=True) as c:
            resp = c.get("/health")
        data = resp.json()
        assert data["ha"] == "ok"
        assert data["miloco"] == "disabled"


# ─── 路由注册 ────────────────────────────────────────────────────────────────

class TestRoutes:
    def test_device_graph_routes_registered(self):
        from lumi.main import app
        paths = app.openapi()["paths"]
        assert any("/api/device_graph" in p for p in paths)

    def test_scenes_routes_registered(self):
        from lumi.main import app
        paths = app.openapi()["paths"]
        assert any("/api/scenes" in p for p in paths)

    def test_ws_route_registered(self):
        from lumi.main import app
        # WS 路由在 _IncludedRouter.original_router.routes 里
        all_routes = []
        for r in app.routes:
            inner = getattr(r, "original_router", None)
            if inner and hasattr(inner, "routes"):
                all_routes.extend(inner.routes)
        types = [type(r).__name__ for r in all_routes]
        paths = [getattr(r, "path", "") for r in all_routes]
        assert any("WebSocket" in t or "ws" in p.lower() for t, p in zip(types, paths))

    def test_health_route_registered(self):
        from lumi.main import app
        paths = app.openapi()["paths"]
        assert "/health" in paths


# ─── CORS ────────────────────────────────────────────────────────────────────

class TestCors:
    def test_cors_headers_present(self):
        with _client() as c:
            resp = c.get("/health", headers={"Origin": "http://localhost:3000"})
        assert resp.headers.get("access-control-allow-origin") in (
            "*", "http://localhost:3000"
        )

    def test_preflight_allowed(self):
        with _client() as c:
            resp = c.options(
                "/health",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert resp.status_code in (200, 204)


# ─── lifespan ────────────────────────────────────────────────────────────────

class TestLifespan:
    def test_lifespan_starts_listener_with_ha(self):
        """lifespan 在 HA 可用时启动事件监听器。"""
        from lumi.main import app
        import lumi.ha.events as ha_events_mod

        ha_client = MagicMock()
        ha_client.get_states.return_value = []
        miloco_client = MagicMock()
        miloco_client.is_available.return_value = True

        started = []
        stopped = []

        async def fake_listener(ha, ws):
            started.append(True)
            try:
                await asyncio.sleep(9999)
            except asyncio.CancelledError:
                stopped.append(True)
                raise

        with patch("lumi.deps.get_ha_client", return_value=ha_client), \
             patch("lumi.deps.get_miloco_client", return_value=miloco_client), \
             patch.object(ha_events_mod, "start_ha_event_listener", fake_listener):
            with TestClient(app, raise_server_exceptions=False):
                pass

        assert started == [True]
        assert stopped == [True]

    def test_lifespan_skips_listener_without_ha(self):
        """lifespan 在 HA 不可用时不启动事件监听器。"""
        from lumi.main import app
        import lumi.ha.events as ha_events_mod

        with patch("lumi.deps.get_ha_client", return_value=None), \
             patch("lumi.deps.get_miloco_client", return_value=None), \
             patch.object(ha_events_mod, "start_ha_event_listener") as mock_listener:
            with TestClient(app, raise_server_exceptions=False):
                pass

        mock_listener.assert_not_called()
