"""主动巡检调度器。

后台定时任务：定时触发分析 + 推送。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from lumi.websocket import manager as ws_manager

if TYPE_CHECKING:
    from lumi.config import LumiConfig
    from lumi.device_graph.service import DeviceGraphService
    from lumi.hermes_bridge import HermesBridge
    from lumi.proactive.analyzer import ProactiveAnalyzer

logger = logging.getLogger(__name__)

# 日志路径
_LOG_PATH = os.path.expanduser("~/.hermes/logs/lumi_proactive.log")


class ProactiveScheduler:
    """主动巡检调度器。

    每隔 interval_seconds 秒：
      1. 拉取设备图 + HA states
      2. analyzer.analyze()
      3. 有告警 → hermes_bridge.send_notification(report)
      4. 记录日志

    告警去重：同一 device_id+level+message 组合，30 分钟内不重复推送。
    """

    def __init__(
        self,
        analyzer: ProactiveAnalyzer,
        device_graph_svc: DeviceGraphService,
        ha_client: Any,
        hermes_bridge: HermesBridge,
        interval_seconds: int = 300,
        min_alert_interval_seconds: int = 1800,
        config: Any = None,
    ) -> None:
        self.analyzer = analyzer
        self.device_graph_svc = device_graph_svc
        self.ha_client = ha_client
        self.hermes_bridge = hermes_bridge
        self.interval_seconds = interval_seconds
        self.min_alert_interval_seconds = min_alert_interval_seconds
        self.config = config

        # 告警去重：key -> 上次推送时间戳
        self._alert_sent_at: dict[str, float] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self.last_check_at: float = 0.0

        # 确保日志目录存在
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)

    # ─── 公开接口 ────────────────────────────────────────────────────────────

    def is_running(self) -> bool:
        """返回调度器当前是否在后台运行。"""
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """启动后台巡检循环。"""
        if self._running:
            logger.warning("ProactiveScheduler 已在运行")
            return
        self._running = True
        self._task = asyncio.create_task(self.run(), name="proactive_scheduler")
        logger.info("ProactiveScheduler 已启动，间隔 %ds", self.interval_seconds)

    def stop(self) -> None:
        """停止后台巡检循环。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("ProactiveScheduler 已停止")

    async def run(self) -> None:
        """后台巡检主循环。第一次延迟 30 秒等待设备图初始化。"""
        # 首次等待 30 秒，让设备图完成初始化
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return

        while self._running:
            try:
                await self._run_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ProactiveScheduler 巡检异常: %s", e)
                self._write_error_log(str(e))

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    async def run_once(self) -> None:
        """单次巡检（供测试或手动触发使用）。"""
        await self._run_once()

    # ─── 内部实现 ────────────────────────────────────────────────────────────

    async def _run_once(self) -> None:
        """执行一次完整巡检流程。"""
        # 1. 拉取设备图
        try:
            graph = self.device_graph_svc.get_graph()
            devices = graph.devices
        except Exception as e:
            logger.error("获取设备图失败: %s", e)
            self._write_error_log(f"获取设备图失败: {e}")
            return

        # 2. 拉取 HA states
        ha_states: list[dict] = []
        try:
            if self.ha_client is not None:
                ha_states = self.ha_client.get_states() or []
        except Exception as e:
            logger.warning("获取 HA states 失败（继续巡检）: %s", e)

        # 3. 执行规则分析
        try:
            alerts = self.analyzer.analyze(devices, ha_states)
        except Exception as e:
            logger.error("规则分析失败: %s", e)
            self._write_error_log(f"规则分析失败: {e}")
            return

        # 4. 去重过滤
        now = time.time()
        new_alerts = []
        for alert in alerts:
            key = self._alert_key(alert)
            last_sent = self._alert_sent_at.get(key, 0.0)
            if (now - last_sent) >= self.min_alert_interval_seconds:
                new_alerts.append(alert)

        logger.info(
            "巡检完成：共 %d 条告警，去重后 %d 条",
            len(alerts),
            len(new_alerts),
        )

        # 5. 无告警 → 安静，不推送
        if not new_alerts:
            self._write_log(alerts=alerts, sent_count=0)
            return

        # 5b. 自动执行纠正动作
        for alert in new_alerts:
            if alert.auto_action:
                asyncio.ensure_future(self._auto_execute(alert))

        # 6. 生成报告并推送
        try:
            report = self.analyzer.format_report(new_alerts)
            if report:
                self.hermes_bridge.send_notification(report)
                # 更新去重时间戳
                for alert in new_alerts:
                    self._alert_sent_at[self._alert_key(alert)] = now
                logger.info("已推送巡检报告（%d 条告警）", len(new_alerts))
        except Exception as e:
            logger.error("推送巡检报告失败: %s", e)
            self._write_error_log(f"推送失败: {e}")

        # 7. 广播 WebSocket 告警
        try:
            await ws_manager.broadcast_alert([a.model_dump() for a in new_alerts])
        except Exception as e:
            logger.warning("WebSocket 广播告警失败: %s", e)

        self._write_log(alerts=alerts, sent_count=len(new_alerts))
        self.last_check_at = time.time()

    @staticmethod
    def _alert_key(alert) -> str:
        """生成告警去重 key。"""
        return f"{alert.device_id}:{alert.level}:{alert.message}"

    async def _auto_execute(self, alert) -> None:
        """执行 alert.auto_action。格式：action:param1:param2"""
        if not self.config or not self.config.proactive.auto_execute:
            return
        if not alert.auto_action:
            return
        try:
            parts = alert.auto_action.split(":")
            action = parts[0]
            # 只允许安全动作（禁止 empty）
            _FORBIDDEN = {"empty", "delete", "restart_ha"}
            if action in _FORBIDDEN or any(p in _FORBIDDEN for p in parts):
                logger.warning("拒绝危险自动执行: %s", alert.auto_action)
                return
            from lumi.lumi_tool import dispatch
            if action == "control" and len(parts) >= 3:
                dispatch("control", {"device_id": parts[1], "command": parts[2]})
            elif action == "ha_trigger_automation" and len(parts) >= 2:
                dispatch("ha_trigger_automation", {"entity_id": parts[1]})
            elif action == "ha_run_script" and len(parts) >= 2:
                dispatch("ha_run_script", {"entity_id": parts[1]})
            logger.info("自动执行: %s", alert.auto_action)
        except Exception as e:
            logger.warning("自动执行失败 %s: %s", alert.auto_action, e)

    def _write_log(self, alerts: list, sent_count: int) -> None:
        """追加写入巡检日志。"""
        try:
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "total_alerts": len(alerts),
                "sent_count": sent_count,
                "alerts": [
                    {
                        "level": a.level,
                        "device_id": a.device_id,
                        "message": a.message,
                    }
                    for a in alerts
                ],
            }
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("写巡检日志失败: %s", e)

    def _write_error_log(self, error: str) -> None:
        """追加写入错误日志。"""
        try:
            entry = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "error": error,
            }
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
