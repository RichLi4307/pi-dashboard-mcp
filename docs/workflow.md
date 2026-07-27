# 开发部署工作流

## 总体流程

```text
Windows i9 (开发机)
  ├── 编辑代码
  ├── 本地测试
  ├── git commit → push
  │
  ▼
GitHub (SSH over clash socks5:17891)
  │
  ▼
树莓派 FocusRasPi4B (运行机)
  ├── git pull
  ├── 同步 deploy/ 配置
  ├── docker compose -f deploy/docker-compose.yml up -d --build
  └── 测试 AstrBot 调用
```

## Windows 侧

1. 克隆仓库：
   ```bash
   git clone git@github.com:RichLi4307/pi-dashboard-mcp.git
   ```
2. 使用 VS Code 或 PyCharm 编辑
3. 本地可用 mock 数据跑单元测试
4. `git push`

## 树莓派侧

1. 拉取代码：
   ```bash
   cd ~/pi-dashboard-mcp
   git pull
   ```
2. 同步运行配置（如果 compose.yml 模板有变）：
   ```bash
   cp compose.yml deploy/docker-compose.yml
   ```
3. 构建并启动：
   ```bash
   docker compose -f deploy/docker-compose.yml up -d --build
   ```
4. 查看日志：
   ```bash
   docker logs -f pi-dashboard-mcp
   ```
5. 在 AstrBot 中测试 Tools

## 回滚

```bash
docker compose -f deploy/docker-compose.yml down
sudo systemctl disable --now pi-dashboard-mcp.service
# 从 nftables 移除 18473 规则
# 从 ~/astrbot/data/mcp_server.json 移除 pi-dashboard server
```
