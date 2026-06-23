"""tests/test_websocket_endpoint.py — websocket_device_graph endpoint 测试。

使用 TestClient WebSocket 上下文管理器，直接连接 FastAPI app。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from lumi.main import app
from lumi.device_graph.schema import DeviceGraph, DeviceGraphSummary


def _make_mock_service(devices=None):
    """构造返回空图的 mock service。"""
    svc = MagicMock()
    graph = DeviceGraph(devices=devices or [], summary=DeviceGraphSummary(
        total_devices=len(devices or []),
        by_platform={},
        by_type={},
        rooms=[],
    ))
    svc.get_graph.return_value = graph
    return svc


# ─── 初始快照 ─────────────────────────────────────────────────────────────────

class TestWebSocketSnapshot:
    def test_receives_snapshot_on_connect(self):
        """连接后立即收到 type=snapshot 消息。"""
        svc = _make_mock_service()
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    msg = ws.receive_json()
                    assert msg["type"] == "snapshot"
                    assert "data" in msg

    def test_snapshot_contains_devices_key(self):
        """snapshot 的 data 里有 devices 字段。"""
        svc = _make_mock_service()
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    msg = ws.receive_json()
                    assert "devices" in msg["data"]

    def test_snapshot_calls_get_graph(self):
        """连接时调用了 service.get_graph()。"""
        svc = _make_mock_service()
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    ws.receive_json()  # 消费快照
        svc.get_graph.assert_called()


# ─── ping/pong ────────────────────────────────────────────────────────────────

class TestWebSocketPingPong:
    def test_ping_receives_pong(self):
        """客户端发送 ping，应收到 pong。"""
        svc = _make_mock_service()
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    ws.receive_json()  # 消费初始快照
                    ws.send_text("ping")
                    resp = ws.receive_text()
                    assert resp == "pong"

    def test_non_ping_message_no_pong(self):
        """发送非 ping 消息，不应收到 pong（连接保持但无回复）。"""
        svc = _make_mock_service()
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    ws.receive_json()  # 消费初始快照
                    ws.send_text("hello")
                    # 断开连接，不期待 pong
                    ws.close()


# ─── 连接管理 ─────────────────────────────────────────────────────────────────

class TestWebSocketConnectionManagement:
    def test_connection_added_to_manager(self):
        """连接建立时，manager.active_connections 增加。"""
        from lumi.websocket import manager
        svc = _make_mock_service()

        before = len(manager.active_connections)
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    ws.receive_json()
                    during = len(manager.active_connections)

        assert during > before

    def test_connection_removed_after_disconnect(self):
        """连接断开后，manager.active_connections 恢复原数量。"""
        from lumi.websocket import manager
        svc = _make_mock_service()

        before = len(manager.active_connections)
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    ws.receive_json()

        after = len(manager.active_connections)
        assert after == before

    def test_multiple_simultaneous_connections(self):
        """多个客户端同时连接，各自收到独立快照。"""
        svc = _make_mock_service()
        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws1, \
                     client.websocket_connect("/ws/device_graph") as ws2:
                    msg1 = ws1.receive_json()
                    msg2 = ws2.receive_json()
                    assert msg1["type"] == "snapshot"
                    assert msg2["type"] == "snapshot"


# ─── 错误处理 ─────────────────────────────────────────────────────────────────

class TestWebSocketErrorHandling:
    def test_service_error_sends_error_message(self):
        """get_graph 抛异常时，客户端收到 type=error 消息。"""
        svc = MagicMock()
        svc.get_graph.side_effect = RuntimeError("设备图获取失败")

        with patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.websocket.get_device_graph_service", return_value=svc):
            with TestClient(app) as client:
                with client.websocket_connect("/ws/device_graph") as ws:
                    msg = ws.receive_json()
                    assert msg["type"] == "error"
                    assert "设备图获取失败" in msg["message"]
