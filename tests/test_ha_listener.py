"""tests/test_ha_listener.py — start_ha_event_listener 重连 + 握手流程测试。"""

from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from lumi.ha.events import start_ha_event_listener


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

def _make_ha_client(base_url: str = "http://ha.local:8123", token: str = "test-token"):
    client = MagicMock()
    client.base_url = base_url
    client.token = token
    return client


def _make_ws_manager():
    mgr = MagicMock()
    mgr.broadcast = AsyncMock()
    return mgr


def _make_ws(recv_sequence: list):
    """
    构造假 WebSocket。recv_sequence 每项是 dict（自动 json.dumps）。
    序列耗尽后 async for 返回 StopAsyncIteration。
    """
    ws = MagicMock()
    ws.send = AsyncMock()

    idx = [0]

    async def _recv():
        if idx[0] >= len(recv_sequence):
            raise asyncio.CancelledError()
        item = recv_sequence[idx[0]]
        idx[0] += 1
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)

    ws.recv = _recv
    # async for raw in ws — 空事件流
    ws.__aiter__ = MagicMock(return_value=iter([]))
    return ws


def _ws_connect(ws):
    """返回可用于 `async with websockets.connect(...)` 的 mock。"""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=ws)
    cm.__aexit__ = AsyncMock(return_value=False)
    # websockets.connect() 是同步调用返回 async-cm（不是 coroutine）
    mod = MagicMock()
    mod.connect = MagicMock(return_value=cm)
    return mod


def _ws_connect_fn(fn):
    """每次 connect() 调用 fn(url) → 返回 async-cm 或抛异常。"""
    def _connect(url, **kwargs):
        return fn(url)
    mod = MagicMock()
    mod.connect = _connect
    return mod


async def _run_listener(ha, mgr, fake_ws_mod, timeout=0.15, reconnect_delay=0):
    """启动 listener task，等 timeout 秒后 cancel，忽略 CancelledError。"""
    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
        sys.modules, {"websockets": fake_ws_mod}
    ):
        task = asyncio.create_task(
            start_ha_event_listener(ha, mgr, reconnect_delay=reconnect_delay)
        )
        await asyncio.sleep(timeout)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


# ─── 认证 + 订阅 握手流程 ──────────────────────────────────────────────────────

class TestListenerAuthFlow:
    @pytest.mark.asyncio
    async def test_successful_auth_and_subscribe(self):
        """完整握手：auth_required → auth_ok → subscribe result(success)。"""
        ws = _make_ws([
            {"type": "auth_required"},
            {"type": "auth_ok", "ha_version": "2026.1.0"},
            {"id": 1, "type": "result", "success": True},
        ])
        ha = _make_ha_client()
        mgr = _make_ws_manager()

        await _run_listener(ha, mgr, _ws_connect(ws))

        calls = [json.loads(c.args[0]) for c in ws.send.call_args_list]
        assert any(c.get("type") == "auth" for c in calls), f"auth not sent, calls={calls}"
        assert any(c.get("type") == "subscribe_events" for c in calls)

    @pytest.mark.asyncio
    async def test_auth_token_sent_correctly(self):
        """auth 消息包含正确的 access_token。"""
        ws = _make_ws([
            {"type": "auth_required"},
            {"type": "auth_ok"},
            {"id": 1, "type": "result", "success": True},
        ])
        ha = _make_ha_client(token="my-secret-token")
        mgr = _make_ws_manager()

        await _run_listener(ha, mgr, _ws_connect(ws))

        calls = [json.loads(c.args[0]) for c in ws.send.call_args_list]
        auth_calls = [c for c in calls if c.get("type") == "auth"]
        assert auth_calls
        assert auth_calls[0]["access_token"] == "my-secret-token"

    @pytest.mark.asyncio
    async def test_subscribe_events_state_changed(self):
        """subscribe_events 消息的 event_type 应为 state_changed。"""
        ws = _make_ws([
            {"type": "auth_required"},
            {"type": "auth_ok"},
            {"id": 1, "type": "result", "success": True},
        ])
        ha = _make_ha_client()
        mgr = _make_ws_manager()

        await _run_listener(ha, mgr, _ws_connect(ws))

        calls = [json.loads(c.args[0]) for c in ws.send.call_args_list]
        sub_calls = [c for c in calls if c.get("type") == "subscribe_events"]
        assert sub_calls
        assert sub_calls[0]["event_type"] == "state_changed"


# ─── 握手异常分支 ─────────────────────────────────────────────────────────────

class TestListenerAuthFailure:
    @pytest.mark.asyncio
    async def test_reconnects_on_wrong_initial_message(self):
        """首条消息不是 auth_required 时，continue 重连。"""
        call_count = [0]

        def fake_connect(url):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise asyncio.CancelledError()
            ws = _make_ws([{"type": "unexpected"}])
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=ws)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        ha = _make_ha_client()
        mgr = _make_ws_manager()
        await _run_listener(ha, mgr, _ws_connect_fn(fake_connect), timeout=0.2)
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_reconnects_on_auth_failure(self):
        """auth_invalid 时，sleep 后重连。"""
        call_count = [0]

        def fake_connect(url):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise asyncio.CancelledError()
            ws = _make_ws([
                {"type": "auth_required"},
                {"type": "auth_invalid"},
            ])
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=ws)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        ha = _make_ha_client()
        mgr = _make_ws_manager()
        await _run_listener(ha, mgr, _ws_connect_fn(fake_connect), timeout=0.2)
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_reconnects_on_subscribe_failure(self):
        """订阅失败（success=False）时，sleep 后重连。"""
        call_count = [0]

        def fake_connect(url):
            call_count[0] += 1
            if call_count[0] >= 3:
                raise asyncio.CancelledError()
            ws = _make_ws([
                {"type": "auth_required"},
                {"type": "auth_ok"},
                {"id": 1, "type": "result", "success": False, "error": {"message": "denied"}},
            ])
            cm = MagicMock()
            cm.__aenter__ = AsyncMock(return_value=ws)
            cm.__aexit__ = AsyncMock(return_value=False)
            return cm

        ha = _make_ha_client()
        mgr = _make_ws_manager()
        await _run_listener(ha, mgr, _ws_connect_fn(fake_connect), timeout=0.2)
        assert call_count[0] >= 2


# ─── 断线重连 ──────────────────────────────────────────────────────────────────

class TestListenerReconnect:
    @pytest.mark.asyncio
    async def test_reconnects_on_connection_error(self):
        """WebSocket 连接失败时，sleep 后重连。"""
        call_count = [0]

        def fake_connect(url):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionRefusedError("HA 不可达")
            raise asyncio.CancelledError()

        ha = _make_ha_client()
        mgr = _make_ws_manager()
        await _run_listener(ha, mgr, _ws_connect_fn(fake_connect), timeout=0.2)
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_ws_url_constructed_correctly(self):
        """HTTP URL 正确转换为 ws:// URL。"""
        seen_urls = []

        def fake_connect(url):
            seen_urls.append(url)
            raise asyncio.CancelledError()

        ha = _make_ha_client(base_url="http://192.168.5.184:8123")
        mgr = _make_ws_manager()
        await _run_listener(ha, mgr, _ws_connect_fn(fake_connect))

        assert seen_urls
        assert seen_urls[0] == "ws://192.168.5.184:8123/api/websocket"

    @pytest.mark.asyncio
    async def test_https_url_converted_to_wss(self):
        """HTTPS URL 正确转换为 wss:// URL。"""
        seen_urls = []

        def fake_connect(url):
            seen_urls.append(url)
            raise asyncio.CancelledError()

        ha = _make_ha_client(base_url="https://ha.example.com")
        mgr = _make_ws_manager()
        await _run_listener(ha, mgr, _ws_connect_fn(fake_connect))

        assert seen_urls
        assert seen_urls[0] == "wss://ha.example.com/api/websocket"
