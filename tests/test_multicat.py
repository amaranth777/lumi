"""多猫支持测试。"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from lumi.config import CatProfile, LumiConfig, PetConfig
from lumi.perception.analyzer import PerceptionAnalyzer
from lumi.perception.events import PerceptionEvent, PerceptionEventType


# ─── 辅助 ────────────────────────────────────────────────────────────────────

def _make_event(weight_kg=None, cat_name=None):
    """构造一个 PET_WEIGHED 事件。"""
    ctx = {}
    if weight_kg is not None:
        ctx["weight_kg"] = weight_kg
    if cat_name is not None:
        ctx["cat_name"] = cat_name
    return PerceptionEvent(
        event_type=PerceptionEventType.PET_WEIGHED,
        context=ctx,
    )



# ─── CatProfile 模型验证 ──────────────────────────────────────────────────────

class TestCatProfile:
    def test_required_name(self):
        with pytest.raises(Exception):
            CatProfile()  # type: ignore[call-arg]  # name 必填

    def test_defaults(self):
        p = CatProfile(name="小白")
        assert p.weight_min_kg == 2.0
        assert p.weight_max_kg == 8.0

    def test_custom_values(self):
        p = CatProfile(name="胖橘", weight_min_kg=3.5, weight_max_kg=7.0)
        assert p.name == "胖橘"
        assert p.weight_min_kg == 3.5
        assert p.weight_max_kg == 7.0


# ─── PetConfig 向后兼容 ────────────────────────────────────────────────────────

class TestPetConfigBackwardCompat:
    def test_default_cats_empty(self):
        cfg = PetConfig()
        assert cfg.cats == []

    def test_single_cat_mode_fields_present(self):
        cfg = PetConfig(name="猫猫", weight_min_kg=2.5, weight_max_kg=6.0, litter_low_kg=1.0)
        assert cfg.name == "猫猫"
        assert cfg.cats == []

    def test_multi_cat_mode(self):
        cats = [CatProfile(name="A"), CatProfile(name="B")]
        cfg = PetConfig(cats=cats)
        assert len(cfg.cats) == 2


# ─── _analyze_pet_weighed 单猫模式 ─────────────────────────────────────────────

class TestAnalyzePetWeighedSingleCat:
    def _run(self, weight_kg, pet_cfg):
        analyzer = PerceptionAnalyzer()
        event = _make_event(weight_kg=weight_kg)
        with patch("lumi.perception.analyzer.get_config") as mock_cfg:
            mock_cfg.return_value = LumiConfig(pet=pet_cfg)
            alerts, _ = analyzer._analyze_pet_weighed(event)
            return alerts

    def test_normal_weight_no_alert(self):
        cfg = PetConfig(name="咪咪", weight_min_kg=3.0, weight_max_kg=6.0, litter_low_kg=1.0)
        alerts = self._run(4.5, cfg)
        assert alerts == []

    def test_underweight_alert(self):
        cfg = PetConfig(name="咪咪", weight_min_kg=3.0, weight_max_kg=6.0, litter_low_kg=1.0)
        alerts = self._run(2.0, cfg)
        assert len(alerts) == 1
        assert "体重偏轻" in alerts[0]
        assert "咪咪" in alerts[0]

    def test_overweight_alert(self):
        cfg = PetConfig(name="咪咪", weight_min_kg=3.0, weight_max_kg=6.0, litter_low_kg=1.0)
        alerts = self._run(7.0, cfg)
        assert len(alerts) == 1
        assert "体重偏重" in alerts[0]
        assert "咪咪" in alerts[0]

    def test_boundary_min_no_alert(self):
        cfg = PetConfig(name="咪咪", weight_min_kg=3.0, weight_max_kg=6.0, litter_low_kg=1.0)
        alerts = self._run(3.0, cfg)
        assert alerts == []

    def test_boundary_max_no_alert(self):
        cfg = PetConfig(name="咪咪", weight_min_kg=3.0, weight_max_kg=6.0, litter_low_kg=1.0)
        alerts = self._run(6.0, cfg)
        assert alerts == []


# ─── weight_kg=None 时返回空列表 ──────────────────────────────────────────────

class TestAnalyzePetWeighedNoneWeight:
    def test_none_weight_returns_empty(self):
        analyzer = PerceptionAnalyzer()
        event = _make_event(weight_kg=None)
        cfg = PetConfig(name="猫", weight_min_kg=2.0, weight_max_kg=8.0, litter_low_kg=1.0)
        with patch("lumi.perception.analyzer.get_config") as mock_cfg:
            mock_cfg.return_value = LumiConfig(pet=cfg)
            alerts, reason = analyzer._analyze_pet_weighed(event)
        assert alerts == []
        assert "缺失" in reason

    def test_none_weight_multi_cat_returns_empty(self):
        analyzer = PerceptionAnalyzer()
        event = _make_event(weight_kg=None)
        cats = [CatProfile(name="大猫", weight_min_kg=3.0, weight_max_kg=7.0)]
        cfg = PetConfig(cats=cats, litter_low_kg=1.0)
        with patch("lumi.perception.analyzer.get_config") as mock_cfg:
            mock_cfg.return_value = LumiConfig(pet=cfg)
            alerts, reason = analyzer._analyze_pet_weighed(event)
        assert alerts == []
        assert "缺失" in reason


# ─── _analyze_pet_weighed 多猫模式 ─────────────────────────────────────────────

class TestAnalyzePetWeighedMultiCat:
    TWO_CATS = [
        CatProfile(name="小白", weight_min_kg=3.0, weight_max_kg=5.0),
        CatProfile(name="胖橘", weight_min_kg=5.5, weight_max_kg=8.0),
    ]

    def _run(self, weight_kg, cat_name=None):
        analyzer = PerceptionAnalyzer()
        event = _make_event(weight_kg=weight_kg, cat_name=cat_name)
        cfg = PetConfig(cats=self.TWO_CATS, litter_low_kg=1.0)
        with patch("lumi.perception.analyzer.get_config") as mock_cfg:
            mock_cfg.return_value = LumiConfig(pet=cfg)
            alerts, _ = analyzer._analyze_pet_weighed(event)
            return alerts

    # 按 cat_name 匹配
    def test_match_by_name_normal(self):
        alerts = self._run(4.0, cat_name="小白")
        assert alerts == []

    def test_match_by_name_overweight(self):
        alerts = self._run(6.0, cat_name="小白")
        assert len(alerts) == 1
        assert "小白" in alerts[0]
        assert "体重偏重" in alerts[0]

    def test_match_by_name_second_cat_normal(self):
        alerts = self._run(6.5, cat_name="胖橘")
        assert alerts == []

    def test_match_by_name_second_cat_underweight(self):
        alerts = self._run(4.0, cat_name="胖橘")
        assert len(alerts) == 1
        assert "胖橘" in alerts[0]
        assert "体重偏轻" in alerts[0]

    # 按体重范围模糊匹配（无 cat_name）
    def test_fuzzy_match_first_cat(self):
        # 3.5kg 落在小白范围 [3.0, 5.0]
        alerts = self._run(3.5)
        assert alerts == []

    def test_fuzzy_match_second_cat(self):
        # 6.0kg 落在胖橘范围 [5.5, 8.0]
        alerts = self._run(6.0)
        assert alerts == []

    def test_fuzzy_match_second_cat_overweight(self):
        # 9.0kg 不在任何范围，fallback 第一只（小白），算偏重
        alerts = self._run(9.0)
        assert len(alerts) == 1
        assert "小白" in alerts[0]  # fallback 第一只
        assert "体重偏重" in alerts[0]

    # fallback 第一只
    def test_fallback_to_first_cat_when_no_match(self):
        # 5.2kg：不在小白[3,5]也不在胖橘[5.5,8]，fallback 小白，偏重
        alerts = self._run(5.2)
        assert len(alerts) == 1
        assert "小白" in alerts[0]

    def test_unknown_cat_name_falls_back_to_weight_range(self):
        # cat_name 不存在，退到体重匹配，6.0 落在胖橘
        alerts = self._run(6.0, cat_name="不存在的猫")
        assert alerts == []  # 6.0 在胖橘范围内，无告警
