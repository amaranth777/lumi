"""lumi/perception/router.py — Miloco webhook 接收端 + 感知事件闭环。

POST /api/perception/webhook  接收 Miloco 推送的感知事件，
触发 PerceptionAnalyzer → HermesBridge 通知链。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel

from lumi.perception.events import PerceptionEvent, PerceptionEventType
from lumi.perception.analyzer import PerceptionAnalyzer, PerceptionDecision
from lumi.hermes_bridge import get_bridge
from lumi.perception.history import HistoryEntry, get_history
from lumi.deps import get_device_graph_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/perception", tags=["perception"])

# 触发设备图缓存失效的感知事件集合
_REFRESH_TRIGGER_EVENTS: frozenset[str] = frozenset([
    "litter_box_full",
    "litter_box_cleaned",
    "litter_box_weight_low",
])


# ─── 请求 / 响应模型 ───────────────────────────────────────────────────────────

class WebhookRequest(BaseModel):
    """Miloco webhook payload（宽松结构，兼容多种推送格式）。"""
    event_type: str = "unknown"
    event_id: str = ""
    camera_id: str | None = None
    camera_name: str | None = None
    room: str | None = None
    subjects: list[dict[str, Any]] = []
    related_device_ids: list[str] = []
    context: dict[str, Any] = {}
    data: dict[str, Any] = {}

    model_config = {"extra": "allow"}


class WebhookResponse(BaseModel):
    """webhook 处理结果。"""
    received: bool = True
    event_id: str
    event_type: str
    should_notify: bool
    notified: bool
    skipped: bool
    skip_reason: str = ""
    message: str | None = None


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

def _parse_event_type(raw: str) -> PerceptionEventType:
    """宽松解析事件类型，未知值返回 UNKNOWN。"""
    try:
        return PerceptionEventType(raw.lower())
    except ValueError:
        logger.debug("未知事件类型 %r，归为 UNKNOWN", raw)
        return PerceptionEventType.UNKNOWN


def _process_webhook(event: PerceptionEvent, notify: bool = True) -> WebhookResponse:
    """同步处理感知事件：分析 → 推送。"""
    from lumi.deps import get_ha_client
    analyzer = PerceptionAnalyzer(ha_client=get_ha_client())
    decision: PerceptionDecision = analyzer.analyze(event)

    notified = False
    skipped = False
    skip_reason = ""

    if notify and decision.should_notify:
        bridge = get_bridge()
        result = bridge.notify(event, decision)
        notified = result.success and not result.skipped
        skipped = result.skipped
        skip_reason = result.skip_reason

    return WebhookResponse(
        event_id=event.event_id or "",
        event_type=event.event_type.value,
        should_notify=decision.should_notify,
        notified=notified,
        skipped=skipped,
        skip_reason=skip_reason,
        message=decision.message,
    )


def _record_history(event: PerceptionEvent, resp: WebhookResponse) -> None:
    """写入感知历史。"""
    try:
        get_history().record(HistoryEntry(
            ts=datetime.now().isoformat(timespec="seconds"),
            event_id=resp.event_id,
            event_type=resp.event_type,
            room=event.room,
            camera_id=event.camera_id,
            should_notify=resp.should_notify,
            notified=resp.notified,
            skipped=resp.skipped,
            skip_reason=resp.skip_reason,
            message=resp.message,
            context=event.context,
        ))
    except Exception as e:
        logger.debug("写感知历史失败（非致命）: %s", e)


# ─── 路由 ─────────────────────────────────────────────────────────────────────

@router.post("/webhook", response_model=WebhookResponse)
async def receive_webhook(
    payload: WebhookRequest,
    background_tasks: BackgroundTasks,
) -> WebhookResponse:
    """接收 Miloco 感知 webhook，触发分析 + 推送 + 历史记录。"""
    raw_dict = payload.model_dump()
    event_type = _parse_event_type(payload.event_type)

    try:
        event = PerceptionEvent.from_miloco_webhook(raw_dict)
    except Exception as e:
        logger.warning("webhook payload 解析失败，使用降级模式: %s", e)
        event = PerceptionEvent(
            event_id=payload.event_id or "",
            event_type=event_type,
            camera_id=payload.camera_id,
            camera_name=payload.camera_name,
            room=payload.room,
            raw=raw_dict,
        )

    logger.info(
        "收到 webhook: event_type=%s event_id=%s room=%s",
        event.event_type, event.event_id, event.room,
    )

    background_tasks.add_task(_broadcast_perception, event)

    result = _process_webhook(event, notify=True)
    try:
        _record_history(event, result)
    except Exception as e:
        logger.debug("记录感知历史失败（非致命）: %s", e)

    # 感知事件完成后，触发设备图增量刷新
    if event.event_type.value in _REFRESH_TRIGGER_EVENTS:
        try:
            svc = get_device_graph_service()
            svc.invalidate_cache()
            logger.info("感知事件 %s 触发设备图缓存失效", event.event_type)
        except Exception as e:
            logger.warning("触发设备图刷新失败: %s", e)

    return result


@router.get("/events/types")
async def list_event_types() -> dict[str, list[str]]:
    """列出所有支持的感知事件类型。"""
    return {"event_types": [e.value for e in PerceptionEventType]}


@router.post("/webhook/test", response_model=WebhookResponse)
async def test_webhook(payload: WebhookRequest) -> WebhookResponse:
    """测试用 webhook 端点——分析但不推送通知（dry run）。"""
    raw_dict = payload.model_dump()
    try:
        event = PerceptionEvent.from_miloco_webhook(raw_dict)
    except Exception:
        event = PerceptionEvent(
            event_id=payload.event_id or "test",
            event_type=_parse_event_type(payload.event_type),
            camera_id=payload.camera_id,
            camera_name=payload.camera_name,
            room=payload.room,
            raw=raw_dict,
        )
    return _process_webhook(event, notify=False)


@router.get("/history")
async def get_perception_history(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = None,
    room: str | None = None,
) -> dict[str, Any]:
    """查询感知事件历史（支持分页）。

    参数：
    - limit: 返回条数（默认 20，最大 200）
    - offset: 跳过条数（默认 0）
    - event_type: 按事件类型过滤（如 litter_box_full）
    - room: 按房间过滤（如 卫生间）
    """
    history = get_history()
    if event_type or room:
        # 过滤模式：用原有 get_recent 取全部再手动分页
        all_events = history.get_recent(limit=history.get_total() or 200, event_type=event_type, room=room)
        total = len(all_events)
        events = all_events[offset:offset + limit]
    else:
        total = history.get_total()
        events = history.get_page(limit=limit, offset=offset)
    return {
        "events": [e.to_dict() for e in events],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_perception_stats() -> dict[str, Any]:
    """感知事件统计摘要（内存中的最近 N 条）。"""
    return get_history().get_stats()


# ─── 后台任务 ─────────────────────────────────────────────────────────────────

async def _broadcast_perception(event: PerceptionEvent) -> None:
    """广播感知事件到所有 WebSocket 客户端。"""
    try:
        from lumi.websocket import manager
        await manager.broadcast_perception(
            event_type=event.event_type.value,
            payload={
                "event_id": event.event_id,
                "room": event.room,
                "camera_id": event.camera_id,
                "subjects": [s.model_dump() for s in event.subjects],
                "context": event.context,
            },
        )
    except Exception as e:
        logger.debug("WebSocket 广播失败（非致命）: %s", e)
