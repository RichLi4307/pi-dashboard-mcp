# pi-dashboard-mcp

让 AstrBot 通过 MCP 协议查询并控制树莓派上的 Pi Dashboard。

## 功能

- 查询系统状态：CPU 占用、温度、内存、磁盘、IP 列表、Tailscale 状态
- 查询 Docker 容器列表
- 获取当前 Pi Dashboard 面板截图
- 远程切换 monitor / console 模式
- 远程滚动容器列表

## 目录结构

```text
.
├── src/pi_dashboard_mcp/    # Python 源码
├── deploy/                  # 实际运行配置
├── docs/                    # 文档
├── systemd/                 # systemd unit 模板
├── nftables/                # 反代规则片段
├── compose.yml              # Docker Compose 模板
└── .env.example             # 环境变量示例
```

## 快速开始

```bash
cd ~/pi-dashboard-mcp
cp .env.example deploy/.env
# 编辑 deploy/.env 按需调整端口
docker compose -f deploy/docker-compose.yml up -d --build
```

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

## 开发工作流

- Windows i9 上写代码、提交、push
- 树莓派上 `git pull` 后运行 `docker compose -f deploy/docker-compose.yml up -d --build`

详见 [docs/workflow.md](docs/workflow.md)。
