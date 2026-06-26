"""WebSocket 实时推送设备状态 + 感知事件。

用于前端/屏幕实时显示设备变化和感知通知。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from lumi.deps import get_device_graph_service
from lumi.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    """管理 WebSocket 连接。"""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket 连接建立，当前连接数: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket 连接断开，当前连接数: %d", len(self.active_connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """广播消息到所有连接。"""
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning("广播失败: %s", e)
                dead_connections.append(connection)

        for conn in dead_connections:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    async def broadcast_perception(self, event_type: str, payload: dict[str, Any]) -> None:
        """广播感知事件到所有 WebSocket 客户端。"""
        await self.broadcast({
            "type": "perception",
            "event_type": event_type,
            "data": payload,
        })

    async def broadcast_alert(self, alerts: list[dict]) -> None:
        """广播主动巡检告警到所有 WebSocket 客户端。"""
        await self.broadcast({
            "type": "proactive_alert",
            "alerts": alerts,
            "count": len(alerts),
        })


manager = ConnectionManager()


@router.websocket("/device_graph")
async def websocket_device_graph(websocket: WebSocket) -> None:
    """WebSocket 端点：实时推送设备图变化 + 感知事件。

    消息格式：
    - type: "snapshot" (完整快照) | "update" (增量更新) | "perception" (感知事件) | "error"
    - data: 设备图数据或增量更新

    增量更新由 HA WebSocket 事件订阅器主动推入（<100ms 延迟），
    本端点只负责发初始快照并保持连接存活。
    """
    await manager.connect(websocket)
    service = get_device_graph_service()

    try:
        # 初始快照
        graph = service.get_graph()
        await websocket.send_json({
            "type": "snapshot",
            "data": graph.model_dump(),
        })

        # 保持连接：等待客户端消息（ping/pong/close）
        # 增量更新由 ha/events.py 的 _handle_ha_event → manager.broadcast 推入
        heartbeat = get_config().server.ws_heartbeat_seconds
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=heartbeat)
                # 客户端发来 ping，回 pong
                if msg == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # 无消息超时，发心跳
                await websocket.send_json({"type": "ping"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket 错误: %s", e)
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
            })
        except Exception:
            pass
        manager.disconnect(websocket)
