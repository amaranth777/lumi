"""Home Assistant REST API 客户端。

强制绕过本地代理（Clash 等），直连 HA 局域网地址。
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
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

