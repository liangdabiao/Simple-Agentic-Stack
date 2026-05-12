# Agentic Stack - 本地 AI Agent 系统

基于 MCP（Model Context Protocol）和 Skill 驱动的 AI Agent 编排系统。LLM 通过自然语言编写的 Skill 按步骤调用 MCP Server 提供的工具，完成复杂的多数据源联动任务。

> 传统编程和 LLM Agent 系统之间的对应关系：**Skill 是程序，MCP 是库，LLM 是语言**。

## 以下是参考资料：
在本地跑一个完整 AI Agent 系统：Ollama、MCP 和 Skill 到底怎么串起来，
https://mp.weixin.qq.com/s/1mZjxN5jb8FGYTS5gQlb8w

## 系统架构

```
orchestrator.py (编排器)
    │
    ├── DeepSeek API (LLM 运行时，Anthropic 兼容接口)
    │
    ├── skills/oncall_holiday_check.md (Skill - 自然语言"程序")
    │
    └── MCP Servers (工具库)
        ├── holidays_server.py → date.nager.at 公共假日 API
        └── ops_server.py      → 本地 SQLite 运维数据库
```

## 演示场景

**值班假日检查**：判断当前值班工程师所在国家今天是否有公共假日，若有则列出其名下的高优先级问题，以便安排备班人员。

示例输出：

```
=== 最终回答 ===

值班正常：Sara Chen（美国），今天是正常工作日。其名下的 P1 问题如下：
- #4 Auth token refresh fails for SSO users
- #1 API gateway returns 502 under load
```

## 项目结构

```
skill-mcp/
├── .env                          # API 密钥和模型配置（不入库）
├── config.json                   # 全局配置：模型、MCP Server、Skill 路径
├── requirements.txt              # Python 依赖
├── orchestrator.py               # 编排器：连接 LLM、MCP Server、Skill
├── seed_db.py                    # 生成 SQLite 测试数据
├── server_test.py                # MCP Server 独立测试脚本
├── ops.db                        # 自动生成的数据库（运行 seed_db.py 后生成）
├── mcp_servers/
│   ├── holidays_server.py        # 外部 API 包装型 MCP Server
│   └── ops_server.py             # 纯本地型 MCP Server（SQLite）
└── skills/
    └── oncall_holiday_check.md   # 值班假日检查 Skill
```

## 快速开始

### 1. 环境准备

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API 密钥

复制示例文件并填入你的 API 密钥：

```bash
cp .env.example .env
```

`.env` 文件内容：

```env
ANTHROPIC_AUTH_TOKEN=your-api-key-here
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
MODEL=deepseek-v4-flash
```

本项目使用 DeepSeek API 的 Anthropic 兼容接口，也支持任何兼容 Anthropic Messages API 的服务端点（如 OpenRouter、自部署 vLLM 等）。

### 3. 初始化数据库

```bash
python seed_db.py
```

生成包含 5 名工程师（分布在美国、意大利、印度、德国、日本）、10 个轮班周期、12 条开放问题的测试数据库。

### 4. 运行

```bash
# 使用默认问题
python orchestrator.py

# 指定问题
python orchestrator.py "本周谁在值班？他们有没有 P0 问题？"
```

## 各组件说明

### MCP Server：工具库

每个 MCP Server 通过 `@mcp.tool()` 装饰器暴露工具接口。模型只能看到函数名、docstring 和类型注解——这就是工具的"语义契约"。

- **holidays_server.py** — 对外封装 [date.nager.at](https://date.nager.at) 公共假日 API，提供 `is_public_holiday` 和 `list_country_holidays` 两个工具。
- **ops_server.py** — 直接查询本地 SQLite 数据库，提供 `get_current_oncall`、`list_open_issues`、`get_engineer`、`list_engineers` 四个工具。

### Skill：自然语言程序

Skill 不是普通 prompt，而是用自然语言编写的带执行逻辑的程序，明确告诉模型按什么步骤组合哪些工具。包含三部分：

1. **目的** — 这个 Skill 做什么
2. **可用工具** — 列出所有工具，标注主流程是否需要
3. **执行步骤 + 约束** — 明确的执行顺序、输出模板和硬约束

### 编排器：串联一切

`orchestrator.py` 是整套系统的胶水层：

1. 读取 `config.json`，将每个 MCP Server 作为子进程拉起
2. 收集所有工具定义，转换为 Anthropic tool schema
3. 将 Skill 注入 system prompt
4. 运行工具调用循环，直到模型给出最终回答

编排器对任何具体的 MCP Server 和 Skill 一无所知——`config.json` 才是真正的程序入口。

### 配置文件

`config.json` 管理所有可变部分：

```json
{
  "model": "deepseek-v4-flash",
  "api_base_url": "https://api.deepseek.com/anthropic",
  "max_steps": 10,
  "skill_path": "skills/oncall_holiday_check.md",
  "default_question": "当前值班工程师所在国家今天是否有公共假日？...",
  "mcp_servers": {
    "holidays": {
      "script": "mcp_servers/holidays_server.py",
      "env": { "HOLIDAY_API_BASE": "https://date.nager.at/api/v3" }
    },
    "ops": {
      "script": "mcp_servers/ops_server.py",
      "env": { "OPS_DB": "{root}/ops.db" }
    }
  }
}
```

- `max_steps` — 限制工具调用最大轮次
- `skill_path` — 换个路径就是换个任务
- `mcp_servers` — 每个条目包含脚本路径和环境变量，`{root}` 自动展开为项目根目录

想换一套完全不同的任务？改 `skill_path`、换掉 `mcp_servers` 里的条目，一行 Python 都不用动。

## 测试

单独验证 MCP Server 是否正常：

```bash
# 测试假日查询 Server
python server_test.py

# 测试运维数据库 Server（需先 seed_db.py）
OPS_DB=./ops.db python server_test.py
```

## 技术栈

| 层 | 技术 | 作用 |
|---|---|---|
| LLM 运行时 | DeepSeek API（Anthropic 兼容接口） | 理解指令、调用工具、生成回答 |
| 工具库 | MCP Server（FastMCP） | 标准化工具接口，模型通过语义契约调用 |
| 程序逻辑 | Markdown Skill | 自然语言编写的执行步骤和约束 |
| 编排器 | Python + Anthropic SDK | 串联 LLM、MCP、Skill，驱动工具调用循环 |

## 依赖

- `mcp[cli]>=1.10` — MCP Server/Client 框架
- `anthropic>=0.40` — Anthropic SDK（用于调用兼容 API）
- `httpx>=0.27` — 异步 HTTP 客户端
- `python-dotenv>=1.0` — 环境变量管理

## 扩展

- **加新工具**：在 `mcp_servers/` 下新建 Server，在 `config.json` 的 `mcp_servers` 中加一条
- **换任务**：写新 Skill，改 `config.json` 的 `skill_path`
- **换模型**：改 `.env` 中的 `MODEL` 和 `ANTHROPIC_BASE_URL`
- **换 LLM 提供商**：任何兼容 Anthropic Messages API 的服务都可直接替换

## License

MIT
