"""Lumi 策略守卫层。

在命令执行前拦截高风险操作，防止误操作。
所有策略以声明式规则描述，易于扩展。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from lumi.device_graph.schema import Device

logger = logging.getLogger(__name__)


@dataclass
class PolicyViolation:
    """策略拦截结果。"""
    blocked: bool
    reason: str
    rule_name: str


@dataclass
class PolicyRule:
    """单条策略规则基类。"""
    name: str
    description: str

    def check(self, device: Device, command: str, params: dict[str, Any]) -> PolicyViolation | None:
        """返回 PolicyViolation 表示拦截，返回 None 表示放行。"""
        raise NotImplementedError


@dataclass
class BlockedCommandRule(PolicyRule):
    """禁止特定设备执行特定命令（精确匹配）。"""
    device_id_fragment: str        # 设备 ID 包含此字符串时触发
    blocked_commands: list[str]    # 被拦截的命令列表
    override_keyword: str = ""     # 用户必须在 params 里提供此关键字才能强制执行

    def check(self, device: Device, command: str, params: dict[str, Any]) -> PolicyViolation | None:
        if self.device_id_fragment not in device.id:
            return None
        if command not in self.blocked_commands:
            return None
        # 检查强制覆盖关键字
        if self.override_keyword and params.get("_force") == self.override_keyword:
            logger.warning(
                "策略 [%s] 被强制覆盖，设备=%s 命令=%s",
                self.name, device.id, command
            )
            return None
        return PolicyViolation(
            blocked=True,
            reason=f"策略拒绝：{self.description}（设备: {device.name}, 命令: {command}）",
            rule_name=self.name,
        )


@dataclass
class DeviceTypeCommandRule(PolicyRule):
    """禁止特定设备类型执行某些命令。"""
    device_type: str
    blocked_commands: list[str]

    def check(self, device: Device, command: str, params: dict[str, Any]) -> PolicyViolation | None:
        if device.type != self.device_type:
            return None
        if command not in self.blocked_commands:
            return None
        return PolicyViolation(
            blocked=True,
            reason=f"策略拒绝：{self.description}（命令: {command}）",
            rule_name=self.name,
        )


@dataclass
class PolicyEngine:
    """策略引擎：按顺序检查所有规则。"""
    rules: list[PolicyRule] = field(default_factory=list)

    def evaluate(
        self, device: Device, command: str, params: dict[str, Any]
    ) -> PolicyViolation | None:
        """顺序评估所有规则，第一条命中即拦截。"""
        for rule in self.rules:
            violation = rule.check(device, command, params)
            if violation and violation.blocked:
                logger.warning(
                    "策略拦截 [%s]: device=%s command=%s reason=%s",
                    rule.name, device.id, command, violation.reason
                )
                return violation
        return None


# ─────────────────────────────────────────────
# 默认策略集（生产用）
# ─────────────────────────────────────────────

def build_default_policy_engine() -> PolicyEngine:
    """构造默认策略引擎，包含所有内置安全规则。"""
    return PolicyEngine(rules=[
        # 猫砂盆：绝对禁止 Empty（清空/清倒）模式
        # 除非 params 里带 _force="CONFIRM_EMPTY"
        BlockedCommandRule(
            name="litter_box_no_empty",
            description="猫砂盆禁止执行 Empty（清空）操作，防止意外清空",
            device_id_fragment="petjc",           # 匹配猫砂盆设备 ID 前缀
            blocked_commands=["empty", "Empty", "set_empty", "call_empty"],
            override_keyword="CONFIRM_EMPTY",
        ),
        # 猫砂盆：禁止直接 call_action 且 aiid=3（通常是倒猫砂动作）
        # 说明：aiid 3 在部分固件版本对应 Empty，保守拦截
        BlockedCommandRule(
            name="litter_box_no_action_3",
            description="猫砂盆禁止 call_action aiid=3（倒猫砂动作）",
            device_id_fragment="petjc",
            blocked_commands=["call_action"],
            override_keyword="CONFIRM_EMPTY",
        ),
    ])


# 全局默认实例（延迟初始化时也可以直接用）
_default_engine: PolicyEngine | None = None


def get_default_policy_engine() -> PolicyEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = build_default_policy_engine()
    return _default_engine
