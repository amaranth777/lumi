"""Home Assistant API 路由。

暴露 HAClient 扩展方法为 HTTP 端点。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from lumi.deps import get_ha_client, get_scene_store
from lumi.ha.client import HAClient

router = APIRouter(prefix="/api/ha", tags=["ha"])


def _require_ha_client() -> HAClient:
    """依赖注入：获取 HA 客户端，未初始化则返回 503。"""
    client = get_ha_client()
    if client is None:
        raise HTTPException(status_code=503, detail="HA client 未初始化或未启用")
    return client


# ─── 请求体模型 ────────────────────────────────────────────────────────────────


class ToggleAutomationRequest(BaseModel):
    enable: bool


class FireEventRequest(BaseModel):
    event_data: dict[str, Any] = {}


class RenderTemplateRequest(BaseModel):
    template: str


# ─── 路由 ─────────────────────────────────────────────────────────────────────


@router.get("/services", response_model=dict)
def get_services(
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """列出所有 HA 可用服务域。"""
    return ha.get_services()


@router.get("/automations", response_model=list)
def get_automations(
    ha: HAClient = Depends(_require_ha_client),
) -> list[dict[str, Any]]:
    """列出所有自动化 entity 状态。"""
    return ha.get_automations()


@router.post("/automations/{entity_id}/trigger", response_model=dict)
def trigger_automation(
    entity_id: str,
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """触发指定自动化。"""
    success = ha.trigger_automation(entity_id)
    return {"success": success, "entity_id": entity_id}


@router.post("/automations/{entity_id}/toggle", response_model=dict)
def toggle_automation(
    entity_id: str,
    body: ToggleAutomationRequest,
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """启用或禁用自动化。"""
    success = ha.toggle_automation(entity_id, body.enable)
    return {"success": success, "entity_id": entity_id, "enable": body.enable}


@router.get("/scripts", response_model=list)
def get_scripts(
    ha: HAClient = Depends(_require_ha_client),
) -> list[dict[str, Any]]:
    """列出所有脚本 entity 状态。"""
    return ha.get_scripts()


@router.post("/scripts/{entity_id}/run", response_model=dict)
def run_script(
    entity_id: str,
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """运行指定脚本。"""
    success = ha.run_script(entity_id)
    return {"success": success, "entity_id": entity_id}


@router.get("/history/{entity_id}", response_model=list)
def get_history(
    entity_id: str,
    hours: int = Query(default=24, ge=1, le=720, description="查询历史小时数"),
    ha: HAClient = Depends(_require_ha_client),
) -> list[Any]:
    """查询指定 entity 的历史状态。"""
    return ha.get_history(entity_id, hours=hours)


@router.post("/events/{event_type}", response_model=dict)
def fire_event(
    event_type: str,
    body: FireEventRequest,
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """触发 HA 自定义事件。"""
    success = ha.fire_event(event_type, body.event_data)
    return {"success": success, "event_type": event_type}


@router.post("/template", response_model=dict)
def render_template(
    body: RenderTemplateRequest,
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """渲染 Jinja2 模板，返回渲染结果。"""
    result = ha.render_template(body.template)
    return {"result": result}


@router.get("/config", response_model=dict)
def get_config(
    ha: HAClient = Depends(_require_ha_client),
) -> dict[str, Any]:
    """获取 HA 实例配置信息。"""
    return ha.get_config()


@router.post("/sync_automations", response_model=dict)
def sync_automations(
    ha: HAClient = Depends(_require_ha_client),
    store=Depends(get_scene_store),
) -> dict[str, Any]:
    """将 HA 自动化同步为 Lumi 场景。每个自动化创建/更新一个场景。"""
    from lumi.scenes.store import Scene

    automations = ha.get_automations()
    synced = 0
    skipped = 0

    for auto in automations:
        entity_id = auto.get("entity_id", "")
        if not entity_id:
            skipped += 1
            continue
        attributes = auto.get("attributes", {})
        friendly_name = attributes.get("friendly_name") or entity_id
        scene = Scene(
            id=f"ha_auto_{entity_id}",
            name=friendly_name,
            description="HA 自动化",
            actions=[],
            metadata={"ha_entity_id": entity_id, "source": "ha_automation"},
        )
        store.upsert(scene)
        synced += 1

    return {"synced": synced, "skipped": skipped}
