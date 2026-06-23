"""设备图 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from lumi.device_graph.schema import DeviceGraph, DeviceGraphSummary
from lumi.device_graph.service import DeviceGraphService
from lumi.deps import get_device_graph_service

router = APIRouter(prefix="/api/device_graph", tags=["device_graph"])


@router.get("", response_model=DeviceGraph)
async def get_device_graph(
    refresh: bool = Query(False, description="强制刷新"),
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> DeviceGraph:
    """获取完整设备图。"""
    return service.get_graph(force_refresh=refresh)


@router.get("/summary", response_model=DeviceGraphSummary)
async def get_device_graph_summary(
    refresh: bool = Query(False, description="强制刷新"),
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> DeviceGraphSummary:
    """获取设备图摘要。"""
    return service.get_summary(force_refresh=refresh)
