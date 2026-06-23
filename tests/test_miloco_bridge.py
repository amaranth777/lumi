"""miloco_bridge/main.py webhook handler 测试。"""

from __future__ import annotations

import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


# ─── App 导入（隔离 side effects）────────────────────────────────────────────

@pytest.fixture
def client():
    from miloco_bridge.main import app
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ─── GET /health ──────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "hermes" in data


# ─── POST /miloco/webhook — action=agent ─────────────────────────────────────

class TestWebhookAgent:
    def test_agent_action_returns_ok(self, client):
        with patch("miloco_bridge.main._run_hermes_async", new_callable=AsyncMock) as mock_hermes:
            resp = client.post("/miloco/webhook", json={
                "action": "agent",
                "payload": {"message": "家里怎么样？"},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "runId" in data["data"]

    def test_agent_empty_message_returns_error(self, client):
        resp = client.post("/miloco/webhook", json={
            "action": "agent",
            "payload": {"message": ""},
        })
        assert resp.status_code == 400

    def test_agent_missing_message_returns_error(self, client):
        resp = client.post("/miloco/webhook", json={
            "action": "agent",
            "payload": {},
        })
        assert resp.status_code == 400


# ─── POST /miloco/webhook — action=notify ────────────────────────────────────

class TestWebhookNotify:
    def test_notify_action_returns_ok(self, client):
        with patch("miloco_bridge.main._run_hermes_async", new_callable=AsyncMock):
            resp = client.post("/miloco/webhook", json={
                "action": "notify",
                "payload": {"message": "有人按门铃了"},
            })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_notify_without_message_uses_payload_str(self, client):
        with patch("miloco_bridge.main._run_hermes_async", new_callable=AsyncMock):
            resp = client.post("/miloco/webhook", json={
                "action": "notify",
                "payload": {"key": "value"},
            })
        assert resp.status_code == 200


# ─── POST /miloco/webhook — action=perception ────────────────────────────────

class TestWebhookPerception:
    def test_perception_action_returns_ok(self, client):
        with patch("miloco_bridge.main._run_perception_async", new_callable=AsyncMock):
            resp = client.post("/miloco/webhook", json={
                "action": "perception",
                "payload": {"event_type": "litter_box_full", "room": "卫生间"},
            })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_perception_unknown_event_still_ok(self, client):
        with patch("miloco_bridge.main._run_perception_async", new_callable=AsyncMock):
            resp = client.post("/miloco/webhook", json={
                "action": "perception",
                "payload": {"event_type": "mystery_event"},
            })
        assert resp.status_code == 200


# ─── POST /miloco/webhook — unknown action ────────────────────────────────────

class TestWebhookUnknownAction:
    def test_unknown_action_returns_ok_with_run_id(self, client):
        resp = client.post("/miloco/webhook", json={
            "action": "unknown_future_action",
            "payload": {},
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/miloco/webhook",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400


# ─── _build_prompt ────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_basic_prompt(self):
        from miloco_bridge.main import _build_prompt
        prompt = _build_prompt("家里怎么样？", {})
        assert "家里怎么样？" in prompt
        assert "Miloco" in prompt

    def test_prompt_with_perception(self):
        from miloco_bridge.main import _build_prompt
        prompt = _build_prompt("查状态", {"perception": "摄像头看到猫"})
        assert "摄像头看到猫" in prompt
        assert "感知上下文" in prompt

    def test_prompt_with_device_summary(self):
        from miloco_bridge.main import _build_prompt
        prompt = _build_prompt("控制灯", {"deviceSummary": "客厅灯: on"})
        assert "客厅灯" in prompt
        assert "设备状态" in prompt
