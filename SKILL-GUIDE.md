# Skill 使用指南

本文档说明 Skill 系统的工作原理、使用流程，以及如何为系统编写和接入新的 Skill。

---

## 一、核心概念

### 什么是 Skill

Skill 是用自然语言（Markdown）编写的**程序**。它明确定义了 LLM 应该怎么一步步组合工具来完成一个任务。类比传统编程：

| 传统编程 | Agent 系统 | 本项目对应物 |
|---|---|---|
| 程序（代码） | Skill（Markdown） | `skills/oncall_holiday_check.md` |
| 库（Library） | MCP Server（Python） | `mcp_servers/ops_server.py` |
| 语言运行时 | LLM | DeepSeek API |
| 入口配置 | config.json | `config.json` / `configs/ecom-image.json` |

### 系统分层架构

```
用户提问
   ↓
orchestrator.py（编排器）
   ↓
   ├── 读取 config.json → 找到 Skill 文件 + MCP Server 列表
   ├── 加载 Skill（.md）→ 注入 system prompt
   ├── 启动 MCP Server 子进程 → 收集工具定义 → 转为 LLM 可用的 tool schema
   └── 工具调用循环：
       LLM 决定调用哪个工具 → 编排器路由到对应 MCP Server → 返回结果 → LLM 继续
       直到 LLM 不再调用工具，输出最终回答
```

### 三个核心角色

1. **Skill（程序）**：告诉 LLM "按什么步骤、用什么工具、遵守什么约束"。LLM 是执行者，Skill 是指令。
2. **MCP Server（工具库）**：通过 `@mcp.tool()` 装饰器暴露工具。每个工具就是一个函数，函数名 + docstring + 类型注解构成"语义契约"——LLM 只能看到这些，看不到函数体。
3. **编排器（胶水层）**：对任何具体的 Skill 和 MCP Server 一无所知。它只负责加载配置、启动进程、转发工具调用。`config.json` 才是真正的程序入口。

---

## 二、运行流程详解

以 `python orchestrator.py --skill oncall` 为例，完整执行链路如下：

### 第 1 步：加载配置

```
orchestrator.py --skill oncall
    ↓
SKILL_CONFIGS["oncall"] → config.json
    ↓
load_config() 解析 JSON：
  - model: "deepseek-v4-flash"
  - skill_path: "skills/oncall_holiday_check.md"
  - mcp_servers: { holidays: {...}, ops: {...} }
  - _root: 项目根目录
```

### 第 2 步：启动 MCP Server

编排器为 `mcp_servers` 中的每个条目启动一个子进程：

```
StdioServerParameters(
    command=sys.executable,
    args=["mcp_servers/holidays_server.py"],
    env={ HOLIDAY_API_BASE: "https://date.nager.at/api/v3" }
)
    ↓ stdio 双向通信
ClientSession.initialize()
    ↓
session.list_tools() → 收集工具名、描述、参数 schema
```

stderr 输出可见注册过程：
```
[注册] holidays.is_public_holiday
[注册] holidays.list_country_holidays
[注册] ops.get_current_oncall
[注册] ops.list_open_issues
[注册] ops.get_engineer
[注册] ops.list_engineers
```

### 第 3 步：注入 Skill + 启动循环

编排器把 Skill 全文注入 system prompt，附加当天日期：

```
system = "今天的日期是 2026-05-12。\n\n你可以使用以下 Skill，请严格按照其步骤执行。\n\n---\n{Skill全文}\n---"
```

然后进入工具调用循环（最多 `max_steps` 轮）：

```
for step in range(max_steps):
    response = llm.chat(messages, tools=anthropic_tools)

    if 没有 tool_use:
        输出最终回答，结束

    for each tool_call:
        1. 查路由表 tool_owner → 找到对应的 MCP Server session
        2. session.call_tool(name, args) → 执行工具
        3. 把结果追加到 messages
```

### 第 4 步：LLM 按 Skill 执行

LLM 根据 Skill 中的步骤依次调用工具：

```
[第0步] → ops.get_current_oncall({})
[第0步] ← {"engineer_id": 1, "name": "Sara Chen", "country_code": "US", ...}

[第1步] → holidays.is_public_holiday({"country_code": "US", "on_date": "2026-05-12"})
[第1步] ← {"is_holiday": false}

[第2步] → ops.list_open_issues({"priority": "P1", "assignee_id": 1})
[第2步] ← [{"issue_id": 4, ...}, {"issue_id": 1, ...}]

→ 不再调用工具，输出最终回答
```

---

## 三、已接入的 Skill

### Skill 1：值班假日检查

| 项目 | 内容 |
|---|---|
| 配置 | `config.json`（默认） |
| Skill 文件 | `skills/oncall_holiday_check.md` |
| MCP Server | `holidays`（假日 API）+ `ops`（运维数据库） |
| 运行 | `python orchestrator.py` 或 `--skill oncall` |
| 工具数 | 6 个（必要 3 个 + 辅助 3 个） |
| 用途 | 检查当前值班工程师所在国家是否假日，列出其高优先级问题 |

### Skill 2：电商图片生成

| 项目 | 内容 |
|---|---|
| 配置 | `configs/ecom-image.json` |
| Skill 文件 | `skills/ecom-details-image/SKILL.md` |
| MCP Server | `ecom`（模板匹配 + 图片生成） |
| 运行 | `python orchestrator.py --skill ecom` |
| 工具数 | 4 个（list_templates, find_template, read_template, generate_image） |
| 用途 | 根据产品描述生成电商主图、详情页图片的 Prompt 或直接出图 |
| 附加资源 | 25 个场景模板（`references/templates/`）+ 生图脚本（`scripts/generate_image.py`） |

---

## 四、操作指南

### 4.1 运行现有 Skill

```bash
# 运行值班检查（默认 Skill）
python orchestrator.py

# 快捷方式：通过 --skill 切换
python orchestrator.py --skill oncall
python orchestrator.py --skill ecom

# 指定自定义问题
python orchestrator.py --skill oncall "本周谁在值班？有没有 P0 问题？"
python orchestrator.py --skill ecom "帮我为蓝牙耳机生成一张白底主图"

# 直接指定配置文件路径
python orchestrator.py --config configs/ecom-image.json "生成小红书种草图"

# 不传问题则使用 config 中的 default_question
python orchestrator.py --skill ecom
```

### 4.2 查看执行过程

编排器把每一步工具调用打印到 stderr，stdout 只输出最终回答：

```bash
# 同时看 trace 和回答
python orchestrator.py --skill oncall 2>&1

# 只看最终回答（重定向 stderr）
python orchestrator.py --skill oncall 2>/dev/null

# 只看 trace（重定向 stdout）
python orchestrator.py --skill oncall 1>/dev/null
```

### 4.3 测试单个 MCP Server

```bash
# 测试假日查询 Server
python server_test.py

# 测试运维数据库 Server（需先 seed_db.py）
# 修改 server_test.py 中的参数即可
```

---

## 五、如何编写新 Skill

### 5.1 最小 Skill 模板

一个 Skill 是一个 Markdown 文件，包含四个部分：

```markdown
# Skill 名称

## 目的
这个 Skill 要解决什么问题，一两句话说清楚。

## 可用工具
- `tool_name(param1, param2)` — 工具做什么，返回什么格式。
  可能返回 `error` 键。
- `another_tool()` — 另一个工具。
  主流程不需要此工具。

## 执行步骤

1. 调用 `tool_name(...)`。若返回 error，回复"xxx"并停止。
2. 根据上一步结果，调用 `another_tool(...)`。
3. 组织最终回答：
   - 若条件 A：以 "前缀A：" 开头，说明 xxx。
   - 若条件 B：以 "前缀B：" 开头，说明 xxx。

## 约束
- 不得自行编造数据，只能使用工具返回的内容。
- 必要工具各调用一次，不循环、不重试。
- 最终回答保持简洁，无需前言，无需总结。
```

### 5.2 编写要点

**工具声明要精确**：LLM 只能看到函数名、docstring 和类型注解。在 Skill 里要把每个工具的参数、返回格式、error 情况写清楚。

**执行步骤要线性**：写清楚"第 1 步做什么，第 2 步做什么"，不要用"视情况而定"这种模糊表述。分支用明确的条件判断（若 A 则 X，若 B 则 Y）。

**标注不需要的工具**：MCP Server 可能暴露多个工具，但某个 Skill 只用其中几个。明确标注"主流程不需要此工具"，防止 LLM 乱调用。

**输出模板要具体**：给出最终回答的格式（以什么开头、包含什么信息、每行格式），LLM 会严格遵循。

**约束要硬性**：不编造数据、不循环重试、回答要简洁——这些约束让 Skill 行为可预测、可复现。

### 5.3 配置文件结构

为每个 Skill 创建一个 config JSON。放在项目根目录或 `configs/` 下均可。

```json
{
  "project_root": "..",
  "model": "deepseek-v4-flash",
  "api_base_url": "https://api.deepseek.com/anthropic",
  "max_steps": 15,
  "skill_path": "skills/my-skill/SASKILL.md",
  "default_question": "默认提问内容",
  "mcp_servers": {
    "server_name": {
      "script": "mcp_servers/my_server.py",
      "env": {
        "MY_VAR": "{root}/some/path"
      }
    }
  }
}
```

各字段说明：

| 字段 | 说明 |
|---|---|
| `project_root` | 可选。config 文件到项目根目录的相对路径。config 在根目录时省略；在 `configs/` 子目录时填 `".."` |
| `model` | 默认模型名，会被 `.env` 中的 `MODEL` 覆盖 |
| `api_base_url` | 默认 API 地址，会被 `.env` 中的 `ANTHROPIC_BASE_URL` 覆盖 |
| `max_steps` | 工具调用最大轮次。简单任务 10 轮够用，复杂多图任务建议 20 |
| `skill_path` | Skill (.md) 文件相对于项目根目录的路径 |
| `default_question` | 命令行不传问题时的默认值 |
| `mcp_servers` | MCP Server 列表，每个条目包含 `script` 和 `env` |
| `mcp_servers.*.script` | MCP Server 脚本相对于项目根目录的路径 |
| `mcp_servers.*.env` | 注入给子进程的环境变量，`{root}` 自动展开为项目根目录绝对路径 |

### 5.4 注册到快捷方式

在 `orchestrator.py` 的 `SKILL_CONFIGS` 字典中添加条目：

```python
SKILL_CONFIGS = {
    "oncall": DEFAULT_CONFIG,
    "ecom": ROOT / "configs" / "ecom-image.json",
    "myskill": ROOT / "configs" / "my-skill.json",   # 新增
}
```

之后即可通过 `python orchestrator.py --skill myskill` 快捷运行。

---

## 六、如何编写新 MCP Server

MCP Server 是工具的容器。用 `FastMCP` 框架几行代码就能写一个：

```python
import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my_server")

@mcp.tool()
def my_tool(param1: str, param2: int = 10) -> dict:
    """工具描述——LLM 会看到这段文字。
    参数：
        param1: 参数说明。
        param2: 可选参数，默认 10。
    返回：
        包含 'result' 键的字典。出错时返回含 'error' 键的字典。
    """
    # 实际逻辑
    return {"result": "ok"}

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

### 关键规则

1. **用 `@mcp.tool()` 装饰器**：普通函数变成 MCP 工具。
2. **docstring 就是契约**：写清楚参数、返回值、error 情况。LLM 靠这个决定怎么调用。
3. **类型注解会变成 JSON Schema**：自动约束 LLM 生成的参数格式。
4. **错误返回结构化结果**：不要 raise，返回 `{"error": "说明"}`，LLM 能理解并处理。
5. **绝对不要 print 到 stdout**：stdout 是 MCP 协议通道，写入会导致 JSON-RPC 解析崩溃。调试用 `print(..., file=sys.stderr)` 或 `logging`。
6. **同步 vs 异步**：纯本地操作（SQLite、文件读写）用同步 `def`；网络 I/O（HTTP 请求）用 `async def`。FastMCP 两种都支持。

---

## 七、完整接入新 Skill 的工作流

假设你要接入一个新 Skill，完整步骤：

```
1. 编写 MCP Server
   └── mcp_servers/my_server.py（暴露工具）

2. 编写 Skill 文件
   └── skills/my-skill/my-skill.md（定义步骤和约束）

3. 创建配置文件
   └── configs/my-skill.json（关联 Skill + MCP Server）

4. 注册快捷方式（可选）
   └── orchestrator.py 的 SKILL_CONFIGS 字典加一条

5. 测试
   ├── 单独测试 MCP Server：python server_test.py
   └── 端到端测试：python orchestrator.py --skill myskill "测试问题"

6. 不需要改任何已有文件（除了 orchestrator.py 可选注册）
```

---

## 八、注意事项

### 环境变量优先级

`.env` 文件中的变量会**覆盖**系统环境变量（`load_dotenv(override=True)`）。读取顺序：

```
.env 文件 > 系统环境变量 > config.json 中的默认值
```

三个关键变量：

| 变量 | 来源 | 作用 |
|---|---|---|
| `ANTHROPIC_AUTH_TOKEN` | `.env` | API 密钥 |
| `ANTHROPIC_BASE_URL` | `.env` | API 地址 |
| `MODEL` | `.env` | 模型名 |

### MCP Server 的环境变量

每个 MCP Server 的环境变量通过 config.json 的 `env` 字段注入：

```json
"env": {
    "OPS_DB": "{root}/ops.db",
    "ECOM_SKILL_DIR": "{root}/skills/ecom-details-image"
}
```

`{root}` 会被自动替换为项目根目录的绝对路径。MCP Server 启动后通过 `os.environ.get()` 读取。

### 模型选择

不同 Skill 对模型能力的要求不同：

- **简单 Skill**（如值班检查，3 步线性流程）：小模型即可，`max_steps=10`
- **复杂 Skill**（如电商图片，多步决策 + 模板匹配）：需要较强的工具调用能力，`max_steps=20`

### 换模型 / 换 API 提供商

只改 `.env`，不用动任何代码：

```env
# 用 DeepSeek
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
MODEL=deepseek-v4-flash

# 或用 OpenRouter
ANTHROPIC_BASE_URL=https://openrouter.ai/api/anthropic
MODEL=anthropic/claude-sonnet-4-6

# 或用本地 vLLM（Anthropic 兼容模式）
ANTHROPIC_BASE_URL=http://localhost:8000/anthropic
MODEL=my-local-model
```

前提是目标 API 兼容 Anthropic Messages API 格式（包括 tool_use 协议）。
