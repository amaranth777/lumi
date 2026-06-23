# Lumi 露米

> 私有家庭智能体平台 — 将 Miloco 感知、Home Assistant 设备总线、Hermes Agent 大脑整合为一套统一系统。

---

## 这是什么

Lumi 不是另一个 Home Assistant 插件，也不是 Miloco 的替代品。它是把三者粘合在一起的那一层：

```
Miloco   → 感知层：摄像头、人物识别、家庭事件
HA       → 设备层：状态读写、自动化、多品牌接入
Hermes   → 大脑层：对话、判断、通知、执行策略
Lumi     → 粘合层：统一设备图、策略守卫、多源融合
```

最终效果：多源数据 → 统一设备图 → 统一分析 → 策略控制 → 多通道执行。

---

## 架构

```
┌─────────────────────────────────────────────────────┐
│              用户交互层                              │
│   微信 / Telegram / Web Dashboard / 语音             │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│              Hermes Agent Runtime                   │
│   对话理解 · 工具调用 · 任务调度 · 家庭策略守卫       │
└──────────────┬────────────────────────┬─────────────┘
               │                        │
               ▼                        ▼
┌──────────────────────────┐  ┌─────────────────────────┐
│   Miloco Hermes Bridge   │  │   Home Assistant API    │
│   POST /miloco/webhook   │  │   REST / WebSocket      │
└──────────────┬───────────┘  └────────────┬────────────┘
               │                           │
               └──────────┬────────────────┘
                          ▼
┌─────────────────────────────────────────────────────┐
│              Unified Device Graph                   │
│   HA entities · MIoT devices · Miloco perception    │
│   统一房间 · 状态 · 能力 · 策略                      │
└──────────────┬────────────────────────┬─────────────┘
               │                        │
               ▼                        ▼
┌──────────────────────────┐  ┌─────────────────────────┐
│      Miloco Backend      │  │    Home Assistant       │
│   摄像头 · 人物/宠物识别  │  │   设备状态 · 自动化      │
│   家庭事件 · 家庭档案     │  │   历史记录 · 多品牌      │
└──────────────────────────┘  └─────────────────────────┘
```

---

## 快速开始

```bash
git clone https://github.com/amaranth777/lumi.git
cd lumi
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
lumi
```

服务默认监听 `http://127.0.0.1:8810`。

最小配置 `~/.lumi/config.json`：

```json
{
  "ha": {
    "enabled": true,
    "base_url": "http://192.168.5.184:8123",
    "token_file": "~/.hermes/ha_token"
  },
  "server": {
    "host": "127.0.0.1",
    "port": 8810,
    "token": ""
  }
}
```

---

## API

基础地址：`http://127.0.0.1:8810`

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查（版本/HA/Miloco 连通性/设备数） |
| `GET /api/status` | 运行时详情（设备分布/场景数/bridge冷却/WS连接数） |
| `GET /api/device_graph` | 完整设备图 |
| `GET /api/device_graph/summary` | 设备图摘要（供 Hermes 分析） |
| `GET /api/device_graph/types` | 设备类型分布（by_type + rooms） |
| `GET /api/device_graph/search?q=` | 按关键词搜索设备（name/id/room/type） |
| `GET /api/device_graph/rooms/{room}` | 按房间查询设备 |
| `POST /api/device_graph/{id}/command` | 统一设备控制（策略守卫保护） |
| `POST /api/device_graph/batch/command` | 批量设备控制（并发执行） |
| `GET /api/scenes` | 列出所有预设场景 |
| `POST /api/scenes` | 创建/更新场景 |
| `POST /api/scenes/{id}/execute` | 执行场景 |
| `WS /ws/device_graph` | 实时状态推送（HA事件驱动，<100ms 延迟） |
| `GET /ui/` | 内置演示页面 |
| `GET /docs` | 自动生成的 API 文档 |

控制示例：

```bash
curl -X POST http://127.0.0.1:8810/api/device_graph/fan.airpurifier/command \
  -H 'Content-Type: application/json' \
  -d '{"command": "turn_on", "params": {}}'
```

WebSocket 实时订阅：

```javascript
const ws = new WebSocket('ws://127.0.0.1:8810/ws/device_graph');
ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  if (type === 'snapshot') renderDevices(data);
};
```

---

## 策略守卫

高风险动作在执行前经过策略层拦截，配置在 `device_aliases` 的 `policies` 字段：

```json
{
  "canonical_id": "litter_box",
  "policies": {
    "forbidden_actions": ["empty"],
    "allowed_actions": ["clean", "off"],
    "requires_precheck": true
  }
}
```

分析可以自由，执行必须受策略约束。

---

## 部署

```bash
# 一键安装（systemd user service）
bash scripts/install.sh

# 查看状态
systemctl --user status lumi.service

# 日志
journalctl --user -u lumi.service -f

# 自检
bash scripts/doctor.sh
```

---

## 项目结构

```
lumi/
├── lumi/               # 核心服务（FastAPI）
├── miloco_bridge/      # Miloco ↔ Hermes 桥接层
├── docs/               # 架构设计、配置、前端对接
├── deploy/             # systemd service 模板
├── scripts/            # install.sh / doctor.sh
└── tests/
```

---

## 实施阶段

| Phase | 目标 | 状态 |
|-------|------|------|
| 1 | 只读融合 — HA + MIoT 统一设备图 | ✅ |
| 2 | Hermes Bridge — Miloco 事件 → 微信通知 | ✅ |
| 3 | 安全控制 — 策略守卫 + 统一设备控制 | ✅ |
| 4 | 感知闭环 — 摄像头事件 + HA 状态联合判断 | ✅ |
| 5 | 打包私有版 — 一键安装、doctor、systemd | ✅ |

---

## 相关项目

- [Hermes Agent](https://hermes-agent.nousresearch.com) — AI 大脑运行时
- [Miloco](https://github.com/idootop/mi-gpt) — 小米家庭感知平台
- [Home Assistant](https://www.home-assistant.io) — 开源智能家居平台
