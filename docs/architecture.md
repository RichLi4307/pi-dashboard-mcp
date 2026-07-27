# 架构设计

## 整体架构

```text
┌─────────────────┐
│   AstrBot 容器   │
│  (mcp client)   │
└────────┬────────┘
         │ SSE over HTTP
         ▼
┌─────────────────────────────┐
│     pi-dashboard-mcp 容器    │
│  ┌───────────────────────┐  │
│  │      server.py        │  │
│  │   (MCP SSE endpoint)  │  │
│  └───────────┬───────────┘  │
│              │              │
│  ┌───────────┴───────────┐  │
│  │  collector.py         │  │  读取 /proc, /sys, docker, tailscale
│  │  ipc_client.py        │  │  Unix socket 请求 pi_dashboard
│  └───────────────────────┘  │
└────────┬────────────────────┘
         │ Unix socket
         ▼
┌─────────────────────────────┐
│     pi_dashboard 进程        │
│  ┌───────────────────────┐  │
│  │    ipc_server.py      │  │  监听 /run/pi_dashboard/pi_dashboard.sock
│  │    metrics.py         │  │  公共数据采集模块
│  │    monitor_mode.py    │  │  面板显示模式
│  └───────────────────────┘  │
└─────────────────────────────┘
```

## 模块职责

- `server.py`：MCP Server 入口，注册 Tools，启动 SSE
- `collector.py`：采集系统指标
- `ipc_client.py`：与 pi_dashboard 进程通信
- `tools.py`：Tool 定义与 handler
- `metrics.py`（在 pi_dashboard 内）：公共数据采集逻辑
- `ipc_server.py`（在 pi_dashboard 内）：接收控制请求

## IPC 协议

Unix socket 路径：`/run/pi_dashboard/pi_dashboard.sock`

请求格式：
```json
{"action": "screenshot"}
{"action": "switch_mode", "mode": "console"}
{"action": "scroll_containers"}
```

响应格式：
```json
{"status": "ok", "data": "base64encodedpng..."}
{"status": "error", "message": "..."}
```

## 端口与网络

- MCP Server 监听 `127.0.0.1:18473`
- 加入 `astrbot_astrbot_network`，AstrBot 容器通过容器名访问
- Tailscale/局域网访问通过 nftables DNAT 映射
