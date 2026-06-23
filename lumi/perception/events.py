"""感知事件模型——Miloco 摄像头/感知层的标准化事件结构。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PerceptionEventType(str, Enum):
    """感知事件类型。"""
    # 生物识别
    PET_DETECTED = "pet_detected"          # 宠物出现
    PERSON_DETECTED = "person_detected"    # 人物出现
    PET_AT_LITTER_BOX = "pet_at_litter_box"  # 宠物在猫砂盆旁
    PET_LEFT_LITTER_BOX = "pet_left_litter_box"  # 宠物离开猫砂盆

    # 设备状态
    LITTER_BOX_FULL = "litter_box_full"        # 集便仓满
    LITTER_BOX_CLEANED = "litter_box_cleaned"  # 猫砂盆完成清洁
    LITTER_BOX_WEIGHT_LOW = "litter_box_weight_low"  # 猫砂余量不足
    PET_WEIGHED = "pet_weighed"                # 宠物称重完成（猫砂盆内置体重秤）

    # 通用
    MOTION_DETECTED = "motion_detected"    # 移动检测
    ANOMALY_DETECTED = "anomaly_detected"  # 异常检测
    UNKNOWN = "unknown"                    # 未知事件


class PerceptionSubject(BaseModel):
    """感知主体（被识别的对象）。"""
    type: str                              # "cat", "person", "dog" 等
    name: str | None = None               # 识别出的名字（如"猫猫"）
    confidence: float = 1.0               # 置信度 0-1
    attributes: dict[str, Any] = Field(default_factory=dict)


class PerceptionEvent(BaseModel):
    """标准化感知事件——从 Miloco webhook 或摄像头推送解析而来。"""
    event_id: str = ""
    event_type: PerceptionEventType = PerceptionEventType.UNKNOWN
    timestamp: datetime = Field(default_factory=datetime.now)

    # 来源
    camera_id: str | None = None          # 摄像头设备 ID
    camera_name: str | None = None        # 摄像头名称
    room: str | None = None               # 发生房间

    # 感知主体
    subjects: list[PerceptionSubject] = Field(default_factory=list)

    # 关联设备
    related_device_ids: list[str] = Field(default_factory=list)

    # 原始 payload（保留供 debug）
    raw: dict[str, Any] = Field(default_factory=dict)

    # 额外上下文（由闭环分析器填充）
    context: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_miloco_webhook(cls, payload: dict[str, Any]) -> "PerceptionEvent":
        """从 Miloco webhook payload 解析感知事件。"""
        event_type_raw = payload.get("event_type", payload.get("type", "unknown"))
        try:
            event_type = PerceptionEventType(event_type_raw)
        except ValueError:
            event_type = PerceptionEventType.UNKNOWN

        subjects = []
        for s in payload.get("subjects", []):
            subjects.append(PerceptionSubject(
                type=s.get("type", "unknown"),
                name=s.get("name"),
                confidence=s.get("confidence", 1.0),
                attributes=s.get("attributes", {}),
            ))

        return cls(
            event_id=payload.get("event_id", ""),
            event_type=event_type,
            camera_id=payload.get("camera_id"),
            camera_name=payload.get("camera_name"),
            room=payload.get("room"),
            subjects=subjects,
            related_device_ids=payload.get("related_device_ids", []),
            raw=payload,
            context=_extract_context(event_type, payload),
        )

    def has_subject_type(self, subject_type: str) -> bool:
        """是否包含特定类型的感知主体。"""
        return any(s.type == subject_type for s in self.subjects)

    def primary_subject(self) -> PerceptionSubject | None:
        """返回置信度最高的主体。"""
        if not self.subjects:
            return None
        return max(self.subjects, key=lambda s: s.confidence)


def _extract_context(
    event_type: PerceptionEventType, payload: dict[str, Any]
) -> dict[str, Any]:
    """从 webhook payload 提取事件特定的上下文数据。"""
    ctx: dict[str, Any] = {}

    # 体重相关事件
    if event_type in (PerceptionEventType.PET_WEIGHED,
                      PerceptionEventType.LITTER_BOX_WEIGHT_LOW):
        for key in ("weight_kg", "weight", "litter_weight_kg", "litter_weight"):
            if key in payload:
                ctx["weight_kg"] = float(payload[key])
                break
        # 也从 data 子字典里找
        data = payload.get("data", {})
        if "weight_kg" not in ctx and isinstance(data, dict):
            for key in ("weight_kg", "weight", "litter_weight_kg"):
                if key in data:
                    ctx["weight_kg"] = float(data[key])
                    break

    # 通用：把 payload 里的 context 字段合并进来
    if isinstance(payload.get("context"), dict):
        ctx.update(payload["context"])

    return ctx
