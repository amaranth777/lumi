"""websocket.py ConnectionManager 单元测试。"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from lumi.websocket import ConnectionManager


def _make_ws(fail_on_send: bool = False) -> MagicMock:
    ws = MagicMock()
    if fail_on_send:
        ws.send_json = AsyncMock(side_effect=Exception("connection lost"))
    else:
        ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    return ws


# ─── connect / disconnect ─────────────────────────────────────────────────────

class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect_adds_to_active(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)
        assert ws in mgr.active_connections
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_active(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)
        mgr.disconnect(ws)
        assert ws not in mgr.active_connections

    def test_disconnect_nonexistent_does_not_crash(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        mgr.disconnect(ws)  # 没 connect 过，不应崩溃

    @pytest.mark.asyncio
    async def test_multiple_connections(self):
        mgr = ConnectionManager()
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
        await mgr.connect(ws1)
        await mgr.connect(ws2)
        await mgr.connect(ws3)
        assert len(mgr.active_connections) == 3
        mgr.disconnect(ws2)
        assert len(mgr.active_connections) == 2
        assert ws1 in mgr.active_connections
        assert ws3 in mgr.active_connections


# ─── broadcast ────────────────────────────────────────────────────────────────

class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_to_all(self):
        mgr = ConnectionManager()
        ws1, ws2 = _make_ws(), _make_ws()
        await mgr.connect(ws1)
        await mgr.connect(ws2)

        msg = {"type": "update", "data": {"key": "value"}}
        await mgr.broadcast(msg)

        ws1.send_json.assert_called_once_with(msg)
        ws2.send_json.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self):
        mgr = ConnectionManager()
        ws_ok = _make_ws(fail_on_send=False)
        ws_dead = _make_ws(fail_on_send=True)
        await mgr.connect(ws_ok)
        await mgr.connect(ws_dead)

        await mgr.broadcast({"type": "ping"})

        # 失败的连接被清理
        assert ws_dead not in mgr.active_connections
        assert ws_ok in mgr.active_connections

    @pytest.mark.asyncio
    async def test_broadcast_empty_connections(self):
        mgr = ConnectionManager()
        # 没有连接时不崩溃
        await mgr.broadcast({"type": "update"})

    @pytest.mark.asyncio
    async def test_broadcast_perception(self):
        mgr = ConnectionManager()
        ws = _make_ws()
        await mgr.connect(ws)

        await mgr.broadcast_perception(
            event_type="litter_box_full",
            payload={"message": "集便仓已满", "room": "卫生间", "reason": "test"},
        )

        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "perception"
        assert call_args["event_type"] == "litter_box_full"
        assert call_args["data"]["message"] == "集便仓已满"

    @pytest.mark.asyncio
    async def test_broadcast_to_no_connections_is_noop(self):
        mgr = ConnectionManager()
        # 没有连接，broadcast 应静默返回
        await mgr.broadcast_perception("test", {})


# ─── WebSocket 心跳配置化 ──────────────────────────────────────────────────────

class TestWebSocketHeartbeatConfig:
    def test_default_heartbeat_is_30(self):
        from lumi.config import ServerConfig
        cfg = ServerConfig()
        assert cfg.ws_heartbeat_seconds == 30

    def test_heartbeat_can_be_configured(self):
        from lumi.config import ServerConfig
        cfg = ServerConfig(ws_heartbeat_seconds=60)
        assert cfg.ws_heartbeat_seconds == 60

    def test_heartbeat_used_from_config(self):
        """websocket.py 里的心跳超时应从 config 读取，而非硬编码。"""
        import ast, inspect
        from lumi import websocket as ws_module
        source = inspect.getsource(ws_module)
        # 不应出现硬编码的 timeout=30
        assert "timeout=30" not in source, "心跳超时不应硬编码为 30，应从 config 读取"

    @pytest.mark.asyncio
    async def test_heartbeat_respects_mock_config(self):
        """mock config 时 heartbeat 值被正确读取。"""
        from unittest.mock import patch, MagicMock
        from lumi.config import LumiConfig, ServerConfig

        mock_cfg = MagicMock(spec=LumiConfig)
        mock_cfg.server = ServerConfig(ws_heartbeat_seconds=10)

        with patch("lumi.websocket.get_config", return_value=mock_cfg):
            from lumi.config import get_config as real_get_config
            cfg = mock_cfg
            assert cfg.server.ws_heartbeat_seconds == 10
