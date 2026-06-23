"""lumi/perception/history.py — 感知事件历史存储。

维护内存中最近 N 条感知事件（ring buffer），
同时追加写入本地 JSONL 日志文件供离线分析。
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_EVENTS = int(os.getenv("LUMI_HISTORY_MAX", "200"))
_DEFAULT_LOG_PATH = os.path.expanduser("~/.hermes/logs/lumi_perception.jsonl")


@dataclass
class HistoryEntry:
    """一条感知事件历史记录。"""
    ts: str                          # ISO 时间戳
    event_id: str
    event_type: str
    room: str | None
    camera_id: str | None
    should_notify: bool
    notified: bool
    skipped: bool
    skip_reason: str
    message: str | None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "room": self.room,
            "camera_id": self.camera_id,
            "should_notify": self.should_notify,
            "notified": self.notified,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "message": self.message,
            "context": self.context,
        }


class PerceptionHistory:
    """感知事件历史 — 内存 ring buffer + JSONL 文件持久化。"""

    def __init__(
        self,
        max_events: int = _DEFAULT_MAX_EVENTS,
        log_path: str = _DEFAULT_LOG_PATH,
        load_from_file: bool = True,
    ) -> None:
        self._events: deque[HistoryEntry] = deque(maxlen=max_events)
        self._log_path = log_path
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
        except Exception:
            pass  # 目录创建失败时静默降级，写入时再处理

        if load_from_file:
            self._load_from_file(max_events)

    def record(self, entry: HistoryEntry) -> None:
        """记录一条事件，追加到内存缓冲和文件。"""
        self._events.append(entry)
        self._write_jsonl(entry)

    def get_recent(
        self,
        limit: int = 20,
        event_type: str | None = None,
        room: str | None = None,
    ) -> list[HistoryEntry]:
        """返回最近的事件（倒序，最新在前）。可按 event_type / room 过滤。"""
        events = list(self._events)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if room:
            events = [e for e in events if e.room == room]
        return list(reversed(events))[:limit]

    def get_stats(self) -> dict[str, Any]:
        """返回统计摘要。"""
        events = list(self._events)
        if not events:
            return {"total": 0, "by_type": {}, "notified": 0, "skipped": 0}

        by_type: dict[str, int] = {}
        notified = 0
        skipped = 0
        for e in events:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            if e.notified:
                notified += 1
            if e.skipped:
                skipped += 1

        return {
            "total": len(events),
            "by_type": by_type,
            "notified": notified,
            "skipped": skipped,
            "oldest_ts": events[0].ts if events else None,
            "newest_ts": events[-1].ts if events else None,
        }

    def _write_jsonl(self, entry: HistoryEntry) -> None:
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("写感知历史日志失败: %s", e)

    def _load_from_file(self, limit: int) -> None:
        """从 JSONL 文件加载最近 limit 条历史到内存 ring buffer。"""
        if not os.path.exists(self._log_path):
            return
        try:
            with open(self._log_path, encoding="utf-8") as f:
                lines = f.readlines()
            # 只取最后 limit 行
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    entry = HistoryEntry(
                        ts=d.get("ts", ""),
                        event_id=d.get("event_id", ""),
                        event_type=d.get("event_type", "unknown"),
                        room=d.get("room"),
                        camera_id=d.get("camera_id"),
                        should_notify=bool(d.get("should_notify", False)),
                        notified=bool(d.get("notified", False)),
                        skipped=bool(d.get("skipped", False)),
                        skip_reason=d.get("skip_reason", ""),
                        message=d.get("message"),
                        context=d.get("context", {}),
                    )
                    self._events.append(entry)
                except Exception:
                    continue  # 跳过损坏的行
            logger.info("从文件恢复感知历史 %d 条: %s", len(self._events), self._log_path)
        except Exception as e:
            logger.warning("加载感知历史失败: %s", e)


# 全局单例
_history: PerceptionHistory | None = None


def get_history() -> PerceptionHistory:
    global _history
    if _history is None:
        _history = PerceptionHistory()
    return _history
