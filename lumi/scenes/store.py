"""场景预设数据模型与持久化。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SceneAction(BaseModel):
    """场景中的单个设备动作。"""

    device_id: str
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class Scene(BaseModel):
    """场景预设。"""

    id: str
    name: str
    icon: str | None = None
    actions: list[SceneAction]


class SceneStore:
    """场景持久化（存储在 ~/.lumi/scenes.json）。"""

    def __init__(self) -> None:
        self._path = Path.home() / ".lumi" / "scenes.json"
        self._scenes: dict[str, Scene] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._scenes = {s["id"]: Scene(**s) for s in data}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = [s.model_dump() for s in self._scenes.values()]
        self._path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def list(self) -> list[Scene]:
        return list(self._scenes.values())

    def get(self, scene_id: str) -> Scene | None:
        return self._scenes.get(scene_id)

    def upsert(self, scene: Scene) -> Scene:
        self._scenes[scene.id] = scene
        self._save()
        return scene

    def delete(self, scene_id: str) -> bool:
        if scene_id in self._scenes:
            del self._scenes[scene_id]
            self._save()
            return True
        return False
