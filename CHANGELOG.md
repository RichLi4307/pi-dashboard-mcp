# 变更日志

## 2026-08-24

### 阶段 1：AstrBot 适配与截图提示修正

- 扩展 `pi_dashboard_switch_mode` 支持更多模式：`monitor` / `temp` / `cpu` / `mem` / `disk` / `net`
- 修复 MCP SSE 重定向问题，提升 AstrBot 连接稳定性
- 强化 `pi_get_dashboard_screenshot` 的返回提示，明确截图的发送方式与限制
- 固定 `mcp<2.0` 依赖，避免新版 MCP SDK 破坏协议兼容性
- 截图 Tool 返回标准 `ImageContent`，兼容更多 MCP Client

### Phase 2.1：截图持久化与清理接口

- 新增 `screenshot_store.py` 持久化模块
- 截图保存到 `/var/lib/pi-dashboard/screenshots/{timestamp}_{uuid8}.png`
- `server.py` 新增 `/screenshots/{filename}` 静态文件路由，带文件名白名单防目录遍历
- `tools.py` 截图返回包含文件名、大小、访问 URL
- 新增 Tool：`pi_dashboard_cleanup_screenshots`
  - 支持按 `max_age_hours` 删除过期截图
  - 支持按 `keep_count` 保留最近 N 张
- `compose.yml` 与 `deploy/docker-compose.yml` 挂载 `/var/lib/pi-dashboard` 持久化卷

## 2026-07-31

- 修复 `pi_get_system_status` 首次调用 CPU 为 0 的问题
- 优化系统状态采集：通过 IPC 从宿主机读取 IP 与 Tailscale 状态
- 后台缓存指标数据并预序列化 JSON，降低 Tool 调用开销

## 2026-07-27

- 重写 README，移除 workflow.md
- 添加 18473 端口 nftables 规则
- 调整容器名称/状态截断策略以匹配面板布局
