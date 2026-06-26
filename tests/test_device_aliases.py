"""设备别名配置化测试（任务3）。

测试 DeviceAliasConfig / DeviceGraphConfig 模型，以及
DeviceGraphService.refresh() 中的别名覆盖逻辑。
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from lumi.config import DeviceAliasConfig, DeviceGraphConfig, LumiConfig
from lumi.device_graph.schema import Device, DeviceGraph
from lumi.device_graph.service import DeviceGraphService
from lumi.device_graph.policy import build_default_policy_engine


# ─── 模型校验 ─────────────────────────────────────────────────────────────────


class TestDeviceAliasConfig:
    def test_minimal_valid(self):
        alias = DeviceAliasConfig(canonical_id="cat_box", name="猫砂盆")
        assert alias.canonical_id == "cat_box"
        assert alias.name == "猫砂盆"
        assert alias.room is None
        assert alias.miot_match is None
        assert alias.ha_entities == []
        assert alias.policies == {}

    def test_full_config(self):
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            room="客厅",
            miot_match="petjc_cn_821633016_pro",
            ha_entities=["select.petjc_cn_821633016_pro_work_mode_p_3_1"],
            policies={"forbidden_actions": ["empty"]},
        )
        assert alias.room == "客厅"
        assert alias.miot_match == "petjc_cn_821633016_pro"
        assert "select.petjc_cn_821633016_pro_work_mode_p_3_1" in alias.ha_entities
        assert alias.policies["forbidden_actions"] == ["empty"]

    def test_missing_canonical_id_raises(self):
        with pytest.raises(Exception):
            DeviceAliasConfig(name="无ID别名")  # type: ignore[call-arg]

    def test_missing_name_raises(self):
        with pytest.raises(Exception):
            DeviceAliasConfig(canonical_id="x")  # type: ignore[call-arg]


class TestDeviceGraphConfig:
    def test_default_empty(self):
        cfg = DeviceGraphConfig()
        assert cfg.aliases == []

    def test_with_aliases(self):
        cfg = DeviceGraphConfig(
            aliases=[
                DeviceAliasConfig(canonical_id="a", name="A"),
                DeviceAliasConfig(canonical_id="b", name="B"),
            ]
        )
        assert len(cfg.aliases) == 2


class TestLumiConfigDeviceGraph:
    def test_default_device_graph(self):
        config = LumiConfig()
        assert hasattr(config, "device_graph")
        assert isinstance(config.device_graph, DeviceGraphConfig)
        assert config.device_graph.aliases == []

    def test_parse_from_dict(self):
        raw = {
            "device_graph": {
                "aliases": [
                    {
                        "canonical_id": "litter_box",
                        "name": "猫砂盆",
                        "room": "客厅",
                        "miot_match": "petjc_cn_821633016_pro",
                        "ha_entities": ["select.petjc_cn_821633016_pro_work_mode_p_3_1"],
                        "policies": {"forbidden_actions": ["empty"]},
                    }
                ]
            }
        }
        config = LumiConfig(**raw)
        assert len(config.device_graph.aliases) == 1
        alias = config.device_graph.aliases[0]
        assert alias.name == "猫砂盆"
        assert alias.room == "客厅"
        assert alias.miot_match == "petjc_cn_821633016_pro"


# ─── DeviceGraphService alias 覆盖逻辑 ───────────────────────────────────────


def _make_device(
    device_id: str,
    name: str = "设备",
    platform: str = "miloco",
    did: str = "",
    room: str | None = None,
    policies: dict | None = None,
) -> Device:
    return Device(
        id=device_id,
        name=name,
        type="light",
        platform=platform,
        state="online",
        attributes={"did": did} if did else {},
        room=room,
        policies=policies or {},
    )


def _make_service_with_aliases(
    devices: list[Device],
    alias_configs: list[DeviceAliasConfig],
) -> DeviceGraphService:
    """构建注入了设备图的 service，mock 掉实际网络调用。"""
    svc = DeviceGraphService(
        ha_client=None,
        miloco_client=None,
        policy_engine=build_default_policy_engine(),
        alias_configs=alias_configs,
    )
    return svc


def _apply(devices: list[Device], alias_configs: list[DeviceAliasConfig]) -> list[Device]:
    """直接调用 _apply_alias_configs，绕开 refresh 网络调用。"""
    svc = DeviceGraphService(alias_configs=alias_configs)
    return svc._apply_alias_configs(devices)


class TestApplyAliasConfigs:
    def test_no_aliases_no_change(self):
        dev = _make_device("miloco.xyz", name="原始名", did="xyz")
        result = _apply([dev], alias_configs=[])
        assert result[0].name == "原始名"

    def test_miot_match_overrides_name(self):
        dev = _make_device("miloco.petjc_cn_821633016_pro", name="原始名", did="petjc_cn_821633016_pro")
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            miot_match="petjc_cn_821633016_pro",
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].name == "猫砂盆"

    def test_miot_match_overrides_room(self):
        dev = _make_device("miloco.petjc_xyz", name="原始名", did="petjc_xyz", room=None)
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            room="客厅",
            miot_match="petjc_xyz",
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].room == "客厅"

    def test_miot_match_overrides_policies(self):
        dev = _make_device("miloco.petjc_abc", name="原始", did="petjc_abc")
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            miot_match="petjc_abc",
            policies={"forbidden_actions": ["empty"]},
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].policies == {"forbidden_actions": ["empty"]}

    def test_ha_entities_match_by_entity_id(self):
        dev = _make_device(
            "select.petjc_cn_821633016_pro_work_mode_p_3_1",
            name="原始名",
            platform="ha",
        )
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            ha_entities=["select.petjc_cn_821633016_pro_work_mode_p_3_1"],
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].name == "猫砂盆"

    def test_no_match_when_prefix_differs(self):
        dev = _make_device("miloco.other_device", name="原始名", did="other_device")
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            miot_match="petjc_cn",
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].name == "原始名"

    def test_ha_entities_no_match_for_wrong_id(self):
        dev = _make_device("light.bedroom", name="卧室灯", platform="ha")
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            ha_entities=["select.something_else"],
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].name == "卧室灯"

    def test_miot_match_prefix_partial_match(self):
        """miot_match 是前缀匹配，did 以 miot_match 开头就算命中。"""
        dev = _make_device("miloco.petjc_cn_12345", name="猫砂盆2", did="petjc_cn_12345")
        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆别名",
            miot_match="petjc_cn",  # 前缀，能匹配
        )
        result = _apply([dev], alias_configs=[alias])
        assert result[0].name == "猫砂盆别名"

    def test_empty_policies_not_overridden_when_alias_has_no_policies(self):
        dev = _make_device("miloco.petjc_z", name="设备", did="petjc_z")
        alias = DeviceAliasConfig(
            canonical_id="x",
            name="覆盖名",
            miot_match="petjc_z",
            policies={},  # empty → should not overwrite existing
        )
        result = _apply([dev], alias_configs=[alias])
        # name should be overridden
        assert result[0].name == "覆盖名"
        # policies stays {}
        assert result[0].policies == {}

    def test_multiple_aliases_applied(self):
        dev1 = _make_device("miloco.dev_a", name="A原始", did="dev_a")
        dev2 = _make_device("miloco.dev_b", name="B原始", did="dev_b")
        aliases = [
            DeviceAliasConfig(canonical_id="alias_a", name="A别名", miot_match="dev_a"),
            DeviceAliasConfig(canonical_id="alias_b", name="B别名", miot_match="dev_b"),
        ]
        result = _apply([dev1, dev2], alias_configs=aliases)
        names = {d.name for d in result}
        assert names == {"A别名", "B别名"}

    def test_alias_applied_in_refresh(self):
        """alias 在 refresh() 里也生效（不只是缓存路径）。"""
        ha = MagicMock()
        ha.get_states.return_value = []

        alias = DeviceAliasConfig(
            canonical_id="litter_box",
            name="猫砂盆",
            miot_match="petjc_test",
        )

        miloco = MagicMock()
        miloco.get_device_list.return_value = [
            {
                "did": "petjc_test_001",
                "name": "原始设备名",
                "category": "appliance",
                "online": True,
                "model": "petjc.litter.v1",
            }
        ]

        svc = DeviceGraphService(
            ha_client=ha,
            miloco_client=miloco,
            policy_engine=build_default_policy_engine(),
            alias_configs=[alias],
        )
        graph = svc.refresh()
        matched = [d for d in graph.devices if "petjc_test_001" in d.id]
        assert len(matched) == 1
        assert matched[0].name == "猫砂盆"
