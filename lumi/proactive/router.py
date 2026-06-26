"""主动巡检 HTTP 端点。

GET  /api/proactive/status  — 查询调度器状态
POST /api/proactive/check   — 立即触发一次全屋巡检，返回告警（不推送 Hermes）
POST /api/proactive/reload  — 重新读取 rules.yaml，热更新规则配置
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from lumi.config import get_config
from lumi.proactive.rules_loader import load_rules_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proactive", tags=["proactive"])


@router.get("/status")
def get_proactive_status() -> dict[str, Any]:
    """查询主动巡检引擎状态（是否运行、上次巡检时间、已知告警数）。"""
    from lumi.deps import get_proactive_scheduler
    scheduler = get_proactive_scheduler()
    if scheduler is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "running": scheduler.is_running(),
        "last_check_at": scheduler.last_check_at,
        "known_alert_count": len(scheduler._alert_sent_at),
    }


@router.post("/check")
def run_proactive_check() -> dict[str, Any]:
    """立即触发一次全屋巡检，返回当前告警列表（不推送 Hermes）。"""
    from lumi.deps import get_proactive_scheduler, get_device_graph_service, get_ha_client
    scheduler = get_proactive_scheduler()
    if scheduler is None:
        return {"alerts": [], "count": 0, "report": "", "error": "proactive scheduler not initialized"}
    svc = get_device_graph_service()
    ha_client = get_ha_client()
    devices = svc.get_graph().devices
    ha_states = ha_client.get_states() if ha_client else []
    alerts = scheduler.analyzer.analyze(devices, ha_states)
    return {
        "alerts": [a.model_dump() for a in alerts],
        "count": len(alerts),
        "report": scheduler.analyzer.format_report(alerts),
    }


@router.post("/reload")
def reload_proactive_rules() -> dict[str, Any]:
    """重新读取 rules.yaml，热更新 ProactiveAnalyzer 的规则配置。"""
    from lumi.deps import get_proactive_scheduler

    scheduler = get_proactive_scheduler()
    if scheduler is None:
        return {"ok": False, "error": "proactive scheduler not initialized", "active_rules": []}

    config = get_config()
    rules_config = load_rules_config(config.proactive.rules_file)
    scheduler.analyzer.reload_rules(rules_config)
    active = scheduler.analyzer.active_rule_names()
    return {
        "ok": True,
        "active_rules": active,
        "disabled_rules": rules_config.disabled_rules,
    }
