❯ 现在有新的需求，我在 skills/ecom-details-image 增加了skill，
  请问怎样才能整合在本系统，让系统能够识别和运行这个新skill，请你先整理方案写给我检查

● 我先看看新的技能包含什么。

  Searched for 1 pattern, read 7 files (ctrl+o to expand)

● 现在我对新的 skill 有了全面的了解。让我阅读当前的编排器和 config，以了解集成点。

  Read 2 files (ctrl+o to expand)

● 分析完成。以下是整合方案：

  ---
  整合方案：将 ecom-details-image Skill 接入系统

  核心问题

  当前编排器只支持一种工具机制——MCP Server 暴露的工具（通过 Anthropic tool_use 协议调用）。但 ecom-details-image skill
  需要的能力不同：

  ┌──────────────────────────┬───────────────────────────────────────────────────────┬─────────────────────────────┐
  │           能力           │                 oncall_holiday_check                  │     ecom-details-image      │
  ├──────────────────────────┼───────────────────────────────────────────────────────┼─────────────────────────────┤
  │ MCP 工具调用             │ get_current_oncall, is_public_holiday,                │ 无                          │
  │                          │ list_open_issues                                      │                             │
  ├──────────────────────────┼───────────────────────────────────────────────────────┼─────────────────────────────┤
  │ 读取本地文件（模板       │ 不需要                                                │ 需要，25 个场景模板         │
  │ JSON）                   │                                                       │                             │
  ├──────────────────────────┼───────────────────────────────────────────────────────┼─────────────────────────────┤
  │ 执行外部脚本（生图）     │ 不需要                                                │ 需要，调用                  │
  │                          │                                                       │ generate_image.py           │
  └──────────────────────────┴───────────────────────────────────────────────────────┴─────────────────────────────┘

  方案：为 ecom skill 新建一个 MCP Server

  创建 mcp_servers/ecom_image_server.py，把 skill 需要的能力包装成 MCP 工具：

  ┌─────────────────────────────────────────────────────────────┬───────────────────────────────────────┐
  │                           工具名                            │                 作用                  │
  ├─────────────────────────────────────────────────────────────┼───────────────────────────────────────┤
  │ list_templates()                                            │ 列出 25 个场景模板的名称和触发词      │
  ├─────────────────────────────────────────────────────────────┼───────────────────────────────────────┤
  │ find_template(keywords)                                     │ 根据关键词匹配最佳模板，返回完整 JSON │
  ├─────────────────────────────────────────────────────────────┼───────────────────────────────────────┤
  │ read_template(template_file)                                │ 读取指定模板文件内容                  │
  ├─────────────────────────────────────────────────────────────┼───────────────────────────────────────┤
  │ generate_image(prompt, size, resolution, image, output_dir) │ 包装 scripts/generate_image.py 的调用 │
  └─────────────────────────────────────────────────────────────┴───────────────────────────────────────┘

  具体改动

  1. 新增 mcp_servers/ecom_image_server.py — 电商图片 MCP Server
  2. 新增 configs/ecom-image.json — 电商图片专用配置，指向新 MCP Server 和 ecom SKILL.md
  3. 微调 orchestrator.py — 增加 --skill 快捷参数，自动切换 config
  4. 不动 任何现有文件 — oncall_holiday_check 完全不受影响

  运行方式

  # 原有值班检查（不变）
  python orchestrator.py

  # 新的电商图片（通过 --config 切换）
  python orchestrator.py --config configs/ecom-image.json "帮我生成一个白色充电宝的白底主图"

  # 或通过快捷方式（加上 --skill 参数后自动选 config）
  python orchestrator.py --skill ecom "帮我生成一个白色充电宝的白底主图"

  技术细节

  - ecom_image_server.py 内部调用 subprocess.run 执行 scripts/generate_image.py，把异步轮询的生图过程封装成一个同步 MCP
  工具
  - 模板匹配逻辑直接在 MCP Server 内完成，LLM 只需调用 find_template 传入用户描述的关键词
  - ecom skill 的 .env（IMG_API_KEY 等）通过 config.json 的 env 字段注入给 MCP Server 子进程

  ---



  ● 全部完成，两个 Skill 测试均通过。

  测试结果

  ┌────────────────────┬──────────────────────────────────────────────────────┬─────────────────────────────────────┐
  │       Skill        │                         命令                         │                结果                 │
  ├────────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ oncall（值班检查） │ python orchestrator.py --skill oncall                │ Sara Chen(US) 非假日，列出 2 条 P1  │
  │                    │                                                      │ 问题                                │
  ├────────────────────┼──────────────────────────────────────────────────────┼─────────────────────────────────────┤
  │ ecom（电商图片）   │ python orchestrator.py --skill ecom                  │ 自动匹配 hero-image 模板，输出完整  │
  │                    │ "帮我为自发热眼罩生成白底主图 Prompt"                │ Visual Brief + Prompt               │
  └────────────────────┴──────────────────────────────────────────────────────┴─────────────────────────────────────┘

  新增/修改文件

  - 新增 mcp_servers/ecom_image_server.py — 4 个 MCP 工具：list_templates、find_template、read_template、generate_image
  - 新增 configs/ecom-image.json — ecom skill 专用配置
  - 修改 orchestrator.py — 增加 --skill 参数快捷切换，支持 project_root 字段解决子目录 config 的路径问题