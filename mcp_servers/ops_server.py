import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(os.environ.get("OPS_DB", "ops.db")).resolve()
mcp = FastMCP("ops")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def get_current_oncall() -> dict:
    """返回当前值班工程师信息。
    返回：
        包含 engineer_id、name、github_login、email、country_code、timezone
        以及当前轮班的 starts_at、ends_at 的字典。若当前无人值班，
        返回含 'error' 键的字典。
    """
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT e.engineer_id, e.name, e.github_login, e.email,
                   e.country_code, e.timezone,
                   r.starts_at, r.ends_at
            FROM rotations r
            JOIN engineers e ON e.engineer_id = r.engineer_id
            WHERE r.starts_at <= ? AND r.ends_at > ?
            LIMIT 1
            """,
            (now, now),
        ).fetchone()
    if not row:
        return {"error": "当前没有工程师在值班。"}
    return dict(row)


@mcp.tool()
def list_open_issues(
    priority: str | None = None,
    assignee_id: int | None = None,
) -> list[dict]:
    """列出开放状态的问题，可按优先级和/或负责人过滤。
    参数：
        priority: 'P0'、'P1'、'P2'、'P3' 之一，不传则返回所有优先级。
        assignee_id: 按工程师 ID 过滤，不传则返回所有人的问题。
    返回：
        包含 issue_id、title、priority、assignee_id、opened_at 的字典列表。
        无匹配时返回空列表。
    """
    clauses = ["status = 'open'"]
    params: list = []
    if priority:
        clauses.append("priority = ?")
        params.append(priority)
    if assignee_id is not None:
        clauses.append("assignee_id = ?")
        params.append(assignee_id)
    sql = (
        "SELECT issue_id, title, priority, assignee_id, opened_at "
        "FROM issues WHERE " + " AND ".join(clauses) +
        " ORDER BY opened_at"
    )
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


@mcp.tool()
def get_engineer(github_login: str) -> dict:
    """通过 GitHub 账号查找工程师。
    参数：
        github_login: GitHub 用户名。
    返回：
        完整的工程师记录，找不到时返回含 'error' 键的字典。
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT engineer_id, name, github_login, email, country_code, "
            "timezone FROM engineers WHERE github_login = ?",
            (github_login,),
        ).fetchone()
    return dict(row) if row else {"error": f"未找到工程师 {github_login}"}


@mcp.tool()
def list_engineers() -> list[dict]:
    """列出所有工程师。"""
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM engineers").fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    mcp.run(transport="stdio")
