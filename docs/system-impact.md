# 系统影响评估

## 新增组件

| 组件 | 说明 |
|------|------|
| `pi-dashboard-mcp` Docker 容器 | Python 轻量 MCP Server |
| `pi-dashboard-mcp.service` | 可选 systemd 托管 |
| nftables 规则 | 18473 端口 DNAT |
| IPC socket | `/run/pi_dashboard/pi_dashboard.sock` |

## 资源影响

| 资源 | 影响 |
|------|------|
| CPU | 后台缓存刷新每 3~6 秒一次，单次 Tool 调用不再实时采集；日常空闲接近 0 |
| 内存 | 容器实测约 50~90MB |
| 磁盘 | 镜像 + 日志，预计 < 500MB |
| 网络 | 仅本地 Docker 网络通信，无外网依赖 |

## 安全影响

| 项 | 说明 |
|------|------|
| `/proc` 挂载 | 只读，用于读取 CPU、内存信息 |
| `/sys` 挂载 | 只读，用于读取温度 |
| `docker.sock` | 只读，用于 `docker ps` 查询容器状态 |
| IPC socket | 容器可读写，用于截图和控制面板 |
| 端口 18473 | 仅监听 127.0.0.1，外部通过 nftables 控制 |

## 对现有服务影响

- `pi_dashboard.service`：需新增 `ipc_server.py`，IPC 失败不影响本地显示
- `astrbot`：只需在 `mcp_server.json` 新增 server 配置
- `nftables`：新增 18473 端口规则

## 失败回滚

```bash
# 停止容器
docker compose -f ~/pi-dashboard-mcp/deploy/docker-compose.yml down

# 停止 systemd 服务
sudo systemctl disable --now pi-dashboard-mcp.service

# 还原 nftables（编辑 /etc/nftables-astrbot-proxy.conf 后重载）
sudo systemctl reload astrbot-tailscale-proxy.service

# 移除 AstrBot MCP 配置
# 编辑 ~/astrbot/data/mcp_server.json，删除 pi-dashboard 条目
```

## 风险等级

**总体风险：低**。新增服务轻量、只读为主、端口不直接暴露公网。
