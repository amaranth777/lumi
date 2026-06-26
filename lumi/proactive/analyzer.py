"""主动巡检分析器。

聚合多条规则，生成告警报告。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from lumi.device_graph.schema import Device
from lumi.proactive.rules import (
    Alert,
    BUILTIN_RULES,
    EntityValueRule,
    LowBatteryRule,
    ProactiveRule,
)

if TYPE_CHECKING:
    from lumi.config import LumiConfig
    from lumi.proactive.rules_loader import RulesConfig

logger = logging.getLogger(__name__)

# 告警级别 emoji
_LEVEL_EMOJI = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


def _build_rules(rules_config: RulesConfig | None, lumi_config: LumiConfig | None) -> list:
    """根据 rules_config 构建规则实例列表。"""
    disabled: set[str] = set(rules_config.disabled_rules) if rules_config else set()

    # 确定需要启用的规则名列表
    if lumi_config is not None:
        enabled_names = list(lumi_config.proactive.rules)
    else:
        enabled_names = list(BUILTIN_RULES.keys())

    rules = []
    for name in enabled_names:
        if name in disabled:
            continue
        rule_cls = BUILTIN_RULES.get(name)
        if rule_cls is None:
            logger.warning("未知规则: %s，跳过", name)
            continue
        # EntityValueRule 仅在有 entity_monitors 时实例化
        if rule_cls is EntityValueRule:
            if rules_config and rules_config.entity_monitors:
                rules.append(rule_cls(rules_config=rules_config))
            continue
        rules.append(rule_cls(rules_config=rules_config))
    return rules


class ProactiveAnalyzer:
    """主动巡检规则引擎。

    聚合多条 ProactiveRule，对设备列表执行全量检查，输出告警列表。
    """

    def __init__(
        self,
        rules: list[ProactiveRule] | None = None,
        config: LumiConfig | None = None,
        rules_config: RulesConfig | None = None,
        lumi_config: LumiConfig | None = None,
    ) -> None:
        # 向后兼容：支持直接传 rules 列表
        self.config = config or lumi_config
        self.rules_config = rules_config
        if rules is not None:
            self.rules = rules
        else:
            self.rules = _build_rules(rules_config, self.config)

    def reload_rules(self, rules_config: RulesConfig) -> None:
        """热重载规则配置（不重启），根据新配置重建规则列表。"""
        self.rules_config = rules_config
        self.rules = _build_rules(rules_config, self.config)
        logger.info(
            "规则热重载完成，已加载 %d 条规则，禁用: %s",
            len(self.rules),
            rules_config.disabled_rules,
        )

    def active_rule_names(self) -> list[str]:
        """返回当前生效的规则名列表。"""
        return [getattr(r, "name", str(r)) for r in self.rules]

    def analyze(self, devices: list[Device], ha_states: list[dict]) -> list[Alert]:
        """对设备列表执行所有规则检查，返回合并的告警列表。"""
        all_alerts: list[Alert] = []
        for rule in self.rules:
            try:
                alerts = rule.check(devices, ha_states)
                all_alerts.extend(alerts)
            except Exception as e:
                logger.error("规则 %s 执行失败: %s", getattr(rule, "name", rule), e)
        return all_alerts

    def format_report(self, alerts: list[Alert]) -> str:
        """生成管家风格的告警报告。

        无告警时返回空字符串（安静原则）。
        """
        if not alerts:
            return ""

        lines: list[str] = ["🏠 Lumi 巡检报告"]
        lines.append("─" * 20)

        # 按级别排序：critical > warning > info
        level_order = {"critical": 0, "warning": 1, "info": 2}
        sorted_alerts = sorted(alerts, key=lambda a: level_order.get(a.level, 99))

        for alert in sorted_alerts:
            emoji = _LEVEL_EMOJI.get(alert.level, "•")
            lines.append(f"{emoji} {alert.message}")
            if alert.action_hint:
                lines.append(f"   💡 建议：{alert.action_hint}")

        lines.append("─" * 20)
        lines.append(f"共 {len(alerts)} 条告警")
        return "\n".join(lines)
