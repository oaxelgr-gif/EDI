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
    s.update({r["key"]: r["value"] for r in rows("SELECT key, value FROM settings")})
    return s


def set_settings(values: dict):
    with conn() as c:
        c.executemany("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      [(k, str(v)) for k, v in values.items() if k in config.DEFAULT_SETTINGS])


# ---------- tareas ----------
def add_task(text: str, due: Optional[datetime] = None, source: str = "usuario") -> int:
    return run("INSERT INTO tasks(text, due, source, created) VALUES (?,?,?,?)",
               (text, due.isoformat(timespec="minutes") if due else None, source, iso()))


def list_tasks(include_done: bool = False):
    return rows("SELECT * FROM tasks" + ("" if include_done else " WHERE done=0") + " ORDER BY done, due IS NULL, due, id")


def update_task(task_id: int, **fields) -> bool:
    allowed = {k: v for k, v in fields.items() if k in ("text", "due", "done")}
    if not allowed:
        return False
    if "due" in allowed:
        allowed["reminded"] = 0
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
