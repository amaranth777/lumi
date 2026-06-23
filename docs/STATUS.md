# Lumi（露米）项目现状文档

> 生成时间：2026-06-23  
> 版本：0.5.0  
> 测试：480 passed，覆盖率 95%，89 commits

---

## 一、架构总览

```
微信 / Telegram / Web Dashboard
         │
         ▼
   Hermes Agent Runtime
   ├── lumi_device 工具 (lumi_tool.py)
   ├── 定时任务 (cron jobs)
   └── 主动分析 / 通知
         │
         ▼
   Lumi API  :8810
   ├── 设备图层 (Device Graph)
   ├── 感知层 (Perception)
   ├── 场景层 (Scenes)
   └── WebSocket 实时推送
         │              │
         ▼              ▼
   Home Assistant   Miloco Bridge
   :8123             :18789
   (498 设备)        (15 设备)
```

---

## 二、完整 API 端点

### 设备图

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/device_graph` | 完整设备图（513 设备） |
| GET | `/api/device_graph/summary` | 摘要（总数/类型/房间分布） |
| GET | `/api/device_graph/types` | 设备类型分布 |
| GET | `/api/device_graph/search?q=` | 按名称/ID/房间/类型搜索 |
| GET | `/api/device_graph/rooms/{room}` | 按房间查询 |
| POST | `/api/device_graph/{id}/command` | 单设备控制（策略守卫保护） |
| POST | `/api/device_graph/batch/command` | 批量控制（并发执行） |

### 感知

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/perception/webhook` | 接收 Miloco 感知事件，触发分析+推送 |
| POST | `/api/perception/webhook/test` | Dry run（分析但不推送） |
| GET | `/api/perception/events/types` | 列出所有事件类型 |
| GET | `/api/perception/history` | 最近感知事件历史（可过滤） |
| GET | `/api/perception/stats` | 感知事件统计摘要 |

### 场景

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scenes` | 列出所有场景 |
| POST | `/api/scenes` | 创建/更新场景 |
| GET | `/api/scenes/{id}` | 查询单个场景 |
| DELETE | `/api/scenes/{id}` | 删除场景 |
| POST | `/api/scenes/{id}/execute` | 执行场景 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查（HA/Miloco连通性/设备数） |
| GET | `/api/status` | 运行时详情（设备分布/bridge冷却/WS连接数） |
| WS | `/ws/device_graph` | 实时状态推送（HA事件驱动，<100ms延迟） |

---

## 三、核心模块说明

### 设备图 (`lumi/device_graph/`)

- **service.py** — 核心服务，融合 HA + Miloco，TTL 缓存（5分钟），增量更新
- **fusion.py** — 房间推断（从设备名/ID推断房间）
- **policy.py** — 策略引擎，`PetLitterBoxEmptyGuard`（猫砂盆 empty 永久拦截）
- **commands.py** — 统一命令映射，支持 30+ 命令类型
- **router.py** — FastAPI 路由，403=策略拒绝，404=设备不存在

**关键设计**：
- `update_device_state()` 增量更新缓存，HA 事件不触发全量重拉
- `batch_execute_command()` 用 `ThreadPoolExecutor(max_workers=8)` 并发执行
- `search_devices()` 支持 name/id/room/type 多字段搜索

### 感知闭环 (`lumi/perception/`)

- **events.py** — `PerceptionEvent` 模型，`from_miloco_webhook()` 解析，自动提取 weight_kg
- **analyzer.py** — `PerceptionAnalyzer`，联合 HA 状态做决策
- **router.py** — webhook 接收端，分析+推送+历史记录+WS广播
- **history.py** — ring buffer（默认200条）+ JSONL 持久化到 `~/.hermes/logs/lumi_perception.jsonl`

**感知事件类型**（10种）：
- `pet_detected` / `person_detected`
- `pet_at_litter_box` / `pet_left_litter_box`
- `litter_box_full` / `litter_box_cleaned` / `litter_box_weight_low`
- `pet_weighed`
- `motion_detected` / `anomaly_detected`

### Hermes Bridge (`lumi/hermes_bridge/`)

- 推送限流（CooldownTracker），各事件独立冷却时间
- 绕过 Clash 代理直连 Hermes gateway API
- 推送日志写入 `~/.hermes/logs/lumi_bridge.log`
- 失败时记录 error，不崩溃

### HA 集成 (`lumi/ha/`)

- **client.py** — HAClient，指数退避重试（retries=3, 2s base）
- **events.py** — WebSocket 订阅 state_changed，断线自动重连，增量更新设备缓存

### Miloco Bridge (`miloco_bridge/main.py`)

- `action=agent` → 转发给 Hermes LLM
- `action=notify` → 转发给 Hermes 直推微信
- `action=perception` → 转发到 Lumi `/api/perception/webhook`（架构精简，不重复分析）
- `/health` 同时检查 Hermes + Lumi 连通性

---

## 四、Hermes 工具 (`lumi_tool.py`)

`lumi_device` 工具支持 12 个 action：

| Action | 说明 |
|--------|------|
| `health` | Lumi 服务状态 |
| `status` | 运行时详情 |
| `summary` | 全屋设备摘要 |
| `types` | 设备类型分布 |
| `search` | 搜索设备 |
| `room` | 按房间查询 |
| `scenes` | 场景列表 |
| `run_scene` | 执行场景 |
| `control` | 单设备控制 |
| `batch_control` | 批量控制 |
| `perception_types` | 感知事件类型列表 |
| `perception_test` | 感知事件 dry run |

---

## 五、测试覆盖

**总计：480 tests，覆盖率 95%**

| 模块 | 覆盖率 | 测试文件 |
|------|--------|----------|
| perception/history.py | ~95% | test_perception_history.py |
| perception/router.py | ~90% | test_perception_router.py |
| hermes_bridge | 98% | test_hermes_bridge.py, test_hermes_send.py |
| device_graph/service.py | 90% | test_service.py |
| device_graph/policy.py | 96% | test_policy.py |
| ha/client.py | 98% | test_ha_client.py |
| ha/events.py | 94% | test_ha_events.py, test_ha_listener.py |
| websocket.py | 95% | test_websocket.py, test_websocket_endpoint.py |
| main.py | 88% | test_main.py, test_api_status.py |

---

## 六、部署组件

| 组件 | 端口 | 管理方式 |
|------|------|----------|
| Lumi API | :8810 | `systemctl --user start lumi` |
| Miloco Bridge | :18789 | `systemctl --user start miloco-hermes-bridge` |
| Home Assistant | :8123 | Docker |
| Hermes Gateway | :8766 | systemd/terminal |

日志路径：
- `~/.hermes/logs/lumi_bridge.log` — 推送记录
- `~/.hermes/logs/lumi_perception.jsonl` — 感知事件历史

---

## 七、可优化方向

### 高优先级

1. **感知历史持久化恢复** — 服务重启后从 JSONL 文件加载历史到内存，当前重启后 ring buffer 清空
2. **感知日报集成** — `GET /api/perception/stats` + `history` 接口已就绪，可在 ha_report.py 里加一段感知摘要
3. **lumi_tool 加 `perception_send`** — 真实触发 webhook（目前只有 dry run），方便 Hermes 模拟/触发感知事件

### 中优先级

4. **设备图增量刷新** — 当前 `refresh()` 是全量拉取，可以只拉 changed_entities（HA 支持 `last_changed` 过滤）
5. **Miloco 融合测试** — `service.py` 60-76 行（Miloco 融合路径）覆盖率 0，需要带 miloco_client mock 的测试
6. **场景执行审计** — 场景执行没有日志，可以加 `~/.hermes/logs/lumi_scenes.log`

### 低优先级

7. **WebSocket 心跳超时调整** — 当前固定 30s，可通过配置文件调整
8. **doctor.sh 加感知历史检查** — 检查 JSONL 文件是否存在且最近有写入
9. **`/api/perception/history` 分页** — 当前只有 limit，可加 offset 支持翻页
10. **设备状态订阅 webhook** — 允许外部服务订阅特定设备的状态变化（目前只有 WS）

### 架构层面

11. **`PerceptionAnalyzer` 规则热加载** — 目前规则硬编码，可以从 `~/.lumi/rules.yaml` 加载
12. **多猫支持** — `PET_WEIGHED` 分析目前假设只有一只猫（麻薯），体重阈值写死
13. **Miloco 摄像头图像接入** — 当前感知事件没有图像附件，可以扩展 `PerceptionEvent` 携带图片 URL

---

## 八、已知限制

- **代理绕过** — 所有本地 HTTP 请求需清除 Clash 代理环境变量（`HTTP_PROXY` 等），已在 `_hermes_send` 和 `_lumi_request` 里处理
- **urllib NO_PROXY CIDR** — Python urllib 不支持 CIDR 格式的 NO_PROXY，只能用 `*` 全局绕过
- **猫砂盆 Empty 铁律** — `aiid=3` 永久拦截，只有 `_force='CONFIRM_EMPTY'` 才能绕过，任何情况不得自动触发
- **HA token 路径** — 固定读 `~/.hermes/ha_token`，不支持其他路径（可通过 config.json 覆盖）
- **小爱语音禁止自动播报** — cron/定时任务绝对不挂语音播报，只有用户明确要求时才调用
