import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
DB_PATH = ROOT / CONFIG["mcp_servers"]["ops"]["env"]["OPS_DB"].replace("{root}/", "")

ENGINEERS = [
    ("Sara Chen",     "schen",    "sara@example.com",  "US", "America/Los_Angeles"),
    ("Marco Rossi",   "marco-r",  "marco@example.com", "IT", "Europe/Rome"),
    ("Priya Patel",   "priya-p",  "priya@example.com", "IN", "Asia/Kolkata"),
    ("Felix Mueller", "fmueller", "felix@example.com", "DE", "Europe/Berlin"),
    ("Yuki Tanaka",   "ytanaka",  "yuki@example.com",  "JP", "Asia/Tokyo"),
]

ISSUE_TITLES = [
    ("API gateway returns 502 under load",         "P1"),
    ("Memory leak in ingestion worker",             "P1"),
    ("Database failover does not promote replica",  "P0"),
    ("Auth token refresh fails for SSO users",      "P1"),
    ("Disk usage alert on log-archive node",        "P2"),
    ("Stale data shown on dashboard for 5+ min",    "P1"),
    ("Slow query on customer search endpoint",      "P2"),
    ("Webhook delivery retries not exponential",    "P2"),
    ("CSV export truncates rows over 10k",          "P1"),
    ("OAuth callback rejects valid state token",    "P1"),
    ("Background job stuck in 'running' state",     "P2"),
    ("Rate limiter counts cached responses",        "P3"),
]


def seed() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    random.seed(42)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript("""
            CREATE TABLE engineers (
                engineer_id   INTEGER PRIMARY KEY,
                name          TEXT NOT NULL,
                github_login  TEXT NOT NULL UNIQUE,
                email         TEXT NOT NULL,
                country_code  TEXT NOT NULL,
                timezone      TEXT NOT NULL
            );
            CREATE TABLE rotations (
                engineer_id INTEGER NOT NULL,
                starts_at   TEXT NOT NULL,
                ends_at     TEXT NOT NULL,
                FOREIGN KEY (engineer_id) REFERENCES engineers(engineer_id)
            );
            CREATE INDEX idx_rotations_window ON rotations (starts_at, ends_at);
            CREATE TABLE issues (
                issue_id    INTEGER PRIMARY KEY,
                title       TEXT NOT NULL,
                priority    TEXT NOT NULL,
                status      TEXT NOT NULL,
                assignee_id INTEGER,
                opened_at   TEXT NOT NULL,
                FOREIGN KEY (assignee_id) REFERENCES engineers(engineer_id)
            );
        """)
        conn.executemany(
            "INSERT INTO engineers (name, github_login, email, country_code, timezone) "
            "VALUES (?, ?, ?, ?, ?)",
            ENGINEERS,
        )
        now = datetime.now(timezone.utc).replace(microsecond=0)
        monday = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0
        )
        rota_rows = []
        for week in range(-2, 8):
            start = monday + timedelta(weeks=week)
            end = start + timedelta(weeks=1)
            engineer_id = (week % len(ENGINEERS)) + 1
            rota_rows.append((engineer_id, start.isoformat(), end.isoformat()))
        conn.executemany("INSERT INTO rotations VALUES (?, ?, ?)", rota_rows)
        issue_rows = []
        for i, (title, priority) in enumerate(ISSUE_TITLES, start=1):
            assignee_id = random.randint(1, len(ENGINEERS))
            opened_at = (now - timedelta(hours=random.randint(2, 240))).isoformat()
            issue_rows.append((i, title, priority, "open", assignee_id, opened_at))
        conn.executemany(
            "INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?)", issue_rows
        )
        conn.commit()
    print(
        f"数据库初始化完成 {DB_PATH}：{len(ENGINEERS)} 名工程师，"
        f"{len(rota_rows)} 个轮班周期，{len(issue_rows)} 条开放问题。"
    )


if __name__ == "__main__":
    seed()
