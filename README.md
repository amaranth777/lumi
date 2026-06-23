# Lumi（露米）

统一家庭智能体平台——将 Miloco 感知、Home Assistant 设备总线、Hermes Agent 大脑整合在一起。

## 架构

```
用户（微信 / Telegram）
    ↓
Hermes Agent Runtime
    ↓           ↓
Lumi Hermes Bridge    Home Assistant API
    ↓
Unified Device Graph
    ↓           ↓
Miloco Backend    MIoT Devices
```

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
lumi
```

## 文档

见 [docs/lumi-architecture-2026-06-23.md](docs/lumi-architecture-2026-06-23.md)
