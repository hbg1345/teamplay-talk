"""P0 검증: HTTP로 ``tools/list`` 를 무인증 호출해 본다.

사용법: 서버를 먼저 띄운 뒤
    python scripts/smoke.py
"""

from __future__ import annotations

import asyncio
import os

from fastmcp import Client

URL = os.getenv("MCP_URL", "http://127.0.0.1:8000/mcp/")


async def main() -> None:
    async with Client(URL) as client:
        tools = await client.list_tools()
        names = [t.name for t in tools]
        print(f"connected: {URL}")
        print(f"tools/list ({len(names)}): {names}")
        result = await client.call_tool("teamplay_ping", {})
        print(f"teamplay_ping -> {result.data!r}")


if __name__ == "__main__":
    asyncio.run(main())
