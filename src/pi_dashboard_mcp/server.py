"""MCP Server entrypoint for Pi Dashboard integration."""

from __future__ import annotations

import os

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Mount, Route

from .tools import list_tools, call_tool

app = Server("pi-dashboard-mcp")
sse = SseServerTransport(
    "/messages",
    security_settings=TransportSecuritySettings(
        allowed_hosts=[
            "127.0.0.1",
            "127.0.0.1:*",
            "localhost",
            "localhost:*",
            "pi-dashboard-mcp",
            "pi-dashboard-mcp:*",
            "100.118.236.1",
            "100.118.236.1:*",
        ]
    ),
)


@app.list_tools()
async def handle_list_tools() -> list:
    return list_tools()


@app.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list:
    return await call_tool(name, arguments)


class SseAsgi:
    async def __call__(self, scope, receive, send):
        async with sse.connect_sse(scope, receive, send) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())


async def health(request):
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("pi-dashboard-mcp ok")


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=SseAsgi()),
        Mount("/messages", app=sse.handle_post_message),
        Route("/health", health),
    ]
)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MCP_PORT", "18473"))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
