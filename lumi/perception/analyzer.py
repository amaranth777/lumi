"""感知闭环分析器——联合 HA 状态 + 感知事件做出决策。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from lumi.perception.events import PerceptionEvent, PerceptionEventType

logger = logging.getLogger(__name__)


@dataclass
class PerceptionDecision:
    """感知分析结果。"""
    should_notify: bool
    message: str | None = None          # 微信推送内容，None 表示不推送
    should_act: bool = False
    actions: list[dict[str, Any]] = None  # [{device_id, command, params}]
    reason: str = ""                    # 内部说明（debug 用）

    def __post_init__(self) -> None:
        if self.actions is None:
            self.actions = []


class PerceptionAnalyzer:
    """感知闭环分析器。

    接收感知事件 + 当前 HA 设备状态，输出 PerceptionDecision。
    规则按优先级顺序执行，第一条命中即返回。
    """

    def __init__(self, ha_client: Any = None) -> None:
        self.ha_client = ha_client

    def analyze(self, event: PerceptionEvent) -> PerceptionDecision:
        """分析感知事件，返回决策。"""
        logger.info("感知分析: event_type=%s room=%s", event.event_type, event.room)

        # 按事件类型分发
        if event.event_type == PerceptionEventType.LITTER_BOX_FULL:
            return self._analyze_litter_box_full(event)

        if event.event_type == PerceptionEventType.PET_AT_LITTER_BOX:
            return self._analyze_pet_at_litter_box(event)

        if event.event_type == PerceptionEventType.PET_LEFT_LITTER_BOX:
            return self._analyze_pet_left_litter_box(event)

        if event.event_type == PerceptionEventType.PET_DETECTED:
            return self._analyze_pet_detected(event)

        if event.event_type == PerceptionEventType.PERSON_DETECTED:
            return self._analyze_person_detected(event)

        if event.event_type == PerceptionEventType.LITTER_BOX_CLEANED:
            return self._analyze_litter_box_cleaned(event)

        if event.event_type == PerceptionEventType.ANOMALY_DETECTED:
            return self._analyze_anomaly_detected(event)

        if event.event_type == PerceptionEventType.LITTER_BOX_WEIGHT_LOW:
            return self._analyze_litter_box_weight_low(event)

        if event.event_type == PerceptionEventType.PET_WEIGHED:
            return self._analyze_pet_weighed(event)

        if event.event_type == PerceptionEventType.MOTION_DETECTED:
            # 普通移动检测，不通知
            return PerceptionDecision(
                should_notify=False,
                reason="普通移动检测，无需通知",
            )

        # 默认：不通知
        return PerceptionDecision(
            should_notify=False,
            reason=f"无处理规则: {event.event_type}",
        )

    # ─── 猫砂盆相关 ──────────────────────────────────────────────────────────

    def _analyze_litter_box_full(self, event: PerceptionEvent) -> PerceptionDecision:
        """集便仓满——查 HA 状态确认，推微信提醒。"""
        # 查 HA 猫砂盆状态做交叉验证
        litter_box_state = self._get_litter_box_state()

        if litter_box_state is None:
            # HA 数据不可用，只依赖感知
            return PerceptionDecision(
                should_notify=True,
                message="🐱 猫砂盆集便仓已满，请及时清理。",
                reason="HA 状态不可用，依赖感知事件",
            )

        # HA 也确认 full
        if litter_box_state.get("full", False):
            return PerceptionDecision(
                should_notify=True,
                message="🐱 猫砂盆集便仓已满（感知 + HA 双重确认），请及时清理。",
                reason="HA + 感知双重确认 full",
            )

        # 感知说满但 HA 不认为满——可能误报，降低优先级
        return PerceptionDecision(
            should_notify=True,
            message="🐱 猫砂盆感知到集便仓可能已满，请检查一下。",
            reason="感知说满，HA 未确认，疑似误报",
        )

    def _analyze_pet_at_litter_box(self, event: PerceptionEvent) -> PerceptionDecision:
        """宠物进入猫砂盆区域——检查猫砂盆状态决定是否需要干预。"""
        litter_box_state = self._get_litter_box_state()

        if litter_box_state is None:
            return PerceptionDecision(
                should_notify=False,
                reason="HA 状态不可用，无法判断猫砂盆状态",
            )

        is_full = litter_box_state.get("full", False)
        is_off = litter_box_state.get("mode") == "off" or not litter_box_state.get("power", True)

        if is_full:
            # 集便仓满 + 猫来了 → 提醒
            return PerceptionDecision(
                should_notify=True,
                message="🐱 猫猫去厕所了，但猫砂盆集便仓已满，需要清理！",
                reason="集便仓满 + 宠物到来",
            )

        if is_off:
            # 猫砂盆关机 + 猫来了 → 静默（Off 是正常工作模式）
            return PerceptionDecision(
                should_notify=False,
                reason="猫砂盆 Off 模式，猫使用中，正常状态",
            )

        # 正常状态，不通知
        return PerceptionDecision(
            should_notify=False,
            reason="猫砂盆正常，宠物正常使用",
        )

    def _analyze_pet_left_litter_box(self, event: PerceptionEvent) -> PerceptionDecision:
        """宠物离开猫砂盆——检查是否需要触发清洁。"""
        litter_box_state = self._get_litter_box_state()

        if litter_box_state is None:
            return PerceptionDecision(should_notify=False, reason="HA 状态不可用")

        is_full = litter_box_state.get("full", False)
        if is_full:
            return PerceptionDecision(
                should_notify=True,
                message="🐱 猫猫用完厕所了，集便仓已满，需要清理。",
                reason="宠物离开 + 集便仓满",
            )

        # 正常：宠物用完，猫砂盆会自动清洁
        return PerceptionDecision(
            should_notify=False,
            reason="宠物离开，集便仓未满，等待自动清洁",
        )

    # ─── 通用感知 ─────────────────────────────────────────────────────────────

    def _analyze_pet_detected(self, event: PerceptionEvent) -> PerceptionDecision:
        """检测到宠物——通常不需要通知，除非关联到异常区域。"""
        room = event.room or "未知区域"
        subject = event.primary_subject()
        name = (subject.name or "猫猫") if subject else "猫猫"

        # 如果是特殊区域（如门口）才通知
        sensitive_rooms = {"门口", "大门", "玄关", "阳台"}
        if room in sensitive_rooms:
            return PerceptionDecision(
                should_notify=True,
                message=f"🐾 {name} 在{room}出现了。",
                reason=f"宠物在敏感区域: {room}",
            )

        return PerceptionDecision(should_notify=False, reason=f"宠物在 {room}，正常活动")

    def _analyze_person_detected(self, event: PerceptionEvent) -> PerceptionDecision:
        """检测到人物——如果是陌生人则通知。"""
        subject = event.primary_subject()
        if subject and subject.name:
            # 已识别的家庭成员，不通知
            return PerceptionDecision(
                should_notify=False,
                reason=f"已识别家庭成员: {subject.name}",
            )

        room = event.room or "未知区域"
        return PerceptionDecision(
            should_notify=True,
            message=f"👤 {room}检测到陌生人，请注意。",
            reason="未识别人物",
        )

    def _analyze_litter_box_cleaned(self, event: PerceptionEvent) -> PerceptionDecision:
        """猫砂盆完成清洁——静默确认，不通知。"""
        return PerceptionDecision(
            should_notify=False,
            reason="猫砂盆清洁完成，正常状态",
        )

    def _analyze_litter_box_weight_low(self, event: PerceptionEvent) -> PerceptionDecision:
        """猫砂余量不足——通知补砂。"""
        weight = event.context.get("weight_kg")
        weight_str = f"（当前 {weight:.2f}kg）" if weight is not None else ""
        return PerceptionDecision(
            should_notify=True,
            message=f"🪣 猫砂余量不足{weight_str}，请及时补充猫砂。",
            reason="猫砂余量低于阈值",
        )

    def _analyze_pet_weighed(self, event: PerceptionEvent) -> PerceptionDecision:
        """宠物称重完成——记录体重，异常时通知。"""
        from lumi.config import get_config
        pet_cfg = get_config().pet

        subject = event.primary_subject()
        name = (subject.name or pet_cfg.name) if subject else pet_cfg.name
        weight = event.context.get("weight_kg")

        if weight is None:
            return PerceptionDecision(should_notify=False, reason="称重数据缺失")

        if weight < pet_cfg.weight_min_kg or weight > pet_cfg.weight_max_kg:
            return PerceptionDecision(
                should_notify=True,
                message=f"⚖️ {name} 体重 {weight:.2f}kg，数值异常，请关注。",
                reason=f"体重异常: {weight:.2f}kg",
            )

        return PerceptionDecision(
            should_notify=False,
            reason=f"{name} 体重 {weight:.2f}kg，正常范围",
        )

    def _analyze_anomaly_detected(self, event: PerceptionEvent) -> PerceptionDecision:
        """检测到异常——通知。"""
        room = event.room or "未知区域"
        subject = event.primary_subject()
        desc = subject.type if subject else "异常情况"
        return PerceptionDecision(
            should_notify=True,
            message=f"⚠️ {room}检测到{desc}，请注意！",
            reason=f"异常事件: {desc}",
        )

    # ─── HA 状态查询辅助 ─────────────────────────────────────────────────────

    def _get_litter_box_state(self) -> dict[str, Any] | None:
        """从 HA 查询猫砂盆状态，返回标准化 dict 或 None。"""
        if not self.ha_client:
            return None

        try:
            states = self.ha_client.get_states()
            # 查找猫砂盆相关实体（petjc 前缀）
            litter_entities = [
                s for s in states
                if "petjc" in s.get("entity_id", "")
            ]
            if not litter_entities:
                return None

            result: dict[str, Any] = {}

            for entity in litter_entities:
                entity_id: str = entity.get("entity_id", "")
                state: str = entity.get("state", "")
                attrs: dict = entity.get("attributes", {})

                # 集便仓状态
                if "trash" in entity_id or "full" in entity_id:
                    result["full"] = state in ("on", "full", "1", "true")

                # 电源/模式
                if entity_id.endswith("_air_purifier") or "switch" in entity_id:
                    result["power"] = state not in ("off", "0", "false")
                    result["mode"] = attrs.get("preset_mode") or state

                # 备用：从 attributes 里捞
                if "deodorization" in entity_id or "clean" in entity_id:
                    result["last_clean"] = attrs.get("last_changed")

            return result if result else None

        except Exception as e:
            logger.warning("查询猫砂盆 HA 状态失败: %s", e)
            return None
