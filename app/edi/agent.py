"""Cerebro de EDI. Primero reglas locales (0 tokens); la IA sólo para resumir y conversar.
Cada respuesta puede incluir una `action` para la interfaz (p. ej. abrir el formulario de correo)."""
import logging
import re
import time
from datetime import datetime

from . import db, drafts, mail, providers, web, whatsapp
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


# ---------------- pendientes y memoria: seguimiento y respaldo con IA ----------------
TIME_WORDS = re.compile(r"\b(recordatorio|recuerdame|recuerdes|avisame|agenda\w*|programa\w*|alarma|aviso)\b")
MEMO_HINT = re.compile(r"\b(recordatorio|recuerd\w*|record\w*|agend\w*|pendiente|tarea|memoria|acuerd\w*|anot\w*|apunt\w*|olvid\w*|guard\w*|memoriz\w*)\b")
NO_DATE = re.compile(r"^(sin (fecha|hora|dia)|nada|no|ninguna?|asi (esta )?bien|solo (anotalo|apuntalo|guardalo)|cuando sea|no importa|da igual)\b")


def _save_task(text: str, when, category: str = "") -> str:
    from .work_voice import category_from
    cat, text = (category, text) if category else category_from(text)
    cat = cat or "personal"
    due = when.strftime("%Y-%m-%dT%H:%M") if when else None
    dup = next((t for t in db.list_tasks() if fold(t["text"]) == fold(text) and (t["due"] or None) == due), None)
    if dup:
        return f"Ya lo tenía en tus pendientes: {text}" + (f", {human_dt(when)}." if when else ".")
    db.add_task(text, when, category=cat)
    where = "pendientes de trabajo" if cat == "trabajo" else "tus pendientes"
    return f"Listo, anotado en {where}: {text}" + (f". Te aviso {human_dt(when)}." if when else ".")


def _set_task_await(session_id: int, text: str):
    import json
    from .work_voice import category_from
    cat, text = category_from(text)
    db.run("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
           (f"_await_task_{session_id}", json.dumps({"text": text, "cat": cat, "at": db.iso(), "tries": 0})))


def _task_followup(text: str, intent, session_id: int, now) -> dict | None:
    """Respuesta a «¿Para cuándo te lo recuerdo?»."""
    import json
    from datetime import timedelta
    from .intents import parse_when
    if not session_id:
        return None
    key = f"_await_task_{session_id}"
    r = db.one("SELECT value FROM settings WHERE key=?", (key,))
    if not r:
        return None
    d = json.loads(r["value"])
    if now - datetime.fromisoformat(d["at"]) > timedelta(minutes=10):
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return None
    f = fold(text).strip(" ¿?¡!.")
    if re.match(r"^(cancela\w*|olvidalo|mejor no|no lo (agendes|anotes))\b", f):
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return {"reply": "Va, no lo anoto."}
    when, _rest = parse_when(text, now)
    if when:
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return {"reply": _save_task(d["text"], when, d.get("cat") or "personal")}
    if NO_DATE.match(f):
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return {"reply": _save_task(d["text"], None, d.get("cat") or "personal")}
    if intent.name != "chat" or d.get("tries", 0) >= 1:   # cambió de tema: lo guardo sin fecha para no perderlo
        db.run("DELETE FROM settings WHERE key=?", (key,))
        db.add_task(d["text"], None, category=d.get("cat") or "personal")
        return None
    d["tries"] = 1
    db.run("UPDATE settings SET value=? WHERE key=?", (json.dumps(d), key))
    return {"reply": "No entendí la fecha. Dime por ejemplo «mañana a las 3 de la tarde», «el viernes a las 10» o «sin fecha»."}


def _memo_fallback(text: str, session_id: int, now) -> dict | None:
    """Frases de pendientes/memoria que las reglas no entendieron: la IA las interpreta con el contexto y EDI las guarda de verdad."""
    import json
    from .intents import parse_when
    hist = db.session_messages(session_id, 8)[:-1] if session_id else []
    ctx = "\n".join(f"{'Usuario' if h['role'] == 'user' else 'EDI'}: {h['text'][:200]}" for h in hist[-6:])
    out, _ = providers.chat(
        "Clasifica la ÚLTIMA frase del usuario para un asistente con pendientes y memoria. Responde SOLO JSON: "
        '{"action": "add_task|add_note|none", "text": "qué anotar, breve, sin la fecha", "when": "fecha/hora tal como la dijo o vacío"}. '
        "add_task = algo que hacer o que le recuerden (recordatorio, pendiente, tarea, cita). add_note = un dato para recordar "
        "(no es una acción). Si la frase sólo comenta o corrige algo ya dicho, usa la conversación para completar text y when. "
        f"Si no es nada de eso: none.\nConversación reciente:\n{ctx}\nÚltima frase: {text}", max_tokens=120)
    if not out:
        return None
    try:
        j = json.loads(out[out.index("{"): out.rindex("}") + 1])
    except Exception:
        return None
    act, what = j.get("action"), (j.get("text") or "").strip(" .")
    if not what or act not in ("add_task", "add_note"):
        return None
    if act == "add_note":
        if any(fold(x["text"]) == fold(what) for x in db.list_notes(50)):
            return {"reply": f"Eso ya lo tenía guardado: {what}.", "intent": "add_note"}
        db.add_note(what)
        return {"reply": f"Guardado en mi memoria: {what}.", "intent": "add_note"}
    when, _ = parse_when(j.get("when") or "", now) if j.get("when") else (None, "")
    if not when and TIME_WORDS.search(fold(text + " " + what)):
        _set_task_await(session_id, what)
        return {"reply": f"¿Para cuándo te recuerdo {what}? Por ejemplo «mañana a las 3», o di «sin fecha».", "intent": "add_task"}
    return {"reply": _save_task(what, when), "intent": "add_task"}


def agenda_text(f: str, now) -> str:
    """«¿Qué tengo mañana?», «mi agenda de esta semana», «¿qué tengo el viernes?»."""
    from datetime import timedelta
    from .intents import parse_when
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "semana" in f or f in ("mi agenda", "agenda"):
        start, end = (today + timedelta(days=7 - today.weekday()), today + timedelta(days=14 - today.weekday())) if "proxima" in f \
            else (today, today + timedelta(days=7))
        label = "la próxima semana" if "proxima" in f else "los próximos 7 días"
    elif "fin de semana" in f or "este fin" in f:
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        end, label = start + timedelta(days=2), "el fin de semana"
    else:
        when, _ = parse_when(f, now)
        start = (when or now).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        label = "hoy" if start == today else "mañana" if start == today + timedelta(days=1) else \
            f"el {DIAS[start.weekday()]} {start.day}"
    items = [t for t in db.list_tasks() if t["due"] and start <= datetime.fromisoformat(t["due"]) < end]
    items.sort(key=lambda t: t["due"])
    if not items:
        return f"No tienes nada agendado para {label}."
    multi = (end - start).days > 1
    parts = [f"{t['text']}, " + (human_dt(datetime.fromisoformat(t["due"])) if multi else
             human_time(datetime.fromisoformat(t["due"]))) for t in items[:8]]
    return f"Para {label} tienes {len(items)}: " + "; ".join(parts) + "."


def _saludo(now) -> str:
    return "Buenas noches" if now.hour < 5 else "Buenos días" if now.hour < 12 else "Buenas tardes" if now.hour < 19 else "Buenas noches"


def greeting() -> dict:
    """Al abrir EDI: el primer saludo del día trae el resumen (clima, pendientes, correo, WhatsApp);
    los demás son un saludo corto."""
    now = db.now()
    s = db.all_settings()
    user = s["user_name"]
    today = now.date().isoformat()
    last = db.one("SELECT value FROM settings WHERE key='_last_brief'")
    if last and last["value"] == today:
        return {"reply": f"{_saludo(now)}, {user}. ¿En qué puedo ayudarlo?", "intent": "greet_short", "data": {}}
    db.run("INSERT INTO settings(key, value) VALUES('_last_brief', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (today,))
    parts, data = [f"{_saludo(now)}, {user}."], {}
    city = s.get("home_city") or ""
    if city:
        try:
            w = web.weather_brief(city)
            if w:
                parts.append(w)
        except Exception as e:
            log.warning("clima del saludo: %s", e)
    tasks = db.list_tasks()
    data["tasks"] = tasks
    hoy = [t for t in tasks if t["due"] and datetime.fromisoformat(t["due"]).date() <= now.date() and t.get("category") != "trabajo"]
    if hoy:
        parts.append(f"Para hoy tiene {len(hoy)} pendiente{'s' if len(hoy) != 1 else ''}: " +
                     "; ".join(f"{t['text']}, {human_dt(datetime.fromisoformat(t['due']))}" for t in hoy[:3]) + ".")
    elif tasks:
        parts.append(f"Tiene {len(tasks)} pendiente{'s' if len(tasks) != 1 else ''}, ninguno para hoy.")
    extras = []
    if mail.list_accounts(only_enabled=True):
        try:
            m = get_mail()
            data["mail"] = m
            if m.get("total"):
                extras.append(f"{m['total']} correo{'s' if m['total'] != 1 else ''} sin leer")
        except Exception as e:
            log.warning("correo del saludo: %s", e)
    try:
        if whatsapp.status().get("state") == "open":
            total, cs = whatsapp.unread_summary()
            if total:
                extras.append(f"mensajes nuevos en {len(cs)} chat{'s' if len(cs) != 1 else ''} de WhatsApp")
    except Exception:
        pass
    if extras:
        parts.append("Tiene " + " y ".join(extras) + ".")
    try:
        from . import connectors
        work_today = [t for t in tasks if t.get("category") == "trabajo" and t["due"] and datetime.fromisoformat(t["due"]).date() <= now.date()]
        if work_today:
            parts.append(f"En el trabajo vencen hoy {len(work_today)}: " + "; ".join(t["text"] for t in work_today[:3]) + ".")
        b = connectors.briefing()
        if b:
            parts.append("Además, " + " y ".join(b) + ".")
    except Exception as e:
        log.info("trabajo en el saludo: %s", e)
    parts.append("¿En qué puedo ayudarlo?")
    return {"reply": " ".join(parts), "intent": "greet_daily", "data": data}


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

    pend_task = _task_followup(text, intent, session_id, now)
    if pend_task:
        if log_it:
            db.log_message(session_id, "edi", pend_task["reply"])
        _last_reply[session_id] = pend_task["reply"]
        return {"intent": "add_task", "data": {"tasks": db.list_tasks()}, "action": None, "provider": None, **pend_task}

    comms = drafts.handle(text, session_id) if n not in ("repeat",) else None
    if comms is None and n == "chat" and MEMO_HINT.search(fold(text)):
        memo = _memo_fallback(text, session_id, now)
        if memo:
            if log_it:
                db.log_message(session_id, "edi", memo["reply"])
            _last_reply[session_id] = memo["reply"]
            return {"data": {"tasks": db.list_tasks()}, "action": None, "provider": None, **memo}
    if comms is None and (n == "chat" or (n == "search" and drafts.COMMS_HINT.search(fold(text)))
                          or (n in ("greet", "mail", "search", "weather") and drafts.has_context(session_id))):
        comms = drafts.fallback(text, session_id)
    if comms:
        _last_reply[session_id] = comms["reply"]
        if log_it:
            db.log_message(session_id, "edi", comms["reply"])
        comms.setdefault("action", None)
        comms.setdefault("provider", None)
        return comms

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
    elif n == "greet":
        g = greeting()
        reply, data = g["reply"], g["data"]
    elif n == "briefing":
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
        elif not intent.when and TIME_WORDS.search(fold(text)):
            _set_task_await(session_id, intent.text)
            from .work_voice import category_from
            reply = f"¿Para cuándo te recuerdo {category_from(intent.text)[1]}? Por ejemplo «mañana a las 3», o di «sin fecha»."
        else:
            reply = _save_task(intent.text, intent.when)
            data["tasks"] = db.list_tasks()
    elif n == "agenda":
        reply = agenda_text(fold(text), now)
        data["tasks"] = db.list_tasks()
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
        if intent.text and any(fold(x["text"]) == fold(intent.text) for x in db.list_notes(50)):
            reply = f"Eso ya lo tenía guardado: {intent.text}."
        elif intent.text:
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
