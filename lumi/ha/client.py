"""Home Assistant REST API 客户端。

强制绕过本地代理（Clash 等），直连 HA 局域网地址。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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


class HAClient:
    """Home Assistant REST API 客户端。"""

    def __init__(self, base_url: str, token_file: str,
                 retries: int = 3, retry_delay: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._token: str | None = None
        self._token_file = Path(token_file).expanduser()
        self._retries = retries
        self._retry_delay = retry_delay

    @property
    def token(self) -> str:
        if self._token is None:
            if not self._token_file.exists():
                raise FileNotFoundError(f"HA token 文件不存在: {self._token_file}")
            self._token = self._token_file.read_text(encoding="utf-8").strip()
        return self._token

    def _request(self, path: str) -> Any:
        """发起 HA API 请求，绕过代理，带指数退避重试。"""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            backup = _clear_proxy()
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read())
            except Exception as e:
                last_exc = e
                _restore_proxy(backup)
                if attempt < self._retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning("HA 请求失败 (attempt %d/%d): %s，%.1fs 后重试",
                                   attempt + 1, self._retries, e, delay)
                    time.sleep(delay)
            else:
                _restore_proxy(backup)
        raise last_exc  # type: ignore[misc]

    def get_states(self) -> list[dict[str, Any]]:
        """拉取所有 entity 状态。"""
        try:
            result = self._request("/api/states")
            logger.debug("HA states: %d entities", len(result))
            return result
        except Exception as e:
            logger.warning("HA get_states 失败（已重试）: %s", e)
            return []

    def get_state(self, entity_id: str) -> dict[str, Any] | None:
        """拉取单个 entity 状态。"""
        try:
            return self._request(f"/api/states/{entity_id}")
        except Exception as e:
            logger.warning("HA get_state(%s) 失败: %s", entity_id, e)
            return None

    def call_service(self, domain: str, service: str, data: dict[str, Any]) -> bool:
        """调用 HA service。"""
        url = f"{self.base_url}/api/services/{domain}/{service}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            backup = _clear_proxy()
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.status in (200, 201)
            except Exception as e:
                last_exc = e
                _restore_proxy(backup)
                if attempt < self._retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning("HA call_service %s.%s 失败 (attempt %d/%d)，%.1fs 后重试",
                                   domain, service, attempt + 1, self._retries, delay)
                    time.sleep(delay)
            else:
                _restore_proxy(backup)
        logger.error("HA call_service %s.%s 最终失败: %s", domain, service, last_exc)
        return False

    def _post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """通用 POST 请求，绕代理，带重试。body 为 None 时发送空 JSON {}。"""
        url = f"{self.base_url}{path}"
        payload = json.dumps(body or {}).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        last_exc: Exception | None = None
        for attempt in range(self._retries):
            backup = _clear_proxy()
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read())
            except Exception as e:
                last_exc = e
                _restore_proxy(backup)
                if attempt < self._retries - 1:
                    delay = self._retry_delay * (2 ** attempt)
                    logger.warning("HA POST %s 失败 (attempt %d/%d): %s，%.1fs 后重试",
                                   path, attempt + 1, self._retries, e, delay)
                    time.sleep(delay)
            else:
                _restore_proxy(backup)
        raise last_exc  # type: ignore[misc]

    # ─── 新增 API 方法 ────────────────────────────────────────────────────────

    def get_services(self) -> dict[str, Any]:
        """GET /api/services — 返回所有可用服务域。"""
        try:
            result = self._request("/api/services")
            # HA 返回 list[{domain, services:{...}}]，转成 {domain: services} dict
            if isinstance(result, list):
                return {item["domain"]: item.get("services", {}) for item in result
                        if isinstance(item, dict) and "domain" in item}
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.warning("HA get_services 失败: %s", e)
            return {}

    def get_automations(self) -> list[dict[str, Any]]:
        """GET /api/states，过滤 domain=automation。"""
        try:
            states = self._request("/api/states")
            return [s for s in states
                    if isinstance(s, dict)
                    and s.get("entity_id", "").startswith("automation.")]
        except Exception as e:
            logger.warning("HA get_automations 失败: %s", e)
            return []

    def trigger_automation(self, entity_id: str) -> bool:
        """POST /api/services/automation/trigger。"""
        return self.call_service("automation", "trigger", {"entity_id": entity_id})

    def toggle_automation(self, entity_id: str, enable: bool) -> bool:
        """启用或禁用自动化。enable=True → turn_on，False → turn_off。"""
        service = "turn_on" if enable else "turn_off"
        return self.call_service("automation", service, {"entity_id": entity_id})

    def get_scripts(self) -> list[dict[str, Any]]:
        """GET /api/states，过滤 domain=script。"""
        try:
            states = self._request("/api/states")
            return [s for s in states
                    if isinstance(s, dict)
                    and s.get("entity_id", "").startswith("script.")]
        except Exception as e:
            logger.warning("HA get_scripts 失败: %s", e)
            return []

    def run_script(self, entity_id: str) -> bool:
        """POST /api/services/script/turn_on。"""
        return self.call_service("script", "turn_on", {"entity_id": entity_id})

    def get_history(self, entity_id: str, hours: int = 24) -> list[Any]:
        """GET /api/history/period/<start> 查询 entity 状态历史。"""
        try:
            start_dt = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
            start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            path = f"/api/history/period/{start_str}?filter_entity_id={entity_id}"
            result = self._request(path)
            return result if isinstance(result, list) else []
        except Exception as e:
            logger.warning("HA get_history(%s) 失败: %s", entity_id, e)
            return []

    def fire_event(self, event_type: str, event_data: dict[str, Any] | None = None) -> bool:
        """POST /api/events/{event_type}。"""
        try:
            self._post(f"/api/events/{event_type}", event_data or {})
            return True
        except Exception as e:
            logger.warning("HA fire_event(%s) 失败: %s", event_type, e)
            return False

    def render_template(self, template: str) -> str:
        """POST /api/template — 渲染 Jinja2 模板，返回渲染结果字符串。"""
        try:
            result = self._post("/api/template", {"template": template})
            if isinstance(result, str):
                return result
            # HA 有时返回 JSON，直接序列化
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            logger.warning("HA render_template 失败: %s", e)
            return ""

    def get_config(self) -> dict[str, Any]:
        """GET /api/config — 返回 HA 实例配置信息。"""
        try:
            result = self._request("/api/config")
            return result if isinstance(result, dict) else {}
        except Exception as e:
            logger.warning("HA get_config 失败: %s", e)
            return {}

    def get_states_since(self, since: datetime) -> list[dict[str, Any]]:
        """只拉取 last_changed >= since 的实体。用于增量刷新。"""
        # HA API: GET /api/states 没有 since 参数，用客户端过滤
        # 过滤逻辑：对比 last_changed 字段
        all_states = self.get_states()
        since_iso = since.astimezone(timezone.utc).isoformat()
        return [
            s for s in all_states
            if s.get("last_changed", "") >= since_iso
        ]

