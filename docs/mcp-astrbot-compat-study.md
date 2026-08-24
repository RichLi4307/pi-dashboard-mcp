# Pi Dashboard MCP 与新版 AstrBot / 面板适配研究报告

> 会话：Pi面板MCP服务器  
> 任务：更新 MCP 服务器，检查与新版 AstrBot、面板的适配与冲突，记录现状与解决方案。  
> 当前时间：2026-08-24  
> AstrBot 版本：`4.27.4`（容器内 `/AstrBot`）  
> pi-dashboard-mcp 版本：`0.1.0`（commit `c147e78`）  
> pi_dashboard 版本：Rust v0.2.x（commit 未精确读取，以 `rust/src/ipc.rs` 为准）  
> MCP SDK 版本（AstrBot 与 pi-dashboard-mcp 容器共用兼容版本）：`1.29.0`

---

## 1. 运行现状

### 1.1 服务健康

- `pi-dashboard-mcp` 容器正常运行，监听 `0.0.0.0:18473`。
- AstrBot 侧 `mcp_server.json` 已配置 `pi-dashboard` SSE 服务。
- 健康检查 `GET /health` 返回 `pi-dashboard-mcp ok`。
- MCP `initialize` / `list_tools` / `call_tool` 均可正常调用。

### 1.2 当前工具列表

| Tool | 说明 | 当前参数 |
| --- | --- | --- |
| `pi_get_system_status` | 系统状态 | 无参数 |
| `pi_get_container_list` | Docker 容器列表 | 无参数 |
| `pi_get_dashboard_screenshot` | 面板截图 | 无参数 |
| `pi_dashboard_switch_mode` | 切换显示模式 | `{"mode": "monitor"}`（当前 enum 仅 `monitor`） |
| `pi_dashboard_scroll_containers` | 滚动容器列表 | 无参数 |

### 1.3 未提交改动

- `Dockerfile` 有本地未提交改动：将清华 PyPI 镜像替换为阿里云镜像，并预装 `setuptools wheel`。
- 该改动属于构建稳定性修复，建议在后续更新中提交或合并。

---

## 2. AstrBot 4.27.4 对 MCP 图片的处理机制

### 2.1 关键代码路径

- `astrbot/core/agent/mcp_client.py`：MCPClient / MCPTool 封装。
- `astrbot/core/agent/runners/tool_loop_agent_runner.py`：工具结果处理与图片缓存。
- `astrbot/core/agent/tool_image_cache.py`：图片缓存到 `data/temp/tool_images/`。
- `astrbot/core/tools/message_tools.py`：`send_message_to_user` 工具定义。

### 2.2 ImageContent 处理流程

当 MCP 工具返回 `mcp.types.ImageContent` 时，AstrBot 执行以下操作：

1. 将 base64 图片数据保存到 `data/temp/tool_images/{tool_call_id}_{index}.png`。
2. 在 tool result 中向 LLM 返回提示文本：
   ```text
   Image returned and cached at path='...'.
   Review the image below.
   Use send_message_to_user to send it to the user if satisfied,
   with type='image' and path='...'.
   ```
3. 同时把图片作为 `role=user` 的消息追加到对话上下文（使用 `data:image/png;base64,...` URL），让 LLM 能"看到"图片内容。
4. **依赖 LLM 在后续步骤中主动调用 `send_message_to_user(type='image', path='...')` 才能把图片发给用户。**

### 2.3 发送渠道的致命限制

`send_message_to_user` 是 AstrBot 内置工具，用于向用户发送图片/文件/文字。但在当前环境中，**`astrbot_plugin_private_companion` 插件会在"被动回复"场景下（尤其是私聊）从工具集中移除 `send_message_to_user`，并向 system_prompt 注入禁止调用的指令**。

相关代码：

```python
# astrbot_plugin_private_companion/main.py:14612
instruction = (
    "【当前会话回复边界】这是普通私聊或群聊的被动回复。请直接输出一次最终正文；"
    "不要调用 `send_message_to_user` 给当前会话发文字，也不要在工具调用后重复输出同一正文。"
    "该工具已从本次请求中移除；即使历史消息里出现过它，也不要调用、补写或猜测该工具调用。"
)
```

这导致：

- `pi_get_dashboard_screenshot` 返回图片后，AstrBot 提示 LLM 调用 `send_message_to_user`。
- LLM 的工具列表中没有 `send_message_to_user`，无法调用。
- 图片只存在于 `data/temp/tool_images/` 临时缓存和对话上下文中，**无法送达用户**。
- 即使用户在下一轮说"把图发给我"，缓存文件可能仍在，但 LLM 依然没有 `send_message_to_user` 可用。

**这是当前图片发送失败的最主要根因。**

---

## 3. 与面板侧（pi_dashboard）的适配点

### 3.1 IPC 接口现状

`pi_dashboard/rust/src/ipc.rs` 当前支持：

- `screenshot` → `{"status": "ok", "data": "base64png..."}`
- `status` → `{"status": "ok", "ips": [...], "tailscale": "..."}`
- `switch_mode` → 支持 `monitor/temp/cpu/mem/disk/net`
- `scroll_containers` → `{"status": "ok", "offset": ..., "total": ...}`

### 3.2 MCP server 与面板接口不一致

`pi-dashboard-mcp/src/pi_dashboard_mcp/tools.py` 中：

```python
Tool(
    name="pi_dashboard_switch_mode",
    description="切换 Pi Dashboard 显示模式（当前仅 monitor）",
    inputSchema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["monitor"],  # 仅允许 monitor
                "description": "目标模式",
            }
        },
        "required": ["mode"],
    },
)
```

但面板实际支持 `monitor/temp/cpu/mem/disk/net`。这会导致：

- 用户无法通过 MCP 切换到温度、CPU、内存、磁盘、网络等模式。
- 工具描述与面板能力不匹配。

**建议：将 enum 扩展为 `["monitor", "temp", "cpu", "mem", "disk", "net"]`，并同步更新 description。**

---

## 4. 其他适配与风险点

### 4.1 SSE `/messages` 端点的 307 重定向

当前 `server.py` 使用：

```python
Mount("/messages", app=sse.handle_post_message)
```

Starlette 的 `Mount` 默认会在请求缺少尾斜杠时返回 `307 Temporary Redirect` 到 `/messages/`。

日志中出现：

```text
POST /messages?session_id=... 307 Temporary Redirect
POST /messages/?session_id=... 202 Accepted
```

虽然 MCP SDK 的 `create_mcp_http_client` 设置了 `follow_redirects=True`，307 对 POST 也会保留 body 重试，但这带来：

- 每个 MCP 消息多一次 RTT。
- 某些反向代理/网络环境下可能出错。
- 日志不美观。

**建议：改为 `Mount("/messages/", ...)` 或在 Starlette 应用中设置 `redirect_slashes=False`。**

### 4.2 容器内 hostname 显示为容器 ID

`collector.py` 返回 `hostname: os.uname().nodename`，在容器内显示的是容器短 ID（如 `4ef32550b6a9`），不是宿主机主机名。虽然不影响功能，但会让用户困惑。

**建议：从宿主机 IPC status 中读取真实 hostname，或提供可配置的 `HOSTNAME` 环境变量覆盖。**

### 4.3 Dockerfile 构建源

当前 Dockerfile 有未提交改动，使用阿里云 PyPI。需要决定是否保留并提交。

---

## 5. 解决方案方向

以下方案按"影响范围"和"根本程度"分类。

### 5.1 在 pi-dashboard-mcp 侧可做的改进

#### 方案 A：扩展 `pi_dashboard_switch_mode` 的 mode 枚举

将 `enum` 扩展为面板实际支持的值，并更新 description：

```json
{
  "mode": {
    "type": "string",
    "enum": ["monitor", "temp", "cpu", "mem", "disk", "net"],
    "description": "目标显示模式：monitor（监控总览）/ temp（温度）/ cpu（CPU）/ mem（内存）/ disk（磁盘）/ net（网络）"
  }
}
```

**优先级：高，改动小，立即生效。**

#### 方案 B：修复 SSE messages 路径的 307 重定向

改为：

```python
Mount("/messages/", app=sse.handle_post_message)
```

或在 `Starlette(...)` 中设置 `redirect_slashes=False`。

**优先级：中，优化稳定性。**

#### 方案 C：服务端持久化截图 + 提供 HTTP URL

在 MCP server 内：

1. 将截图保存到持久化目录（如 `/var/lib/pi-dashboard/screenshots/{timestamp}.png`）。
2. 增加静态文件路由 `/screenshots/{filename}`。
3. `pi_get_dashboard_screenshot` 返回：
   - `ImageContent`（保持现有行为，让 AstrBot 缓存并展示给 LLM）
   - 一个 `TextContent` 说明截图的持久化 URL/路径

返回示例：

```python
[
    ImageContent(type="image", data=base64, mimeType="image/png"),
    TextContent(
        type="text",
        text=(
            "Pi Dashboard 截图已生成。"
            "如需要发送给用户，请调用 send_message_to_user，"
            "messages=[{\"type\": \"image\", \"url\": \"http://pi-dashboard-mcp:18473/screenshots/xxx.png\"}]"
        )
    )
]
```

**优点**：

- 图片文件持久化，跨轮次可用。
- 提供 URL 渠道，LLM 可通过 `send_message_to_user(url=...)` 发送。
- 即使 AstrBot 临时缓存被清理，仍可通过 URL 重新获取。

**缺点**：

- 若 `send_message_to_user` 被 private_companion 移除，LLM 仍无法主动发送；但 URL 会保留在对话中，用户可手动访问。
- 需要增加静态文件服务和卷持久化。

**优先级：中，属于"拓宽发送渠道"的核心动作。**

#### 方案 D：在工具描述和返回文本中强化发送提示

当前 `pi_get_dashboard_screenshot` 的 description：

```text
获取当前 Pi Dashboard 面板截图（Base64 PNG）
```

建议改为：

```text
获取当前 Pi Dashboard 面板截图。
返回一张 PNG 图片，AstrBot 会将其缓存到临时目录。
如果用户要求查看/发送截图，请在获得图片后调用 send_message_to_user，
messages=[{"type": "image", "path": "< AstrBot 返回给你的缓存路径 >"}]。
```

同时在返回的 TextContent 中给出明确指令（见方案 C）。

**优点**：提高 LLM 调用 `send_message_to_user` 的成功率。

**缺点**：无法解决 `send_message_to_user` 被禁用的问题。

**优先级：中，成本低，应该做。**

### 5.2 需要 AstrBot / 插件侧配合的改进

#### 方案 E：AstrBot 自动发送 MCP 图片

修改 `tool_loop_agent_runner.py`：

当检测到 `cached_images` 非空时，**自动将图片加入当前 assistant 回复的消息链**（`result.chain`），而不是仅追加到对话上下文并依赖 LLM 调用 `send_message_to_user`。

这是从根本上解决 private_companion 禁用 `send_message_to_user` 导致图片无法发送的问题。

**优先级：高（如果允许修改 AstrBot 源码）。**

#### 方案 F：private_companion 对 MCP 图片发送开例外

修改 `astrbot_plugin_private_companion/main.py`：

- 在移除 `send_message_to_user` 前，检测当前请求是否包含 MCP 图片缓存。
- 如果检测到，保留 `send_message_to_user` 或自动转发图片。

**优先级：高（如果允许修改插件）。**

#### 方案 G：AstrBot 自动将回复中的图片 URL 渲染为 Image 组件

在 `result_decorate` 或 `respond` stage 中，识别 assistant 回复中的 markdown 图片语法 `![alt](http://...)` 或裸图片 URL，自动转换为 `Image.fromURL(url)`。

这样即使 LLM 不调用 `send_message_to_user`，只要它在回复中输出截图 URL，AstrBot 也会自动发送图片。

**优先级：中（通用改进，不止利于 pi-dashboard-mcp）。**

---

## 6. 推荐实施顺序

### 第一阶段：立即修复（低侵入）

1. 扩展 `pi_dashboard_switch_mode` 的 mode 枚举。
2. 修复 SSE `/messages` 307 重定向。
3. 提交/整理 Dockerfile 的 PyPI 源改动。
4. 强化 `pi_get_dashboard_screenshot` 的 description 和返回 TextContent 提示。

### 第二阶段：拓宽图片发送渠道

5. 在 MCP server 内持久化截图到 `/var/lib/pi-dashboard/screenshots/`。
6. 增加 `/screenshots/{filename}` 静态文件路由。
7. 返回 TextContent 中附带可访问的 HTTP URL。
8. 在 docker-compose 中挂载持久化目录。

### 第三阶段：根治发送失败（需改 AstrBot 或其插件）

9. 选择以下任一方案实施：
   - 修改 AstrBot `tool_loop_agent_runner.py` 自动发送 MCP 图片；
   - 修改 private_companion 插件，对 MCP 图片发送开例外；
   - 或增加 AstrBot 对回复中图片 URL 的自动渲染。

---

## 7. 待确认事项

- 用户是否允许修改 AstrBot 源码或 private_companion 插件源码？
- 是否需要为截图设置访问控制（token / IP 白名单）？当前 18473 仅本地/内网可访问，公网需通过 nftables。
- 截图保存策略：保留最近 N 张 / 保留 N 天 / 永久保留？
- 当前 Dockerfile 的阿里云 PyPI 改动是否保留？

---

## 8. 关键文件引用

- `pi-dashboard-mcp/src/pi_dashboard_mcp/server.py`
- `pi-dashboard-mcp/src/pi_dashboard_mcp/tools.py`
- `pi-dashboard-mcp/src/pi_dashboard_mcp/collector.py`
- `pi-dashboard-mcp/Dockerfile`
- `pi-dashboard-mcp/compose.yml`
- `pi-dashboard-mcp/deploy/docker-compose.yml`
- `pi_dashboard/rust/src/ipc.rs`
- `AstrBot/astrbot/core/agent/runners/tool_loop_agent_runner.py`
- `AstrBot/astrbot/core/agent/tool_image_cache.py`
- `AstrBot/astrbot/core/tools/message_tools.py`
- `AstrBot/data/plugins/astrbot_plugin_private_companion/main.py`

---

---

## 9. 阶段一实施记录（2026-08-24）

已完成以下改动并重新构建、验证：

- [x] 扩展 `pi_dashboard_switch_mode` 的 mode 枚举为 `monitor/temp/cpu/mem/disk/net`，同步更新 description。
- [x] 修复 SSE `/messages` 端点的 307 重定向：`SseServerTransport("/messages/")` + `Mount("/messages/", ...)`。
- [x] 强化 `pi_get_dashboard_screenshot` 的 description，并在返回中追加 `TextContent` 发送提示。
- [x] 整理 Dockerfile：保留并提交阿里云 PyPI 源 + 预装 `setuptools wheel` 的改动。
- [x] 更新 `README.md` 与 `docs/architecture.md` 中的工具说明和示例。

验证结果：

- 容器重新构建并启动成功。
- `GET /health` 返回 `pi-dashboard-mcp ok`。
- SSE endpoint 返回 `/messages/?session_id=...`，POST 不再触发 307，直接返回 202 Accepted。
- `list_tools` 正确返回扩展后的 6 种模式。
- `call_tool('pi_dashboard_switch_mode', {'mode': 'temp/cpu/mem/disk/net/monitor'})` 均返回 `{"status": "ok"}`。
- `call_tool('pi_get_dashboard_screenshot', {})` 返回 `ImageContent` + `TextContent` 提示。

注意：AstrBot 侧需要重新初始化 MCP 连接（重启 AstrBot 或在 WebUI 中重新启用 `pi-dashboard` MCP 服务）才能加载新的工具 schema。

*报告生成：Kimi Code CLI*  
*基于实际代码读取与运行时检查*
