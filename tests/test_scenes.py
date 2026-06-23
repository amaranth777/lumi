"""scenes/store.py 单元测试。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from lumi.scenes.store import Scene, SceneAction, SceneStore


@pytest.fixture
def tmp_store(tmp_path: Path) -> SceneStore:
    """使用临时目录的 SceneStore，不污染 ~/.lumi/。"""
    store = SceneStore.__new__(SceneStore)
    store._path = tmp_path / "scenes.json"
    store._scenes = {}
    return store


def _make_scene(sid: str = "s1", name: str = "测试场景") -> Scene:
    return Scene(
        id=sid,
        name=name,
        icon="mdi:home",
        actions=[
            SceneAction(device_id="light.living_room", command="turn_on", params={}),
            SceneAction(device_id="fan.purifier", command="turn_off", params={}),
        ],
    )


# ─── 基础 CRUD ────────────────────────────────────────────────────────────────

class TestSceneStoreCRUD:
    def test_list_empty(self, tmp_store):
        assert tmp_store.list() == []

    def test_upsert_and_get(self, tmp_store):
        scene = _make_scene()
        tmp_store.upsert(scene)
        result = tmp_store.get("s1")
        assert result is not None
        assert result.name == "测试场景"
        assert len(result.actions) == 2

    def test_list_returns_all(self, tmp_store):
        tmp_store.upsert(_make_scene("s1", "场景一"))
        tmp_store.upsert(_make_scene("s2", "场景二"))
        assert len(tmp_store.list()) == 2

    def test_get_nonexistent_returns_none(self, tmp_store):
        assert tmp_store.get("nonexistent") is None

    def test_delete_existing(self, tmp_store):
        tmp_store.upsert(_make_scene())
        assert tmp_store.delete("s1") is True
        assert tmp_store.get("s1") is None

    def test_delete_nonexistent_returns_false(self, tmp_store):
        assert tmp_store.delete("ghost") is False

    def test_upsert_overwrites(self, tmp_store):
        tmp_store.upsert(_make_scene("s1", "原始名"))
        tmp_store.upsert(_make_scene("s1", "新名字"))
        assert tmp_store.get("s1").name == "新名字"
        assert len(tmp_store.list()) == 1  # 没有重复


# ─── 持久化 ───────────────────────────────────────────────────────────────────

class TestSceneStorePersistence:
    def test_save_and_load(self, tmp_path):
        """upsert 后文件写入，重新加载能读回。"""
        store1 = SceneStore.__new__(SceneStore)
        store1._path = tmp_path / "scenes.json"
        store1._scenes = {}
        store1.upsert(_make_scene("s1", "持久化场景"))

        # 新实例从同一文件加载
        store2 = SceneStore.__new__(SceneStore)
        store2._path = tmp_path / "scenes.json"
        store2._scenes = {}
        store2._load()

        result = store2.get("s1")
        assert result is not None
        assert result.name == "持久化场景"
        assert len(result.actions) == 2

    def test_json_format(self, tmp_path):
        """存储的 JSON 格式正确。"""
        store = SceneStore.__new__(SceneStore)
        store._path = tmp_path / "scenes.json"
        store._scenes = {}
        store.upsert(_make_scene("s1"))

        data = json.loads((tmp_path / "scenes.json").read_text())
        assert isinstance(data, list)
        assert data[0]["id"] == "s1"
        assert len(data[0]["actions"]) == 2

    def test_load_nonexistent_file(self, tmp_path):
        """文件不存在时静默初始化空列表。"""
        store = SceneStore.__new__(SceneStore)
        store._path = tmp_path / "nonexistent.json"
        store._scenes = {}
        store._load()  # 不应抛异常
        assert store.list() == []

    def test_delete_persists(self, tmp_path):
        store = SceneStore.__new__(SceneStore)
        store._path = tmp_path / "scenes.json"
        store._scenes = {}
        store.upsert(_make_scene("s1"))
        store.upsert(_make_scene("s2"))
        store.delete("s1")

        store2 = SceneStore.__new__(SceneStore)
        store2._path = tmp_path / "scenes.json"
        store2._scenes = {}
        store2._load()
        assert store2.get("s1") is None
        assert store2.get("s2") is not None


# ─── SceneAction / Scene schema ───────────────────────────────────────────────

class TestSceneSchema:
    def test_scene_action_defaults(self):
        action = SceneAction(device_id="light.x", command="turn_on")
        assert action.params == {}

    def test_scene_with_params(self):
        action = SceneAction(device_id="light.x", command="set_brightness", params={"brightness": 80})
        assert action.params["brightness"] == 80

    def test_scene_no_icon(self):
        scene = Scene(id="s1", name="无图标", actions=[])
        assert scene.icon is None

    def test_scene_empty_actions(self):
        scene = Scene(id="s1", name="空场景", actions=[])
        assert scene.actions == []
