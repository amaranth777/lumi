"""lumi/lumi_tool.py — Lumi 工具 action 分发器。

供外部调用（Hermes 工具调用、MCP、CLI 等），每个 action 封装一个能力。
所有 action 统一通过 HTTP 调用本地 Lumi API（:8810），不直接导入内部模块。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.parse
from typing import Any

logger = logging.getLogger(__name__)


def _lumi_base_url() -> str:
    """获取本地 lumi 服务地址。"""
    from lumi.config import get_config
    cfg = get_config()
    return f"http://{cfg.server.host}:{cfg.server.port}"


def _clear_proxy() -> dict[str, str]:
    """清除代理环境变量，返回备份。"""
    backup: dict[str, str] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                "http_proxy", "https_proxy", "all_proxy"):
        if key in os.environ:
            backup[key] = os.environ.pop(key)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    return backup


def _restore_proxy(backup: dict[str, str]) -> None:
    """恢复代理环境变量。"""
    for key, val in backup.items():
        os.environ[key] = val


def _lumi_get(path: str) -> Any:
    """向本地 lumi 服务发 GET，绕代理。"""
    url = f"{_lumi_base_url()}{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    backup = _clear_proxy()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    finally:
        _restore_proxy(backup)


def _lumi_post(path: str, body: dict[str, Any]) -> Any:
    """向本地 lumi 服务发 POST，绕代理。"""
    url = f"{_lumi_base_url()}{path}"
    payload = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    backup = _clear_proxy()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    finally:
        _restore_proxy(backup)


# ─── 基础 action ───────────────────────────────────────────────────────────────

def health() -> dict[str, Any]:
    """检查 Lumi 服务健康状态（HA/Miloco连通性、设备数）。"""
    return _lumi_get("/health")


def status() -> dict[str, Any]:
    """获取 Lumi 运行时详情（设备分布/场景数/bridge状态/感知统计）。"""
    return _lumi_get("/api/status")


def summary() -> dict[str, Any]:
    """获取全屋设备摘要（总数/类型/房间分布）。"""
    return _lumi_get("/api/device_graph/summary")


def types() -> dict[str, Any]:
    """获取设备类型分布统计。"""
    return _lumi_get("/api/device_graph/types")


def search(query: str) -> list[dict[str, Any]]:
    """搜索设备（按名称/ID/房间/类型关键字）。"""
    q = urllib.parse.quote(query)
    return _lumi_get(f"/api/device_graph/search?q={q}")


def room(room_name: str) -> list[dict[str, Any]]:
    """查询指定房间的所有设备。"""
    name = urllib.parse.quote(room_name)
    return _lumi_get(f"/api/device_graph/rooms/{name}")


def control(device_id: str, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """控制单个设备。command 如 turn_on/turn_off/clean 等，params 为命令参数。"""
    return _lumi_post(
        f"/api/device_graph/{device_id}/command",
        {"command": command, "params": params or {}},
    )


def batch_control(commands: list[dict[str, Any]]) -> dict[str, Any]:
    """批量控制多个设备。commands=[{device_id, command, params}, ...]"""
    return _lumi_post("/api/device_graph/batch/command", {"commands": commands})


def scenes() -> list[dict[str, Any]]:
    """列出所有已定义场景。"""
    return _lumi_get("/api/scenes")


def run_scene(scene_id: str) -> dict[str, Any]:
    """执行指定场景。"""
    return _lumi_post(f"/api/scenes/{scene_id}/execute", {})


def perception_types() -> list[str]:
    """列出所有感知事件类型。"""
    return _lumi_get("/api/perception/events/types")


def perception_test(
    event_type: str,
    subject: str = "cat",
    room_name: str = "客厅",
) -> dict[str, Any]:
    """感知事件 dry run（分析但不推送 Hermes）。"""
    return _lumi_post("/api/perception/webhook/test", {
        "event_type": event_type,
        "subjects": [{"type": subject}],
        "room": room_name,
    })


def perception_send(
    event_type: str,
    event_id: str = "",
    camera_id: str | None = None,
    room_name: str | None = None,
    context: dict[str, Any] | None = None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
) -> dict[str, Any]:
    """真实触发感知 webhook（POST /api/perception/webhook），会推送 Hermes 通知。"""
    body: dict[str, Any] = {
        "event_type": event_type,
        "event_id": event_id,
        "camera_id": camera_id,
        "room": room_name,
        "context": context or {},
        "image_url": image_url,
        "thumbnail_url": thumbnail_url,
    }
    try:
        result = _lumi_post("/api/perception/webhook", body)
        return {"sent": True, "response": result}
    except Exception as e:
        logger.warning("perception_send 失败: %s", e)
        return {"sent": False, "error": str(e)}


# ─── HA action ────────────────────────────────────────────────────────────────

def ha_services() -> dict[str, Any]:
    """列出 HA 可用服务域列表。"""
    return _lumi_get("/api/ha/services")


def ha_automations() -> list[dict[str, Any]]:
    """列出所有自动化（entity_id / friendly_name / state）。"""
    return _lumi_get("/api/ha/automations")


def ha_toggle_automation(entity_id: str, enable: bool) -> dict[str, Any]:
    """启用（enable=True）或禁用（enable=False）自动化。"""
    return _lumi_post(f"/api/ha/automations/{entity_id}/toggle", {"enable": enable})


def ha_trigger_automation(entity_id: str) -> dict[str, Any]:
    """触发执行 HA 自动化（不同于 toggle，这里是立即运行一次）。"""
    return _lumi_post(f"/api/ha/automations/{entity_id}/trigger", {})


def ha_run_script(entity_id: str) -> dict[str, Any]:
    """执行 HA 脚本。"""
    return _lumi_post(f"/api/ha/scripts/{entity_id}/run", {})


def ha_history(entity_id: str, hours: int = 24) -> dict[str, Any]:
    """查询设备状态历史（最近 hours 小时）。"""
    eid = urllib.parse.quote(entity_id)
    return _lumi_get(f"/api/ha/history/{eid}?hours={hours}")


def ha_fire_event(event_type: str, event_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """触发 HA 自定义事件。"""
    return _lumi_post(f"/api/ha/events/{event_type}", {"event_data": event_data or {}})


def ha_render_template(template: str) -> dict[str, Any]:
    """渲染 Jinja2 模板（通过 HA /api/template）。"""
    return _lumi_post("/api/ha/template", {"template": template})


def ha_config() -> dict[str, Any]:
    """获取 HA 实例配置信息。"""
    return _lumi_get("/api/ha/config")


def ha_sync_automations() -> dict[str, Any]:
    """将 HA 自动化同步到 Lumi 场景列表（一键导入）。"""
    return _lumi_post("/api/ha/sync_automations", {})


def ha_device_summary(entity_id: str) -> dict[str, Any]:
    """获取 HA 单个实体的当前状态摘要（state + 主要属性 + 最近 1 小时变化趋势）。"""
    eid = urllib.parse.quote(entity_id)
    return _lumi_get(f"/api/ha/history/{eid}?hours=1")


# ─── Miloco action ────────────────────────────────────────────────────────────

def cameras() -> list[dict[str, Any]]:
    """获取 Miloco 摄像头设备列表（含 did/name/room/online 等信息）。"""
    from lumi.deps import get_miloco_client
    client = get_miloco_client()
    if client is None:
        return []
    return client.get_camera_list()


# ─── 主动巡检 action ──────────────────────────────────────────────────────────

def proactive_status() -> dict[str, Any]:
    """查询主动巡检引擎状态（是否运行、上次巡检时间、已知告警数）。"""
    return _lumi_get("/api/proactive/status")


def proactive_alerts() -> dict[str, Any]:
    """立即触发一次全屋巡检，返回当前告警列表（不推送 Hermes）。"""
    return _lumi_post("/api/proactive/check", {})


def proactive_reload() -> dict[str, Any]:
    """热重载巡检规则配置（读取 ~/.lumi/rules.yaml）。"""
    return _lumi_post("/api/proactive/reload", {})


# ─── 设备图 action ─────────────────────────────────────────────────────────────

def device_graph(rooms: list[str] | None = None, device_types: list[str] | None = None) -> dict[str, Any]:
    """获取完整设备图。可按房间和设备类型过滤。返回 {devices: [...], total: N}"""
    graph = _lumi_get("/api/device_graph")
    devices = graph.get("devices", []) if isinstance(graph, dict) else []
    if rooms:
        devices = [d for d in devices if d.get("room") in rooms]
    if device_types:
        devices = [d for d in devices if d.get("type") in device_types]
    return {"devices": devices, "total": len(devices)}


def device_refresh() -> dict[str, Any]:
    """强制刷新设备图缓存（从 HA 和 Miloco 重新拉取）。"""
    return _lumi_get("/api/device_graph?force_refresh=true")


def device_state(device_id: str) -> dict[str, Any]:
    """查询单个设备当前完整状态（包含所有属性）。"""
    q = urllib.parse.quote(device_id)
    results = _lumi_get(f"/api/device_graph/search?q={q}")
    devices = results if isinstance(results, list) else []
    if not devices:
        return {"error": f"未找到设备: {device_id}"}
    # 返回第一个匹配结果
    return devices[0]


# ─── 感知历史 action ──────────────────────────────────────────────────────────

def perception_history(limit: int = 20, offset: int = 0, event_type: str | None = None) -> dict[str, Any]:
    """查询感知事件历史，支持分页和按类型过滤。"""
    path = f"/api/perception/history?limit={limit}&offset={offset}"
    if event_type:
        path += f"&event_type={urllib.parse.quote(event_type)}"
    return _lumi_get(path)


# ─── 日报 action ──────────────────────────────────────────────────────────────

def daily_report(report_type: str = "morning") -> dict[str, Any]:
    """生成并获取全屋日报内容（不自动推送）。report_type: morning 或 evening"""
    from lumi.reports.daily import DailyReport
    report = DailyReport()
    content = report.generate(report_type=report_type)
    return {"report": content, "type": report_type}


def send_daily_report(report_type: str = "morning") -> dict[str, Any]:
    """生成并推送全屋日报到 Hermes。"""
    from lumi.reports.daily import DailyReport
    report = DailyReport()
    ok = report.send(report_type=report_type)
    return {"sent": ok, "type": report_type}


# ─── 全屋状态摘要 action ───────────────────────────────────────────────────────

def home_summary() -> dict[str, Any]:
    """获取全屋综合状态摘要，包括：设备数据、告警、感知、服务状态。供 Hermes 快速建立全屋上下文。"""
    import concurrent.futures

    results: dict[str, Any] = {}

    def _fetch(key: str, fn: Any) -> None:
        try:
            results[key] = fn()
        except Exception as e:
            results[key] = {"error": str(e)}

    tasks = [
        ("summary", summary),
        ("alerts", proactive_alerts),
        ("proactive", proactive_status),
        ("health", health),
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_fetch, k, fn) for k, fn in tasks]
        concurrent.futures.wait(futs)

    return results


# ─── 统一 dispatch 入口 ───────────────────────────────────────────────────────

_VALID_ACTIONS: frozenset[str] = frozenset([
    # 基础
    "health",
    "status",
    "summary",
    "types",
    "search",
    "room",
    "control",
    "batch_control",
    "scenes",
    "run_scene",
    "perception_types",
    "perception_test",
    "perception_send",
    # HA
    "ha_services",
    "ha_automations",
    "ha_toggle_automation",
    "ha_trigger_automation",
    "ha_run_script",
    "ha_history",
    "ha_fire_event",
    "ha_render_template",
    "ha_config",
    # Miloco
    "cameras",
    # 主动巡检
    "proactive_status",
    "proactive_alerts",
    "proactive_reload",
    # 设备图全量查询
    "device_graph",
    "device_refresh",
    "device_state",
    # 全屋摘要 & 设备状态摘要
    "ha_device_summary",
    "home_summary",
    # HA 自动化同步
    "ha_sync_automations",
    # 感知历史
    "perception_history",
    # 全屋日报
    "daily_report",
    "send_daily_report",
])


def dispatch(action: str, params: dict[str, Any] | None = None) -> Any:
    """按 action 名称分发工具调用。

    动态查找模块属性，确保测试 patch 生效。

    Args:
        action: action 名称（见 _VALID_ACTIONS）
        params: 参数字典（关键字参数形式）

    Returns:
        action 返回值

    Raises:
        ValueError: action 不存在时
    """
    if action not in _VALID_ACTIONS:
        raise ValueError(f"未知 action: {action!r}，可用: {sorted(_VALID_ACTIONS)}")
    import lumi.lumi_tool as _self
    fn = getattr(_self, action)
    return fn(**(params or {}))
