"""tests/test_image_url.py — PerceptionEvent image_url 支持 + HermesBridge 推送 + perception_send 参数测试。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lumi.perception.events import PerceptionEvent, PerceptionEventType
from lumi.perception.analyzer import PerceptionDecision
from lumi.hermes_bridge import HermesBridge


# ─── 任务1：PerceptionEvent image_url 解析 ────────────────────────────────────

class TestPerceptionEventImageUrl:
    def test_image_url_from_image_url_field(self):
        payload = {
            "event_type": "pet_detected",
            "image_url": "https://example.com/shot.jpg",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.image_url == "https://example.com/shot.jpg"

    def test_image_url_from_snapshot_url_field(self):
        payload = {
            "event_type": "pet_detected",
            "snapshot_url": "https://example.com/snapshot.jpg",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.image_url == "https://example.com/snapshot.jpg"

    def test_image_url_from_photo_url_field(self):
        payload = {
            "event_type": "pet_detected",
            "photo_url": "https://example.com/photo.jpg",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.image_url == "https://example.com/photo.jpg"

    def test_image_url_priority_image_url_over_snapshot(self):
        """image_url 字段优先于 snapshot_url。"""
        payload = {
            "event_type": "pet_detected",
            "image_url": "https://example.com/image.jpg",
            "snapshot_url": "https://example.com/snapshot.jpg",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.image_url == "https://example.com/image.jpg"

    def test_image_url_none_when_absent(self):
        payload = {"event_type": "pet_detected"}
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.image_url is None

    def test_thumbnail_url_parsed(self):
        payload = {
            "event_type": "pet_detected",
            "image_url": "https://example.com/full.jpg",
            "thumbnail_url": "https://example.com/thumb.jpg",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.thumbnail_url == "https://example.com/thumb.jpg"

    def test_thumbnail_url_none_when_absent(self):
        payload = {"event_type": "pet_detected", "image_url": "https://example.com/full.jpg"}
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.thumbnail_url is None

    def test_image_url_none_does_not_break_existing_fields(self):
        """无 image_url 时，其他字段解析不受影响。"""
        payload = {
            "event_type": "litter_box_full",
            "camera_id": "cam_001",
            "room": "卫生间",
        }
        event = PerceptionEvent.from_miloco_webhook(payload)
        assert event.event_type == PerceptionEventType.LITTER_BOX_FULL
        assert event.camera_id == "cam_001"
        assert event.room == "卫生间"
        assert event.image_url is None
        assert event.thumbnail_url is None

    def test_direct_field_assignment(self):
        """直接构造 PerceptionEvent 时 image_url 字段可用。"""
        event = PerceptionEvent(
            event_type=PerceptionEventType.PET_DETECTED,
            image_url="https://example.com/direct.jpg",
            thumbnail_url="https://example.com/thumb.jpg",
        )
        assert event.image_url == "https://example.com/direct.jpg"
        assert event.thumbnail_url == "https://example.com/thumb.jpg"


# ─── 任务2：HermesBridge 推送含图片 URL ──────────────────────────────────────

class TestHermesBridgeImageUrl:
    def _make_decision(self, message: str = "检测到宠物") -> PerceptionDecision:
        return PerceptionDecision(should_notify=True, message=message, reason="test")

    def test_notify_appends_image_url(self):
        bridge = HermesBridge()
        event = PerceptionEvent(
            event_type=PerceptionEventType.PET_DETECTED,
            room="客厅",
            image_url="https://example.com/pet.jpg",
        )
        decision = self._make_decision("检测到宠物")

        with patch("lumi.hermes_bridge._hermes_send", return_value={}) as mock_send:
            result = bridge.notify(event, decision)

        sent_msg = mock_send.call_args[0][0]
        assert "摄像头截图：https://example.com/pet.jpg" in sent_msg
        assert "检测到宠物" in sent_msg
        assert result.message == sent_msg

    def test_notify_no_image_url_sends_original_message(self):
        bridge = HermesBridge()
        event = PerceptionEvent(
            event_type=PerceptionEventType.PET_DETECTED,
            room="客厅",
        )
        decision = self._make_decision("检测到宠物")

        with patch("lumi.hermes_bridge._hermes_send", return_value={}) as mock_send:
            result = bridge.notify(event, decision)

        sent_msg = mock_send.call_args[0][0]
        assert sent_msg == "检测到宠物"
        assert "摄像头截图" not in sent_msg

    def test_notify_image_url_format(self):
        """推送格式为：原始消息 + 换行 + 摄像头截图：URL。"""
        bridge = HermesBridge()
        event = PerceptionEvent(
            event_type=PerceptionEventType.ANOMALY_DETECTED,
            room="门口",
            image_url="https://cam.local/img/001.jpg",
        )
        decision = self._make_decision("异常检测")

        with patch("lumi.hermes_bridge._hermes_send", return_value={}) as mock_send:
            bridge.notify(event, decision)

        sent_msg = mock_send.call_args[0][0]
        assert sent_msg == "异常检测\n摄像头截图：https://cam.local/img/001.jpg"


# ─── 任务3：perception_send 新参数 ───────────────────────────────────────────

class TestPerceptionSendImageUrl:
    def test_image_url_included_in_body(self):
        import lumi.lumi_tool as tool_module
        mock_post = MagicMock(return_value={"status": "ok"})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            result = tool_module.perception_send(
                "pet_detected",
                image_url="https://example.com/pet.jpg",
                thumbnail_url="https://example.com/thumb.jpg",
            )
        assert result["sent"] is True
        _, body = mock_post.call_args[0]
        assert body["image_url"] == "https://example.com/pet.jpg"
        assert body["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_image_url_none_by_default(self):
        import lumi.lumi_tool as tool_module
        mock_post = MagicMock(return_value={"status": "ok"})
        with patch("lumi.lumi_tool._lumi_post", mock_post):
            tool_module.perception_send("pet_detected")
        _, body = mock_post.call_args[0]
        assert body["image_url"] is None
        assert body["thumbnail_url"] is None

    def test_mcp_perception_send_passes_image_url(self):
        """mcp_server.lumi_perception_send 把 image_url/thumbnail_url 传给 perception_send。"""
        import importlib
        import sys
        # 动态导入 mcp_server 避免副作用
        mod_name = "lumi.mcp_server"
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            mod = importlib.import_module(mod_name)

        mock_fn = MagicMock(return_value={"sent": True, "response": {}})
        with patch("lumi.lumi_tool.perception_send", mock_fn):
            mod.lumi_perception_send(
                "pet_detected",
                image_url="https://example.com/img.jpg",
                thumbnail_url="https://example.com/thumb.jpg",
            )

        mock_fn.assert_called_once_with(
            event_type="pet_detected",
            event_id="",
            camera_id=None,
            room_name=None,
            context=None,
            image_url="https://example.com/img.jpg",
            thumbnail_url="https://example.com/thumb.jpg",
        )

    def test_mcp_perception_send_image_url_defaults_none(self):
        """mcp_server.lumi_perception_send 默认不传 image_url 时为 None。"""
        import importlib
        import sys
        mod_name = "lumi.mcp_server"
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            mod = importlib.import_module(mod_name)

        mock_fn = MagicMock(return_value={"sent": True, "response": {}})
        with patch("lumi.lumi_tool.perception_send", mock_fn):
            mod.lumi_perception_send("pet_detected", room_name="客厅")

        mock_fn.assert_called_once_with(
            event_type="pet_detected",
            event_id="",
            camera_id=None,
            room_name="客厅",
            context=None,
            image_url=None,
            thumbnail_url=None,
        )
