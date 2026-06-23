"""tests/test_perception_router.py — 感知 webhook 端点测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from lumi.main import app
from lumi.perception.analyzer import PerceptionDecision


def _client():
    """返回配好 mock 的 TestClient，屏蔽 HA/bridge 外部依赖。"""
    ha_client = MagicMock()
    ha_client.get_states.return_value = []

    class _CM:
        def __enter__(self):
            self._p1 = patch("lumi.deps.get_ha_client", return_value=ha_client)
            self._p2 = patch("lumi.perception.router.get_bridge")
            self._p3 = patch("lumi.perception.router._broadcast_perception")
            self._p1.__enter__()
            self._mock_bridge = self._p2.__enter__().return_value
            self._mock_bridge.notify.return_value = MagicMock(
                success=True, skipped=False, skip_reason="", message="测试通知"
            )
            self._p3.__enter__()
            self._tc = TestClient(app, raise_server_exceptions=False)
            return self._tc, self._mock_bridge

        def __exit__(self, *a):
            self._p3.__exit__(*a)
            self._p2.__exit__(*a)
            self._p1.__exit__(*a)

    return _CM()


# ─── 基本响应结构 ──────────────────────────────────────────────────────────────

class TestWebhookBasic:
    def test_returns_200(self):
        with _client() as (c, _):
            resp = c.post("/api/perception/webhook", json={"event_type": "pet_detected"})
        assert resp.status_code == 200

    def test_response_has_required_fields(self):
        with _client() as (c, _):
            data = c.post("/api/perception/webhook", json={"event_type": "pet_detected"}).json()
        assert "received" in data
        assert "event_type" in data
        assert "should_notify" in data
        assert "notified" in data
        assert "skipped" in data

    def test_received_is_true(self):
        with _client() as (c, _):
            data = c.post("/api/perception/webhook", json={"event_type": "pet_detected"}).json()
        assert data["received"] is True

    def test_event_type_echoed(self):
        with _client() as (c, _):
            data = c.post("/api/perception/webhook", json={"event_type": "litter_box_full"}).json()
        assert data["event_type"] == "litter_box_full"

    def test_unknown_event_type_normalized(self):
        with _client() as (c, _):
            data = c.post("/api/perception/webhook", json={"event_type": "totally_unknown_xyz"}).json()
        assert data["event_type"] == "unknown"

    def test_empty_payload_accepted(self):
        with _client() as (c, _):
            resp = c.post("/api/perception/webhook", json={})
        assert resp.status_code == 200


# ─── 感知分析集成 ──────────────────────────────────────────────────────────────

class TestWebhookAnalysis:
    def test_litter_box_full_triggers_notify(self):
        """猫砂盆满 → analyzer 应决定推送。"""
        with _client() as (c, mock_bridge):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_analyzer_cls:
                mock_analyzer = MagicMock()
                mock_analyzer.analyze.return_value = PerceptionDecision(
                    should_notify=True,
                    message="🐱 集便仓已满，请及时清理",
                    reason="litter_full",
                )
                mock_analyzer_cls.return_value = mock_analyzer

                data = c.post("/api/perception/webhook", json={
                    "event_type": "litter_box_full",
                    "room": "卫生间",
                }).json()

        assert data["should_notify"] is True

    def test_room_passed_to_event(self):
        """webhook payload 里的 room 正确传入事件。"""
        captured_events = []

        with _client() as (c, mock_bridge):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_analyzer = MagicMock()

                def capture_analyze(event):
                    captured_events.append(event)
                    return PerceptionDecision(should_notify=False, reason="test")

                mock_analyzer.analyze.side_effect = capture_analyze
                mock_cls.return_value = mock_analyzer

                c.post("/api/perception/webhook", json={
                    "event_type": "pet_detected",
                    "room": "客厅",
                })

        assert captured_events
        assert captured_events[0].room == "客厅"

    def test_camera_id_passed_to_event(self):
        """camera_id 正确传入事件。"""
        captured = []

        with _client() as (c, _):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_a = MagicMock()

                def cap(event):
                    captured.append(event)
                    return PerceptionDecision(should_notify=False, reason="test")

                mock_a.analyze.side_effect = cap
                mock_cls.return_value = mock_a

                c.post("/api/perception/webhook", json={
                    "event_type": "motion_detected",
                    "camera_id": "cam_kitchen_001",
                })

        assert captured[0].camera_id == "cam_kitchen_001"


# ─── 推送集成 ──────────────────────────────────────────────────────────────────

class TestWebhookNotify:
    def test_bridge_called_when_should_notify(self):
        """analyzer 决定推送时，bridge.notify 被调用。"""
        with _client() as (c, mock_bridge):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_a = MagicMock()
                mock_a.analyze.return_value = PerceptionDecision(
                    should_notify=True, message="通知内容", reason="test"
                )
                mock_cls.return_value = mock_a
                mock_bridge.notify.return_value = MagicMock(
                    success=True, skipped=False, skip_reason=""
                )

                c.post("/api/perception/webhook", json={"event_type": "anomaly_detected"})

        mock_bridge.notify.assert_called_once()

    def test_bridge_not_called_when_no_notify(self):
        """analyzer 决定不推送时，bridge.notify 不被调用。"""
        with _client() as (c, mock_bridge):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_a = MagicMock()
                mock_a.analyze.return_value = PerceptionDecision(
                    should_notify=False, reason="cooldown"
                )
                mock_cls.return_value = mock_a

                c.post("/api/perception/webhook", json={"event_type": "pet_detected"})

        mock_bridge.notify.assert_not_called()

    def test_cooldown_skip_reflected_in_response(self):
        """bridge 限流跳过时，response.skipped=True。"""
        with _client() as (c, mock_bridge):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_a = MagicMock()
                mock_a.analyze.return_value = PerceptionDecision(
                    should_notify=True, message="msg", reason="test"
                )
                mock_cls.return_value = mock_a
                mock_bridge.notify.return_value = MagicMock(
                    success=True, skipped=True, skip_reason="冷却中，剩余 250s"
                )

                data = c.post("/api/perception/webhook", json={
                    "event_type": "litter_box_full"
                }).json()

        assert data["skipped"] is True
        assert "冷却" in data["skip_reason"]


# ─── 体重上下文提取 ────────────────────────────────────────────────────────────

class TestWebhookWeightContext:
    def test_weight_extracted_into_context(self):
        """cat 体重数据从 payload 提取到 event.context。"""
        captured = []

        with _client() as (c, _):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_a = MagicMock()

                def cap(event):
                    captured.append(event)
                    return PerceptionDecision(should_notify=False, reason="test")

                mock_a.analyze.side_effect = cap
                mock_cls.return_value = mock_a

                c.post("/api/perception/webhook", json={
                    "event_type": "pet_weighed",
                    "weight_kg": 3.64,
                    "room": "卫生间",
                })

        assert captured
        assert "weight_kg" in captured[0].context
        assert abs(captured[0].context["weight_kg"] - 3.64) < 0.01


# ─── 测试端点 (dry run) ────────────────────────────────────────────────────────

class TestWebhookTestEndpoint:
    def test_test_endpoint_returns_200(self):
        with _client() as (c, mock_bridge):
            resp = c.post("/api/perception/webhook/test", json={
                "event_type": "litter_box_full"
            })
        assert resp.status_code == 200

    def test_test_endpoint_does_not_call_bridge(self):
        """dry run 端点不触发 bridge 推送。"""
        with _client() as (c, mock_bridge):
            c.post("/api/perception/webhook/test", json={
                "event_type": "litter_box_full"
            })
        mock_bridge.notify.assert_not_called()

    def test_test_endpoint_returns_analysis(self):
        """dry run 端点仍然返回 should_notify 分析结果。"""
        with _client() as (c, _):
            with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                mock_a = MagicMock()
                mock_a.analyze.return_value = PerceptionDecision(
                    should_notify=True, message="干运行分析", reason="test"
                )
                mock_cls.return_value = mock_a

                data = c.post("/api/perception/webhook/test", json={
                    "event_type": "anomaly_detected"
                }).json()

        assert data["should_notify"] is True
        assert data["notified"] is False  # dry run 不实际发送


# ─── 事件类型列表 ──────────────────────────────────────────────────────────────

class TestEventTypesList:
    def test_returns_200(self):
        with _client() as (c, _):
            resp = c.get("/api/perception/events/types")
        assert resp.status_code == 200

    def test_contains_known_types(self):
        with _client() as (c, _):
            data = c.get("/api/perception/events/types").json()
        types = data["event_types"]
        assert "litter_box_full" in types
        assert "pet_detected" in types
        assert "pet_weighed" in types
        assert "litter_box_weight_low" in types

    def test_all_enum_values_present(self):
        from lumi.perception.events import PerceptionEventType
        with _client() as (c, _):
            data = c.get("/api/perception/events/types").json()
        for et in PerceptionEventType:
            assert et.value in data["event_types"], f"{et.value} missing"


# ─── 降级路径覆盖 ──────────────────────────────────────────────────────────────

class TestWebhookFallback:
    def test_from_miloco_webhook_failure_falls_back(self):
        """from_miloco_webhook 抛异常时，使用降级 PerceptionEvent。"""
        with _client() as (c, _):
            with patch("lumi.perception.router.PerceptionEvent") as mock_cls:
                # 让 from_miloco_webhook 抛异常，构造器正常工作
                mock_event = MagicMock()
                mock_event.event_type.value = "unknown"
                mock_event.event_id = ""
                mock_event.room = None
                mock_event.camera_id = None
                mock_event.context = {}
                mock_event.subjects = []
                mock_cls.from_miloco_webhook.side_effect = ValueError("parse error")
                mock_cls.return_value = mock_event

                with patch("lumi.perception.router.PerceptionAnalyzer") as mock_analyzer_cls:
                    mock_a = MagicMock()
                    mock_a.analyze.return_value = PerceptionDecision(
                        should_notify=False, reason="fallback"
                    )
                    mock_analyzer_cls.return_value = mock_a

                    resp = c.post("/api/perception/webhook", json={"event_type": "unknown"})

        assert resp.status_code == 200

    def test_record_history_failure_does_not_break_response(self):
        """_record_history 抛异常时，response 仍然正常返回。"""
        with _client() as (c, _):
            with patch("lumi.perception.router._record_history", side_effect=RuntimeError("disk full")):
                with patch("lumi.perception.router.PerceptionAnalyzer") as mock_cls:
                    mock_a = MagicMock()
                    mock_a.analyze.return_value = PerceptionDecision(
                        should_notify=False, reason="test"
                    )
                    mock_cls.return_value = mock_a
                    resp = c.post("/api/perception/webhook", json={"event_type": "pet_detected"})

        assert resp.status_code == 200

    def test_test_endpoint_fallback_on_parse_error(self):
        """test endpoint 解析失败时降级构造 PerceptionEvent。"""
        with _client() as (c, _):
            with patch("lumi.perception.router.PerceptionEvent") as mock_cls:
                mock_event = MagicMock()
                mock_event.event_type.value = "unknown"
                mock_event.event_id = "test"
                mock_event.room = None
                mock_event.camera_id = None
                mock_event.context = {}
                mock_event.subjects = []
                mock_cls.from_miloco_webhook.side_effect = ValueError("parse error")
                mock_cls.return_value = mock_event

                with patch("lumi.perception.router.PerceptionAnalyzer") as mock_analyzer_cls:
                    mock_a = MagicMock()
                    mock_a.analyze.return_value = PerceptionDecision(
                        should_notify=False, reason="test"
                    )
                    mock_analyzer_cls.return_value = mock_a

                    resp = c.post("/api/perception/webhook/test", json={"event_type": "unknown"})

        assert resp.status_code == 200


# ─── history / stats 端点 ─────────────────────────────────────────────────────

class TestHistoryStatsEndpoints:
    def test_history_returns_200(self):
        with _client() as (c, _):
            resp = c.get("/api/perception/history")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_stats_returns_200(self):
        with _client() as (c, _):
            resp = c.get("/api/perception/stats")
        assert resp.status_code == 200
        assert "total" in resp.json()

    def test_history_with_filters(self):
        with _client() as (c, _):
            resp = c.get("/api/perception/history?limit=5&event_type=litter_box_full")
        assert resp.status_code == 200
        assert resp.json()["count"] <= 5

