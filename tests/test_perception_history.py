"""tests/test_perception_history.py — PerceptionHistory 单元测试。"""

from __future__ import annotations

import json
import time

import pytest

from lumi.perception.history import HistoryEntry, PerceptionHistory


def _entry(
    event_type: str = "litter_box_full",
    room: str | None = "卫生间",
    notified: bool = True,
    skipped: bool = False,
    ts: str = "2026-06-23T10:00:00",
) -> HistoryEntry:
    return HistoryEntry(
        ts=ts,
        event_id="evt-001",
        event_type=event_type,
        room=room,
        camera_id=None,
        should_notify=True,
        notified=notified,
        skipped=skipped,
        skip_reason="" if not skipped else "冷却中",
        message="测试消息",
        context={},
    )


# ─── 基本存储 ─────────────────────────────────────────────────────────────────

class TestHistoryRecord:
    def test_record_adds_entry(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry())
        assert len(h.get_recent()) == 1

    def test_record_multiple(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        for i in range(5):
            h.record(_entry(event_type=f"event_{i}"))
        assert len(h.get_recent(limit=10)) == 5

    def test_ring_buffer_max_events(self, tmp_path):
        h = PerceptionHistory(max_events=3, log_path=str(tmp_path / "test.jsonl"))
        for i in range(5):
            h.record(_entry(event_type=f"event_{i}"))
        # 最多保留 3 条
        assert len(h.get_recent(limit=10)) == 3

    def test_newest_first(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(event_type="old", ts="2026-06-23T09:00:00"))
        h.record(_entry(event_type="new", ts="2026-06-23T10:00:00"))
        events = h.get_recent()
        assert events[0].event_type == "new"
        assert events[1].event_type == "old"


# ─── 过滤 ─────────────────────────────────────────────────────────────────────

class TestHistoryFilter:
    def test_filter_by_event_type(self, tmp_path):
        h = PerceptionHistory(max_events=20, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(event_type="litter_box_full"))
        h.record(_entry(event_type="pet_detected"))
        h.record(_entry(event_type="litter_box_full"))

        results = h.get_recent(event_type="litter_box_full")
        assert len(results) == 2
        assert all(e.event_type == "litter_box_full" for e in results)

    def test_filter_by_room(self, tmp_path):
        h = PerceptionHistory(max_events=20, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(room="卫生间"))
        h.record(_entry(room="客厅"))
        h.record(_entry(room="卫生间"))

        results = h.get_recent(room="卫生间")
        assert len(results) == 2
        assert all(e.room == "卫生间" for e in results)

    def test_filter_no_match(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(event_type="pet_detected"))
        results = h.get_recent(event_type="anomaly_detected")
        assert results == []

    def test_limit_respected(self, tmp_path):
        h = PerceptionHistory(max_events=20, log_path=str(tmp_path / "test.jsonl"))
        for i in range(10):
            h.record(_entry())
        assert len(h.get_recent(limit=3)) == 3


# ─── 统计 ─────────────────────────────────────────────────────────────────────

class TestHistoryStats:
    def test_empty_stats(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        stats = h.get_stats()
        assert stats["total"] == 0
        assert stats["notified"] == 0

    def test_total_count(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(notified=True))
        h.record(_entry(notified=True))
        h.record(_entry(notified=False, skipped=True))
        stats = h.get_stats()
        assert stats["total"] == 3
        assert stats["notified"] == 2
        assert stats["skipped"] == 1

    def test_by_type_counts(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(event_type="litter_box_full"))
        h.record(_entry(event_type="litter_box_full"))
        h.record(_entry(event_type="pet_detected"))
        stats = h.get_stats()
        assert stats["by_type"]["litter_box_full"] == 2
        assert stats["by_type"]["pet_detected"] == 1

    def test_timestamps_in_stats(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        h.record(_entry(ts="2026-06-23T09:00:00"))
        h.record(_entry(ts="2026-06-23T11:00:00"))
        stats = h.get_stats()
        assert stats["oldest_ts"] == "2026-06-23T09:00:00"
        assert stats["newest_ts"] == "2026-06-23T11:00:00"


# ─── JSONL 持久化 ─────────────────────────────────────────────────────────────

class TestHistoryPersistence:
    def test_writes_jsonl_file(self, tmp_path):
        log_file = tmp_path / "perception.jsonl"
        h = PerceptionHistory(max_events=10, log_path=str(log_file))
        h.record(_entry(event_type="litter_box_full"))
        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event_type"] == "litter_box_full"

    def test_appends_multiple_records(self, tmp_path):
        log_file = tmp_path / "perception.jsonl"
        h = PerceptionHistory(max_events=10, log_path=str(log_file))
        h.record(_entry(event_type="a"))
        h.record(_entry(event_type="b"))
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_to_dict_has_all_fields(self, tmp_path):
        h = PerceptionHistory(max_events=10, log_path=str(tmp_path / "test.jsonl"))
        entry = _entry()
        h.record(entry)
        d = entry.to_dict()
        for key in ("ts", "event_id", "event_type", "room", "camera_id",
                    "should_notify", "notified", "skipped", "skip_reason",
                    "message", "context"):
            assert key in d, f"missing key: {key}"

    def test_invalid_log_path_does_not_crash(self):
        """写入失败时不应崩溃（静默降级）。"""
        h = PerceptionHistory(max_events=10, log_path="/nonexistent_dir/test.jsonl", load_from_file=False)
        h.record(_entry())
        assert len(h.get_recent()) == 1


# ─── 持久化恢复 ───────────────────────────────────────────────────────────────

class TestHistoryRestore:
    def test_loads_from_existing_file(self, tmp_path):
        """重启后从 JSONL 文件恢复历史。"""
        log_file = tmp_path / "perception.jsonl"
        # 先写入几条
        h1 = PerceptionHistory(max_events=10, log_path=str(log_file), load_from_file=False)
        h1.record(_entry(event_type="litter_box_full", ts="2026-06-23T08:00:00"))
        h1.record(_entry(event_type="pet_detected", ts="2026-06-23T09:00:00"))

        # 新实例从文件恢复
        h2 = PerceptionHistory(max_events=10, log_path=str(log_file), load_from_file=True)
        events = h2.get_recent()
        assert len(events) == 2
        assert events[0].event_type == "pet_detected"  # 最新在前
        assert events[1].event_type == "litter_box_full"

    def test_no_file_does_not_crash(self, tmp_path):
        """文件不存在时静默跳过。"""
        h = PerceptionHistory(
            max_events=10,
            log_path=str(tmp_path / "nonexistent.jsonl"),
            load_from_file=True,
        )
        assert len(h.get_recent()) == 0

    def test_respects_max_events_on_load(self, tmp_path):
        """加载时只保留最近 max_events 条。"""
        log_file = tmp_path / "perception.jsonl"
        h1 = PerceptionHistory(max_events=100, log_path=str(log_file), load_from_file=False)
        for i in range(10):
            h1.record(_entry(ts=f"2026-06-23T{i:02d}:00:00"))

        # max_events=3 时只保留最后 3 条
        h2 = PerceptionHistory(max_events=3, log_path=str(log_file), load_from_file=True)
        assert len(h2.get_recent(limit=100)) == 3

    def test_skips_corrupt_lines(self, tmp_path):
        """跳过损坏的 JSONL 行，不崩溃。"""
        log_file = tmp_path / "perception.jsonl"
        log_file.write_text(
            '{"ts":"2026-06-23T08:00:00","event_id":"e1","event_type":"pet_detected",'
            '"room":null,"camera_id":null,"should_notify":true,"notified":true,'
            '"skipped":false,"skip_reason":"","message":"ok","context":{}}\n'
            'THIS IS NOT JSON\n'
            '{"ts":"2026-06-23T09:00:00","event_id":"e2","event_type":"litter_box_full",'
            '"room":"卫生间","camera_id":null,"should_notify":true,"notified":true,'
            '"skipped":false,"skip_reason":"","message":"满了","context":{}}\n'
        )
        h = PerceptionHistory(max_events=10, log_path=str(log_file), load_from_file=True)
        events = h.get_recent()
        assert len(events) == 2  # 损坏行被跳过

    def test_new_records_append_after_restore(self, tmp_path):
        """恢复后新记录正常追加。"""
        log_file = tmp_path / "perception.jsonl"
        h1 = PerceptionHistory(max_events=10, log_path=str(log_file), load_from_file=False)
        h1.record(_entry(event_type="old_event", ts="2026-06-23T08:00:00"))

        h2 = PerceptionHistory(max_events=10, log_path=str(log_file), load_from_file=True)
        h2.record(_entry(event_type="new_event", ts="2026-06-23T10:00:00"))

        events = h2.get_recent()
        assert len(events) == 2
        assert events[0].event_type == "new_event"


# ─── history API 端点 ─────────────────────────────────────────────────────────

class TestHistoryEndpoints:
    def test_history_endpoint_returns_200(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch, MagicMock
        from lumi.main import app
        from lumi.perception.history import PerceptionHistory

        mock_history = PerceptionHistory(max_events=10, log_path="/tmp/test_hist.jsonl")
        with patch("lumi.perception.router.get_history", return_value=mock_history):
            with TestClient(app) as client:
                resp = client.get("/api/perception/history")
        assert resp.status_code == 200
        assert "events" in resp.json()
        assert "count" in resp.json()

    def test_stats_endpoint_returns_200(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from lumi.main import app
        from lumi.perception.history import PerceptionHistory

        mock_history = PerceptionHistory(max_events=10, log_path="/tmp/test_hist_stats.jsonl")
        with patch("lumi.perception.router.get_history", return_value=mock_history):
            with TestClient(app) as client:
                resp = client.get("/api/perception/stats")
        assert resp.status_code == 200
        assert "total" in resp.json()

    def test_history_limit_param(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        from lumi.main import app
        from lumi.perception.history import PerceptionHistory

        mock_history = PerceptionHistory(max_events=50, log_path="/tmp/test_hist_limit.jsonl")
        for i in range(10):
            mock_history.record(_entry(ts=f"2026-06-23T{i:02d}:00:00"))

        with patch("lumi.perception.router.get_history", return_value=mock_history):
            with TestClient(app) as client:
                resp = client.get("/api/perception/history?limit=3")
        assert resp.json()["count"] == 3
