#!/usr/bin/env bash
# install.sh — Lumi 一键安装脚本
# 用法: bash scripts/install.sh [--no-systemd]
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
DEPLOY_DIR="$REPO_DIR/deploy"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

NO_SYSTEMD=0
for arg in "$@"; do
  [[ "$arg" == "--no-systemd" ]] && NO_SYSTEMD=1
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Lumi（露米）安装程序"
echo "  目录: $REPO_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. 检查依赖 ──────────────────────────────────────────────
echo ""
echo "▶ 检查依赖..."
command -v python3 >/dev/null 2>&1 || { echo "✗ 缺少 python3"; exit 1; }
command -v uv >/dev/null 2>&1 && USE_UV=1 || USE_UV=0

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python $PY_VER"

# ── 2. 创建虚拟环境 & 安装依赖 ──────────────────────────────
echo ""
echo "▶ 安装 Python 依赖..."
if [[ $USE_UV -eq 1 ]]; then
  uv venv "$VENV_DIR" --quiet 2>/dev/null || true
  uv pip install -e "$REPO_DIR[dev]" --quiet
else
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install -e "$REPO_DIR[dev]" -q
fi
echo "  ✓ 依赖已安装"

# ── 3. 检查 HA token ────────────────────────────────────────
echo ""
echo "▶ 检查配置..."
HA_TOKEN_FILE="$HOME/.hermes/ha_token"
if [[ -f "$HA_TOKEN_FILE" ]]; then
  echo "  ✓ HA token: $HA_TOKEN_FILE"
else
  echo "  ⚠ 未找到 HA token: $HA_TOKEN_FILE"
  echo "    请创建该文件并写入 HA Long-Lived Access Token"
fi

# ── 4. 安装 systemd 服务 ─────────────────────────────────────
if [[ $NO_SYSTEMD -eq 0 ]]; then
  echo ""
  echo "▶ 安装 systemd 用户服务..."
  mkdir -p "$SYSTEMD_USER_DIR"

  for svc in lumi.service miloco-hermes-bridge.service; do
    if [[ -f "$DEPLOY_DIR/$svc" ]]; then
      # 替换占位符
      sed "s|__REPO_DIR__|$REPO_DIR|g; s|__HOME__|$HOME|g" \
        "$DEPLOY_DIR/$svc" > "$SYSTEMD_USER_DIR/$svc"
      echo "  ✓ $svc → $SYSTEMD_USER_DIR/$svc"
    else
      echo "  ⚠ 未找到 $DEPLOY_DIR/$svc，跳过"
    fi
  done

  systemctl --user daemon-reload
  echo "  ✓ systemd daemon-reload 完成"

  echo ""
  echo "  启动服务："
  echo "    systemctl --user enable --now lumi"
  echo "    systemctl --user enable --now miloco-hermes-bridge"
fi

# ── 5. 完成 ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ 安装完成"
echo ""
echo "  手动启动（不用 systemd）："
echo "    cd $REPO_DIR"
echo "    .venv/bin/python -m uvicorn lumi.main:app --host 127.0.0.1 --port 18788"
echo "    .venv/bin/python -m uvicorn miloco_bridge.main:app --host 127.0.0.1 --port 18789"
echo ""
echo "  诊断："
echo "    bash scripts/doctor.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
