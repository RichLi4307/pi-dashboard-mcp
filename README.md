# pi-dashboard-mcp

让 AstrBot 通过 MCP 协议查询并控制树莓派上的 Pi Dashboard。

## 功能

- 查询系统状态：CPU 占用、温度、内存、磁盘、IP 列表、Tailscale 状态
- 查询 Docker 容器列表
- 获取当前 Pi Dashboard 面板截图
- 远程切换 monitor / console 模式
- 远程滚动容器列表

## 架构

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
│  └───────────────────────┘  │
└─────────────────────────────┘
```

详细设计见 [`docs/architecture.md`](docs/architecture.md)。

## 目录结构

```text
.
├── src/pi_dashboard_mcp/    # Python 源码
│   ├── server.py            # MCP SSE 入口
│   ├── tools.py             # Tool 定义与 handler
│   ├── collector.py         # 系统指标采集
│   └── ipc_client.py        # 与 pi_dashboard 通信
├── deploy/                  # 实际运行配置
│   ├── docker-compose.yml   # 生产用 compose
│   └── .env                 # 环境变量（从 .env.example 复制）
├── docs/                    # 文档
│   ├── architecture.md      # 架构设计
│   └── system-impact.md     # 系统影响评估与回滚
├── systemd/                 # systemd unit 模板
├── nftables/                # 反代规则片段
├── compose.yml              # 开发用 compose 模板
├── Dockerfile               # 容器镜像构建
└── .env.example             # 环境变量示例
```

## 前置要求

- 树莓派已安装并运行 [`pi-dashboard`](https://github.com/RichLi4307/pi-dashboard)
- Docker 已安装，`astrbot_astrbot_network` 网络已存在（AstrBot 部署时自动创建）
- 如需 Tailscale / 局域网访问，需把 `nftables/pi-dashboard-mcp.nft` 合并到 `/etc/nftables-astrbot-proxy.conf`

## 快速开始

```bash
cd ~/pi-dashboard-mcp
cp .env.example deploy/.env
# 编辑 deploy/.env 按需调整端口（默认 18473）
docker compose -f deploy/docker-compose.yml up -d --build
```

容器会加入 `astrbot_astrbot_network`，AstrBot 可以通过容器名 `pi-dashboard-mcp` 访问。

## 接入 AstrBot

在 `~/astrbot/data/mcp_server.json` 中新增：

```json
{
  "mcpServers": {
    "pi-dashboard": {
      "active": true,
      "url": "http://pi-dashboard-mcp:18473/sse",
      "transport": "sse",
      "timeout": 30
    }
  }
}
```

重启 AstrBot 后，日志中应出现类似：

```text
MCP server pi-dashboard loaded successfully (3/3 successful)
```

## 可用 Tools

| Tool | 说明 | 示例参数 |
| --- | --- | --- |
| `pi_get_system_status` | 获取 CPU、温度、内存、磁盘、IP、Tailscale 状态 | 无 |
| `pi_get_container_list` | 获取 Docker 容器列表（名称 / 状态 / State） | 无 |
| `pi_get_dashboard_screenshot` | 获取当前面板 PNG 截图（Base64） | 无 |
| `pi_dashboard_switch_mode` | 切换 Pi Dashboard 显示模式 | `{"mode": "monitor"}` 或 `{"mode": "console"}` |
| `pi_dashboard_scroll_containers` | 在监控模式容器列表中向下滚动一页 | 无 |

## 测试

容器内健康检查：

```bash
docker exec astrbot python3 -c "import urllib.request; print(urllib.request.urlopen('http://pi-dashboard-mcp:18473/health', timeout=5).read().decode())"
```

应输出：

```text
pi-dashboard-mcp ok
```

在 AstrBot 对话中直接让 LLM 调用 `pi_get_system_status` 即可查询树莓派实时状态。

## 网络说明

- MCP Server 在容器内监听 `0.0.0.0:18473`
- Docker compose 中端口只绑定 `127.0.0.1:18473`，**不直接暴露公网**
- AstrBot 容器通过 `astrbot_astrbot_network` 直接访问
- Tailscale IP `100.118.236.1:18473` 和局域网 IP `192.168.137.10:18473` 由 `nftables` DNAT 注入

## 性能

- 系统状态每 3 秒、容器列表每 6 秒后台刷新一次，结果预序列化为 JSON
- `pi_get_system_status` / `pi_get_container_list` 不再每次调用都执行 `docker ps` / `tailscale status`，单次请求开销极低
- IPC 截图/模式切换仍实时转发，调用时仍会触发面板渲染

## 可选：systemd 托管

仓库提供 `systemd/pi-dashboard-mcp.service`，可直接使用：

```bash
sudo cp ~/pi-dashboard-mcp/systemd/pi-dashboard-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pi-dashboard-mcp.service
```

该服务依赖 `docker.service` 和 `pi-dashboard.service`，启动时会自动 `docker compose up -d --build`。

## 回滚与故障排查

- 停止容器：`docker compose -f ~/pi-dashboard-mcp/deploy/docker-compose.yml down`
- 停止 systemd 托管：`sudo systemctl disable --now pi-dashboard-mcp.service`
- 移除 AstrBot 配置：编辑 `~/astrbot/data/mcp_server.json`，删除 `pi-dashboard` 条目

更详细的系统影响评估见 [`docs/system-impact.md`](docs/system-impact.md)。

## 开发

- 在 Windows / Linux 开发机上修改代码并 push 到 GitHub
- 在树莓派上 `git pull` 后执行：

```bash
cd ~/pi-dashboard-mcp
docker compose -f deploy/docker-compose.yml up -d --build
```

## 相关项目

- [pi-dashboard](https://github.com/RichLi4307/pi-dashboard) — 树莓派 3.5 寸 TFT 系统仪表盘
