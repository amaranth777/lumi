#!/usr/bin/env bash
# doctor.sh — Lumi 环境诊断脚本
# 用法: bash scripts/doctor.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"

PASS=0
WARN=0
FAIL=0

ok()   { echo "  ✓ $1"; ((PASS++)); }
warn() { echo "  ⚠ $1"; ((WARN++)); }
fail() { echo "  ✗ $1"; ((FAIL++)); }

check_http() {
  local url="$1" label="$2"
  # 可选第3个参数：接受的额外状态码（如 401）
  local extra_ok="${3:-}"
  local code
  # 绕过 Clash 代理
  code=$(NO_PROXY='*' curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>/dev/null || echo "000")
  if [[ "$code" == "200" ]] || [[ -n "$extra_ok" && "$code" == "$extra_ok" ]]; then
    ok "$label ($url) → $code"
  else
    fail "$label ($url) → $code"
  fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Lumi Doctor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Python 环境 ──────────────────────────────────────────────
echo ""
echo "▶ Python 环境"
if [[ -f "$VENV_PYTHON" ]]; then
  PY_VER=$("$VENV_PYTHON" --version 2>&1)
  ok "venv: $PY_VER"
else
  fail "venv 未找到: $VENV_PYTHON（请先运行 scripts/install.sh）"
fi

# ── 配置文件 ─────────────────────────────────────────────────
echo ""
echo "▶ 配置文件"
HA_TOKEN="$HOME/.hermes/ha_token"
[[ -f "$HA_TOKEN" ]] && ok "HA token: $HA_TOKEN" || fail "HA token 不存在: $HA_TOKEN"

LUMI_CONFIG="$HOME/.lumi/config.json"
[[ -f "$LUMI_CONFIG" ]] && ok "Lumi config: $LUMI_CONFIG" || warn "Lumi config 不存在（将使用默认值）: $LUMI_CONFIG"

# ── 服务健康检查 ──────────────────────────────────────────────
echo ""
echo "▶ 服务健康检查"
check_http "http://127.0.0.1:8810/health" "Lumi API"
check_http "http://127.0.0.1:8810/api/status" "Lumi Status"
check_http "http://127.0.0.1:8810/api/perception/events/types" "Lumi Perception"
check_http "http://127.0.0.1:18789/health" "Miloco-Hermes Bridge"
check_http "http://192.168.5.184:8123/api/" "Home Assistant" "401"

# ── systemd 服务状态 ──────────────────────────────────────────
echo ""
echo "▶ systemd 服务"
for svc in lumi miloco-hermes-bridge; do
  if systemctl --user is-active "$svc" >/dev/null 2>&1; then
    ok "$svc: active"
  else
    status=$(systemctl --user is-active "$svc" 2>/dev/null | tr -d '\n' || echo "unknown")
    warn "$svc: $status"
  fi
done

# ── 策略守卫自检 ──────────────────────────────────────────────
echo ""
echo "▶ 策略守卫"
POLICY_CODE=$(NO_PROXY='*' curl -s -o /dev/null -w "%{http_code}" \
  --max-time 3 -X POST \
  -H "Content-Type: application/json" \
  -d '{"command":"empty","params":{}}' \
  "http://127.0.0.1:8810/api/device_graph/button.petjc_cn_821633016_pro_clean_a_2_1/command" \
  2>/dev/null || echo "000")
if [[ "$POLICY_CODE" == "403" ]]; then
  ok "猫砂盆 Empty 拦截正常 → 403"
elif [[ "$POLICY_CODE" == "000" ]]; then
  warn "Lumi API 未运行，跳过策略守卫检查"
else
  fail "猫砂盆 Empty 未被拦截，预期 403，实际 $POLICY_CODE"
fi


echo ""
echo "▶ 单元测试"
if [[ -f "$VENV_PYTHON" ]]; then
  TEST_OUT=$("$VENV_PYTHON" -m pytest \
    "$REPO_DIR/tests/" \
    -q --tb=no 2>&1)
  if echo "$TEST_OUT" | grep -q "passed"; then
    PASSED=$(echo "$TEST_OUT" | grep -oP '\d+ passed' | head -1)
    ok "pytest: $PASSED"
  else
    fail "pytest 失败:\n$TEST_OUT"
  fi
else
  warn "跳过测试（venv 未就绪）"
fi

# ── 汇总 ─────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  通过: $PASS  警告: $WARN  失败: $FAIL"
if [[ $FAIL -eq 0 ]]; then
  echo "  ✓ 环境正常"
else
  echo "  ✗ 存在问题，请检查上方输出"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
