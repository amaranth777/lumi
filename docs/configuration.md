# Lumi 配置示例

## 最小配置（~/.lumi/config.json）

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

## 完整配置（带设备别名）

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
    "token": "your-secret-token"
  },
  "device_aliases": [
    {
      "entity_id": "fan.zhimi_airpurifier_ma2",
      "name": "客厅空气净化器",
      "room": "客厅",
      "icon": "mdi:air-purifier"
    },
    {
      "entity_id": "light.yeelink_light_ceiling3_123456",
      "name": "卧室吸顶灯",
      "room": "卧室"
    },
    {
      "entity_id": "switch.chuangmi_plug_v3_123456",
      "name": "书房插座",
      "room": "书房"
    }
  ]
}
```

## 环境变量覆盖

```bash
export LUMI_HA_BASE_URL=http://192.168.5.184:8123
export LUMI_HA_TOKEN_FILE=~/.hermes/ha_token
export LUMI_SERVER_TOKEN=my-token
```

## 安装为 systemd 服务（用户模式）

```bash
# 1. 复制 service 文件
mkdir -p ~/.config/systemd/user/
cp deploy/lumi.service ~/.config/systemd/user/

# 2. 重新加载并启动
systemctl --user daemon-reload
systemctl --user enable lumi.service
systemctl --user start lumi.service

# 3. 查看状态
systemctl --user status lumi.service

# 4. 查看日志
journalctl --user -u lumi.service -f
```

## API 使用示例

### 健康检查

```bash
curl http://127.0.0.1:8810/health
```

### 获取设备图摘要

```bash
curl 'http://127.0.0.1:8810/api/device_graph/summary?refresh=true' | jq
```

### 获取完整设备图

```bash
curl 'http://127.0.0.1:8810/api/device_graph' | jq
```

### 按房间筛选（通过 jq）

```bash
curl -s 'http://127.0.0.1:8810/api/device_graph' | \
  jq '.devices[] | select(.room == "客厅")'
```
