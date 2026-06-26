"""增量刷新能力测试。

覆盖：
- HAClient.get_states_since() 过滤逻辑
- DeviceGraphService.refresh_incremental() 更新设备数
- DeviceGraphService.refresh_incremental() 当无缓存时返回 0
- POST /api/device_graph/refresh_incremental 端点
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi.device_graph.router import router
from lumi.device_graph.schema import Device, DeviceGraph
from lumi.device_graph.service import DeviceGraphService
from lumi.deps import get_device_graph_service
from lumi.ha.client import HAClient


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

def _ha_client(tmp_path: Path, token: str = "tok") -> HAClient:
    tf = tmp_path / "ha_token"
    tf.write_text(token)
    return HAClient(
        base_url="http://ha.local:8123",
        token_file=str(tf),
        retries=1,
        retry_delay=0.0,
    )


def _make_device(
    device_id: str = "light.test",
    dtype: str = "light",
    state: str = "off",
    room: str | None = None,
) -> Device:
    return Device(
        id=device_id,
        name=device_id,
        type=dtype,
        platform="ha",
        state=state,
        attributes={},
        room=room,
    )


def _make_service_with_devices(*devices: Device, ha_client=None) -> DeviceGraphService:
    svc = DeviceGraphService.__new__(DeviceGraphService)
    svc.ha_client = ha_client
    svc.miloco_client = None
    svc.aliases = []
    from lumi.device_graph.policy import build_default_policy_engine
    svc.policy_engine = build_default_policy_engine()
    svc.cache_ttl = 3600
    svc._cache_time = time.monotonic()
    svc.alias_configs = []
    rooms: dict[str, list[str]] = {}
    for d in devices:
        if d.room:
            rooms.setdefault(d.room, []).append(d.id)
    svc._cached_graph = DeviceGraph(devices=list(devices), rooms=rooms)
    return svc


def _make_app_with_service(service: DeviceGraphService) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_device_graph_service] = lambda: service
    return app


# ─── HAClient.get_states_since() ──────────────────────────────────────────────

class TestGetStatesSince:
    def _states(self):
        """三条假实体，last_changed 分布在不同时间。"""
        now = datetime.now(tz=timezone.utc)
        return [
            {
                "entity_id": "light.old",
                "state": "off",
                "last_changed": (now - timedelta(seconds=120)).isoformat(),
            },
            {
                "entity_id": "light.recent",
                "state": "on",
                "last_changed": (now - timedelta(seconds=30)).isoformat(),
            },
            {
                "entity_id": "switch.newest",
                "state": "on",
                "last_changed": (now - timedelta(seconds=5)).isoformat(),
            },
        ]

    def test_filters_older_states(self, tmp_path):
        client = _ha_client(tmp_path)
        states = self._states()

        with patch.object(client, "get_states", return_value=states):
            since = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
            result = client.get_states_since(since)

        ids = [s["entity_id"] for s in result]
        assert "light.old" not in ids
        assert "light.recent" in ids
        assert "switch.newest" in ids

    def test_returns_all_when_since_is_old(self, tmp_path):
        client = _ha_client(tmp_path)
        states = self._states()

        with patch.object(client, "get_states", return_value=states):
            since = datetime.now(tz=timezone.utc) - timedelta(hours=1)
            result = client.get_states_since(since)

        assert len(result) == 3

    def test_returns_empty_when_since_is_future(self, tmp_path):
        client = _ha_client(tmp_path)
        states = self._states()

        with patch.object(client, "get_states", return_value=states):
            since = datetime.now(tz=timezone.utc) + timedelta(seconds=10)
            result = client.get_states_since(since)

        assert result == []

    def test_handles_missing_last_changed(self, tmp_path):
        client = _ha_client(tmp_path)
        states = [{"entity_id": "sensor.no_ts", "state": "42"}]  # no last_changed

        with patch.object(client, "get_states", return_value=states):
            since = datetime.now(tz=timezone.utc) - timedelta(seconds=60)
            result = client.get_states_since(since)

        # empty string < any ISO timestamp → filtered out
        assert result == []

    def test_naive_since_converted_to_utc(self, tmp_path):
        """since 传入带时区 datetime 时正常工作。"""
        client = _ha_client(tmp_path)
        now_utc = datetime.now(tz=timezone.utc)
        states = [
            {
                "entity_id": "light.x",
                "state": "on",
                "last_changed": (now_utc - timedelta(seconds=10)).isoformat(),
            }
        ]

        with patch.object(client, "get_states", return_value=states):
            since = now_utc - timedelta(seconds=30)
            result = client.get_states_since(since)

        assert len(result) == 1


# ─── DeviceGraphService.refresh_incremental() ─────────────────────────────────

class TestRefreshIncremental:
    def test_returns_zero_when_no_cache(self):
        svc = DeviceGraphService.__new__(DeviceGraphService)
        svc.ha_client = MagicMock()
        svc._cached_graph = None
        assert svc.refresh_incremental() == 0

    def test_returns_zero_when_no_ha_client(self):
        dev = _make_device("light.a", state="off")
        svc = _make_service_with_devices(dev)
        svc.ha_client = None
        assert svc.refresh_incremental() == 0

    def test_updates_changed_devices(self):
        dev = _make_device("light.living", state="off")
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = [
            {"entity_id": "light.living", "state": "on", "last_changed": "2024-01-01T00:00:00+00:00"},
        ]
        svc = _make_service_with_devices(dev, ha_client=mock_ha)

        count = svc.refresh_incremental(since_seconds=60)

        assert count == 1
        updated_dev = next(d for d in svc._cached_graph.devices if d.id == "light.living")
        assert updated_dev.state == "on"

    def test_skips_entities_not_in_graph(self):
        dev = _make_device("light.known", state="off")
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = [
            {"entity_id": "sensor.unknown", "state": "42", "last_changed": "2024-01-01T00:00:00+00:00"},
        ]
        svc = _make_service_with_devices(dev, ha_client=mock_ha)

        count = svc.refresh_incremental(since_seconds=60)

        assert count == 0  # unknown entity → not updated

    def test_updates_multiple_devices(self):
        devs = [
            _make_device("light.a", state="off"),
            _make_device("light.b", state="off"),
            _make_device("light.c", state="off"),
        ]
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = [
            {"entity_id": "light.a", "state": "on", "last_changed": "2024-01-01T00:00:00+00:00"},
            {"entity_id": "light.b", "state": "on", "last_changed": "2024-01-01T00:00:00+00:00"},
            {"entity_id": "sensor.outside", "state": "20", "last_changed": "2024-01-01T00:00:00+00:00"},
        ]
        svc = _make_service_with_devices(*devs, ha_client=mock_ha)

        count = svc.refresh_incremental(since_seconds=60)

        assert count == 2

    def test_passes_correct_since_to_ha_client(self):
        dev = _make_device("light.x", state="off")
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = []
        svc = _make_service_with_devices(dev, ha_client=mock_ha)

        svc.refresh_incremental(since_seconds=120)

        mock_ha.get_states_since.assert_called_once()
        called_since: datetime = mock_ha.get_states_since.call_args[0][0]
        now = datetime.now(tz=timezone.utc)
        delta = abs((now - called_since).total_seconds() - 120)
        assert delta < 2  # within 2s tolerance


# ─── POST /api/device_graph/refresh_incremental ───────────────────────────────

class TestRefreshIncrementalEndpoint:
    def test_returns_updated_count(self):
        dev = _make_device("light.hall", state="off")
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = [
            {"entity_id": "light.hall", "state": "on", "last_changed": "2024-01-01T00:00:00+00:00"},
        ]
        svc = _make_service_with_devices(dev, ha_client=mock_ha)
        app = _make_app_with_service(svc)

        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post("/api/device_graph/refresh_incremental", json={"since_seconds": 60})

        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] == 1
        assert "message" in data

    def test_default_since_seconds(self):
        dev = _make_device("light.x", state="off")
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = []
        svc = _make_service_with_devices(dev, ha_client=mock_ha)
        app = _make_app_with_service(svc)

        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post("/api/device_graph/refresh_incremental", json={})

        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    def test_no_cache_returns_zero(self):
        svc = DeviceGraphService.__new__(DeviceGraphService)
        svc.ha_client = MagicMock()
        svc._cached_graph = None
        svc.miloco_client = None
        svc.aliases = []
        svc.alias_configs = []
        from lumi.device_graph.policy import build_default_policy_engine
        svc.policy_engine = build_default_policy_engine()
        svc.cache_ttl = 3600
        svc._cache_time = 0.0
        app = _make_app_with_service(svc)

        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post("/api/device_graph/refresh_incremental", json={"since_seconds": 30})

        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    def test_empty_body_uses_defaults(self):
        dev = _make_device("switch.fan", state="off")
        mock_ha = MagicMock()
        mock_ha.get_states_since.return_value = [
            {"entity_id": "switch.fan", "state": "on", "last_changed": "2024-01-01T00:00:00+00:00"},
        ]
        svc = _make_service_with_devices(dev, ha_client=mock_ha)
        app = _make_app_with_service(svc)

        with TestClient(app, raise_server_exceptions=True) as c:
            resp = c.post("/api/device_graph/refresh_incremental")

        assert resp.status_code == 200
        data = resp.json()
        assert "updated" in data
        assert "message" in data
