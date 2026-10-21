"""Persistencia de EDI en un solo archivo SQLite (data/edi.sqlite3)."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, due TEXT,
    done INTEGER DEFAULT 0, reminded INTEGER DEFAULT 0, source TEXT DEFAULT 'usuario', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, created TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(text, content='notes', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON notes BEGIN
  INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER IF NOT EXISTS notes_ad AFTER DELETE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, text) VALUES('delete', old.id, old.text); END;
CREATE TRIGGER IF NOT EXISTS notes_au AFTER UPDATE ON notes BEGIN
  INSERT INTO notes_fts(notes_fts, rowid, text) VALUES('delete', old.id, old.text);
  INSERT INTO notes_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL, base_url TEXT DEFAULT '',
    username TEXT DEFAULT '', secret TEXT DEFAULT '', config TEXT DEFAULT '{}', enabled INTEGER DEFAULT 1,
    last_sync TEXT, last_error TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, created TEXT, updated TEXT);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, text TEXT NOT NULL, created TEXT NOT NULL,
    session_id INTEGER, meta TEXT);
CREATE TABLE IF NOT EXISTS mail_seen (uid TEXT PRIMARY KEY, account TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, kind TEXT NOT NULL, base_url TEXT,
    api_key TEXT, model TEXT, priority INTEGER DEFAULT 10, enabled INTEGER DEFAULT 1, created TEXT);
CREATE TABLE IF NOT EXISTS usage (
    provider_id INTEGER, day TEXT, requests INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0, errors INTEGER DEFAULT 0,
    last_error TEXT, PRIMARY KEY (provider_id, day));
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, channel TEXT NOT NULL, account_id INTEGER,
    to_addr TEXT, to_name TEXT, subject TEXT, body TEXT, reply_uid TEXT, status TEXT DEFAULT 'pending',
    error TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, provider TEXT NOT NULL, host TEXT, port INTEGER DEFAULT 993,
    user TEXT NOT NULL, password TEXT, folders TEXT DEFAULT 'INBOX', enabled INTEGER DEFAULT 1, created TEXT);
"""


def now() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(config.TIMEZONE)).replace(tzinfo=None)


def iso() -> str:
    return now().isoformat(timespec="seconds")


@contextmanager
def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(messages)")}
        for col, ddl in (("session_id", "INTEGER"), ("meta", "TEXT")):  # migración desde v1
            if col not in cols:
                c.execute(f"ALTER TABLE messages ADD COLUMN {col} {ddl}")
        tcols = {r["name"] for r in c.execute("PRAGMA table_info(tasks)")}
        for col, ddl in (("notes", "TEXT DEFAULT ''"), ("priority", "TEXT DEFAULT 'normal'"), ("link", "TEXT DEFAULT ''"),  # v0.5
                         ("category", "TEXT DEFAULT 'personal'"), ("ext_key", "TEXT DEFAULT ''"), ("conn_id", "INTEGER"),
                         ("ext_status", "TEXT DEFAULT ''"), ("updated", "TEXT")):
            if col not in tcols:
                c.execute(f"ALTER TABLE tasks ADD COLUMN {col} {ddl}")
        dcols = {r["name"] for r in c.execute("PRAGMA table_info(drafts)")}
        if "extra" not in dcols:   # v0.5: datos propios del canal (fecha del ticket, canal de Slack…)
            c.execute("ALTER TABLE drafts ADD COLUMN extra TEXT DEFAULT ''")
        acols = {r["name"] for r in c.execute("PRAGMA table_info(accounts)")}
        for col, ddl in (("smtp_host", "TEXT"), ("smtp_port", "INTEGER")):  # migración v0.4
            if col not in acols:
                c.execute(f"ALTER TABLE accounts ADD COLUMN {col} {ddl}")


def rows(sql: str, args=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def one(sql: str, args=()):
    with conn() as c:
        r = c.execute(sql, args).fetchone()
        return dict(r) if r else None


def run(sql: str, args=()) -> int:
    with conn() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


# ---------- ajustes ----------
def get_setting(key: str) -> str:
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else config.DEFAULT_SETTINGS.get(key, "")


def all_settings() -> dict:
    s = dict(config.DEFAULT_SETTINGS)
    s.update({r["key"]: r["value"] for r in rows("SELECT key, value FROM settings WHERE substr(key, 1, 1) != '_'")})
    return s


def set_settings(values: dict):
    with conn() as c:
        c.executemany("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      [(k, str(v)) for k, v in values.items() if k in config.DEFAULT_SETTINGS])


# ---------- tareas ----------
TASK_FIELDS = ("text", "due", "done", "notes", "priority", "link", "category", "ext_key", "conn_id", "ext_status", "source")


def add_task(text: str, due: Optional[datetime] = None, source: str = "usuario", **extra) -> int:
    f = {k: v for k, v in extra.items() if k in TASK_FIELDS}
    cols = ["text", "due", "source", "created", "updated"] + list(f)
    vals = [text, due.isoformat(timespec="minutes") if isinstance(due, datetime) else due, source, iso(), iso()] + list(f.values())
    return run(f"INSERT INTO tasks({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)


def get_task(task_id: int):
    return one("SELECT * FROM tasks WHERE id=?", (task_id,))


def task_by_ext(conn_id: int, ext_key: str):
    return one("SELECT * FROM tasks WHERE conn_id=? AND ext_key=?", (conn_id, ext_key))


def list_tasks(include_done: bool = False, category: str | None = None):
    where = [] if include_done else ["done=0"]
    args = []
    if category:
        where.append("category=?")
        args.append(category)
    return rows("SELECT * FROM tasks" + (" WHERE " + " AND ".join(where) if where else "") +
                " ORDER BY done, due IS NULL, due, id", args)


def update_task(task_id: int, **fields) -> bool:
    allowed = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if not allowed:
        return False
    if "due" in allowed:
        allowed["reminded"] = 0
    allowed["updated"] = iso()
    sets = ", ".join(f"{k}=?" for k in allowed)
    return run(f"UPDATE tasks SET {sets} WHERE id=?", (*allowed.values(), task_id)) > 0


def complete_task(task_id: int) -> bool:
    return run("UPDATE tasks SET done=1 WHERE id=?", (task_id,)) > 0


def delete_task(task_id: int) -> bool:
    return run("DELETE FROM tasks WHERE id=?", (task_id,)) > 0


def find_task(fragment: str):
    return one("SELECT * FROM tasks WHERE done=0 AND lower(text) LIKE ? ORDER BY id DESC LIMIT 1", (f"%{fragment.lower()}%",))


def due_reminders():
    with conn() as c:
        found = [dict(r) for r in c.execute(
            "SELECT * FROM tasks WHERE done=0 AND reminded=0 AND due IS NOT NULL AND due<=?",
            (now().isoformat(timespec="minutes"),))]
        if found:
            c.execute(f"UPDATE tasks SET reminded=1 WHERE id IN ({','.join('?' * len(found))})", [t["id"] for t in found])
        return found


# ---------- notas ----------
def add_note(text: str) -> int:
    return run("INSERT INTO notes(text, created) VALUES (?,?)", (text, iso()))


def list_notes(limit: int = 200):
    return rows("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,))


def search_notes(query: str, limit: int = 5):
    words = [w for w in query.replace('"', " ").split() if len(w) > 2]
    if not words:
        return []
    try:
        return rows("SELECT n.* FROM notes_fts f JOIN notes n ON n.id=f.rowid WHERE notes_fts MATCH ? ORDER BY rank LIMIT ?",
                    (" OR ".join(f'"{w}"' for w in words), limit))
    except sqlite3.OperationalError:
        return []


def update_note(note_id: int, text: str) -> bool:
    return run("UPDATE notes SET text=? WHERE id=?", (text, note_id)) > 0


def delete_note(note_id: int) -> bool:
    return run("DELETE FROM notes WHERE id=?", (note_id,)) > 0


# ---------- sesiones y mensajes ----------
def create_session(title: str = "Nueva conversación") -> int:
    return run("INSERT INTO sessions(title, created, updated) VALUES (?,?,?)", (title, iso(), iso()))


def list_sessions(limit: int = 60):
    return rows("""SELECT s.*, (SELECT COUNT(*) FROM messages m WHERE m.session_id=s.id) AS count
                   FROM sessions s ORDER BY updated DESC LIMIT ?""", (limit,))


def rename_session(sid: int, title: str) -> bool:
    return run("UPDATE sessions SET title=? WHERE id=?", (title[:80], sid)) > 0


def delete_session(sid: int) -> bool:
    run("DELETE FROM messages WHERE session_id=?", (sid,))
    return run("DELETE FROM sessions WHERE id=?", (sid,)) > 0


def log_message(session_id: int, role: str, text: str, meta: str = ""):
    run("INSERT INTO messages(session_id, role, text, created, meta) VALUES (?,?,?,?,?)", (session_id, role, text, iso(), meta))
    s = one("SELECT title FROM sessions WHERE id=?", (session_id,))
    if s and role == "user" and s["title"] == "Nueva conversación":
        run("UPDATE sessions SET title=?, updated=? WHERE id=?", (text[:60], iso(), session_id))
    else:
        run("UPDATE sessions SET updated=? WHERE id=?", (iso(), session_id))


def session_messages(session_id: int, limit: int = 300):
    return rows("SELECT id, role, text, created, meta FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit))[::-1]


# ---------- correo ya anunciado ----------
def unseen_mail_uids(uids):
    if not uids:
        return set()
    seen = {r["uid"] for r in rows(f"SELECT uid FROM mail_seen WHERE uid IN ({','.join('?' * len(uids))})", list(uids))}
    return set(uids) - seen


def mark_mail_seen(uids):
    with conn() as c:
        c.executemany("INSERT OR IGNORE INTO mail_seen(uid, account, created) VALUES (?,?,?)", [(u, "", iso()) for u in uids])


# ---------- borradores (correo / WhatsApp) que esperan tu confirmación ----------
def add_draft(session_id: int, channel: str, **f) -> int:
    run("UPDATE drafts SET status='replaced' WHERE session_id=? AND status='pending'", (session_id,))
    return run("INSERT INTO drafts(session_id, channel, account_id, to_addr, to_name, subject, body, reply_uid, extra, created) "
               "VALUES (?,?,?,?,?,?,?,?,?,?)",
               (session_id, channel, f.get("account_id"), f.get("to_addr", ""), f.get("to_name", ""), f.get("subject", ""),
                f.get("body", ""), f.get("reply_uid", ""), f.get("extra", ""), iso()))


def get_draft(did: int):
    return one("SELECT * FROM drafts WHERE id=?", (did,))


def pending_draft(session_id: int):
    return one("SELECT * FROM drafts WHERE session_id=? AND status='pending' ORDER BY id DESC LIMIT 1", (session_id,))


def update_draft(did: int, **f) -> bool:
    f = {k: v for k, v in f.items() if k in ("account_id", "to_addr", "to_name", "subject", "body", "status", "error", "extra")}
    if not f:
        return False
    return run(f"UPDATE drafts SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), did)) > 0


# ---------- conexiones (Jira, GitHub, Slack…) ----------
def list_connections(kind: str | None = None, only_enabled: bool = False):
    where, args = [], []
    if kind:
        where.append("kind=?"); args.append(kind)
    if only_enabled:
        where.append("enabled=1")
    return rows("SELECT * FROM connections" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id", args)


def get_connection(cid: int):
    return one("SELECT * FROM connections WHERE id=?", (cid,))


def add_connection(kind: str, name: str, base_url: str = "", username: str = "", secret: str = "", config: str = "{}",
                   enabled: int = 1) -> int:
    return run("INSERT INTO connections(kind, name, base_url, username, secret, config, enabled, created) VALUES (?,?,?,?,?,?,?,?)",
               (kind, name, base_url, username, secret, config, enabled, iso()))


def update_connection(cid: int, **f) -> bool:
    allowed = {k: v for k, v in f.items() if k in ("name", "base_url", "username", "secret", "config", "enabled", "last_sync", "last_error")}
    if not allowed:
        return False
    return run(f"UPDATE connections SET {', '.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), cid)) > 0


def delete_connection(cid: int) -> bool:
    run("DELETE FROM tasks WHERE conn_id=? AND done=1", (cid,))
    run("UPDATE tasks SET conn_id=NULL WHERE conn_id=?", (cid,))
    return run("DELETE FROM connections WHERE id=?", (cid,)) > 0
