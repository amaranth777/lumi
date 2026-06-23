"""WebSocket 实时推送设备状态。

用于前端/屏幕实时显示设备变化。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from lumi.deps import get_device_graph_service

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
        
        # 清理断开的连接
        for conn in dead_connections:
            if conn in self.active_connections:
                self.active_connections.remove(conn)


manager = ConnectionManager()


@router.websocket("/device_graph")
async def websocket_device_graph(websocket: WebSocket) -> None:
    """WebSocket 端点：实时推送设备图变化。
    
    消息格式：
    - type: "snapshot" (完整快照) | "update" (增量更新) | "error"
    - data: 设备图数据或增量更新
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
        
        # 缓存上次的设备状态（id → state）
        last_states = {d.id: d.state for d in graph.devices}
        
        while True:
            await asyncio.sleep(5)  # 每 5 秒检查一次
            
            # 刷新设备图
            new_graph = service.get_graph(force_refresh=True)
            new_states = {d.id: d.state for d in new_graph.devices}
            
            # 计算变化
            changed = {}
            for device_id, new_state in new_states.items():
                old_state = last_states.get(device_id)
                if old_state != new_state:
                    changed[device_id] = new_state
            
            # 推送增量更新
            if changed:
                await websocket.send_json({
                    "type": "update",
                    "data": {
                        "changed_devices": changed,
                        "timestamp": new_graph.metadata.get("last_refresh"),
                    }
                })
                last_states = new_states
    
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
