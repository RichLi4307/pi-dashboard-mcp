# Pi Dashboard MCP 项目规范

## 项目信息

- 仓库：`git@github.com:RichLi4307/pi-dashboard-mcp.git`
- 运行位置：`~/pi-dashboard-mcp/deploy/`
- 服务端口：`127.0.0.1:18473`（外部通过 nftables DNAT）
- 依赖网络：`astrbot_astrbot_network`

## 常用命令

```bash
# 构建并启动
docker compose -f deploy/docker-compose.yml up -d --build

# 查看日志
docker logs -f pi-dashboard-mcp

# 停止
docker compose -f deploy/docker-compose.yml down

# 测试 SSH 到 GitHub
ssh -T git@github.com

# 更新依赖后重新构建
docker compose -f deploy/docker-compose.yml up -d --build --force-recreate
```

## 目录约定

- `src/`：源码工程，提交 Git
- `deploy/`：运行实例，`deploy/.env` 不提交 Git
- `docs/`：项目文档
- `systemd/`：systemd unit 模板
- `nftables/`：nftables 规则片段

## 端口约定

- `18473`：MCP Server SSE 端口
- IPC socket：`/run/pi_dashboard/pi_dashboard.sock`

## 注意事项

- 修改 compose.yml 模板后，同步更新 deploy/docker-compose.yml
- 不要提交 `deploy/.env`
- IPC socket 权限需保证容器内进程可读写
