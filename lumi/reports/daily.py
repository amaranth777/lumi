"""全屋日报生成器，支持早报（清晨 7:00）和晚间（晚上 22:00）。"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

# 模块级导入，使测试 patch 可以拦截
from lumi.lumi_tool import summary, proactive_alerts, health
from lumi.hermes_bridge import HermesBridge

logger = logging.getLogger(__name__)

_LOG_PATH = os.path.expanduser("~/.hermes/logs/lumi_daily_report.log")


def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """静默调用，失败返回 None。"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.warning("日报数据拉取失败 %s: %s", fn.__name__ if hasattr(fn, "__name__") else fn, e)
        return None


def _fmt_alerts(alerts_data: Any) -> str:
    """格式化告警列表为日报文本段落。"""
    if not alerts_data or isinstance(alerts_data, dict) and alerts_data.get("error"):
        return "  ✅ 无异常告警"

    # proactive_alerts 返回 {"alerts": [...]} 或 list
    items: list[Any] = []
    if isinstance(alerts_data, dict):
        items = alerts_data.get("alerts", [])
    elif isinstance(alerts_data, list):
        items = alerts_data

    if not items:
        return "  ✅ 无异常告警"

    lines = []
    for alert in items[:5]:  # 最多显示 5 条
        if isinstance(alert, dict):
            level = alert.get("level", "info")
            emoji = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}.get(level, "⚠️")
            msg = alert.get("message") or alert.get("msg") or str(alert)
            lines.append(f"  {emoji} {msg}")
        else:
            lines.append(f"  ⚠️ {alert}")

    if len(items) > 5:
        lines.append(f"  … 另有 {len(items) - 5} 条告警")

    return "\n".join(lines)


def _fmt_summary(summary_data: Any) -> str:
    """格式化设备摘要。"""
    if not summary_data or (isinstance(summary_data, dict) and summary_data.get("error")):
        return "  暂无设备数据"

    if isinstance(summary_data, dict):
        total = summary_data.get("total_devices") or summary_data.get("total", "—")
        online = summary_data.get("online_devices") or summary_data.get("online", "—")
        rooms = summary_data.get("room_count") or summary_data.get("rooms", "—")
        lines = [f"  共 {total} 台设备，在线 {online} 台"]
        if rooms and rooms != "—":
            lines.append(f"  覆盖 {rooms} 个房间")
        # 设备类型分布
        by_type = summary_data.get("by_type") or summary_data.get("types", {})
        if by_type and isinstance(by_type, dict):
            top = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:3]
            if top:
                type_str = "、".join(f"{k}×{v}" for k, v in top)
                lines.append(f"  主要类型：{type_str}")
        return "\n".join(lines)

    return f"  设备数据：{summary_data}"


def _fmt_health(health_data: Any) -> str:
    """格式化服务健康状态。"""
    if not health_data or (isinstance(health_data, dict) and health_data.get("error")):
        return "  ⚠️ 健康状态未知"

    if isinstance(health_data, dict):
        lines = []
        status = health_data.get("status", "unknown")
        if status == "ok":
            lines.append("  ✅ 服务运行正常")
        else:
            lines.append(f"  ⚠️ 服务状态：{status}")

        for key in ("ha", "miloco", "bridge"):
            val = health_data.get(key)
            if val is not None:
                icon = "✅" if val in ("ok", "connected", True) else "❌"
                label = {"ha": "Home Assistant", "miloco": "Miloco", "bridge": "Bridge"}.get(key, key)
                lines.append(f"  {icon} {label}: {val}")
        return "\n".join(lines)

    return f"  健康状态：{health_data}"


def _fmt_perception(history_data: Any) -> str:
    """格式化感知事件摘要（最近 12h）。"""
    if not history_data or (isinstance(history_data, dict) and history_data.get("error")):
        return "  暂无感知记录"

    items: list[Any] = []
    if isinstance(history_data, dict):
        items = history_data.get("events") or history_data.get("items", [])
        total = history_data.get("total", len(items))
    elif isinstance(history_data, list):
        items = history_data
        total = len(items)
    else:
        return "  暂无感知记录"

    if not items:
        return "  暂无感知记录"

    # 聚合事件类型
    by_type: dict[str, int] = {}
    for ev in items:
        if isinstance(ev, dict):
            t = ev.get("event_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

    lines = [f"  近期感知事件共 {total} 条"]
    top = sorted(by_type.items(), key=lambda x: x[1], reverse=True)[:4]
    for etype, cnt in top:
        lines.append(f"    · {etype}: {cnt} 次")

    return "\n".join(lines)


class DailyReport:
    """全屋日报生成器。"""

    def generate(self, report_type: str = "morning") -> str:
        """生成日报内容（管家风格）。

        Args:
            report_type: "morning" 早报 或 "evening" 晚报
        """
        is_morning = report_type == "morning"
        title = "☀️ 府上早安" if is_morning else "🌙 晚间好"
        date_str = time.strftime("%Y年%m月%d日")
        time_str = time.strftime("%H:%M")

        # 并行拉取数据
        import concurrent.futures
        import lumi.reports.daily as _self

        results: dict[str, Any] = {}

        def _fetch(key: str, fn: Any) -> None:
            results[key] = _safe_call(fn)

        tasks: list[tuple[str, Any]] = [
            ("summary", _self.summary),
            ("alerts", _self.proactive_alerts),
            ("health", _self.health),
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_fetch, k, fn) for k, fn in tasks]
            concurrent.futures.wait(futs)

        # 拉取感知历史（最近 10 条）
        try:
            import lumi.lumi_tool as _tool
            results["perception"] = _safe_call(_tool.perception_history, limit=10)
        except Exception:
            results["perception"] = None

        # 构建日报
        lines = [
            f"{'─' * 32}",
            f"  {title}",
            f"  {date_str}  {time_str}",
            f"{'─' * 32}",
            "",
            "【全屋设备概况】",
            _fmt_summary(results.get("summary")),
            "",
            "【当前告警】",
            _fmt_alerts(results.get("alerts")),
            "",
            "【感知事件摘要】",
            _fmt_perception(results.get("perception")),
            "",
            "【服务健康状态】",
            _fmt_health(results.get("health")),
            "",
            f"{'─' * 32}",
        ]

        content = "\n".join(lines)
        self._write_log(report_type, content)
        return content

    def send(self, report_type: str = "morning") -> bool:
        """Generate + 通过 HermesBridge 推送。

        Args:
            report_type: "morning" 早报 或 "evening" 晚报

        Returns:
            True 推送成功，False 推送失败
        """
        import lumi.reports.daily as _self

        content = self.generate(report_type=report_type)
        try:
            bridge = _self.HermesBridge()
            result = bridge.send_notification(content)
            ok = result.success
            logger.info("日报推送 %s: type=%s", "成功" if ok else "失败", report_type)
            return ok
        except Exception as e:
            logger.error("日报推送异常: %s", e)
            return False

    def _write_log(self, report_type: str, content: str) -> None:
        """追加写入日报日志。"""
        try:
            os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "type": report_type,
                "content": content,
            }
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("写日报日志失败: %s", e)
