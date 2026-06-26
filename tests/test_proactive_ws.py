"""tests/test_proactive_ws.py — ConnectionManager.broadcast_alert 测试。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from lumi.websocket import ConnectionManager


class TestBroadcastAlert:
    def test_broadcast_alert_sends_proactive_alert_type(self):
        """broadcast_alert 广播的消息 type 为 proactive_alert。"""
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager.active_connections.append(ws)

        alerts = [{"level": "warning", "device_id": "dev_1", "message": "温度异常", "action_hint": None}]
        asyncio.run(manager.broadcast_alert(alerts))

        ws.send_json.assert_called_once()
        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "proactive_alert"

    def test_broadcast_alert_includes_alerts_list(self):
        """broadcast_alert 消息包含 alerts 列表。"""
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager.active_connections.append(ws)

        alerts = [{"level": "critical", "device_id": "dev_2", "message": "设备离线", "action_hint": "重启"}]
        asyncio.run(manager.broadcast_alert(alerts))

        msg = ws.send_json.call_args[0][0]
        assert msg["alerts"] == alerts

    def test_broadcast_alert_count_matches_alerts_length(self):
        """broadcast_alert 消息中 count 与 alerts 长度一致。"""
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager.active_connections.append(ws)

        alerts = [
            {"level": "info", "device_id": "d1", "message": "m1", "action_hint": None},
            {"level": "warning", "device_id": "d2", "message": "m2", "action_hint": None},
            {"level": "critical", "device_id": "d3", "message": "m3", "action_hint": None},
        ]
        asyncio.run(manager.broadcast_alert(alerts))

        msg = ws.send_json.call_args[0][0]
        assert msg["count"] == 3

    def test_broadcast_alert_empty_list(self):
        """broadcast_alert 可接受空告警列表。"""
        manager = ConnectionManager()
        ws = MagicMock()
        ws.send_json = AsyncMock()
        manager.active_connections.append(ws)

        asyncio.run(manager.broadcast_alert([]))

        msg = ws.send_json.call_args[0][0]
        assert msg["type"] == "proactive_alert"
        assert msg["alerts"] == []
        assert msg["count"] == 0

    def test_broadcast_alert_no_connections(self):
        """无连接时 broadcast_alert 静默成功，不抛异常。"""
        manager = ConnectionManager()
        asyncio.run(manager.broadcast_alert([{"level": "info", "message": "x"}]))

    def test_broadcast_alert_broadcasts_to_all_connections(self):
        """broadcast_alert 广播到所有连接。"""
        manager = ConnectionManager()
        ws1 = MagicMock()
        ws1.send_json = AsyncMock()
        ws2 = MagicMock()
        ws2.send_json = AsyncMock()
        manager.active_connections.extend([ws1, ws2])

        asyncio.run(manager.broadcast_alert([]))

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    def test_broadcast_alert_dead_connection_removed(self):
        """broadcast_alert 遇到失效连接时将其移除。"""
        manager = ConnectionManager()
        dead_ws = MagicMock()
        dead_ws.send_json = AsyncMock(side_effect=RuntimeError("连接已断开"))
        manager.active_connections.append(dead_ws)

        asyncio.run(manager.broadcast_alert([]))

        assert dead_ws not in manager.active_connections
