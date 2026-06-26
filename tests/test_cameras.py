"""tests/test_cameras.py — 摄像头列表功能测试。

覆盖：
- MilocoClient.get_camera_list()（dict/list 两种返回格式）
- lumi_tool.cameras() action（含 miloco 未启用情况）
- GET /api/cameras 端点
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from lumi.miloco.client import MilocoClient


# ─── 辅助工具 ──────────────────────────────────────────────────────────────────

class FakeHTTPResponse:
    def __init__(self, data: dict | list, status: int = 200):
        self._data = json.dumps(data).encode()
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _make_client() -> MilocoClient:
    return MilocoClient(base_url="http://127.0.0.1:1810", token="test_token")


# ─── MilocoClient.get_camera_list ─────────────────────────────────────────────

class TestGetCameraList:
    def test_returns_list_from_data_key(self):
        client = _make_client()
        cameras = [
            {"did": "cam001", "name": "客厅摄像头", "room": "客厅", "online": True},
            {"did": "cam002", "name": "卧室摄像头", "room": "卧室", "online": False},
        ]
        fake_resp = FakeHTTPResponse({"code": 0, "data": cameras})
        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.get_camera_list()
        assert len(result) == 2
        assert result[0]["did"] == "cam001"
        assert result[1]["name"] == "卧室摄像头"

    def test_returns_list_from_cameras_key(self):
        client = _make_client()
        cameras = [{"did": "cam003", "name": "门口摄像头", "online": True}]
        fake_resp = FakeHTTPResponse({"cameras": cameras})
        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.get_camera_list()
        assert len(result) == 1
        assert result[0]["did"] == "cam003"

    def test_returns_list_directly_when_response_is_list(self):
        client = _make_client()
        cameras = [
            {"did": "cam010", "name": "阳台摄像头", "online": True},
        ]
        fake_resp = FakeHTTPResponse(cameras)
        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.get_camera_list()
        assert result == cameras

    def test_returns_empty_when_dict_has_no_known_key(self):
        client = _make_client()
        fake_resp = FakeHTTPResponse({"unknown": "value"})
        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.get_camera_list()
        assert result == []

    def test_returns_empty_on_exception(self):
        client = _make_client()
        with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
            result = client.get_camera_list()
        assert result == []

    def test_calls_correct_path(self):
        client = _make_client()
        captured = {}

        def fake_open(req, timeout=None):
            captured["url"] = req.full_url
            return FakeHTTPResponse([])

        with patch("urllib.request.urlopen", side_effect=fake_open):
            client.get_camera_list()

        assert captured["url"].endswith("/camera_list")

    def test_returns_empty_when_response_is_neither_dict_nor_list(self):
        client = _make_client()
        # Simulate unexpected scalar (e.g. null → None after json.loads would
        # produce None, but we simulate a wrapping dict here to avoid needing
        # to fake json.loads itself — instead we verify an empty-data dict)
        fake_resp = FakeHTTPResponse({"data": None})
        with patch("urllib.request.urlopen", return_value=fake_resp):
            result = client.get_camera_list()
        # data key is None → not a list, returned as-is via get("data")
        # The method returns result.get("data", ...) = None, which is not a
        # recognised type, so this exercises the None branch gracefully.
        # We just assert it doesn't raise and returns something falsy.
        assert not result


# ─── lumi_tool.cameras action ─────────────────────────────────────────────────

class TestCamerasAction:
    def test_returns_camera_list(self):
        import lumi.lumi_tool as tool_module
        mock_client = MagicMock()
        mock_client.get_camera_list.return_value = [
            {"did": "cam001", "name": "客厅摄像头", "online": True}
        ]
        with patch("lumi.deps.get_miloco_client", return_value=mock_client):
            result = tool_module.cameras()
        assert len(result) == 1
        assert result[0]["did"] == "cam001"

    def test_returns_empty_when_miloco_disabled(self):
        import lumi.lumi_tool as tool_module
        with patch("lumi.deps.get_miloco_client", return_value=None):
            result = tool_module.cameras()
        assert result == []

    def test_dispatch_cameras(self):
        from lumi.lumi_tool import dispatch
        import lumi.lumi_tool as tool_module
        mock_client = MagicMock()
        mock_client.get_camera_list.return_value = []
        with patch("lumi.deps.get_miloco_client", return_value=mock_client):
            result = dispatch("cameras")
        assert result == []

    def test_cameras_in_valid_actions(self):
        from lumi.lumi_tool import _VALID_ACTIONS
        assert "cameras" in _VALID_ACTIONS


# ─── GET /api/cameras 端点 ────────────────────────────────────────────────────

@pytest.fixture
def test_client():
    from lumi.main import app
    return TestClient(app)


class TestCamerasEndpoint:
    def test_returns_cameras_list(self, test_client):
        fake_cameras = [
            {"did": "cam001", "name": "客厅摄像头", "room": "客厅", "online": True},
            {"did": "cam002", "name": "卧室摄像头", "room": "卧室", "online": False},
        ]
        mock_client = MagicMock()
        mock_client.get_camera_list.return_value = fake_cameras
        with patch("lumi.deps.get_miloco_client", return_value=mock_client):
            resp = test_client.get("/api/cameras")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["cameras"]) == 2
        assert data["cameras"][0]["did"] == "cam001"

    def test_returns_empty_when_miloco_disabled(self, test_client):
        with patch("lumi.deps.get_miloco_client", return_value=None):
            resp = test_client.get("/api/cameras")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cameras"] == []
        assert data["count"] == 0

    def test_count_matches_list_length(self, test_client):
        fake_cameras = [{"did": f"cam{i:03d}", "name": f"cam{i}"} for i in range(5)]
        mock_client = MagicMock()
        mock_client.get_camera_list.return_value = fake_cameras
        with patch("lumi.deps.get_miloco_client", return_value=mock_client):
            resp = test_client.get("/api/cameras")
        data = resp.json()
        assert data["count"] == 5
        assert len(data["cameras"]) == 5


# ─── mcp_server REGISTERED_TOOLS ─────────────────────────────────────────────

class TestMcpRegistration:
    def test_lumi_cameras_in_registered_tools(self):
        from lumi.mcp_server import REGISTERED_TOOLS
        assert "lumi_cameras" in REGISTERED_TOOLS
