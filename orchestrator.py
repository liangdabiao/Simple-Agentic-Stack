import argparse
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config.json"

load_dotenv(ROOT / ".env", override=True)


def load_config(config_path: Path) -> dict:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg["_root"] = config_path.resolve().parent
    return cfg


def env_for_server(server_cfg: dict, root: Path) -> dict[str, str]:
    base = os.environ.copy()
    for k, v in server_cfg.get("env", {}).items():
        base[k] = v.replace("{root}", str(root))
    return base


def mcp_to_anthropic_tool(tool) -> dict:
    schema = dict(tool.inputSchema)
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": schema,
    }


def trace(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def run(question: str, cfg: dict) -> None:
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", cfg.get("api_base_url", ""))
    model = os.environ.get("MODEL", cfg.get("model", ""))

    async with AsyncExitStack() as stack:
        sessions: dict[str, ClientSession] = {}
        tool_owner: dict[str, str] = {}
        anthropic_tools: list[dict] = []

        for server_name, server_cfg in cfg["mcp_servers"].items():
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(cfg["_root"] / server_cfg["script"])],
                env=env_for_server(server_cfg, cfg["_root"]),
            )
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            sessions[server_name] = session

            listed = await session.list_tools()
            for t in listed.tools:
                if t.name in tool_owner:
                    raise RuntimeError(f"工具名冲突：{t.name}")
                tool_owner[t.name] = server_name
                anthropic_tools.append(mcp_to_anthropic_tool(t))
                trace(f"[注册] {server_name}.{t.name}")

        skill = (cfg["_root"] / cfg["skill_path"]).read_text(encoding="utf-8")
        system = (
            f"今天的日期是 {date.today().isoformat()}。\n\n"
            f"你可以使用以下 Skill，请严格按照其步骤执行。\n\n"
            f"---\n{skill}\n---"
        )

        client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url)

        messages = [
            {"role": "user", "content": question},
        ]

        for step in range(cfg["max_steps"]):
            response = await client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                messages=messages,
                tools=anthropic_tools,
            )

            # Collect assistant content blocks
            text_parts = []
            tool_use_blocks = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    tool_use_blocks.append(block)

            # Build assistant message for history
            messages.append({"role": "assistant", "content": response.content})

            if not tool_use_blocks:
                print("\n=== 最终回答 ===\n")
                print("\n".join(text_parts) or "(空)")
                return

            # Execute each tool call
            tool_results = []
            for call in tool_use_blocks:
                name = call.name
                args = call.input if isinstance(call.input, dict) else {}
                call_id = call.id

                owner = tool_owner.get(name)
                if owner is None:
                    result_text = json.dumps({"error": f"未知工具 {name}"}, ensure_ascii=False)
                    trace(f"[第{step}步] -> ?? {name}({args}) [未知工具]")
                else:
                    trace(f"[第{step}步] -> {owner}.{name}({args})")
                    result = await sessions[owner].call_tool(name, args)
                    chunks = [c.text for c in result.content if hasattr(c, "text")]
                    result_text = "\n".join(chunks) if chunks else "{}"
                    preview = result_text.replace("\n", " ")[:160]
                    trace(f"[第{step}步] <- {preview}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "content": result_text,
                })

            messages.append({"role": "user", "content": tool_results})

        trace(f"[中止] 已达最大步数 max_steps={cfg['max_steps']}，未能得到最终回答")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="按 Skill 驱动 MCP Server 回答问题。")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="配置文件路径（默认：脚本同目录下的 config.json）。",
    )
    parser.add_argument(
        "question", nargs="*",
        help="要提问的内容，不传则使用 config 里的 default_question。",
    )
    args = parser.parse_args()

    cfg = load_config(args.config.resolve())
    question = " ".join(args.question) or cfg["default_question"]
    asyncio.run(run(question, cfg))
