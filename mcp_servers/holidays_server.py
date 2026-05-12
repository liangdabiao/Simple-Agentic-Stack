import os
from datetime import date as date_cls
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("holidays")
API_BASE = os.environ.get("HOLIDAY_API_BASE", "https://date.nager.at/api/v3")
USER_AGENT = "agentic-stack-demo/1.0"


@mcp.tool()
async def is_public_holiday(country_code: str, on_date: str) -> dict[str, Any]:
    """查询某个日期在指定国家是否为公共假日。
    参数：
        country_code: ISO 3166-1 二位字母国家代码，例如 'US'、'IT'、'JP'。
        on_date: 日期字符串，格式为 YYYY-MM-DD。
    返回：
        包含 'is_holiday'（布尔值）的字典；若为假日，还会包含 'holiday_name'
        和 'holiday_local_name'。出错时返回含 'error' 键的字典。
    """
    try:
        target = date_cls.fromisoformat(on_date)
    except ValueError:
        return {"error": "on_date 格式须为 YYYY-MM-DD"}
    if len(country_code) != 2:
        return {"error": "country_code 须为两位 ISO 国家代码"}
    url = f"{API_BASE}/PublicHolidays/{target.year}/{country_code.upper()}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return {"error": f"未知国家代码 {country_code!r}"}
            resp.raise_for_status()
            holidays = resp.json()
    except httpx.HTTPError as e:
        return {"error": f"假日 API 请求失败：{e}"}
    iso = target.isoformat()
    for h in holidays:
        if h.get("date") == iso:
            return {
                "is_holiday": True,
                "holiday_name": h.get("name"),
                "holiday_local_name": h.get("localName"),
            }
    return {"is_holiday": False}


@mcp.tool()
async def list_country_holidays(country_code: str, year: int) -> list[dict[str, Any]]:
    """列出指定国家某年的所有公共假日。
    参数：
        country_code: ISO 3166-1 二位字母国家代码。
        year: 四位年份，例如 2026。
    返回：
        包含 'date'、'name'、'local_name' 的字典列表。出错时返回单元素列表，
        其中含 'error' 键。
    """
    if len(country_code) != 2:
        return [{"error": "country_code 须为两位 ISO 国家代码"}]
    url = f"{API_BASE}/PublicHolidays/{year}/{country_code.upper()}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 404:
                return [{"error": f"未知国家代码 {country_code!r}"}]
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        return [{"error": f"假日 API 请求失败：{e}"}]
    return [
        {"date": h["date"], "name": h["name"], "local_name": h.get("localName")}
        for h in data
    ]


if __name__ == "__main__":
    mcp.run(transport="stdio")
