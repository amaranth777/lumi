"""ha/events.py 单元测试——不依赖真实 HA WebSocket。"""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from lumi.ha.events import _handle_ha_event


# ─── Mock WS Manager ─────────────────────────────────────────────────────────

class MockWSManager:
    """记录所有广播消息的假 WS manager。"""

    def __init__(self) -> None:
        self.broadcasts: list[dict] = []

    async def broadcast(self, message: dict) -> None:
        self.broadcasts.append(message)


def _make_state_changed_msg(
    entity_id: str,
    new_state: str,
    old_state: str,
    last_changed: str = "2026-06-23T12:00:00+00:00",
) -> dict:
    return {
        "type": "event",
        "event": {
            "event_type": "state_changed",
            "data": {
                "entity_id": entity_id,
                "new_state": {
                    "state": new_state,
                    "last_changed": last_changed,
                    "attributes": {"friendly_name": entity_id},
                },
                "old_state": {
                    "state": old_state,
                    "attributes": {},
                },
            },
        },
    }


# ─── 基础功能 ─────────────────────────────────────────────────────────────────

class TestHandleHaEvent:
    @pytest.mark.asyncio
    async def test_state_changed_triggers_broadcast(self):
        mgr = MockWSManager()
        msg = _make_state_changed_msg("light.living_room", "on", "off")
        await _handle_ha_event(msg, mgr)
        assert len(mgr.broadcasts) == 1
        broadcast = mgr.broadcasts[0]
        assert broadcast["type"] == "update"
        assert "light.living_room" in broadcast["data"]["changed_devices"]
        assert broadcast["data"]["changed_devices"]["light.living_room"] == "on"
        assert broadcast["data"]["source"] == "ha_event"

    @pytest.mark.asyncio
    async def test_no_state_change_no_broadcast(self):
        """新旧状态相同时不广播。"""
        mgr = MockWSManager()
        msg = _make_state_changed_msg("switch.test", "off", "off")
        await _handle_ha_event(msg, mgr)
        assert len(mgr.broadcasts) == 0

    @pytest.mark.asyncio
    async def test_non_event_msg_ignored(self):
        """非 event 类型消息忽略。"""
        mgr = MockWSManager()
        await _handle_ha_event({"type": "result", "success": True}, mgr)
        assert len(mgr.broadcasts) == 0

    @pytest.mark.asyncio
    async def test_non_state_changed_ignored(self):
        """非 state_changed 事件类型忽略。"""
        mgr = MockWSManager()
        msg = {
            "type": "event",
            "event": {
                "event_type": "call_service",
                "data": {},
            },
        }
        await _handle_ha_event(msg, mgr)
        assert len(mgr.broadcasts) == 0

    @pytest.mark.asyncio
    async def test_timestamp_included(self):
        """广播消息包含 last_changed 时间戳。"""
        mgr = MockWSManager()
        msg = _make_state_changed_msg(
            "sensor.temp", "22.5", "22.0",
            last_changed="2026-06-23T15:30:00+00:00"
        )
        await _handle_ha_event(msg, mgr)
        assert mgr.broadcasts[0]["data"]["timestamp"] == "2026-06-23T15:30:00+00:00"

    @pytest.mark.asyncio
    async def test_null_new_state_handled(self):
        """new_state 为 None 时不崩溃（设备被删除的情况）。"""
        mgr = MockWSManager()
        msg = {
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "light.deleted",
                    "new_state": None,
                    "old_state": {"state": "on", "attributes": {}},
                },
            },
        }
        await _handle_ha_event(msg, mgr)
        # new_state 为 None，new_val 为 "" ≠ old_val "on"，会广播空状态
        # 关键是不崩溃
        # 实现里 new_state or {} 让 new_val=""，old_val="on"，会广播
        assert len(mgr.broadcasts) == 1

    @pytest.mark.asyncio
    async def test_null_old_state_handled(self):
        """old_state 为 None 时（新设备添加）不崩溃。"""
        mgr = MockWSManager()
        msg = {
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "light.new_device",
                    "new_state": {"state": "off", "last_changed": "", "attributes": {}},
                    "old_state": None,
                },
            },
        }
        await _handle_ha_event(msg, mgr)
        # old_val="" != new_val="off"，应该广播
        assert len(mgr.broadcasts) == 1
        assert mgr.broadcasts[0]["data"]["changed_devices"]["light.new_device"] == "off"

    @pytest.mark.asyncio
    async def test_multiple_events_sequential(self):
        """多个独立事件各自广播。"""
        mgr = MockWSManager()
        for i in range(3):
            msg = _make_state_changed_msg(f"light.device_{i}", "on", "off")
            await _handle_ha_event(msg, mgr)
        assert len(mgr.broadcasts) == 3

    @pytest.mark.asyncio
    async def test_state_changed_invalidates_cache(self):
        """state_changed 事件触发设备图缓存失效。"""
        from unittest.mock import MagicMock, patch
        from lumi.device_graph.service import DeviceGraphService

    @pytest.mark.asyncio
    async def test_state_changed_invalidates_cache(self):
        """state_changed 事件触发缓存更新（增量或全量）。"""
        from lumi.device_graph.service import DeviceGraphService

        svc = MagicMock(spec=DeviceGraphService)
        svc.update_device_state.return_value = True  # 增量更新成功

        mgr = MockWSManager()
        msg = _make_state_changed_msg("light.living_room", "on", "off")

        with patch("lumi.deps.get_device_graph_service", return_value=svc):
            await _handle_ha_event(msg, mgr)

        # 增量更新被调用
        svc.update_device_state.assert_called_once_with("light.living_room", "on")
        # 增量成功时不需要全量失效
        svc.invalidate_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_invalidation_failure_does_not_block_broadcast(self):
        """缓存失效失败时，广播仍然正常发送。"""
        from unittest.mock import patch

        mgr = MockWSManager()
        msg = _make_state_changed_msg("light.test", "on", "off")

        with patch("lumi.deps.get_device_graph_service", side_effect=RuntimeError("deps error")):
            await _handle_ha_event(msg, mgr)

        # 广播不受缓存失效失败的影响
        assert len(mgr.broadcasts) == 1


# ─── start_ha_event_listener ─────────────────────────────────────────────────

class TestStartHaEventListener:
    """测试 HA WebSocket 连接握手和重连逻辑（不需要真实 HA）。"""

    @pytest.mark.asyncio
    async def test_successful_auth_and_subscribe(self):
        """正常握手流程：auth_required → auth_ok → subscribe_ok → 不崩溃。"""
        from lumi.ha.events import start_ha_event_listener

        ha_client = MagicMock()
        ha_client.base_url = "http://192.168.5.184:8123"
        ha_client.token = "test_token"
        mgr = MockWSManager()

        messages = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok", "ha_version": "2026.6.0"}),
            json.dumps({"type": "result", "id": 1, "success": True}),
        ]
        msg_index = [0]

        class FakeWS:
            async def recv(self):
                i = msg_index[0]
                if i >= len(messages):
                    raise asyncio.CancelledError("消息耗尽")
                msg_index[0] += 1
                return messages[i]

            async def send(self, data):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        import sys
        mock_ws_mod = MagicMock()
        mock_ws_mod.connect.return_value = FakeWS()
        sys.modules.setdefault("websockets", mock_ws_mod)

        try:
            await asyncio.wait_for(
                start_ha_event_listener(ha_client, mgr, reconnect_delay=0),
                timeout=2.0,
            )
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass  # 正常退出

    @pytest.mark.asyncio
    async def test_reconnects_on_connection_error(self):
        """连接失败时触发重连（验证 sleep 被调用）。"""
        from lumi.ha.events import start_ha_event_listener
        import sys

        ha_client = MagicMock()
        ha_client.base_url = "http://192.168.5.184:8123"
        ha_client.token = "test_token"
        mgr = MockWSManager()

        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)
            if len(sleep_calls) >= 3:
                raise asyncio.CancelledError("测试终止")

        # 强制替换 sys.modules["websockets"] 让 connect 抛异常
        mock_ws_mod = MagicMock()
        mock_ws_mod.connect.side_effect = ConnectionRefusedError("拒绝连接")
        old_ws = sys.modules.get("websockets")
        sys.modules["websockets"] = mock_ws_mod

        try:
            with patch("asyncio.sleep", side_effect=mock_sleep):
                try:
                    await start_ha_event_listener(ha_client, mgr, reconnect_delay=0.001)
                except asyncio.CancelledError:
                    pass
        finally:
            if old_ws is not None:
                sys.modules["websockets"] = old_ws
            else:
                sys.modules.pop("websockets", None)

        assert len(sleep_calls) >= 2

    @pytest.mark.asyncio
    async def test_incremental_cache_update_on_state_changed(self):
        """state_changed 事件优先走增量更新，不做全量失效。"""
        from lumi.device_graph.service import DeviceGraphService
        import time

        svc = MagicMock(spec=DeviceGraphService)
        svc.update_device_state.return_value = True  # 增量更新成功

        mgr = MockWSManager()
        msg = _make_state_changed_msg("light.living_room", "on", "off")

        with patch("lumi.deps.get_device_graph_service", return_value=svc):
            await _handle_ha_event(msg, mgr)

        svc.update_device_state.assert_called_once_with("light.living_room", "on")
        svc.invalidate_cache.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_invalidate_when_device_not_in_cache(self):
        """增量更新找不到设备时，降级为全量 invalidate_cache。"""
        from lumi.device_graph.service import DeviceGraphService

        svc = MagicMock(spec=DeviceGraphService)
        svc.update_device_state.return_value = False  # 设备不在缓存

        mgr = MockWSManager()
        msg = _make_state_changed_msg("light.new_device", "on", "off")

        with patch("lumi.deps.get_device_graph_service", return_value=svc):
            await _handle_ha_event(msg, mgr)

        svc.update_device_state.assert_called_once()
        svc.invalidate_cache.assert_called_once()
