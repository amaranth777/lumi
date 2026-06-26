# Lumi（露米）项目现状文档

> 生成时间：2026-06-26  
> 版本：0.7.0  
> 测试：924 passed，覆盖率约 95%

---

## 一、架构总览

```
微信 / Telegram / Web Dashboard
         │
         ▼
   Hermes Agent Runtime
   ├── lumi_* 工具 x28 (lumi_tool.py / MCP)
   ├── 定时任务 (cron jobs)
   └── 主动分析 / 通知
         │
         ▼
   Lumi API  :8810
   ├── 设备图层 (Device Graph)
   ├── HA 扩展层 (HA Extended)
   ├── 感知层 (Perception)
   ├── 场景层 (Scenes)
   ├── 主动巡检层 (Proactive)
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
| POST | `/api/device_graph/refresh_incremental` | 增量刷新设备图（不触发全量重拉） |

### HA 扩展（新增）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ha/services` | 列出所有 HA 服务 |
| GET | `/api/ha/automations` | 列出所有自动化 |
| POST | `/api/ha/automations/{id}/trigger` | 手动触发自动化 |
| POST | `/api/ha/automations/{id}/toggle` | 启用/禁用自动化 |
| GET | `/api/ha/scripts` | 列出所有脚本 |
| POST | `/api/ha/scripts/{id}/run` | 执行脚本 |
| GET | `/api/ha/history/{id}?hours=24` | 查询实体历史状态 |
| POST | `/api/ha/events/{event_type}` | 触发自定义 HA 事件 |
| POST | `/api/ha/template` | 渲染 Jinja2 模板 |
| GET | `/api/ha/config` | 获取 HA 配置信息 |

### 感知

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/perception/webhook` | 接收 Miloco 感知事件，触发分析+推送 |
| POST | `/api/perception/webhook/test` | Dry run（分析但不推送） |
| GET | `/api/perception/events/types` | 列出所有事件类型 |
| GET | `/api/perception/history?limit=&offset=` | 最近感知事件历史（支持 offset 分页） |
| GET | `/api/perception/stats` | 感知事件统计摘要 |

### 场景

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/scenes` | 列出所有场景 |
| POST | `/api/scenes` | 创建/更新场景 |
| GET | `/api/scenes/{id}` | 查询单个场景 |
| DELETE | `/api/scenes/{id}` | 删除场景 |
| POST | `/api/scenes/{id}/execute` | 执行场景（含审计日志） |

### 主动巡检（新增）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/proactive/status` | 巡检引擎状态及最近结果 |
| POST | `/api/proactive/check` | 手动触发一次巡检 |
| POST | `/api/proactive/reload` | 重新加载巡检规则 |

### 摄像头（新增）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/cameras` | Miloco 摄像头列表（id/name/room/stream_url） |

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
- `refresh_incremental()` 新增增量刷新端点，Hermes 可主动触发局部刷新
- `batch_execute_command()` 用 `ThreadPoolExecutor(max_workers=8)` 并发执行
- `search_devices()` 支持 name/id/room/type 多字段搜索

### HA 扩展 (`lumi/ha/`)

- **client.py** — HAClient，指数退避重试（retries=3, 2s base）
- **events.py** — WebSocket 订阅 state_changed，断线自动重连，增量更新设备缓存
- **router.py** — HA 全量 API 路由（新增），代理 services/automations/scripts/history/events/template/config
- **ha_trigger_automation** — 触发指定 HA 自动化的 lumi_* action，已暴露至 MCP

### 感知闭环 (`lumi/perception/`)

- **events.py** — `PerceptionEvent` 模型，`from_miloco_webhook()` 解析，自动提取 weight_kg；新增 `image_url` / `thumbnail_url` 字段，感知推送可附图
- **analyzer.py** — `PerceptionAnalyzer`，联合 HA 状态做决策；多猫支持（`CatProfile`），`PET_WEIGHED` 分析匹配多猫体重档案
- **router.py** — webhook 接收端，分析+推送+历史记录+WS广播；`/api/perception/history` 支持 `offset` 参数分页
- **history.py** — ring buffer（默认200条）+ JSONL 持久化到 `~/.hermes/logs/lumi_perception.jsonl`，重启后自动恢复

**感知事件类型**（10种）：
- `pet_detected` / `person_detected`
- `pet_at_litter_box` / `pet_left_litter_box`
- `litter_box_full` / `litter_box_cleaned` / `litter_box_weight_low`
- `pet_weighed`
- `motion_detected` / `anomaly_detected`

### 主动巡检 (`lumi/proactive/`)（新增）

- 内置 5 条巡检规则，每 5 分钟自动执行
- 支持手动触发和规则重载
- 规则异常自动通知 Hermes
- **rules_loader.py** — 新增，支持从 `~/.lumi/rules.yaml` 热加载巡检规则，文件变更后无需重启服务
- **auto_execute** — 主动执行能力，规则触发后可直接调用设备控制，`SafetyGuard` 拦截危险操作（`PetLitterBoxEmptyGuard` 等永久生效）

### 多猫档案 (`lumi/cats/`)（新增）

- **CatProfile** — 猫咪档案模型，含 name/weight_range/rfid 等字段
- `PET_WEIGHED` 感知事件自动按体重范围匹配猫咪档案，推送附猫名
- 档案通过 `~/.lumi/cats.yaml` 配置，支持热加载

### WebSocket (`lumi/websocket.py`)

- 实时状态推送，<100ms 延迟
- `ws_heartbeat_seconds` 配置化（默认 30s，可通过 `~/.lumi/config.yaml` 调整）

### Hermes Bridge (`lumi/hermes_bridge/`)

- 推送限流（CooldownTracker），各事件独立冷却时间
- 绕过 Clash 代理直连 Hermes gateway API
- 推送日志写入 `~/.hermes/logs/lumi_bridge.log`
- 失败时记录 error，不崩溃

### Miloco Bridge (`miloco_bridge/main.py`)

- `action=agent` → 转发给 Hermes LLM
- `action=notify` → 转发给 Hermes 直推微信
- `action=perception` → 转发到 Lumi `/api/perception/webhook`（架构精简，不重复分析）
- `/health` 同时检查 Hermes + Lumi 连通性
- `/api/cameras` — 摄像头列表端点，返回 Miloco 所有摄像头 id/name/room/stream_url

### MCP Server (`lumi/mcp_server.py`)（新增）

- 标准 MCP server，供 Hermes Agent 通过 MCP 协议调用
- 暴露全部 28 个 `lumi_*` tool
- 与 `lumi_tool.py` 共用同一 action 入口，保持一致性

---

## 四、Hermes 工具 (`lumi_tool.py` / MCP)

通过 `lumi_tool.py` 统一入口 + MCP server 双路暴露，共 **28 个 lumi_* tool**，覆盖设备控制、场景、感知、HA 扩展、主动巡检、多猫档案、摄像头七大领域：

| Action | 说明 |
|--------|------|
| `health` | Lumi 服务状态 |
| `status` | 运行时详情 |
| `summary` | 全屋设备摘要 |
| `types` | 设备类型分布 |
| `search` | 搜索设备 |
| `room` | 按房间查询 |
| `refresh_incremental` | 增量刷新设备图 |
| `scenes` | 场景列表 |
| `run_scene` | 执行场景 |
| `control` | 单设备控制 |
| `batch_control` | 批量控制 |
| `auto_execute` | 主动执行（安全守卫保护） |
| `perception_types` | 感知事件类型列表 |
| `perception_test` | 感知事件 dry run |
| `perception_send` | 真实触发感知 webhook |
| `perception_history` | 查询感知历史（支持 offset 分页） |
| `perception_stats` | 感知统计摘要 |
| `cat_profiles` | 多猫档案查询（CatProfile） |
| `ha_services` | 列出 HA 服务 |
| `ha_automations` | 列出自动化 |
| `ha_trigger_automation` | 触发自动化 |
| `ha_toggle_automation` | 启用/禁用自动化 |
| `ha_run_script` | 执行脚本 |
| `ha_history` | 查询实体历史 |
| `ha_template` | 渲染模板 |
| `cameras` | Miloco 摄像头列表 |
| `proactive_status` | 巡检引擎状态 |
| `proactive_check` | 手动触发巡检 |

---

## 五、测试覆盖

**总计：924 tests，覆盖率约 95%**

| 模块 | 覆盖率 | 测试文件 |
|------|--------|----------|
| perception/history.py | ~95% | test_perception_history.py |
| perception/router.py | ~90% | test_perception_router.py |
| perception/events.py | ~93% | test_perception_events.py |
| hermes_bridge | 98% | test_hermes_bridge.py, test_hermes_send.py |
| device_graph/service.py | 90% | test_service.py |
| device_graph/policy.py | 96% | test_policy.py |
| ha/client.py | 98% | test_ha_client.py |
| ha/events.py | 94% | test_ha_events.py, test_ha_listener.py |
| ha/router.py | ~92% | test_ha_router.py |
| proactive/ | ~90% | test_proactive.py, test_rules_loader.py |
| cats/ | ~91% | test_cat_profiles.py |
| mcp_server.py | ~88% | test_mcp_server.py |
| lumi_tool.py | ~93% | test_lumi_tool.py |
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
- `~/.hermes/logs/lumi_perception.jsonl` — 感知事件历史（持久化，重启恢复）
- `~/.hermes/logs/lumi_scenes.log` — 场景执行审计日志

配置路径：
- `~/.lumi/config.yaml` — 主配置（ws_heartbeat_seconds 等）
- `~/.lumi/rules.yaml` — 巡检规则（支持热加载）
- `~/.lumi/cats.yaml` — 多猫档案（CatProfile）

---

## 七、已完成优化项

- ✅ 感知历史持久化恢复 — 重启后从 JSONL 自动加载 ring buffer
- ✅ lumi_tool 加 `perception_send` — 真实触发 webhook，方便 Hermes 模拟感知事件
- ✅ Miloco 融合测试 — service.py 融合路径覆盖率补全
- ✅ 场景执行审计日志 — 写入 `~/.hermes/logs/lumi_scenes.log`
- ✅ HA 全量 API 接入 — `lumi/ha/router.py` 新增 10 个端点
- ✅ 设备别名配置化 — 支持通过配置文件覆盖设备显示名
- ✅ 主动管理能力 — `lumi/proactive/` 5条内置规则，每5分钟自动巡检
- ✅ Hermes MCP 接入 — `lumi/mcp_server.py` 暴露 28 个 lumi_* tool
- ✅ 规则热加载 — `lumi/proactive/rules_loader.py`，`~/.lumi/rules.yaml` 运行时重载，无需重启
- ✅ 多猫支持 — `CatProfile` + `cats.yaml`，`PET_WEIGHED` 按体重范围匹配猫咪
- ✅ PerceptionEvent 图片 URL — `image_url` / `thumbnail_url` 字段，感知推送附图
- ✅ `/api/perception/history` 分页 — 新增 `offset` 参数支持翻页
- ✅ WebSocket 心跳配置化 — `ws_heartbeat_seconds` 通过 `~/.lumi/config.yaml` 调整
- ✅ 主动执行能力 — `auto_execute` action + `SafetyGuard` 安全守卫，规则可直接触发设备控制
- ✅ ha_trigger_automation — lumi_* tool 直接触发 HA 自动化
- ✅ 设备图增量刷新 — `refresh_incremental` 端点 + lumi_* tool，Hermes 可主动触发局部刷新
- ✅ Miloco 摄像头列表 — `/api/cameras` + `cameras` tool，暴露摄像头 id/name/room/stream_url

---

## 八、可优化方向

1. **前端看板升级** — WebSocket 实时告警显示，Dashboard 接入 `/ws/device_graph` 推送，异常事件高亮提示
2. **Miloco 摄像头串流接入** — 在感知推送中附上摄像头截图或缩略图，目前 `image_url` 已就位，需 Miloco 侧推流支持
3. **HA 自动化规则全量导入到 Lumi 场景** — 将 HA automations 批量同步为 Lumi scenes，统一执行入口和审计日志
4. **多用户/多设备权限隔离** — 当前所有 API 无鉴权，引入 token/role 体系，支持多人共用同一 Lumi 实例

---

## 九、已知限制

- **代理绕过** — 所有本地 HTTP 请求需清除 Clash 代理环境变量（`HTTP_PROXY` 等），已在 `_hermes_send` 和 `_lumi_request` 里处理
- **urllib NO_PROXY CIDR** — Python urllib 不支持 CIDR 格式的 NO_PROXY，只能用 `*` 全局绕过
- **猫砂盆 Empty 铁律** — `aiid=3` 永久拦截，只有 `_force='CONFIRM_EMPTY'` 才能绕过，任何情况不得自动触发
- **HA token 路径** — 固定读 `~/.hermes/ha_token`，不支持其他路径（可通过 config.json 覆盖）
- **小爱语音禁止自动播报** — cron/定时任务绝对不挂语音播报，只有用户明确要求时才调用
