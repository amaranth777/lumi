#!/usr/bin/env python3
"""Lumi MCP Server — 将 lumi_tool 所有 action 暴露为 MCP tools。

启动方式：
    /home/amaranth/code/lumi/.venv/bin/python -m lumi.mcp_server
或：
    /home/amaranth/code/lumi/.venv/bin/lumi-mcp
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from lumi.lumi_tool import _VALID_ACTIONS

mcp = FastMCP("lumi")


# ─── 基础 tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def lumi_health() -> str:
    """检查 Lumi 服务健康状态（HA/Miloco连通性、设备数）。"""
    from lumi.lumi_tool import health
    return json.dumps(health(), ensure_ascii=False)


@mcp.tool()
def lumi_status() -> str:
    """获取 Lumi 运行时详情（设备分布/场景数/bridge状态/感知统计）。"""
    from lumi.lumi_tool import status
    return json.dumps(status(), ensure_ascii=False)


@mcp.tool()
def lumi_summary() -> str:
    """获取全屋设备摘要（总数/类型/房间分布）。"""
    from lumi.lumi_tool import summary
    return json.dumps(summary(), ensure_ascii=False)


@mcp.tool()
def lumi_types() -> str:
    """获取设备类型分布统计。"""
    from lumi.lumi_tool import types
    return json.dumps(types(), ensure_ascii=False)


@mcp.tool()
def lumi_search(query: str) -> str:
    """搜索设备（按名称/ID/房间/类型关键字）。

    Args:
        query: 搜索关键字，如 "猫砂盆"、"客厅"、"light"
    """
    from lumi.lumi_tool import search
    return json.dumps(search(query=query), ensure_ascii=False)


@mcp.tool()
def lumi_room(room_name: str) -> str:
    """查询指定房间的所有设备。

    Args:
        room_name: 房间名称，如 "客厅"、"卧室"
    """
    from lumi.lumi_tool import room
    return json.dumps(room(room_name=room_name), ensure_ascii=False)


@mcp.tool()
def lumi_control(
    device_id: str,
    command: str,
    params: dict[str, Any] | None = None,
) -> str:
    """控制单个设备。

    Args:
        device_id: 设备 ID（canonical_id 或 entity_id）
        command: 命令，如 turn_on / turn_off / clean / set_brightness
        params: 命令参数（可选），如 {"brightness": 80}
    """
    from lumi.lumi_tool import control
    return json.dumps(control(device_id=device_id, command=command, params=params), ensure_ascii=False)


@mcp.tool()
def lumi_batch_control(commands: list[dict[str, Any]]) -> str:
    """批量控制多个设备。

    Args:
        commands: 命令列表，每项为 {device_id, command, params}
    """
    from lumi.lumi_tool import batch_control
    return json.dumps(batch_control(commands=commands), ensure_ascii=False)


@mcp.tool()
def lumi_scenes() -> str:
    """列出所有已定义场景。"""
    from lumi.lumi_tool import scenes
    return json.dumps(scenes(), ensure_ascii=False)


@mcp.tool()
def lumi_run_scene(scene_id: str) -> str:
    """执行指定场景。

    Args:
        scene_id: 场景 ID
    """
    from lumi.lumi_tool import run_scene
    return json.dumps(run_scene(scene_id=scene_id), ensure_ascii=False)


@mcp.tool()
def lumi_perception_types() -> str:
    """列出所有感知事件类型。"""
    from lumi.lumi_tool import perception_types
    return json.dumps(perception_types(), ensure_ascii=False)


@mcp.tool()
def lumi_perception_test(
    event_type: str,
    subject: str = "cat",
    room_name: str = "客厅",
) -> str:
    """感知事件 dry run（分析但不推送 Hermes）。

    Args:
        event_type: 事件类型，如 pet_detected、litter_box_full
        subject: 主体类型，如 cat、person，默认 cat
        room_name: 房间名，默认 客厅
    """
    from lumi.lumi_tool import perception_test
    return json.dumps(perception_test(event_type=event_type, subject=subject, room_name=room_name), ensure_ascii=False)


@mcp.tool()
def lumi_perception_send(
    event_type: str,
    event_id: str = "",
    camera_id: str | None = None,
    room_name: str | None = None,
    context: dict[str, Any] | None = None,
    image_url: str | None = None,
    thumbnail_url: str | None = None,
) -> str:
    """真实触发感知 webhook，会推送 Hermes 通知。

    Args:
        event_type: 感知事件类型，如 litter_box_full、pet_detected
        event_id: 事件 ID（可选）
        camera_id: 摄像头 ID（可选）
        room_name: 房间名（可选）
        context: 附加上下文数据（可选）
        image_url: 摄像头截图 URL（可选）
        thumbnail_url: 缩略图 URL（可选）
    """
    from lumi.lumi_tool import perception_send
    return json.dumps(
        perception_send(event_type=event_type, event_id=event_id, camera_id=camera_id, room_name=room_name, context=context, image_url=image_url, thumbnail_url=thumbnail_url),
        ensure_ascii=False,
    )


# ─── HA tools ─────────────────────────────────────────────────────────────────

@mcp.tool()
def lumi_ha_services() -> str:
    """列出 HA 可用服务域列表。"""
    from lumi.lumi_tool import ha_services
    return json.dumps(ha_services(), ensure_ascii=False)


@mcp.tool()
def lumi_ha_automations() -> str:
    """列出所有自动化（entity_id / friendly_name / state）。"""
    from lumi.lumi_tool import ha_automations
    return json.dumps(ha_automations(), ensure_ascii=False)


@mcp.tool()
def lumi_ha_toggle_automation(entity_id: str, enable: bool) -> str:
    """启用或禁用自动化。

    Args:
        entity_id: 自动化实体 ID，如 automation.morning
        enable: True 启用，False 禁用
    """
    from lumi.lumi_tool import ha_toggle_automation
    return json.dumps(ha_toggle_automation(entity_id=entity_id, enable=enable), ensure_ascii=False)


@mcp.tool()
def lumi_ha_trigger_automation(entity_id: str) -> str:
    """立即触发执行一次 HA 自动化（不同于启用/禁用）。

    Args:
        entity_id: 自动化实体 ID，如 automation.morning
    """
    from lumi.lumi_tool import ha_trigger_automation
    return json.dumps(ha_trigger_automation(entity_id=entity_id), ensure_ascii=False)


@mcp.tool()
def lumi_ha_run_script(entity_id: str) -> str:
    """执行 HA 脚本。

    Args:
        entity_id: 脚本实体 ID，如 script.welcome
    """
    from lumi.lumi_tool import ha_run_script
    return json.dumps(ha_run_script(entity_id=entity_id), ensure_ascii=False)


@mcp.tool()
def lumi_ha_history(entity_id: str, hours: int = 24) -> str:
    """查询设备状态历史。

    Args:
        entity_id: 设备实体 ID，如 light.living_room
        hours: 查询最近多少小时，默认 24
    """
    from lumi.lumi_tool import ha_history
    return json.dumps(ha_history(entity_id=entity_id, hours=hours), ensure_ascii=False)


@mcp.tool()
def lumi_ha_device_summary(entity_id: str) -> str:
    """获取 HA 单个实体的当前状态摘要（state + 主要属性 + 最近 1 小时变化趋势）。

    Args:
        entity_id: 设备实体 ID，如 light.living_room
    """
    from lumi.lumi_tool import ha_device_summary
    return json.dumps(ha_device_summary(entity_id=entity_id), ensure_ascii=False)


@mcp.tool()
def lumi_ha_fire_event(
    event_type: str,
    event_data: dict[str, Any] | None = None,
) -> str:
    """触发 HA 自定义事件。

    Args:
        event_type: 事件类型名称
        event_data: 附加事件数据（可选）
    """
    from lumi.lumi_tool import ha_fire_event
    return json.dumps(ha_fire_event(event_type=event_type, event_data=event_data), ensure_ascii=False)


@mcp.tool()
def lumi_ha_render_template(template: str) -> str:
    """渲染 Jinja2 模板（通过 HA /api/template）。

    Args:
        template: Jinja2 模板字符串，如 \"{{ states('light.x') }}\"
    """
    from lumi.lumi_tool import ha_render_template
    return json.dumps(ha_render_template(template=template), ensure_ascii=False)


@mcp.tool()
def lumi_ha_config() -> str:
    """获取 HA 实例配置信息（版本/位置/时区等）。"""
    from lumi.lumi_tool import ha_config
    return json.dumps(ha_config(), ensure_ascii=False)


# ─── Miloco tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def lumi_cameras() -> str:
    """获取 Miloco 摄像头设备列表（含 did/name/room/online 等信息）。"""
    from lumi.lumi_tool import cameras
    return json.dumps(cameras(), ensure_ascii=False)


# ─── 主动巡检 tools ───────────────────────────────────────────────────────────

@mcp.tool()
def lumi_proactive_status() -> str:
    """查询主动巡检引擎状态（是否运行、上次巡检时间、已知告警数）。"""
    from lumi.lumi_tool import proactive_status
    return json.dumps(proactive_status(), ensure_ascii=False)


@mcp.tool()
def lumi_proactive_alerts() -> str:
    """立即触发一次全屋巡检，返回当前告警列表（不推送 Hermes）。"""
    from lumi.lumi_tool import proactive_alerts
    return json.dumps(proactive_alerts(), ensure_ascii=False)


@mcp.tool()
def lumi_proactive_reload() -> str:
    """热重载巡检规则配置（读取 ~/.lumi/rules.yaml），返回当前生效规则列表。"""
    from lumi.lumi_tool import proactive_reload
    return json.dumps(proactive_reload(), ensure_ascii=False)


# ─── 设备图全量查询 tools ──────────────────────────────────────────────────────

@mcp.tool()
def lumi_device_graph(
    rooms: list[str] | None = None,
    device_types: list[str] | None = None,
) -> str:
    """获取完整设备图。可按房间和设备类型过滤。

    Args:
        rooms: 房间列表过滤，如 ["客厅", "卧室"]，None 表示不过滤
        device_types: 设备类型列表过滤，如 ["light", "switch"]，None 表示不过滤
    """
    from lumi.lumi_tool import device_graph
    return json.dumps(device_graph(rooms=rooms, device_types=device_types), ensure_ascii=False)


@mcp.tool()
def lumi_device_refresh() -> str:
    """强制刷新设备图缓存（从 HA 和 Miloco 重新拉取）。"""
    from lumi.lumi_tool import device_refresh
    return json.dumps(device_refresh(), ensure_ascii=False)


@mcp.tool()
def lumi_home_summary() -> str:
    """获取全屋综合状态摘要，包括：设备数据、告警、感知、服务状态。供 Hermes 快速建立全屋上下文。"""
    from lumi.lumi_tool import home_summary
    return json.dumps(home_summary(), ensure_ascii=False)


@mcp.tool()
def lumi_device_state(device_id: str) -> str:
    """查询单个设备当前完整状态（包含所有属性）。

    Args:
        device_id: 设备 ID 或名称关键字
    """
    from lumi.lumi_tool import device_state
    return json.dumps(device_state(device_id=device_id), ensure_ascii=False)


@mcp.tool()
def lumi_ha_sync_automations() -> str:
    """将 HA 自动化同步到 Lumi 场景列表（一键导入）。返回 {synced, skipped}。"""
    from lumi.lumi_tool import ha_sync_automations
    return json.dumps(ha_sync_automations(), ensure_ascii=False)


# ─── 感知历史 tools ────────────────────────────────────────────────────────────

@mcp.tool()
def lumi_perception_history(
    limit: int = 20,
    offset: int = 0,
    event_type: str | None = None,
) -> str:
    """查询感知事件历史，支持分页和按类型过滤。

    Args:
        limit: 返回条数，默认 20
        offset: 分页偏移，默认 0
        event_type: 按事件类型过滤，如 pet_detected，None 表示不过滤
    """
    from lumi.lumi_tool import perception_history
    return json.dumps(perception_history(limit=limit, offset=offset, event_type=event_type), ensure_ascii=False)


# ─── 全屋日报 tools ────────────────────────────────────────────────────────────

@mcp.tool()
def lumi_daily_report(report_type: str = "morning") -> str:
    """生成全屋日报内容（不推送）。

    Args:
        report_type: morning（早报）或 evening（晚报）
    """
    from lumi.lumi_tool import daily_report
    return json.dumps(daily_report(report_type=report_type), ensure_ascii=False)


@mcp.tool()
def lumi_send_daily_report(report_type: str = "morning") -> str:
    """生成并推送全屋日报到 Hermes。

    Args:
        report_type: morning（早报）或 evening（晚报）
    """
    from lumi.lumi_tool import send_daily_report
    return json.dumps(send_daily_report(report_type=report_type), ensure_ascii=False)


# ─── 注册验证 ─────────────────────────────────────────────────────────────────

REGISTERED_TOOLS: frozenset[str] = frozenset([
    "lumi_health", "lumi_status", "lumi_summary", "lumi_types",
    "lumi_search", "lumi_room", "lumi_control", "lumi_batch_control",
    "lumi_scenes", "lumi_run_scene",
    "lumi_perception_types", "lumi_perception_test", "lumi_perception_send",
    "lumi_ha_services", "lumi_ha_automations", "lumi_ha_toggle_automation",
    "lumi_ha_trigger_automation",
    "lumi_ha_run_script", "lumi_ha_history", "lumi_ha_fire_event",
    "lumi_ha_render_template", "lumi_ha_config",
    "lumi_cameras",
    "lumi_proactive_status", "lumi_proactive_alerts",
    "lumi_proactive_reload",
    "lumi_device_graph", "lumi_device_refresh", "lumi_device_state",
    "lumi_ha_device_summary", "lumi_home_summary",
    "lumi_ha_sync_automations",
    "lumi_perception_history",
    "lumi_daily_report", "lumi_send_daily_report",
])

_expected = frozenset(f"lumi_{a}" for a in _VALID_ACTIONS)
assert REGISTERED_TOOLS == _expected, (
    f"REGISTERED_TOOLS 与 _VALID_ACTIONS 不匹配！\n"
    f"  缺少: {_expected - REGISTERED_TOOLS}\n"
    f"  多余: {REGISTERED_TOOLS - _expected}"
)


# ─── 入口 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    """启动 Lumi MCP stdio server。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
