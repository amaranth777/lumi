"""场景预设 API 路由。"""

from __future__ import annotations

import json
import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException

from lumi.device_graph.schema import BatchCommandResponse
from lumi.device_graph.service import DeviceGraphService
from lumi.deps import get_device_graph_service, get_ha_client, get_scene_store
from lumi.scenes.store import Scene, SceneStore

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
logger = logging.getLogger(__name__)

_SCENE_LOG_PATH = os.path.expanduser("~/.hermes/logs/lumi_scenes.log")


def _log_scene_execution(scene_id: str, scene_name: str, result: BatchCommandResponse) -> None:
    """写场景执行审计日志。"""
    try:
        os.makedirs(os.path.dirname(_SCENE_LOG_PATH), exist_ok=True)
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "scene_id": scene_id,
            "scene_name": scene_name,
            "total": result.total,
            "success": result.success,
            "failed": result.failed,
        }
        with open(_SCENE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("写场景审计日志失败: %s", e)


@router.get("", response_model=list[Scene])
def list_scenes(store: SceneStore = Depends(get_scene_store)) -> list[Scene]:
    """列出所有场景。"""
    return store.list()


@router.get("/{scene_id}", response_model=Scene)
def get_scene(scene_id: str, store: SceneStore = Depends(get_scene_store)) -> Scene:
    """获取单个场景。"""
    scene = store.get(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"场景不存在: {scene_id}")
    return scene


@router.post("", response_model=Scene)
def create_or_update_scene(
    scene: Scene, store: SceneStore = Depends(get_scene_store)
) -> Scene:
    """创建或更新场景。"""
    return store.upsert(scene)


@router.delete("/{scene_id}")
def delete_scene(scene_id: str, store: SceneStore = Depends(get_scene_store)) -> dict:
    """删除场景。"""
    if not store.delete(scene_id):
        raise HTTPException(status_code=404, detail=f"场景不存在: {scene_id}")
    return {"message": "删除成功"}


@router.post("/{scene_id}/execute", response_model=BatchCommandResponse)
def execute_scene(
    scene_id: str,
    store: SceneStore = Depends(get_scene_store),
    device_service: DeviceGraphService = Depends(get_device_graph_service),
) -> BatchCommandResponse:
    """执行场景（批量执行所有动作）。"""
    scene = store.get(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail=f"场景不存在: {scene_id}")

    # HA 自动化场景：直接触发对应自动化
    if scene.metadata.get("source") == "ha_automation":
        ha_entity_id = scene.metadata.get("ha_entity_id", "")
        ha = get_ha_client()
        if ha is None:
            raise HTTPException(status_code=503, detail="HA client 未初始化或未启用")
        success = ha.trigger_automation(ha_entity_id)
        response = BatchCommandResponse(
            total=1,
            success=1 if success else 0,
            failed=0 if success else 1,
            results=[],
        )
        _log_scene_execution(scene_id, scene.name, response)
        logger.info("HA 自动化场景执行: %s (%s) — %s", scene.name, scene_id, "成功" if success else "失败")
        return response

    results = []
    for action in scene.actions:
        result = device_service.execute_command(
            action.device_id, action.command, action.params
        )
        results.append(result)

    success_count = sum(1 for r in results if r.success)
    response = BatchCommandResponse(
        total=len(results),
        success=success_count,
        failed=len(results) - success_count,
        results=results,
    )

    # 审计日志
    _log_scene_execution(scene_id, scene.name, response)
    logger.info("场景执行: %s (%s) — %d/%d 成功", scene.name, scene_id, success_count, len(results))

    return response
