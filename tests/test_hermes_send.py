"""tests/test_hermes_send.py — _hermes_send 代理清理 + HTTP 行为测试。"""

from __future__ import annotations

import json
import os
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from lumi.hermes_bridge import _hermes_send


def _make_response(body: dict, status: int = 200):
    """构造 urlopen 返回的假 response。"""
    raw = json.dumps(body).encode()
    resp = MagicMock()
    resp.read.return_value = raw
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ─── 正常发送 ─────────────────────────────────────────────────────────────────

class TestHermesSendSuccess:
    def test_returns_response_dict(self):
        resp = _make_response({"status": "sent"})
        with patch("urllib.request.urlopen", return_value=resp):
            result = _hermes_send("测试消息", target="weixin")
        assert result == {"status": "sent"}

    def test_sends_correct_target(self):
        resp = _make_response({})
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(json.loads(req.data))
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _hermes_send("hello", target="telegram")

        assert calls[0]["target"] == "telegram"
        assert calls[0]["message"] == "hello"

    def test_sends_api_key_header_when_set(self):
        resp = _make_response({})
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(dict(req.headers))
            return resp

        with patch("lumi.hermes_bridge.HERMES_API_KEY", "secret-key"), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _hermes_send("msg")

        headers = {k.lower(): v for k, v in captured[0].items()}
        assert "authorization" in headers
        assert "secret-key" in headers["authorization"]

    def test_no_auth_header_when_key_empty(self):
        resp = _make_response({})
        captured = []

        def fake_urlopen(req, timeout=None):
            captured.append(dict(req.headers))
            return resp

        with patch("lumi.hermes_bridge.HERMES_API_KEY", ""), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _hermes_send("msg")

        headers = {k.lower(): v for k, v in captured[0].items()}
        assert "authorization" not in headers


# ─── 代理环境变量清理 ──────────────────────────────────────────────────────────

class TestHermesSendProxyCleanup:
    def test_proxy_env_cleared_during_request(self):
        """urlopen 调用期间，HTTP_PROXY 等变量应被清除。"""
        seen_proxy = []
        resp = _make_response({})

        def fake_urlopen(req, timeout=None):
            seen_proxy.append(os.environ.get("HTTP_PROXY"))
            seen_proxy.append(os.environ.get("HTTPS_PROXY"))
            seen_proxy.append(os.environ.get("ALL_PROXY"))
            return resp

        old_env = os.environ.copy()
        try:
            os.environ["HTTP_PROXY"] = "http://proxy:7897"
            os.environ["HTTPS_PROXY"] = "http://proxy:7897"
            os.environ["ALL_PROXY"] = "socks5://proxy:7898"

            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                _hermes_send("msg")

            # 请求期间这些变量应该不存在（被临时清除）
            assert seen_proxy[0] is None, "HTTP_PROXY should be cleared during request"
            assert seen_proxy[1] is None, "HTTPS_PROXY should be cleared during request"
            assert seen_proxy[2] is None, "ALL_PROXY should be cleared during request"
        finally:
            # 恢复原始环境（_hermes_send 会在 finally 里恢复，但我们也做一次保险）
            for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
                if k in old_env:
                    os.environ[k] = old_env[k]
                else:
                    os.environ.pop(k, None)

    def test_proxy_env_restored_after_request(self):
        """请求完成后，原始代理环境变量应被恢复。"""
        resp = _make_response({})

        os.environ["HTTP_PROXY"] = "http://proxy:7897"
        try:
            with patch("urllib.request.urlopen", return_value=resp):
                _hermes_send("msg")
            assert os.environ.get("HTTP_PROXY") == "http://proxy:7897"
        finally:
            os.environ.pop("HTTP_PROXY", None)

    def test_proxy_restored_even_on_error(self):
        """即使 urlopen 抛异常，代理变量也应恢复。"""
        import urllib.error

        os.environ["HTTP_PROXY"] = "http://proxy:7897"
        try:
            mock_fp = MagicMock()
            mock_fp.read.return_value = b"bad gateway"
            err = urllib.error.HTTPError(
                url="http://x", code=502, msg="Bad Gateway",
                hdrs=MagicMock(), fp=mock_fp,
            )
            with patch("urllib.request.urlopen", side_effect=err):
                with pytest.raises(RuntimeError, match="502"):
                    _hermes_send("msg")
            # 即使失败，变量应恢复
            assert os.environ.get("HTTP_PROXY") == "http://proxy:7897"
        finally:
            os.environ.pop("HTTP_PROXY", None)

    def test_no_proxy_star_set_during_request(self):
        """请求期间 NO_PROXY 应被设为 '*'。"""
        seen = []
        resp = _make_response({})

        def fake_urlopen(req, timeout=None):
            seen.append(os.environ.get("NO_PROXY"))
            return resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            _hermes_send("msg")

        assert seen[0] == "*"


# ─── HTTP 错误处理 ─────────────────────────────────────────────────────────────

class TestHermesSendErrors:
    def test_http_502_raises_runtime_error(self):
        import urllib.error
        mock_fp = MagicMock()
        mock_fp.read.return_value = b"Bad Gateway"
        err = urllib.error.HTTPError(
            url="http://x", code=502, msg="Bad Gateway",
            hdrs=MagicMock(), fp=mock_fp,
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError, match="502"):
                _hermes_send("msg")

    def test_http_error_message_in_exception(self):
        import urllib.error
        mock_fp = MagicMock()
        mock_fp.read.return_value = b"Unauthorized"
        err = urllib.error.HTTPError(
            url="http://x", code=401, msg="Unauthorized",
            hdrs=MagicMock(), fp=mock_fp,
        )
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(RuntimeError) as exc_info:
                _hermes_send("msg")
        assert "401" in str(exc_info.value)
