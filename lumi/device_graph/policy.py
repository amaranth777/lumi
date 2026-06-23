"""策略守卫层 — 高风险设备操作拦截。

PolicyEngine 在 DeviceGraphService.execute_command() 里被调用，
在真正执行命令前检查规则，返回 PolicyViolation 表示拦截，None 表示放行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lumi.device_graph.schema import Device


# ─── 数据结构 ─────────────────────────────────────────────────────────────────


@dataclass
class PolicyViolation:
    """命令被策略拦截时的返回值。"""

    blocked: bool
    reason: str
    rule_name: str


@dataclass
class PolicyRule:
    """策略规则基类。子类实现 check()。"""

    name: str
    description: str

    def check(
        self, device: Device, command: str, params: dict[str, Any]
    ) -> PolicyViolation | None:
        raise NotImplementedError


# ─── 内置规则 ─────────────────────────────────────────────────────────────────


@dataclass
class BlockedCommandRule(PolicyRule):
    """按 device_id 片段 + 命令名拦截，支持 _force override。"""

    device_id_fragment: str = ""
    blocked_commands: list[str] = field(default_factory=list)

    def check(
        self, device: Device, command: str, params: dict[str, Any]
    ) -> PolicyViolation | None:
        # 设备 ID 不包含目标片段 → 放行
        if self.device_id_fragment not in device.id:
            return None
        # 命令不在拦截列表 → 放行
        if command.lower() not in [c.lower() for c in self.blocked_commands]:
            return None
        # _force override → 放行
        if params.get("_force") == "CONFIRM_EMPTY":
            return None
        return PolicyViolation(
            blocked=True,
            reason=f"[{self.name}] 命令 '{command}' 被策略拦截：{self.description}",
            rule_name=self.name,
        )


@dataclass
class CallActionParamRule(PolicyRule):
    """按 device_id 片段 + call_action 参数拦截特定 siid/aiid 组合。"""

    device_id_fragment: str = ""
    blocked_aiids: list[int] = field(default_factory=list)

    def check(
        self, device: Device, command: str, params: dict[str, Any]
    ) -> PolicyViolation | None:
        if command != "call_action":
            return None
        if self.device_id_fragment not in device.id:
            return None
        aiid = params.get("aiid")
        if aiid not in self.blocked_aiids:
            return None
        # _force override → 放行
        if params.get("_force") == "CONFIRM_EMPTY":
            return None
        return PolicyViolation(
            blocked=True,
            reason=(
                f"[{self.name}] call_action aiid={aiid} 被策略拦截：{self.description}"
            ),
            rule_name=self.name,
        )


# ─── 引擎 ─────────────────────────────────────────────────────────────────────


@dataclass
class PolicyEngine:
    """按顺序评估规则链，第一个拦截立即返回。"""

    rules: list[PolicyRule] = field(default_factory=list)

    def evaluate(
        self, device: Device, command: str, params: dict[str, Any]
    ) -> PolicyViolation | None:
        for rule in self.rules:
            result = rule.check(device, command, params)
            if result is not None:
                return result
        return None


# ─── 默认策略 ─────────────────────────────────────────────────────────────────

_LITTER_BOX_FRAGMENT = "petjc"


def build_default_policy_engine() -> PolicyEngine:
    """构建默认策略引擎，包含猫砂盆 Empty 模式拦截规则。"""
    return PolicyEngine(
        rules=[
            # 规则1：拦截 empty / Empty 命令
            BlockedCommandRule(
                name="litter_box_no_empty",
                description="禁止对猫砂盆执行 Empty（清空）模式，防止意外倾倒猫砂",
                device_id_fragment=_LITTER_BOX_FRAGMENT,
                blocked_commands=["empty", "Empty"],
            ),
            # 规则2：拦截 call_action aiid=3（MIoT Empty action）
            CallActionParamRule(
                name="litter_box_no_action_3",
                description="禁止对猫砂盆执行 call_action aiid=3（MIoT Empty 指令）",
                device_id_fragment=_LITTER_BOX_FRAGMENT,
                blocked_aiids=[3],
            ),
        ]
    )


def get_default_policy_engine() -> PolicyEngine:
    """service.py 注入点 — 返回默认策略引擎实例。"""
    return build_default_policy_engine()
