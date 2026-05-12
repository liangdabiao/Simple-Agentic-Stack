# 值班假日检查

## 目的
判断当前值班工程师所在国家今天是否有公共假日，若有，列出其名下
待处理的高优先级问题，以便安排备班人员。

## 可用工具
- `get_current_oncall()` — 返回当前值班工程师，包含 `engineer_id`、
  `name`、`country_code` 等字段。可能返回 `error` 键。
- `is_public_holiday(country_code, on_date)` — 返回
  `{is_holiday: bool, holiday_name?: str, holiday_local_name?: str}`
  或 `{error: str}`。`on_date` 格式须为 YYYY-MM-DD。
- `list_open_issues(priority, assignee_id)` — 返回开放问题列表，
  两个参数均为可选过滤条件。
- `get_engineer(github_login)` — 按 GitHub 账号查找工程师。
  主流程不需要此工具。
- `list_engineers()` — 列出所有工程师。主流程不需要此工具。
- `list_country_holidays(country_code, year)` — 列出某国某年全部假日。
  主流程不需要此工具。

## 执行步骤

今天的日期已在系统上下文中提供。

1. 调用 `get_current_oncall()`。若返回 error，回复
   "当前没有工程师在值班。"并停止。
2. 调用一次 `is_public_holiday(country_code, on_date)`，传入
   值班工程师的 `country_code` 和今天的日期。
3. 调用一次 `list_open_issues(priority=<问题中指定的优先级>,
   assignee_id=<id>)`，传入值班工程师的 `engineer_id`。
   若问题未指定优先级，省略该过滤条件，返回所有开放问题。
4. 组织一段简短的最终回答：
   - 若 `is_holiday` 为 true：以 "需要升级：" 开头，说明工程师姓名、
     所在国家和假日名称，然后将其每条对应优先级的开放问题单独列为
     一行，格式为 `#<issue_id> <标题>`。若该优先级下没有问题，
     请明确说明。
   - 若 `is_holiday` 为 false：以 "值班正常：" 开头，说明工程师姓名、
     所在国家和今天是正常工作日，问题列表格式相同。

## 约束
- 不得自行编造工程师、问题、假日或任何数据，只能使用工具返回的内容。
- 三个必要工具各调用一次，不循环、不重试。
- 最终回答保持简洁，无需前言，无需总结。
