import os
import sqlite3
import uuid
from datetime import datetime

import pandas as pd

DB_PATH = os.environ.get("RATA_DB_PATH") or (
    "/tmp/rata.db" if os.environ.get("SPACE_ID") else "rata.db"
)


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  deadline TEXT NOT NULL,
  owner TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS members (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT DEFAULT 'MEMBER'
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  estimate_hours REAL DEFAULT 2,
  priority TEXT DEFAULT 'MEDIUM',
  assignee_id TEXT,
  status TEXT DEFAULT 'TODO',
  evidence_url TEXT,
  note TEXT,
  order_index INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  member_id TEXT,
  type TEXT NOT NULL,
  detail TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_runs (
  id TEXT PRIMARY KEY,
  function TEXT,
  model TEXT,
  prompt_tokens INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- tulis

def create_project(title: str, description: str, deadline: str, owner: str) -> str:
    pid = new_id()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO projects (id, title, description, deadline, owner) VALUES (?,?,?,?,?)",
            (pid, title, description, deadline, owner),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


def add_members(project_id: str, names: list[str]) -> list[str]:
    ids: list[str] = []
    conn = get_conn()
    try:
        for name in names:
            mid = new_id()
            conn.execute(
                "INSERT INTO members (id, project_id, name) VALUES (?,?,?)",
                (mid, project_id, name.strip()),
            )
            ids.append(mid)
        conn.commit()
    finally:
        conn.close()
    return ids


def add_task(
    project_id: str,
    title: str,
    description: str,
    estimate_hours: float,
    priority: str,
    assignee_id: str | None,
    order_index: int = 0,
    status: str = "TODO",
    evidence_url: str | None = None,
    note: str | None = None,
) -> str:
    tid = new_id()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO tasks
               (id, project_id, title, description, estimate_hours, priority,
                assignee_id, status, evidence_url, note, order_index)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, project_id, title, description, float(estimate_hours),
             priority, assignee_id, status, evidence_url, note, order_index),
        )
        conn.commit()
    finally:
        conn.close()
    return tid


def add_tasks(project_id: str, tasks: list[dict], member_map: dict[str, str]) -> None:
    for i, t in enumerate(tasks):
        assignee = member_map.get(t.get("assignee_name", ""))
        if not assignee and member_map:
            assignee = list(member_map.values())[i % len(member_map)]
        add_task(
            project_id=project_id,
            title=t.get("title", "Tugas"),
            description=t.get("description", ""),
            estimate_hours=t.get("estimate_hours", 2),
            priority=t.get("priority", "MEDIUM"),
            assignee_id=assignee,
            order_index=i,
        )


def update_task_status(
    task_id: str,
    status: str,
    member_id: str | None = None,
    evidence_url: str | None = None,
    note: str | None = None,
) -> None:
    conn = get_conn()
    try:
        if evidence_url is not None:
            conn.execute(
                "UPDATE tasks SET status=?, evidence_url=? WHERE id=?",
                (status, evidence_url, task_id),
            )
        elif note is not None:
            conn.execute(
                "UPDATE tasks SET status=?, note=? WHERE id=?",
                (status, note, task_id),
            )
        else:
            conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        conn.commit()
    finally:
        conn.close()


def log_event(task_id: str, member_id: str | None, type_: str, detail: str | None = None) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO events (id, task_id, member_id, type, detail) VALUES (?,?,?,?,?)",
            (new_id(), task_id, member_id, type_, detail),
        )
        conn.commit()
    finally:
        conn.close()


def log_ai_run(function: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO ai_runs (id, function, model, prompt_tokens, completion_tokens) VALUES (?,?,?,?,?)",
            (new_id(), function, model, int(prompt_tokens), int(completion_tokens)),
        )
        conn.commit()
    finally:
        conn.close()


def mark_escalated(project_id: str) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            "UPDATE tasks SET status='ESCALATED' WHERE project_id=? AND status='TODO'",
            (project_id,),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def reset_all() -> None:
    conn = get_conn()
    try:
        for table in ("events", "tasks", "members", "projects", "ai_runs"):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- baca

def _rows(sql: str, params: tuple = ()) -> list[dict]:
    conn = get_conn()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def list_projects() -> list[dict]:
    return _rows("SELECT * FROM projects ORDER BY created_at DESC")


def get_project(project_id: str) -> dict | None:
    rows = _rows("SELECT * FROM projects WHERE id=?", (project_id,))
    return rows[0] if rows else None


def get_members(project_id: str) -> list[dict]:
    return _rows("SELECT * FROM members WHERE project_id=? ORDER BY rowid", (project_id,))


def get_tasks(project_id: str) -> list[dict]:
    return _rows(
        """SELECT t.*, m.name AS assignee_name
           FROM tasks t LEFT JOIN members m ON m.id = t.assignee_id
           WHERE t.project_id=? ORDER BY t.order_index, t.rowid""",
        (project_id,),
    )


def get_ai_usage() -> dict:
    rows = _rows(
        """SELECT COUNT(*) AS calls,
                  COALESCE(SUM(prompt_tokens),0) AS prompt,
                  COALESCE(SUM(completion_tokens),0) AS completion
           FROM ai_runs"""
    )
    return rows[0]


def contribution_df(project_id: str) -> pd.DataFrame:
    rows = _rows(
        """SELECT m.id, m.name,
                  COUNT(t.id) AS total,
                  SUM(CASE WHEN t.status='DONE' THEN 1 ELSE 0 END) AS done,
                  COALESCE(SUM(CASE WHEN t.status='DONE' THEN t.estimate_hours ELSE 0 END),0) AS done_hours
           FROM members m LEFT JOIN tasks t ON t.assignee_id = m.id
           WHERE m.project_id=?
           GROUP BY m.id, m.name
           ORDER BY m.rowid""",
        (project_id,),
    )
    df = pd.DataFrame(rows, columns=["id", "name", "total", "done", "done_hours"])
    if df.empty:
        df["kontribusi"] = []
        return df
    total_done = float(df["done_hours"].sum())
    df["kontribusi"] = df["done_hours"].apply(
        lambda h: round(float(h) / total_done * 100, 1) if total_done > 0 else 0.0
    )
    return df


def project_stats(project_id: str) -> dict:
    tasks = get_tasks(project_id)
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "DONE")
    running = sum(1 for t in tasks if t["status"] in ("READY", "HELP"))
    attention = sum(1 for t in tasks if t["status"] in ("ESCALATED", "DECLINED"))
    return {
        "total": total,
        "done": done,
        "running": running,
        "attention": attention,
        "progress": (done / total) if total else 0.0,
    }
