"""Miloco → Hermes 桥接服务。

监听 http://127.0.0.1:18789/miloco/webhook，接收 Miloco 后端发来的 agent 请求，
fire-and-forget 触发 Hermes agent run，立即返回给 Miloco，Hermes 处理完后自己推微信。

Miloco 期望的响应格式：
    { "code": 0, "message": "ok", "data": { "runId": "...", "status": "ok" } }
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lumi.perception.events import PerceptionEvent
from lumi.perception.analyzer import PerceptionAnalyzer

# 懒加载 WS manager，避免循环导入
def _get_ws_manager():
    try:
        from lumi.websocket import manager
        return manager
    except Exception:
        return None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Miloco-Hermes Bridge", version="0.2.0")

# Hermes OpenAI-compatible API server
HERMES_API_URL = os.getenv("HERMES_API_URL", "http://127.0.0.1:8642")
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "any")
HERMES_MODEL = os.getenv("HERMES_MODEL", "hermes-agent")


def _ok(data: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"code": 0, "message": "ok", "data": data})


def _err(msg: str, code: int = 500) -> JSONResponse:
    return JSONResponse({"code": 1, "message": msg, "data": None}, status_code=code)


@app.get("/health")
async def health() -> dict:
    hermes_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{HERMES_API_URL}/health")
            hermes_ok = r.status_code == 200
    except Exception:
        pass
    return {"status": "ok", "hermes": hermes_ok}


@app.post("/miloco/webhook")
async def miloco_webhook(request: Request) -> JSONResponse:
    """接收 Miloco 后端请求，fire-and-forget 触发 Hermes，立即返回。"""
    try:
        body = await request.json()
    except Exception:
        return _err("Invalid JSON", 400)

    action = body.get("action", "")
    payload = body.get("payload", {})
    run_id = str(uuid.uuid4())

    logger.info("Miloco webhook action=%s run_id=%s", action, run_id)

    if action == "agent":
        message = payload.get("message", "")
        if not message:
            return _err("Empty message", 400)

        prompt = _build_prompt(message, payload)
        # fire-and-forget：不等 Hermes 完成，立即回包给 Miloco
        asyncio.create_task(_run_hermes_async(run_id, prompt))
        return _ok({"runId": run_id, "status": "ok"})

    elif action == "notify":
        # 直接推微信（通过 Hermes agent）
        message = payload.get("message", str(payload))
        asyncio.create_task(_run_hermes_async(run_id, f"[Miloco通知] {message}\\n请直接用 send_message 推送到微信，不需要额外处理。"))
        return _ok({"runId": run_id, "status": "ok"})

    elif action == "perception":
        # 感知闭环：解析事件 → 分析 → 按需推微信
        asyncio.create_task(_run_perception_async(run_id, payload))
        return _ok({"runId": run_id, "status": "ok"})

    else:
        logger.warning("Unknown action: %s", action)
        return _ok({"runId": run_id, "status": "ok"})


def _build_prompt(message: str, payload: dict) -> str:
    """构造发给 Hermes 的 prompt，附带 Miloco 感知上下文。"""
    lines = [
        "【Miloco 智能体请求】请处理以下内容，完成后用 send_message 工具把结果推送到微信（target='weixin'）。",
        "",
        message,
    ]

    perception = payload.get("perception")
    if perception:
        lines.append(f"\n[感知上下文]\n{perception}")

    device_summary = payload.get("deviceSummary")
    if device_summary:
        lines.append(f"\n[设备状态]\n{device_summary}")

    return "\n".join(lines)


async def _run_hermes_async(run_id: str, prompt: str) -> None:
    """异步调用 Hermes，结果通过 Hermes 自身的 send_message 工具推微信。"""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{HERMES_API_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {HERMES_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": HERMES_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.info("run_id=%s Hermes completed: %d chars", run_id, len(content))
    except Exception as e:
        logger.error("run_id=%s Hermes call failed: %s", run_id, e)


async def _run_perception_async(run_id: str, payload: dict) -> None:
    """感知闭环：解析事件 → PerceptionAnalyzer 分析 → 按需直接推微信。

    直接走 Hermes send_message API，不经过 LLM 推理，减少延迟。
    """
    try:
        event = PerceptionEvent.from_miloco_webhook(payload)
        # 不传 ha_client（bridge 层无 HA 直连），分析器走纯感知判断
        analyzer = PerceptionAnalyzer(ha_client=None)
        decision = analyzer.analyze(event)

        logger.info(
            "run_id=%s perception event_type=%s should_notify=%s reason=%s",
            run_id, event.event_type, decision.should_notify, decision.reason,
        )

        if decision.should_notify and decision.message:
            # 广播到 WebSocket 前端
            ws_manager = _get_ws_manager()
            if ws_manager:
                asyncio.create_task(ws_manager.broadcast_perception(
                    event_type=event.event_type.value,
                    payload={
                        "message": decision.message,
                        "room": event.room,
                        "reason": decision.reason,
                    },
                ))

            # 直接推微信：让 Hermes agent 转发消息
            prompt = (
                f"请直接用 send_message 工具把以下内容推送到微信（target='weixin'），"
                f"不要修改内容，不要额外处理：\n\n{decision.message}"
            )
            await _run_hermes_async(run_id, prompt)

    except Exception as e:
        logger.error("run_id=%s perception analysis failed: %s", run_id, e)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=18789, log_level="info")
