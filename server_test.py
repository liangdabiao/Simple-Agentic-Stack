import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent


async def main(server_script: Path, tool_name: str, arguments: dict) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            print("服务器暴露的工具列表：")
            for t in listed.tools:
                first_line = (t.description or "").splitlines()[0]
                print(f"  - {t.name}: {first_line}")
            print(f"\n正在调用 {tool_name}({arguments})：")
            result = await session.call_tool(tool_name, arguments=arguments)
            for chunk in result.content:
                if hasattr(chunk, "text"):
                    print(chunk.text)


if __name__ == "__main__":
    asyncio.run(main(
        server_script=ROOT / "mcp_servers" / "holidays_server.py",
        tool_name="is_public_holiday",
        arguments={"country_code": "IT", "on_date": "2026-04-25"},
    ))
