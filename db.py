import os
import secrets
import sqlite3
import uuid
from datetime import datetime

import pandas as pd

DB_PATH = os.environ.get("RATA_DB_PATH") or (
    "/tmp/rata.db" if os.environ.get("SPACE_ID") else "rata.db"
)


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def new_token() -> str:
    return secrets.token_urlsafe(12)


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

# Kolom yang ditambahkan setelah versi pertama aplikasi. Database lama tidak
# mendapatkannya lewat CREATE TABLE IF NOT EXISTS, jadi ditambahkan manual.
MIGRATIONS = {
    "members": [
        ("token", "TEXT"),
        ("role", "TEXT DEFAULT 'MEMBER'"),
    ],
    "tasks": [
        ("actual_hours", "REAL"),
        ("submitted_at", "TEXT"),
        ("verified_by", "TEXT"),
        ("verified_at", "TEXT"),
        ("reject_reason", "TEXT"),
    ],
    "events": [
        ("actor_source", "TEXT"),
        ("actual_hours", "REAL"),
    ],
}


def _migrate(conn: sqlite3.Connection) -> None:
    added: dict[str, set[str]] = {}
    for table, columns in MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.setdefault(table, set()).add(name)

    # Data lama: tugas DONE dibuat sebelum ada konsep verifikasi. Tanpa backfill,
    # kontribusi mereka tiba-tiba menjadi 0 setelah pembaruan. Tandai sebagai
    # warisan supaya tetap terhitung dan jelas asalnya di laporan.
    if "verified_by" in added.get("tasks", set()):
        conn.execute(
            """UPDATE tasks
               SET actual_hours=COALESCE(actual_hours, estimate_hours),
                   verified_by='legacy',
                   verified_at=COALESCE(verified_at, CURRENT_TIMESTAMP),
                   submitted_at=COALESCE(submitted_at, CURRENT_TIMESTAMP)
               WHERE status='DONE' AND verified_by IS NULL"""
        )


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
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
        for index, name in enumerate(names):
            mid = new_id()
            role = "OWNER" if index == 0 else "MEMBER"
            conn.execute(
                "INSERT INTO members (id, project_id, name, token, role) VALUES (?,?,?,?,?)",
                (mid, project_id, name.strip(), new_token(), role),
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


def _insert_event(
    conn: sqlite3.Connection,
    task_id: str,
    member_id: str | None,
    type_: str,
    detail: str | None,
    actor_source: str | None,
    actual_hours: float | None,
) -> None:
    conn.execute(
        """INSERT INTO events (id, task_id, member_id, type, detail, actor_source, actual_hours)
           VALUES (?,?,?,?,?,?,?)""",
        (new_id(), task_id, member_id, type_, detail, actor_source, actual_hours),
    )


def log_event(
    task_id: str,
    member_id: str | None,
    type_: str,
    detail: str | None = None,
    actor_source: str | None = None,
    actual_hours: float | None = None,
) -> None:
    conn = get_conn()
    try:
        _insert_event(conn, task_id, member_id, type_, detail, actor_source, actual_hours)
        conn.commit()
    finally:
        conn.close()


def submit_task(
    task_id: str,
    evidence_url: str,
    actual_hours: float,
    member_id: str | None = None,
    actor_source: str | None = None,
) -> None:
    """Tandai tugas terkumpul. Belum dihitung sebagai kontribusi."""
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE tasks
               SET status='SUBMITTED', evidence_url=?, actual_hours=?,
                   submitted_at=CURRENT_TIMESTAMP, verified_by=NULL,
                   verified_at=NULL, reject_reason=NULL
               WHERE id=?""",
            (evidence_url, float(actual_hours), task_id),
        )
        _insert_event(
            conn,
            task_id,
            member_id,
            "SUBMITTED",
            f"{actual_hours:g} jam · {evidence_url}",
            actor_source,
            float(actual_hours),
        )
        conn.commit()
    finally:
        conn.close()


def verify_task(
    task_id: str,
    verifier_id: str,
    actor_source: str | None = None,
) -> bool:
    """Konfirmasi selesai. False bila pemilik tugas mencoba mengonfirmasi sendiri."""
    task = get_task(task_id)
    if not task:
        return False
    if task.get("assignee_id") and task["assignee_id"] == verifier_id:
        return False
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE tasks
               SET status='DONE', verified_by=?, verified_at=CURRENT_TIMESTAMP,
                   reject_reason=NULL
               WHERE id=?""",
            (verifier_id, task_id),
        )
        _insert_event(conn, task_id, verifier_id, "VERIFIED", "Dikonfirmasi selesai", actor_source, None)
        conn.commit()
    finally:
        conn.close()
    return True


def reject_task(
    task_id: str,
    reason: str,
    member_id: str | None = None,
    actor_source: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE tasks
               SET status='READY', verified_by=NULL, verified_at=NULL,
                   reject_reason=?, submitted_at=NULL
               WHERE id=?""",
            (reason, task_id),
        )
        _insert_event(conn, task_id, member_id, "REJECTED", reason, actor_source, None)
        conn.commit()
    finally:
        conn.close()


def reopen_task(
    task_id: str,
    reason: str,
    member_id: str | None = None,
    actor_source: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE tasks
               SET status='READY', verified_by=NULL, verified_at=NULL,
                   reject_reason=?
               WHERE id=?""",
            (reason, task_id),
        )
        _insert_event(conn, task_id, member_id, "REOPENED", reason, actor_source, None)
        conn.commit()
    finally:
        conn.close()


def reply_task(
    task_id: str,
    intent: str,
    reason: str,
    member_id: str | None = None,
    actor_source: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE tasks SET status=?, note=? WHERE id=?",
            (intent, reason, task_id),
        )
        _insert_event(conn, task_id, member_id, intent, reason, actor_source, None)
        conn.commit()
    finally:
        conn.close()


def set_task_status(
    task_id: str,
    status: str,
    member_id: str | None = None,
    actor_source: str | None = None,
    detail: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        _insert_event(conn, task_id, member_id, status, detail, actor_source, None)
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
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM tasks WHERE project_id=? AND status='TODO'", (project_id,)
            )
        ]
        conn.execute(
            "UPDATE tasks SET status='ESCALATED' WHERE project_id=? AND status='TODO'",
            (project_id,),
        )
        for tid in ids:
            _insert_event(
                conn,
                tid,
                None,
                "ESCALATED",
                "Tidak ada respons dalam 24 jam",
                "system",
                None,
            )
        conn.commit()
        return len(ids)
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
                  SUM(CASE WHEN t.status='DONE' AND t.verified_by IS NOT NULL
                           THEN 1 ELSE 0 END) AS done,
                  SUM(CASE WHEN t.status='SUBMITTED' THEN 1 ELSE 0 END) AS pending,
                  COALESCE(SUM(CASE WHEN t.status='DONE' AND t.verified_by IS NOT NULL
                                    THEN COALESCE(t.actual_hours, 0) ELSE 0 END), 0) AS done_hours,
                  COALESCE(SUM(t.estimate_hours), 0) AS estimate_hours,
                  COALESCE(SUM(CASE WHEN t.status='DONE' AND t.verified_by IS NOT NULL
                                    THEN COALESCE(t.estimate_hours, 0) ELSE 0 END), 0) AS done_estimate
           FROM members m LEFT JOIN tasks t ON t.assignee_id = m.id
           WHERE m.project_id=?
           GROUP BY m.id, m.name
           ORDER BY m.rowid""",
        (project_id,),
    )
    columns = [
        "id",
        "name",
        "total",
        "done",
        "pending",
        "done_hours",
        "estimate_hours",
        "done_estimate",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        df["kontribusi"] = []
        return df
    total_done = float(df["done_hours"].sum())
    df["kontribusi"] = df["done_hours"].apply(
        lambda h: round(float(h) / total_done * 100, 1) if total_done > 0 else 0.0
    )
    return df


def get_events(project_id: str, limit: int = 60) -> list[dict]:
    return _rows(
        """SELECT e.created_at, e.type, e.detail, e.actor_source, e.actual_hours,
                  m.name AS actor_name, t.title AS task_title
           FROM events e
           JOIN tasks t ON t.id = e.task_id
           LEFT JOIN members m ON m.id = e.member_id
           WHERE t.project_id=?
           ORDER BY e.created_at DESC, e.rowid DESC
           LIMIT ?""",
        (project_id, int(limit)),
    )


def get_anomalies(project_id: str) -> list[dict]:
    """Sinyal kecurangan ringan. Menandai, tidak memblokir."""
    tasks = get_tasks(project_id)
    found: list[dict] = []

    by_url: dict[str, list[str]] = {}
    for t in tasks:
        url = (t.get("evidence_url") or "").strip()
        if url:
            by_url.setdefault(url, []).append(t["title"])
    for url, titles in by_url.items():
        if len(titles) > 1:
            found.append(
                {
                    "jenis": "Bukti duplikat",
                    "detail": f"{len(titles)} tugas memakai tautan yang sama: {', '.join(titles[:3])}",
                }
            )

    for t in tasks:
        if t["status"] in ("SUBMITTED", "DONE") and t.get("actual_hours") is not None:
            estimate = float(t.get("estimate_hours") or 0)
            actual = float(t["actual_hours"])
            if estimate > 0 and actual < 0.25 * estimate:
                found.append(
                    {
                        "jenis": "Jam tidak wajar",
                        "detail": f"'{t['title']}' dilaporkan {actual:g} jam dari estimasi {estimate:g} jam",
                    }
                )

    verified = [
        t
        for t in tasks
        if t["status"] == "DONE" and t.get("verified_at")
    ]
    per_minute: dict[str, int] = {}
    for t in verified:
        # Data warisan memakai waktu migrasi yang seragam, bukan verifikasi nyata.
        if t.get("verified_by") == "legacy":
            continue
        stamp = str(t["verified_at"])[:16]
        per_minute[stamp] = per_minute.get(stamp, 0) + 1
    for stamp, count in per_minute.items():
        if count >= 3:
            found.append(
                {
                    "jenis": "Verifikasi serentak",
                    "detail": f"{count} tugas diverifikasi pada menit yang sama ({stamp})",
                }
            )

    per_verifier: dict[str, int] = {}
    for t in verified:
        vid = t.get("verified_by") or ""
        if vid == "legacy":
            continue
        per_verifier[vid] = per_verifier.get(vid, 0) + 1
    for vid, count in per_verifier.items():
        if count >= 4:
            names = {m["id"]: m["name"] for m in get_members(project_id)}
            found.append(
                {
                    "jenis": "Verifikasi sepihak",
                    "detail": f"{names.get(vid, vid)} mengonfirmasi {count} tugas",
                }
            )

    return found


def get_member_by_token(token: str) -> dict | None:
    token = (token or "").strip()
    if not token:
        return None
    rows = _rows("SELECT * FROM members WHERE token=?", (token,))
    return rows[0] if rows else None


def get_task(task_id: str) -> dict | None:
    rows = _rows(
        """SELECT t.*, m.name AS assignee_name
           FROM tasks t LEFT JOIN members m ON m.id = t.assignee_id
           WHERE t.id=?""",
        (task_id,),
    )
    return rows[0] if rows else None


def project_stats(project_id: str) -> dict:
    tasks = get_tasks(project_id)
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "DONE")
    pending = sum(1 for t in tasks if t["status"] == "SUBMITTED")
    running = sum(1 for t in tasks if t["status"] in ("READY", "HELP"))
    attention = sum(1 for t in tasks if t["status"] in ("ESCALATED", "DECLINED"))
    return {
        "total": total,
        "done": done,
        "pending": pending,
        "running": running,
        "attention": attention,
        "progress": (done / total) if total else 0.0,
    }
