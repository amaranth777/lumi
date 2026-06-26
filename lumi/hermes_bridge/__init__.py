"""Hermes Bridge — 感知事件 → Hermes gateway 推送通知。

职责：
  1. 接收 PerceptionAnalyzer 的决策结果
  2. 通过 Hermes gateway HTTP API 推送微信通知
  3. 维护推送限流（同类事件 cooldown，防止轰炸）
  4. 记录推送日志到 ~/.hermes/logs/lumi_bridge.log
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from lumi.perception.analyzer import PerceptionDecision
from lumi.perception.events import PerceptionEvent, PerceptionEventType

logger = logging.getLogger(__name__)

# Hermes gateway API — 本地直连
HERMES_API_BASE = os.getenv("HERMES_API_BASE", "http://127.0.0.1:8766")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")

# 默认推送目标：微信 home channel
DEFAULT_TARGET = os.getenv("LUMI_NOTIFY_TARGET", "weixin")

# 同类事件推送冷却（秒）
DEFAULT_COOLDOWN = int(os.getenv("LUMI_NOTIFY_COOLDOWN", "300"))  # 5 分钟


@dataclass
class NotifyResult:
    """推送结果。"""
    success: bool
    target: str
    message: str
    skipped: bool = False   # 被限流跳过
    skip_reason: str = ""
    error: str = ""
    response: dict[str, Any] = field(default_factory=dict)


class CooldownTracker:
    """同类事件限流追踪器。"""

    def __init__(self, default_cooldown: int = DEFAULT_COOLDOWN) -> None:
        self._last_sent: dict[str, float] = {}
        self.default_cooldown = default_cooldown

    def is_cooled_down(self, key: str, cooldown: int | None = None) -> bool:
        """返回 True 表示可以发送（已冷却）。"""
        cd = cooldown if cooldown is not None else self.default_cooldown
        last = self._last_sent.get(key, 0.0)
        return (time.time() - last) >= cd

    def mark_sent(self, key: str) -> None:
        self._last_sent[key] = time.time()

    def remaining(self, key: str, cooldown: int | None = None) -> float:
        """返回剩余冷却秒数（0 表示已可发送）。"""
        cd = cooldown if cooldown is not None else self.default_cooldown
        last = self._last_sent.get(key, 0.0)
        return max(0.0, cd - (time.time() - last))


# 每种事件类型的冷却时间（秒）
EVENT_COOLDOWNS: dict[PerceptionEventType, int] = {
    PerceptionEventType.LITTER_BOX_FULL: 1800,        # 30 分钟
    PerceptionEventType.PET_AT_LITTER_BOX: 600,       # 10 分钟
    PerceptionEventType.PET_LEFT_LITTER_BOX: 600,
    PerceptionEventType.PET_DETECTED: 300,
    PerceptionEventType.PERSON_DETECTED: 120,          # 2 分钟（安全优先）
    PerceptionEventType.ANOMALY_DETECTED: 60,          # 1 分钟（告警优先）
    PerceptionEventType.LITTER_BOX_CLEANED: 3600,      # 1 小时
    PerceptionEventType.LITTER_BOX_WEIGHT_LOW: 14400,  # 4 小时（补砂提醒）
    PerceptionEventType.PET_WEIGHED: 3600,             # 1 小时（体重异常才推送）
    PerceptionEventType.MOTION_DETECTED: 600,
    PerceptionEventType.UNKNOWN: 300,
}


def _hermes_send(message: str, target: str = DEFAULT_TARGET) -> dict[str, Any]:
    """通过 Hermes gateway send_message API 推送消息。"""
    url = f"{HERMES_API_BASE}/api/send_message"
    payload = json.dumps({"target": target, "message": message}).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if HERMES_API_KEY:
        headers["Authorization"] = f"Bearer {HERMES_API_KEY}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")

    # 绕过 Clash 代理
    backup = {}
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        if k in os.environ:
            backup[k] = os.environ.pop(k)
    os.environ["NO_PROXY"] = "*"

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from e
    finally:
        for k, v in backup.items():
            os.environ[k] = v


class HermesBridge:
    """Lumi 感知决策 → Hermes 推送桥。

    用法::

        bridge = HermesBridge()
        decision = analyzer.analyze(event)
        result = bridge.notify(event, decision)
    """

    def __init__(
        self,
        target: str = DEFAULT_TARGET,
        cooldown_tracker: CooldownTracker | None = None,
    ) -> None:
        self.target = target
        self.cooldown = cooldown_tracker or CooldownTracker()
        self._log_path = os.path.expanduser("~/.hermes/logs/lumi_bridge.log")
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)

    def notify(
        self,
        event: PerceptionEvent,
        decision: PerceptionDecision,
        force: bool = False,
    ) -> NotifyResult:
        """根据感知决策推送通知。

        Args:
            event: 触发的感知事件
            decision: 感知分析器的决策结果
            force: True 时跳过冷却检查（用于测试/紧急场景）
        """
        if not decision.should_notify or not decision.message:
            result = NotifyResult(
                success=True,
                target=self.target,
                message=decision.message or "",
                skipped=True,
                skip_reason=f"decision.should_notify=False: {decision.reason}",
            )
            self._write_log(event, decision, result)
            return result

        # 冷却检查
        cooldown_key = f"{event.event_type}:{event.room or 'any'}"
        event_cooldown = EVENT_COOLDOWNS.get(event.event_type, DEFAULT_COOLDOWN)

        if not force and not self.cooldown.is_cooled_down(cooldown_key, event_cooldown):
            remaining = self.cooldown.remaining(cooldown_key, event_cooldown)
            result = NotifyResult(
                success=True,
                target=self.target,
                message=decision.message,
                skipped=True,
                skip_reason=f"冷却中，剩余 {remaining:.0f}s (key={cooldown_key})",
            )
            logger.debug("限流跳过推送: %s", result.skip_reason)
            self._write_log(event, decision, result)
            return result

        # 推送
        try:
            final_message = decision.message
            if event.image_url:
                final_message = f"{decision.message}\n摄像头截图：{event.image_url}"
            resp = _hermes_send(final_message, self.target)
            self.cooldown.mark_sent(cooldown_key)
            result = NotifyResult(
                success=True,
                target=self.target,
                message=final_message,
                response=resp,
            )
            logger.info("推送成功: target=%s event=%s", self.target, event.event_type)
        except Exception as e:
            result = NotifyResult(
                success=False,
                target=self.target,
                message=decision.message,
                error=str(e),
            )
            logger.error("推送失败: %s", e)

        self._write_log(event, decision, result)
        return result

    def send_notification(self, message: str) -> NotifyResult:
        """直接推送纯文本通知（不需要 PerceptionEvent/Decision）。

        用于主动巡检报告等场景。
        """
        try:
            resp = _hermes_send(message, self.target)
            result = NotifyResult(
                success=True,
                target=self.target,
                message=message,
                response=resp,
            )
            logger.info("send_notification 推送成功: target=%s", self.target)
        except Exception as e:
            result = NotifyResult(
                success=False,
                target=self.target,
                message=message,
                error=str(e),
            )
            logger.error("send_notification 推送失败: %s", e)
        return result

    def _write_log(
        self,
        event: PerceptionEvent,
        decision: PerceptionDecision,
        result: NotifyResult,
    ) -> None:
        """追加写入本地推送日志。"""
        try:
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "event_id": event.event_id,
                "event_type": event.event_type,
                "room": event.room,
                "should_notify": decision.should_notify,
                "message": decision.message,
                "skipped": result.skipped,
                "skip_reason": result.skip_reason,
                "success": result.success,
                "error": result.error,
            }
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("写推送日志失败: %s", e)


# 全局单例（可被其他模块直接 import）
_bridge: HermesBridge | None = None


def get_bridge(target: str = DEFAULT_TARGET) -> HermesBridge:
    """获取全局 HermesBridge 单例。"""
    global _bridge
    if _bridge is None:
        _bridge = HermesBridge(target=target)
    return _bridge
