"""Miloco REST API 客户端。

通过 HTTP 对接 Miloco 后端（默认 http://127.0.0.1:1810）。
Miloco 需单独启动：miloco-cli service start
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://127.0.0.1:1810"
_DEFAULT_CONFIG_PATH = "~/.miloco/config.json"


class MilocoClient:
    """Miloco REST API 客户端。"""

    def __init__(self, base_url: str = _DEFAULT_BASE_URL, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token

    @classmethod
    def from_config(cls, config_path: str = _DEFAULT_CONFIG_PATH) -> "MilocoClient":
        """从 ~/.miloco/config.json 读取 token 并创建客户端。"""
        path = Path(config_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"Miloco 配置文件不存在: {path}\n"
                "请先安装并启动 Miloco：miloco-cli service start"
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        token = data.get("token", "")
        base_url = data.get("base_url", _DEFAULT_BASE_URL)
        return cls(base_url=base_url, token=token)

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """发起 Miloco API 请求。注意：不走代理直连本地。"""
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        # 绕过 Clash 代理（本地服务）
        backup = {}
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                    "http_proxy", "https_proxy", "all_proxy"):
            if key in os.environ:
                backup[key] = os.environ.pop(key)
        os.environ.setdefault("NO_PROXY", "*")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        finally:
            for key, val in backup.items():
                os.environ[key] = val

    # =========== 设备列表 ===========

    def get_device_list(self) -> list[dict[str, Any]]:
        """获取所有 MIoT 设备列表。"""
        try:
            result = self._request("GET", "/api/miot/device_list")
            devices = result.get("data", [])
            logger.info("Miloco 设备数: %d", len(devices))
            return devices
        except Exception as e:
            logger.warning("Miloco get_device_list 失败: %s", e)
            return []

    def get_home(self, refresh: bool = False) -> dict[str, Any]:
        """获取完整家庭信息（设备 + 房间 + 场景）。"""
        params = "?refresh=true" if refresh else ""
        try:
            return self._request("GET", f"/api/miot/home{params}")
        except Exception as e:
            logger.warning("Miloco get_home 失败: %s", e)
            return {}

    # =========== 设备状态 ===========

    def get_device_status(
        self,
        did: str,
        iids: list[str] | None = None,
    ) -> dict[str, Any]:
        """查询单设备属性状态。

        Args:
            did: 设备 ID
            iids: 属性 IID 列表，如 ["prop.2.1", "prop.3.1"]，None 表示查全部
        """
        params = ""
        if iids:
            params = "?iid=" + ",".join(iids)
        try:
            result = self._request("GET", f"/api/miot/devices/{did}/status{params}")
            return result.get("data", {})
        except Exception as e:
            logger.warning("Miloco get_device_status(%s) 失败: %s", did, e)
            return {}

    # =========== 设备控制 ===========

    def set_property(self, did: str, siid: int, piid: int, value: Any) -> bool:
        """设置设备属性。"""
        try:
            result = self._request(
                "POST",
                f"/api/miot/devices/{did}/control",
                {"type": "set_property", "iid": f"prop.{siid}.{piid}", "value": value},
            )
            return result.get("code", -1) == 0
        except Exception as e:
            logger.error("Miloco set_property(%s, %d.%d) 失败: %s", did, siid, piid, e)
            return False

    def set_properties(
        self, did: str, properties: list[dict[str, Any]]
    ) -> bool:
        """批量设置设备属性。

        Args:
            properties: [{"iid": "prop.2.1", "value": True}, ...]
        """
        try:
            result = self._request(
                "POST",
                f"/api/miot/devices/{did}/control",
                {"type": "set_properties", "properties": properties},
            )
            return result.get("code", -1) == 0
        except Exception as e:
            logger.error("Miloco set_properties(%s) 失败: %s", did, e)
            return False

    def call_action(
        self,
        did: str,
        siid: int,
        aiid: int,
        params: list[Any] | None = None,
    ) -> bool:
        """调用设备动作。"""
        try:
            result = self._request(
                "POST",
                f"/api/miot/devices/{did}/control",
                {
                    "type": "call_action",
                    "iid": f"action.{siid}.{aiid}",
                    "params": params or [],
                },
            )
            return result.get("code", -1) == 0
        except Exception as e:
            logger.error("Miloco call_action(%s, %d.%d) 失败: %s", did, siid, aiid, e)
            return False

    # =========== 设备图 ===========

    def get_device_graph_summary(self) -> str:
        """获取 Miloco 统一设备图自然语言摘要（可直接注入 prompt）。"""
        try:
            result = self._request("GET", "/api/device_graph/summary")
            return result.get("summary", "")
        except Exception as e:
            logger.warning("Miloco get_device_graph_summary 失败: %s", e)
            return ""

    # =========== 健康检查 ===========

    def is_available(self) -> bool:
        """检查 Miloco 服务是否在线。"""
        try:
            self._request("GET", "/health")
            return True
        except Exception:
            return False
