"""HA WebSocket 事件订阅器。

订阅 HA 的 state_changed 事件，实时推送到 Lumi WebSocket 客户端。
相比轮询（每 5 秒），延迟从 ~2.5s 降到 <100ms。

用法（在 FastAPI lifespan 里启动）：
    from lumi.ha.events import start_ha_event_listener
    asyncio.create_task(start_ha_event_listener(ha_client, ws_manager))
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from lumi.ha.client import HAClient
    from lumi.websocket import ConnectionManager


async def start_ha_event_listener(
    ha_client: "HAClient",
    ws_manager: "ConnectionManager",
    reconnect_delay: float = 5.0,
) -> None:
    """持续订阅 HA WebSocket 事件，断线自动重连。"""
    import websockets  # type: ignore

    ws_url = ha_client.base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/api/websocket"

    while True:
        try:
            logger.info("连接 HA WebSocket: %s", ws_url)
            async with websockets.connect(ws_url, ping_interval=30) as ws:
                # 1. 收 auth_required
                msg = json.loads(await ws.recv())
                if msg.get("type") != "auth_required":
                    logger.warning("HA WS 握手异常: %s", msg)
                    continue

                # 2. 发 auth
                await ws.send(json.dumps({
                    "type": "auth",
                    "access_token": ha_client.token,
                }))
                msg = json.loads(await ws.recv())
                if msg.get("type") != "auth_ok":
                    logger.error("HA WS 认证失败: %s", msg)
                    await asyncio.sleep(reconnect_delay)
                    continue

                logger.info("HA WebSocket 认证成功，HA version=%s", msg.get("ha_version"))

                # 3. 订阅 state_changed 事件
                await ws.send(json.dumps({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "state_changed",
                }))
                msg = json.loads(await ws.recv())
                if not msg.get("success"):
                    logger.error("HA WS 订阅失败: %s", msg)
                    await asyncio.sleep(reconnect_delay)
                    continue

                logger.info("HA state_changed 订阅成功")

                # 4. 持续接收事件
                async for raw in ws:
                    try:
                        await _handle_ha_event(json.loads(raw), ws_manager)
                    except Exception as e:
                        logger.warning("处理 HA 事件失败: %s", e)

        except Exception as e:
            logger.warning("HA WebSocket 断线: %s，%gs 后重连", e, reconnect_delay)
            await asyncio.sleep(reconnect_delay)


async def _handle_ha_event(
    msg: dict[str, Any],
    ws_manager: "ConnectionManager",
) -> None:
    """处理单条 HA state_changed 事件，推送到 Lumi WebSocket 客户端。"""
    if msg.get("type") != "event":
        return

    event = msg.get("event", {})
    if event.get("event_type") != "state_changed":
        return

    data = event.get("data", {})
    entity_id: str = data.get("entity_id", "")
    new_state: dict = data.get("new_state") or {}
    old_state: dict = data.get("old_state") or {}

    new_val = new_state.get("state", "")
    old_val = old_state.get("state", "")

    if new_val == old_val:
        return  # 无实质变化，跳过

    logger.debug("HA state_changed: %s %s → %s", entity_id, old_val, new_val)

    # 广播设备状态变更到所有 WS 客户端
    await ws_manager.broadcast({
        "type": "update",
        "data": {
            "changed_devices": {entity_id: new_val},
            "timestamp": new_state.get("last_changed"),
            "source": "ha_event",
        },
    })
