"""设备图 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lumi.device_graph.schema import (
    CommandRequest,
    CommandResponse,
    DeviceGraph,
    DeviceGraphSummary,
)
from lumi.device_graph.service import DeviceGraphService
from lumi.deps import get_device_graph_service

router = APIRouter(prefix="/api/device_graph", tags=["device_graph"])


@router.get("", response_model=DeviceGraph)
def get_device_graph(
    refresh: bool = Query(False),
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> DeviceGraph:
    return service.get_graph(force_refresh=refresh)


@router.get("/summary", response_model=DeviceGraphSummary)
def get_device_graph_summary(
    refresh: bool = Query(False),
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> DeviceGraphSummary:
    return service.get_summary(force_refresh=refresh)


@router.post("/{device_id:path}/command", response_model=CommandResponse)
def execute_command(
    device_id: str,
    body: CommandRequest,
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> CommandResponse:
    result = service.execute_command(device_id, body.command, body.params)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result
