"""deps.py 依赖注入层单元测试。"""

from __future__ import annotations

import json
import pytest
from pathlib import Path


# 每个测试前重置所有单例
@pytest.fixture(autouse=True)
def reset_deps():
    import lumi.deps as deps_mod
    import lumi.config as cfg_mod
    deps_mod._ha_client = None
    deps_mod._miloco_client = None
    deps_mod._device_graph_service = None
    deps_mod._scene_store = None
    cfg_mod._config = None
    yield
    deps_mod._ha_client = None
    deps_mod._miloco_client = None
    deps_mod._device_graph_service = None
    deps_mod._scene_store = None
    cfg_mod._config = None


def _write_config(tmp_path: Path, data: dict) -> None:
    cfg_dir = tmp_path / ".lumi"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "config.json").write_text(json.dumps(data), encoding="utf-8")


# ─── get_ha_client ────────────────────────────────────────────────────────────

class TestGetHAClient:
    def test_returns_none_when_ha_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {"ha": {"enabled": False}})
        from lumi.deps import get_ha_client
        assert get_ha_client() is None

    def test_returns_client_when_ha_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        token_file = tmp_path / "ha_token"
        token_file.write_text("test_token", encoding="utf-8")
        _write_config(tmp_path, {
            "ha": {
                "enabled": True,
                "base_url": "http://192.168.5.184:8123",
                "token_file": str(token_file),
            }
        })
        from lumi.deps import get_ha_client
        client = get_ha_client()
        assert client is not None
        assert client.base_url == "http://192.168.5.184:8123"

    def test_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        token_file = tmp_path / "ha_token"
        token_file.write_text("t", encoding="utf-8")
        _write_config(tmp_path, {"ha": {"enabled": True, "token_file": str(token_file)}})
        from lumi.deps import get_ha_client
        c1 = get_ha_client()
        c2 = get_ha_client()
        assert c1 is c2


# ─── get_miloco_client ────────────────────────────────────────────────────────

class TestGetMilocoClient:
    def test_returns_none_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {"miloco": {"enabled": False}})
        from lumi.deps import get_miloco_client
        assert get_miloco_client() is None

    def test_returns_client_with_explicit_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {
            "miloco": {
                "enabled": True,
                "base_url": "http://127.0.0.1:1810",
                "token": "miloco_test_token",
            }
        })
        from lumi.deps import get_miloco_client
        client = get_miloco_client()
        assert client is not None
        assert client._token == "miloco_test_token"

    def test_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {
            "miloco": {"enabled": True, "token": "t"}
        })
        from lumi.deps import get_miloco_client
        c1 = get_miloco_client()
        c2 = get_miloco_client()
        assert c1 is c2


# ─── get_device_graph_service ─────────────────────────────────────────────────

class TestGetDeviceGraphService:
    def test_returns_service(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {})
        from lumi.deps import get_device_graph_service
        from lumi.device_graph.service import DeviceGraphService
        svc = get_device_graph_service()
        assert isinstance(svc, DeviceGraphService)

    def test_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {})
        from lumi.deps import get_device_graph_service
        s1 = get_device_graph_service()
        s2 = get_device_graph_service()
        assert s1 is s2

    def test_includes_aliases(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        _write_config(tmp_path, {
            "device_aliases": [{"entity_id": "light.x", "name": "测试灯"}]
        })
        from lumi.deps import get_device_graph_service
        svc = get_device_graph_service()
        assert len(svc.aliases) == 1
        assert svc.aliases[0]["name"] == "测试灯"


# ─── get_scene_store ──────────────────────────────────────────────────────────

class TestGetSceneStore:
    def test_returns_scene_store(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from lumi.deps import get_scene_store
        from lumi.scenes.store import SceneStore
        store = get_scene_store()
        assert isinstance(store, SceneStore)

    def test_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from lumi.deps import get_scene_store
        s1 = get_scene_store()
        s2 = get_scene_store()
        assert s1 is s2
