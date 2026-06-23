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
