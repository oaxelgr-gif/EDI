"""Cerebro de EDI. Primero reglas locales (0 tokens); la IA sólo para resumir y conversar.
Cada respuesta puede incluir una `action` para la interfaz (p. ej. abrir el formulario de correo)."""
import logging
import re
import time
from datetime import datetime

from . import db, mail, providers, web
from .intents import fold
from .intents import detect

log = logging.getLogger("edi.agent")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

_mail_cache = {"t": 0.0, "data": None}
_last_reply: dict[int, str] = {}


def human_time(dt: datetime) -> str:
    h = dt.strftime("%-I") if dt.minute == 0 else dt.strftime("%-I:%M")
    periodo = ("de la madrugada" if dt.hour < 6 else "de la mañana" if dt.hour < 12 else
               "del mediodía" if dt.hour < 13 else "de la tarde" if dt.hour < 19 else "de la noche")
    return f"{h} {periodo}"


def human_dt(dt: datetime) -> str:
    today = db.now().date()
    delta = (dt.date() - today).days
    hora = human_time(dt)
    if delta == 0:
        return f"hoy a las {hora}"
    if delta == 1:
        return f"mañana a las {hora}"
    if 0 < delta < 7:
        return f"el {DIAS[dt.weekday()]} a las {hora}"
    return f"el {dt.day} de {MESES[dt.month - 1]} a las {hora}"


def get_mail(force: bool = False) -> dict:
    if force or not _mail_cache["data"] or time.time() - _mail_cache["t"] > 120:
        _mail_cache["data"] = mail.fetch_unread()
        _mail_cache["t"] = time.time()
    return _mail_cache["data"]


def invalidate_mail():
    _mail_cache["data"] = None


def tasks_text(tasks) -> str:
    if not tasks:
        return "No tienes pendientes."
    parts = []
    for t in tasks[:6]:
        due = f", {human_dt(datetime.fromisoformat(t['due']))}" if t["due"] else ""
        parts.append(f"{t['text']}{due}")
    extra = f", y {len(tasks) - 6} más" if len(tasks) > 6 else ""
    n = len(tasks)
    return f"Tienes {n} pendiente{'s' if n != 1 else ''}: " + "; ".join(parts) + extra + "."


def mail_text(data: dict, summarize: bool = True) -> tuple[str, str | None]:
    accounts = data["accounts"]
    if not accounts:
        return "Todavía no tengo cuentas de correo. Te abro el formulario para que registres una.", None
    total = data["total"]
    errors = [a["name"] for a in accounts if a["error"]]
    per = ", ".join(f"{a['unread_total']} en {a['name']}" for a in accounts if not a["error"])
    msg = f"Tienes {total} correo{'s' if total != 1 else ''} sin leer" + (f": {per}." if per else ".")
    if errors:
        msg += f" No pude entrar a {', '.join(errors)}."
    if total and summarize and providers.active():
        resumen, prov = providers.chat("Resume en máximo 3 frases qué correos parecen importantes o urgentes y cuáles "
                                       "son promociones.", context=mail.compact_for_llm(data), max_tokens=200)
        if resumen:
            return msg + " " + resumen, prov
    if total:
        top = [it for a in accounts for it in a["items"]][:3]
        msg += " Lo más reciente: " + "; ".join(f"{it['from']}, {it['subject']}" for it in top) + "."
    return msg, None


def handle(text: str, session_id: int, log_it: bool = True) -> dict:
    now = db.now()
    s = db.all_settings()
    user = s["user_name"]
    intent = detect(text, now)
    n = intent.name
    log.info("intent=%s text=%r", n, intent.text)
    if log_it:
        db.log_message(session_id, "user", text)
    data, action, prov = {}, None, None

    if n == "repeat":
        return {"reply": _last_reply.get(session_id) or "Todavía no he dicho nada.", "intent": n, "data": {},
                "repeat": True}

    if n == "help":
        reply = ("Puedo darte tu resumen del día, revisar todas tus cuentas de correo, guardar pendientes con aviso, "
                 "por ejemplo: recuérdame pagar la luz mañana a las 5. También recuerdo lo que me digas con "
                 "'recuerda que', y lo busco con 'qué te dije de'. Para agregar un correo o una llave de IA, pídemelo.")
    elif n == "time":
        reply = f"{'Es la' if now.strftime('%-I') == '1' else 'Son las'} {human_time(now)}."
    elif n == "date":
        reply = f"Hoy es {DIAS[now.weekday()]} {now.day} de {MESES[now.month - 1]} de {now.year}."
    elif n in ("greet", "briefing"):
        saludo = "Buenos días" if now.hour < 12 else "Buenas tardes" if now.hour < 19 else "Buenas noches"
        tasks = db.list_tasks()
        data["tasks"] = tasks
        parts = [f"{saludo}, {user}.", tasks_text(tasks)]
        if mail.list_accounts(only_enabled=True):
            try:
                m = get_mail()
                data["mail"] = m
                t, prov = mail_text(m, summarize=(n == "briefing"))
                parts.append(t)
            except Exception as e:
                parts.append(f"No pude revisar el correo: {e}")
        reply = " ".join(parts)
    elif n == "exchange":
        code = web.find_currency(text) or "USD"
        try:
            reply = web.exchange(code)
        except Exception as e:
            log.warning("exchange: %s", e)
            reply = "No pude consultar el tipo de cambio en este momento. Revisa la conexión a internet."
    elif n == "weather":
        city = web.find_city(intent.text) or s.get("home_city") or ""
        if not city:
            reply = "¿De qué ciudad quieres el clima? Puedes fijar tu ciudad en Ajustes."
        else:
            try:
                reply = web.weather(city, tomorrow="manana" in fold(text) and "en la manana" not in fold(text))
            except Exception as e:
                log.warning("weather: %s", e)
                reply = "No pude consultar el clima ahora. Revisa la conexión a internet."
    elif n == "search":
        query = intent.text or text
        ctx, sources = web.research(query)
        data["sources"] = sources
        if not sources:
            reply = "No encontré resultados en la web para eso, o no hay conexión a internet."
        else:
            ans, prov = providers.chat(
                f"Con base en estos resultados de búsqueda de hoy ({now:%d/%m/%Y}), responde a: {query}. "
                "Da el dato concreto primero, en 1 a 3 frases. Si los resultados no lo dicen, dilo.",
                context=ctx, max_tokens=220)
            reply = ans or f"Esto encontré: {sources[0]['title']}. {sources[0]['snippet']}"
    elif n == "settings_mail":
        reply = "Claro. Te abro el registro de correos: elige el proveedor, escribe tu correo y la contraseña de aplicación."
        action = {"open": "settings", "tab": "mail", "new": True}
    elif n == "settings_ai":
        reply = "Te abro la sección de inteligencia. Ahí puedes agregar OmniRoute u otra llave y ordenar las prioridades."
        action = {"open": "settings", "tab": "ai", "new": True}
    elif n == "mail":
        if not mail.list_accounts(only_enabled=True):
            reply = "Todavía no tengo cuentas de correo. Te abro el formulario para que registres una."
            action = {"open": "settings", "tab": "mail", "new": True}
        else:
            m = get_mail(force=True)
            data["mail"] = m
            reply, prov = mail_text(m)
    elif n == "add_task":
        if not intent.text:
            reply = "¿Qué quieres que te recuerde?"
        else:
            db.add_task(intent.text, intent.when)
            data["tasks"] = db.list_tasks()
            reply = f"Anotado: {intent.text}" + (f". Te aviso {human_dt(intent.when)}." if intent.when else ".")
    elif n == "list_tasks":
        data["tasks"] = db.list_tasks()
        reply = tasks_text(data["tasks"])
    elif n == "complete":
        t = None
        if intent.ref:
            t = next((x for x in db.list_tasks() if x["id"] == intent.ref), None)
        elif intent.text:
            t = db.find_task(intent.text)
        reply = f"Hecho. Taché: {t['text']}." if t and db.complete_task(t["id"]) else \
            "No encontré ese pendiente. Dime 'mis tareas' para revisarlos."
        data["tasks"] = db.list_tasks()
    elif n == "delete_task":
        ok = intent.ref and db.delete_task(intent.ref)
        reply = "Pendiente eliminado." if ok else "Dime el número del pendiente que quieres borrar."
        data["tasks"] = db.list_tasks()
    elif n == "add_note":
        if intent.text:
            db.add_note(intent.text)
            reply = f"Guardado en mi memoria: {intent.text}."
        else:
            reply = "¿Qué quieres que recuerde?"
    elif n == "delete_note":
        ok = intent.ref and db.delete_note(intent.ref)
        reply = "Lo olvidé." if ok else "Dime el número de la nota."
    elif n == "list_notes" or (n == "recall" and not intent.text):
        notes = db.list_notes(8)
        reply = ("Lo último que me pediste recordar: " + "; ".join(x["text"] for x in notes) + "."
                 if notes else "Aún no tengo nada guardado. Dime 'recuerda que…' y lo anoto.")
    elif n == "recall":
        notes = db.search_notes(intent.text)
        if not notes:
            reply = f"No tengo nada guardado sobre {intent.text}."
        elif len(notes) == 1 or not providers.active():
            reply = "Me dijiste: " + "; ".join(x["text"] for x in notes[:3]) + "."
        else:
            ans, prov = providers.chat(f"¿Qué me dijiste sobre {intent.text}?", max_tokens=150,
                                       context="\n".join(f"- ({x['created'][:10]}) {x['text']}" for x in notes))
            reply = ans or ("Me dijiste: " + notes[0]["text"])
    else:
        notes = db.search_notes(intent.text, 3)
        tasks = db.list_tasks()[:5]
        ctx = (f"Fecha y hora: {now:%Y-%m-%d %H:%M}\n"
               + ("Notas relevantes:\n" + "\n".join("- " + x["text"] for x in notes) + "\n" if notes else "")
               + ("Pendientes:\n" + "\n".join("- " + x["text"] for x in tasks) if tasks else ""))
        history = db.session_messages(session_id, 12)[:-1] if session_id else []
        if re.search(r"\b(hoy|actual|actualmente|ultim[oa]s?|precio|cuanto cuesta|noticias?|202\d|esta semana)\b", fold(intent.text)):
            web_ctx, sources = web.research(intent.text)   # datos frescos para preguntas de actualidad
            if sources:
                ctx += "\nResultados web de hoy:\n" + web_ctx
                data["sources"] = sources
        ans, prov = providers.chat(intent.text, context=ctx, history=history)
        if ans:
            reply = ans
        elif not providers.active():
            reply = "No tengo ningún proveedor de IA activo. Te abro Ajustes para agregar uno."
            action = {"open": "settings", "tab": "ai"}
        else:
            reply = "Mis proveedores de IA no respondieron. Revisa tu conexión o las llaves en Ajustes."

    _last_reply[session_id] = reply
    if log_it:
        db.log_message(session_id, "edi", reply, prov or "")
    return {"reply": reply, "intent": n, "data": data, "action": action, "provider": prov}
