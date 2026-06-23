# 前端对接指南

Lumi 提供了完整的 REST API + WebSocket 接口，支持前端页面、独立屏幕、移动端等各种交互场景。

## 快速体验

访问内置演示页面：

```
http://127.0.0.1:8810/ui/
```

## API 端点

### REST API

**基础地址：** `http://127.0.0.1:8810/api/device_graph`

#### 1. 获取设备图摘要

```bash
GET /api/device_graph/summary?refresh=true
```

响应示例：
```json
{
  "total_devices": 498,
  "by_type": {"sensor": 102, "switch": 80, "light": 7},
  "by_platform": {"ha": 498},
  "by_room": {"客厅": 3, "卧室": 2},
  "rooms": ["客厅", "卧室"]
}
```

#### 2. 获取完整设备图

```bash
GET /api/device_graph
```

响应示例：
```json
{
  "devices": [
    {
      "id": "fan.zhimi_airpurifier_ma2",
      "name": "客厅空气净化器",
      "type": "fan",
      "platform": "ha",
      "state": "on",
      "room": "客厅",
      "capabilities": ["toggle", "speed"]
    }
  ],
  "rooms": {
    "客厅": ["fan.zhimi_airpurifier_ma2"]
  }
}
```

#### 3. 控制设备

```bash
POST /api/device_graph/{device_id}/command
Content-Type: application/json

{
  "command": "turn_on",
  "params": {}
}
```

响应示例：
```json
{
  "success": true,
  "message": "执行成功",
  "device_id": "fan.zhimi_airpurifier_ma2",
  "command": "turn_on"
}
```

**支持的命令：**

| 命令 | 适用设备类型 | 参数 |
|------|-------------|------|
| `turn_on` | 所有 | - |
| `turn_off` | 所有 | - |
| `toggle` | 所有 | - |
| `set_brightness` | light | `{"brightness": 0-100}` |
| `set_color_temp` | light | `{"color_temp": 色温K}` |
| `set_temperature` | climate | `{"temperature": 温度}` |
| `set_hvac_mode` | climate | `{"hvac_mode": "heat/cool/auto"}` |
| `set_humidity` | humidifier | `{"humidity": 0-100}` |
| `set_mode` | fan/climate/humidifier | `{"mode": "模式名"}` |
| `set_percentage` | fan | `{"percentage": 0-100}` |
| `start` | vacuum | - |
| `stop` | vacuum | - |
| `open` | cover | - |
| `close` | cover | - |
| `set_position` | cover | `{"position": 0-100}` |

### WebSocket 实时推送

**连接地址：** `ws://127.0.0.1:8810/ws/device_graph`

#### 消息格式

**服务端 → 客户端：**

```json
{
  "type": "snapshot",
  "data": {
    "devices": [...],
    "rooms": {...}
  }
}
```

- `type`: `"snapshot"` (完整快照) | `"update"` (增量更新) | `"error"` (错误)
- `data`: 设备图数据

#### JavaScript 示例

```javascript
const ws = new WebSocket('ws://127.0.0.1:8810/ws/device_graph');

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'snapshot') {
    console.log('设备总数:', msg.data.devices.length);
    renderDevices(msg.data);
  }
};

// 控制设备
async function toggleDevice(deviceId) {
  const res = await fetch(`http://127.0.0.1:8810/api/device_graph/${deviceId}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: 'toggle', params: {} })
  });
  return await res.json();
}
```

## CORS 配置

默认允许所有来源（开发友好）。生产环境建议修改 `lumi/main.py`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],  # 限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 静态文件部署

前端 build 产物放到 `lumi/static/` 目录，访问路径：

- `http://127.0.0.1:8810/ui/` → `lumi/static/index.html`
- `http://127.0.0.1:8810/ui/assets/` → `lumi/static/assets/`

支持 SPA 路由（`html=True`），404 自动回退到 `index.html`。

## 独立屏幕方案

推荐技术栈：

1. **Electron / NW.js** → 打包为桌面应用
2. **React Native / Flutter** → 移动端 APP
3. **树莓派 + 触摸屏** → 原生 HTML5 页面
4. **ESP32 触摸屏** → 通过 REST API 轮询 + 按钮控制

## 调试技巧

```bash
# 查看 API 文档（自动生成）
open http://127.0.0.1:8810/docs

# WebSocket 测试工具
wscat -c ws://127.0.0.1:8810/ws/device_graph

# CORS 测试
curl -H "Origin: http://localhost:3000" -v http://127.0.0.1:8810/health
```

## 生产部署建议

1. **反向代理：** Nginx/Caddy 前置，配置 HTTPS
2. **Token 认证：** 在 `config.json` 里设置 `server.token`，前端请求头带 `Authorization: Bearer <token>`
3. **限流：** FastAPI middleware 或 Nginx `limit_req`
4. **监控：** 接入 Prometheus + Grafana
