"""Varias cuentas de correo por IMAP, sólo lectura (nunca marca como leído).
Las cuentas se registran desde Ajustes → Correos y se guardan en data/edi.sqlite3."""
import logging
import os
from typing import List

from imap_tools import AND, MailBox

from . import config, db

log = logging.getLogger("edi.mail")

PRESETS = {
    "gmail":   {"label": "Gmail / Google Workspace", "host": "imap.gmail.com",
                "help": "Activa la verificación en 2 pasos y crea una contraseña de aplicación.",
                "help_url": "https://myaccount.google.com/apppasswords"},
    "outlook": {"label": "Outlook / Hotmail", "host": "outlook.office365.com",
                "help": "Microsoft exige OAuth: lo más fácil es reenviar tu Outlook a Gmail.",
                "help_url": "https://outlook.live.com/mail/0/options/mail/forwarding"},
    "yahoo":   {"label": "Yahoo", "host": "imap.mail.yahoo.com",
                "help": "Genera una contraseña de aplicación en Seguridad de la cuenta.",
                "help_url": "https://login.yahoo.com/account/security"},
    "icloud":  {"label": "iCloud", "host": "imap.mail.me.com",
                "help": "Crea una contraseña específica para apps.", "help_url": "https://account.apple.com"},
    "zoho":    {"label": "Zoho", "host": "imap.zoho.com", "help": "Usa una contraseña de aplicación.", "help_url": ""},
    "imap":    {"label": "Otro (IMAP)", "host": "", "help": "Pide a tu proveedor el servidor IMAP y el puerto (normalmente 993).",
                "help_url": ""},
}


def public(a: dict) -> dict:
    out = {k: v for k, v in a.items() if k != "password"}
    out["has_password"] = bool(a.get("password"))
    out["provider_label"] = PRESETS.get(a["provider"], PRESETS["imap"])["label"]
    return out


def list_accounts(only_enabled=False) -> List[dict]:
    return db.rows("SELECT * FROM accounts" + (" WHERE enabled=1" if only_enabled else "") + " ORDER BY id")


def add_account(d: dict) -> int:
    return db.run("INSERT INTO accounts(name, provider, host, port, user, password, folders, enabled, created) "
                  "VALUES (?,?,?,?,?,?,?,?,?)",
                  (d.get("name") or d["user"], d.get("provider", "imap"), d.get("host") or "", int(d.get("port") or 993),
                   d["user"].strip(), (d.get("password") or "").replace(" ", ""), d.get("folders") or "INBOX",
                   int(d.get("enabled", 1)), db.iso()))


def update_account(aid: int, d: dict) -> bool:
    f = {k: d[k] for k in ("name", "provider", "host", "port", "user", "folders", "enabled") if k in d}
    if d.get("password"):
        f["password"] = d["password"].replace(" ", "")
    if not f:
        return False
    return db.run(f"UPDATE accounts SET {', '.join(f'{k}=?' for k in f)} WHERE id=?", (*f.values(), aid)) > 0


def delete_account(aid: int) -> bool:
    return db.run("DELETE FROM accounts WHERE id=?", (aid,)) > 0


def import_yaml_once():
    """Migra las cuentas de config/accounts.yaml (v1) a la base de datos, una sola vez."""
    if db.one("SELECT id FROM accounts LIMIT 1") or not config.ACCOUNTS_FILE.exists():
        return
    try:
        import yaml
        for it in (yaml.safe_load(config.ACCOUNTS_FILE.read_text()) or {}).get("accounts", []):
            pwd = os.getenv(it.get("password_env", ""), "")
            if it.get("enabled", True) and pwd and "tu_correo" not in it.get("user", ""):
                add_account({**it, "password": pwd, "folders": ",".join(it.get("folders", ["INBOX"]))})
    except Exception as e:
        log.warning("No se pudo importar accounts.yaml: %s", e)


def _host(a: dict) -> str:
    return a.get("host") or PRESETS.get(a["provider"], {}).get("host", "")


def _login(a: dict) -> MailBox:
    mb = MailBox(_host(a), port=int(a.get("port") or 993), timeout=20)
    if a["provider"] == "outlook" and config.MS_CLIENT_ID and not a.get("password"):
        from .oauth_ms import get_access_token
        token = get_access_token(a["user"])
        if not token:
            raise RuntimeError("Falta autorizar Outlook (./scripts/edi.sh outlook correo)")
        return mb.xoauth2(a["user"], token, initial_folder=None)
    if not a.get("password"):
        raise RuntimeError("Falta la contraseña de aplicación")
    return mb.login(a["user"], a["password"], initial_folder=None)


def test_login(a: dict) -> dict:
    try:
        with _login(a) as mb:
            mb.folder.set("INBOX")
            n = len(mb.uids(AND(seen=False)))
        return {"ok": True, "unread": n}
    except Exception as e:
        msg = str(e)
        if "AUTHENTICATIONFAILED" in msg or "Invalid credentials" in msg or "LOGIN failed" in msg:
            msg = "Usuario o contraseña de aplicación incorrectos."
        return {"ok": False, "error": msg[:240]}


def fetch_unread(limit_per_account: int | None = None) -> dict:
    limit = limit_per_account or int(db.get_setting("mail_max_per_account") or 15)
    out = {"accounts": [], "total": 0}
    for a in list_accounts(only_enabled=True):
        entry = {"id": a["id"], "name": a["name"], "user": a["user"], "unread_total": 0, "items": [], "error": None}
        try:
            with _login(a) as mb:
                for folder in [f.strip() for f in (a["folders"] or "INBOX").split(",") if f.strip()]:
                    mb.folder.set(folder)
                    entry["unread_total"] += len(mb.uids(AND(seen=False)))
                    for msg in mb.fetch(AND(seen=False), limit=limit, reverse=True, mark_seen=False, bulk=True):
                        snippet = " ".join((msg.text or msg.html or "").split())[:220]
                        name = msg.from_values.name if msg.from_values and msg.from_values.name else msg.from_
                        entry["items"].append({
                            "uid": f"{a['id']}:{folder}:{msg.uid}", "from": name, "from_addr": msg.from_,
                            "subject": msg.subject or "(sin asunto)", "snippet": snippet, "folder": folder,
                            "date": msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else ""})
        except Exception as e:
            log.warning("Cuenta %s: %s", a["name"], e)
            entry["error"] = str(e)[:200]
        out["total"] += entry["unread_total"]
        out["accounts"].append(entry)
    return out


def compact_for_llm(data: dict, max_items: int = 25) -> str:
    lines = []
    for a in data["accounts"]:
        for it in a["items"]:
            if len(lines) >= max_items:
                break
            lines.append(f"[{a['name']}] {it['from']} | {it['subject']} | {it['snippet'][:100]}")
    return "\n".join(lines)
