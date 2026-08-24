FROM python:3.11-slim

WORKDIR /app

# Keep image minimal; docker queries use the Python SDK over docker.sock.
RUN apt-get update && apt-get install -y --no-install-recommends \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/
COPY src /app/src

# 预装构建依赖，避免清华 PyPI 镜像缺少 setuptools 时构建失败
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ setuptools wheel \
    && pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -e /app

ENV PYTHONUNBUFFERED=1
ENV MCP_PORT=18473

EXPOSE 18473

CMD ["python", "-u", "-m", "pi_dashboard_mcp.server"]
