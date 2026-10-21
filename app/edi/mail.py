"""Varias cuentas de correo: leer (IMAP), marcar como leído y enviar/responder (SMTP).
EDI nunca envía nada sin tu confirmación: todo pasa primero por un borrador.
Las cuentas se registran desde Ajustes → Correos y se guardan en data/edi.sqlite3."""
import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid, parseaddr
from typing import List

from imap_tools import AND, MailBox, MailMessageFlags

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


SMTP = {"gmail": ("smtp.gmail.com", 465), "outlook": ("smtp.office365.com", 587), "yahoo": ("smtp.mail.yahoo.com", 465),
        "icloud": ("smtp.mail.me.com", 587), "zoho": ("smtp.zoho.com", 465)}


def public(a: dict) -> dict:
    out = {k: v for k, v in a.items() if k != "password"}
    out["has_password"] = bool(a.get("password"))
    out["provider_label"] = PRESETS.get(a["provider"], PRESETS["imap"])["label"]
    return out


def list_accounts(only_enabled=False) -> List[dict]:
    return db.rows("SELECT * FROM accounts" + (" WHERE enabled=1" if only_enabled else "") + " ORDER BY id")


def add_account(d: dict) -> int:
    return db.run("INSERT INTO accounts(name, provider, host, port, user, password, folders, enabled, created, smtp_host, smtp_port) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (d.get("name") or d["user"], d.get("provider", "imap"), d.get("host") or "", int(d.get("port") or 993),
                   d["user"].strip(), (d.get("password") or "").replace(" ", ""), d.get("folders") or "INBOX",
                   int(d.get("enabled", 1)), db.iso(), d.get("smtp_host") or "", int(d.get("smtp_port") or 0)))


def update_account(aid: int, d: dict) -> bool:
    f = {k: d[k] for k in ("name", "provider", "host", "port", "user", "folders", "enabled", "smtp_host", "smtp_port") if k in d}
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


def friendly(msg: str, provider: str = "") -> str:
    if "AUTHENTICATIONFAILED" in msg or "Invalid credentials" in msg or "LOGIN failed" in msg:
        if provider == "gmail":
            return ("Gmail rechazó la contraseña. Necesita una contraseña de aplicación de 16 letras "
                    "(myaccount.google.com/apppasswords), no tu contraseña normal.")
        return "Usuario o contraseña de aplicación incorrectos."
    return msg


def find_address(name: str) -> tuple[str, str, int | None]:
    """Busca la dirección de alguien por su nombre en tus correos recibidos y enviados.
    Regresa (correo, nombre, id_de_cuenta) o ("", "", None)."""
    from email.utils import getaddresses
    q = name.strip()
    accs = sorted(list_accounts(only_enabled=True), key=lambda a: a["provider"] != "gmail")
    for a in accs:
        try:
            with _login(a) as mb:
                sent = next((f.name for f in mb.folder.list() if "\\Sent" in f.flags), None)
                for folder, crit in (("INBOX", AND(from_=q)), (sent, AND(to=q))):
                    if not folder:
                        continue
                    mb.folder.set(folder)
                    for msg in mb.fetch(crit, limit=1, reverse=True, headers_only=True, mark_seen=False, charset="UTF-8"):
                        pairs = getaddresses([msg.headers.get("from", [""])[0]] if folder == "INBOX" else msg.headers.get("to", [""]))
                        for nm, addr in pairs:
                            if addr and (q.lower() in (nm or "").lower() or q.lower() in addr.lower()):
                                return addr, nm or addr, a["id"]
                        if pairs and pairs[0][1]:
                            return pairs[0][1], pairs[0][0] or pairs[0][1], a["id"]
        except Exception as e:
            log.warning("find_address %s: %s", a.get("user"), e)
    return "", "", None


def test_login(a: dict) -> dict:
    try:
        with _login(a) as mb:
            mb.folder.set("INBOX")
            n = len(mb.uids(AND(seen=False)))
        return {"ok": True, "unread": n}
    except Exception as e:
        return {"ok": False, "error": friendly(str(e), a.get("provider", ""))[:240]}


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
            entry["error"] = friendly(str(e), a["provider"])[:220]
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


# ---------------- acciones: ver, marcar leído, enviar ----------------
def get_account(aid: int) -> dict | None:
    return db.one("SELECT * FROM accounts WHERE id=?", (aid,))


def _split_uid(uid: str):
    aid, folder, num = uid.split(":", 2)
    return int(aid), folder, num


def get_message(uid: str) -> dict:
    aid, folder, num = _split_uid(uid)
    a = get_account(aid)
    if not a:
        raise RuntimeError("La cuenta ya no existe.")
    with _login(a) as mb:
        mb.folder.set(folder)
        for msg in mb.fetch(AND(uid=num), mark_seen=False, limit=1):
            text = (msg.text or "").strip()
            if not text:
                text = " ".join(re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>|<[^>]+>", " ", msg.html or "").split())
            return {"uid": uid, "account_id": aid, "account": a["name"], "from": msg.from_values.name if msg.from_values else msg.from_,
                    "from_addr": msg.from_, "to": list(msg.to), "subject": msg.subject or "(sin asunto)",
                    "date": msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "", "text": text[:20000],
                    "message_id": (msg.headers.get("message-id") or [""])[0].strip(),
                    "references": (msg.headers.get("references") or [""])[0].strip()}
    raise RuntimeError("No encontré ese correo; quizá ya se movió o borró.")


def mark_read(uids: list[str], seen: bool = True) -> int:
    """Marca como leídos (o no leídos) correos 'cuenta:carpeta:uid'. Regresa cuántos cambió."""
    groups: dict[tuple, list] = {}
    for u in uids:
        aid, folder, num = _split_uid(u)
        groups.setdefault((aid, folder), []).append(num)
    n = 0
    for (aid, folder), nums in groups.items():
        a = get_account(aid)
        if not a:
            continue
        with _login(a) as mb:
            mb.folder.set(folder)
            mb.flag(nums, MailMessageFlags.SEEN, seen)
            n += len(nums)
    return n


def mark_all_read() -> int:
    n = 0
    for a in list_accounts(only_enabled=True):
        try:
            with _login(a) as mb:
                for folder in [f.strip() for f in (a["folders"] or "INBOX").split(",") if f.strip()]:
                    mb.folder.set(folder)
                    uids = mb.uids(AND(seen=False))
                    if uids:
                        mb.flag(uids, MailMessageFlags.SEEN, True)
                        n += len(uids)
        except Exception as e:
            log.warning("mark_all_read %s: %s", a["name"], e)
    return n


def _smtp_server(a: dict) -> tuple[str, int]:
    if a.get("smtp_host"):
        return a["smtp_host"], int(a.get("smtp_port") or 465)
    if a["provider"] in SMTP:
        return SMTP[a["provider"]]
    domain = a["user"].split("@")[-1]
    return f"smtp.{domain}", 465


def send(account_id: int, to: str, subject: str, body: str, in_reply_to: str = "", references: str = "") -> str:
    a = get_account(account_id)
    if not a:
        raise RuntimeError("Elige una cuenta para enviar.")
    if not a.get("password"):
        raise RuntimeError("Esa cuenta no tiene contraseña de aplicación.")
    name, addr = parseaddr(to)
    if "@" not in addr:
        raise RuntimeError("Escribe un correo de destino válido.")
    msg = EmailMessage()
    msg["From"] = a["user"]
    msg["To"] = to
    msg["Subject"] = subject or "(sin asunto)"
    msg["Message-ID"] = make_msgid(domain=a["user"].split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = (references + " " + in_reply_to).strip()
    msg.set_content(body)
    host, port = _smtp_server(a)
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=25) as s:
                s.login(a["user"], a["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=25) as s:
                s.starttls(context=ctx)
                s.login(a["user"], a["password"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(friendly("AUTHENTICATIONFAILED", a["provider"]))
    return msg["Message-ID"]
