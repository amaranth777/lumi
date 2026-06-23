"""场景预设 API 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from lumi.device_graph.schema import BatchCommandResponse
from lumi.device_graph.service import DeviceGraphService
from lumi.deps import get_device_graph_service, get_scene_store
from lumi.scenes.store import Scene, SceneStore

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


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

    results = []
    for action in scene.actions:
        result = device_service.execute_command(
            action.device_id, action.command, action.params
        )
        results.append(result)

    success_count = sum(1 for r in results if r.success)
    return BatchCommandResponse(
        total=len(results),
        success=success_count,
        failed=len(results) - success_count,
        results=results,
    )
