"""tests/test_proactive_router.py — GET /api/proactive/status, POST /api/proactive/check 测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from lumi.main import app

client = TestClient(app)


# ─── GET /api/proactive/status ────────────────────────────────────────────────

class TestProactiveStatusEndpoint:
    def test_returns_200(self):
        with patch("lumi.deps.get_proactive_scheduler", return_value=None):
            resp = client.get("/api/proactive/status")
        assert resp.status_code == 200

    def test_disabled_when_no_scheduler(self):
        with patch("lumi.deps.get_proactive_scheduler", return_value=None):
            resp = client.get("/api/proactive/status")
        assert resp.json() == {"enabled": False}

    def test_enabled_when_scheduler_present(self):
        scheduler = MagicMock()
        scheduler.is_running.return_value = True
        scheduler.last_check_at = 0.0
        scheduler._alert_sent_at = {}
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler):
            resp = client.get("/api/proactive/status")
        assert resp.json()["enabled"] is True

    def test_running_field_present(self):
        scheduler = MagicMock()
        scheduler.is_running.return_value = False
        scheduler.last_check_at = 0.0
        scheduler._alert_sent_at = {}
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler):
            resp = client.get("/api/proactive/status")
        assert "running" in resp.json()

    def test_last_check_at_field_present(self):
        scheduler = MagicMock()
        scheduler.is_running.return_value = True
        scheduler.last_check_at = 12345.0
        scheduler._alert_sent_at = {}
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler):
            resp = client.get("/api/proactive/status")
        assert resp.json()["last_check_at"] == 12345.0

    def test_known_alert_count_field(self):
        scheduler = MagicMock()
        scheduler.is_running.return_value = True
        scheduler.last_check_at = 0.0
        scheduler._alert_sent_at = {"x": 1.0, "y": 2.0}
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler):
            resp = client.get("/api/proactive/status")
        assert resp.json()["known_alert_count"] == 2


# ─── POST /api/proactive/check ────────────────────────────────────────────────

class TestProactiveCheckEndpoint:
    def test_returns_200(self):
        scheduler = MagicMock()
        scheduler.analyzer.analyze.return_value = []
        scheduler.analyzer.format_report.return_value = ""
        svc = MagicMock()
        svc.get_graph.return_value = MagicMock(devices=[])
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.deps.get_ha_client", return_value=None):
            resp = client.post("/api/proactive/check")
        assert resp.status_code == 200

    def test_returns_alerts_key(self):
        scheduler = MagicMock()
        scheduler.analyzer.analyze.return_value = []
        scheduler.analyzer.format_report.return_value = ""
        svc = MagicMock()
        svc.get_graph.return_value = MagicMock(devices=[])
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.deps.get_ha_client", return_value=None):
            resp = client.post("/api/proactive/check")
        assert "alerts" in resp.json()

    def test_returns_count_key(self):
        scheduler = MagicMock()
        scheduler.analyzer.analyze.return_value = []
        scheduler.analyzer.format_report.return_value = ""
        svc = MagicMock()
        svc.get_graph.return_value = MagicMock(devices=[])
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.deps.get_ha_client", return_value=None):
            resp = client.post("/api/proactive/check")
        assert "count" in resp.json()

    def test_returns_report_key(self):
        scheduler = MagicMock()
        scheduler.analyzer.analyze.return_value = []
        scheduler.analyzer.format_report.return_value = "全屋正常"
        svc = MagicMock()
        svc.get_graph.return_value = MagicMock(devices=[])
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.deps.get_ha_client", return_value=None):
            resp = client.post("/api/proactive/check")
        assert resp.json()["report"] == "全屋正常"

    def test_no_scheduler_returns_error(self):
        svc = MagicMock()
        svc.get_graph.return_value = MagicMock(devices=[])
        with patch("lumi.deps.get_proactive_scheduler", return_value=None), \
             patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.deps.get_ha_client", return_value=None):
            resp = client.post("/api/proactive/check")
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_alert_count_matches_alerts_length(self):
        alert = MagicMock()
        alert.model_dump.return_value = {"level": "warning", "device_id": "d1", "message": "m", "action_hint": None}
        scheduler = MagicMock()
        scheduler.analyzer.analyze.return_value = [alert, alert]
        scheduler.analyzer.format_report.return_value = "2 条告警"
        svc = MagicMock()
        svc.get_graph.return_value = MagicMock(devices=[])
        with patch("lumi.deps.get_proactive_scheduler", return_value=scheduler), \
             patch("lumi.deps.get_device_graph_service", return_value=svc), \
             patch("lumi.deps.get_ha_client", return_value=None):
            resp = client.post("/api/proactive/check")
        data = resp.json()
        assert data["count"] == 2
        assert len(data["alerts"]) == 2
