"""设备图 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lumi.device_graph.schema import (
    BatchCommandRequest,
    BatchCommandResponse,
    CommandRequest,
    CommandResponse,
    Device,
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


@router.get("/search", response_model=list[Device])
def search_devices(
    q: str = Query(..., description="搜索关键词（名称/ID/房间）"),
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> list[Device]:
    return service.search_devices(q)


@router.get("/rooms/{room}", response_model=list[Device])
def get_devices_by_room(
    room: str,
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> list[Device]:
    devices = service.get_devices_by_room(room)
    if not devices:
        raise HTTPException(status_code=404, detail=f"房间不存在或无设备: {room}")
    return devices


@router.post("/batch/command", response_model=BatchCommandResponse)
def batch_execute_command(
    body: BatchCommandRequest,
    service: DeviceGraphService = Depends(get_device_graph_service),
) -> BatchCommandResponse:
    return service.batch_execute_command(body.device_ids, body.command, body.params)


# 通配符路径放最后，避免吃掉其他路由
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
