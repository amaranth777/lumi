"""lumi/miloco/router.py — Miloco 摄像头 API 路由。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["miloco"])


@router.get("/cameras")
async def get_cameras() -> dict[str, Any]:
    """获取 Miloco 摄像头设备列表。"""
    from lumi.deps import get_miloco_client

    client = get_miloco_client()
    if client is None:
        return {"cameras": [], "count": 0}
    camera_list = client.get_camera_list()
    return {"cameras": camera_list, "count": len(camera_list)}
