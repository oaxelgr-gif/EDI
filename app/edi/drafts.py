"""Mensajes salientes (correo y WhatsApp) con confirmación obligatoria.

Flujo: tú pides → EDI arma un BORRADOR y te lo muestra/lee → sólo se envía cuando dices
"envíalo" o presionas Enviar. "Cancela" lo descarta. Nunca se envía nada automáticamente."""
import logging
import re

from . import db, mail, providers, whatsapp
from .intents import fold

log = logging.getLogger("edi.drafts")

WA = r"(?:whats ?app|whatsapp|wasap|guasap|wats|whats)"
SAY = r"(?:diciendole|diciendo|que diga|que dice|con el mensaje|para decirle que|y dile que|de que|que)"
# "mándale un mensaje a X [diciendo …]" = WhatsApp siempre. "manda un correo a X" = correo (Gmail primero).
P_WA_SEND = re.compile(rf"^(?:manda|envia|escribe|enviar|mandar)(?:le|me)?\s+(?:un\s+)?(?:{WA}|mensaje|mensajito|msj)(?:\s+(?:de|por)\s+{WA})?"
                       rf"\s+(?:a|para)\s+(?P<who>.+?)(?:\s+(?:por|en)\s+{WA})?(?:\s+{SAY}\s+(?P<msg>.+))?$")
P_WA_SEND2 = re.compile(rf"^(?:dile|escribele|mandale)\s+a\s+(?P<who>.+?)\s+(?:por\s+{WA}\s+)?{SAY}\s+(?P<msg>.+)$")
P_MAIL_REPLY = re.compile(rf"^responde(?:le)?\s+(?:el|al)\s+(?:correo|mail|email)\s+de\s+(?P<who>.+?)\s+{SAY}\s+(?P<msg>.+)$")
P_WA_REPLY = re.compile(rf"^responde(?:le)?\s+a\s+(?P<who>.+?)\s+(?:por\s+{WA}\s+)?{SAY}\s+(?P<msg>.+)$")
P_MAIL_SEND = re.compile(rf"^(?:manda|envia|escribe|redacta|enviar|mandar)(?:le|me)?\s+(?:un\s+)?(?:correo|mail|email|gmail)(?:\s+electronico)?"
                         rf"\s+(?:a|para)\s+(?P<who>.+?)(?:\s+(?:{SAY}|sobre|acerca de)\s+(?P<msg>.+))?$")
P_WA_CHECK = re.compile(rf"\b{WA}\b")
NUM = r"(?:\d+|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
P_WA_READ = re.compile(rf"^(?:lee(?:me)?|leer|muestrame|ensename|abre|revisa|dime|cuales son)\s+(?:el\s+|la\s+|los\s+|mis\s+)?(?:ultimos?\s+(?:(?P<n>{NUM})\s+)?)?"
                       rf"(?:mensajes?|chat|conversacion|whats ?app)(?:\s+de\s+{WA})?\s+(?:de|del|con)\s+(?P<who>.+?)(?:\s+en\s+{WA})?$")
VERB_SENT = r"(?:envio|envia|mando|manda|escribio|escribe|dijo|dice|ha enviado|ha mandado|ha escrito|ha dicho|han enviado|han mandado|han escrito|han dicho)"
# "lee los últimos mensajes que me envió Juan", "lee lo que me escribió mamá"
P_WA_READ3 = re.compile(rf"^(?:lee(?:me)?|leer|dime|muestrame|cuales son|que dicen)\s+(?:los\s+|mis\s+|lo\s+)?(?:ultimos?\s+(?:(?P<n>{NUM})\s+)?)?"
                        rf"(?:(?P<n2>{NUM})\s+)?(?:ultimos\s+)?(?:mensajes?\s+)?que\s+me\s+{VERB_SENT}\s+(?P<who>.+?)(?:\s+(?:en|por)\s+{WA})?$")
# "léeme los últimos mensajes (que me han dicho / nuevos / de WhatsApp)" — sin persona: lo más reciente de todos tus chats
P_WA_LATEST = re.compile(rf"^(?:lee(?:me)?|leer|dime|cuales son|muestrame|que dicen)\s+(?:los\s+|mis\s+)?(?:ultimos?\s+)?(?:(?P<n>{NUM})\s+)?(?:ultimos\s+)?"
                         rf"mensajes?(?:\s+(?:nuevos|recientes|sin leer|de\s+{WA}|que me (?:han|hayan)?\s*\w+|que tengo|que me llegaron))*$")
P_WA_READ2 = re.compile(rf"^(?:que|que cosa)\s+(?:me\s+)?(?:dijo|escribio|mando|dice|ha dicho)\s+(?P<who>.+?)(?:\s+(?:en|por)\s+{WA})?$")
P_WA_SUM = re.compile(rf"^(?:resume(?:me)?|resumen|hazme un resumen|dame un resumen)\s+(?:de\s+)?(?:el\s+|la\s+|los\s+)?(?:chat|conversacion|mensajes)(?:\s+de\s+{WA})?\s+(?:de|del|con)\s+(?P<who>.+?)(?:\s+en\s+{WA})?$")
WORDNUM = {"uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
P_MAIL_ALLREAD = re.compile(r"\bmarca(?:r|lo|los|me)?\b.*\b(?:leidos?|leidas?)\b")
# Confirmación: la frase completa debe ser corta y explícita (nunca "manda un correo a…")
P_CONFIRM = re.compile(r"^(?:(?:si|ok|va|dale|claro|perfecto)[\s,]+)?(?:si[\s,]+)?(?:envia(?:lo|la|los)?|manda(?:lo|la|los)?|confirmo|adelante|hazlo|enviar|mandar)"
                       r"(?:\s+(?:ya|ahora|por favor|porfa))?$|^(?:si|ok|dale|va|si por favor)$")
P_CANCEL = re.compile(r"^(?:no|cancela(?:lo|la)?|no lo (?:envies|mandes)|olvidalo|descarta(?:lo|la)?|mejor no)(?:\s+(?:gracias|por favor))?$")


def _slice(original: str, folded_match, group: str) -> str:
    a, b = folded_match.span(group)
    return original[a:b].strip(" ,.;:¿?¡!\"'«»")


EMOJI = [(r"corazon(?:cito)?\s+rojo|corazon(?:cito)?|corazones", "❤️"), (r"carita feliz|carita sonriente|sonrisa", "😊"),
         (r"beso|besito|besos", "😘"), (r"carita (?:de )?risa|risa|jajaja", "😂"), (r"pulgar(?: arriba)?|manita arriba|like", "👍"),
         (r"abrazo|abrazos", "🤗"), (r"carita triste", "😢"), (r"fueguito|fuego", "🔥"), (r"aplausos", "👏"), (r"rezando|manitas juntas", "🙏")]


def _clean_msg(msg: str) -> str:
    msg = re.sub(r"^(?:que|de que|diciendo que|diciendole que)\s+", "", msg.strip(), flags=re.I)
    # "con un corazón rojo", "y un beso" → emoji al final
    emojis = []
    for pat, emo in EMOJI:
        rx = re.compile(rf"(?:^|\s)(?:con|y|mas|más)?\s*(?:un|una|unos|unas)?\s*(?:emoji(?:\s+de)?\s+)?(?:{pat})\b", re.I)
        folded = fold(msg)
        mm = rx.search(folded)
        if mm:
            a, b = mm.span()
            msg = (msg[:a] + " " + msg[b:]).strip()
            emojis.append(emo)
    msg = re.sub(r"\s{2,}", " ", msg).strip(" ,")
    msg = msg[:1].upper() + msg[1:] if msg else msg
    return (msg + " " + "".join(emojis)).strip() if emojis else msg


def _end(s: str) -> str:
    return s if s.rstrip()[-1:] in ".?!…" else s + "."


def _sender_account():
    accs = [a for a in mail.list_accounts(only_enabled=True) if a.get("password")]
    return accs[0] if accs else None


def _find_mail_item(who: str):
    """Busca entre los correos sin leer uno cuyo remitente coincida con 'who'."""
    from . import agent
    q = fold(who)
    try:
        data = agent.get_mail()
    except Exception:
        return None
    for a in data.get("accounts", []):
        for it in a.get("items", []):
            if q in fold(it.get("from") or "") or q in fold(it.get("from_addr") or "") or q in fold(it.get("subject") or ""):
                return it
    return None


def _compose_email(instruction: str, original: dict | None = None) -> tuple[str, str]:
    user = db.get_setting("user_name")
    ctx = ""
    if original:
        ctx = f"Correo original de {original['from']} con asunto «{original['subject']}»:\n{original['text'][:1500]}"
    out, _ = providers.chat(
        f"Redacta un correo breve, claro y cordial en español de parte de {user}. Mensaje a transmitir: {instruction}. "
        f"Formato EXACTO: primera línea 'Asunto: …', línea vacía, cuerpo con saludo y despedida firmada como {user}. "
        "Sin markdown.", context=ctx, max_tokens=320)
    if out and out.lower().startswith("asunto:"):
        first, _, rest = out.partition("\n")
        return first.split(":", 1)[1].strip(), rest.strip()
    subject = (original and ("Re: " + original["subject"])) or _clean_msg(instruction)[:60]
    return subject, out or f"Hola,\n\n{_clean_msg(instruction)}.\n\nSaludos,\n{user}"


def _draft_reply(did: int, prefix: str) -> dict:
    d = db.get_draft(did)
    return {"reply": prefix + " ¿Lo envío? Di «envíalo» o «cancela».", "data": {"draft": d}, "intent": "draft"}


POLITE = re.compile(r"^(?:(?:oye|por favor|porfa|porfavor|me gustaria que|me gustaria|quisiera que|quiero que|necesito que|"
                    r"puedes|podrias|ayudame a|ahora|y|ok|okay|va|bueno|ahora si|edi)[\s,]+)+")
# Formas como "que le mandes…", "me leas…" → imperativo, para que las reglas de abajo las entiendan
VERB_FIX = [(r"^le\s+mandes\b", "mandale"), (r"^le\s+envies\b", "enviale"), (r"^le\s+escribas\b", "escribele"),
            (r"^le\s+digas\b", "dile"), (r"^le\s+respondas\b", "respondele"), (r"^mandes\b", "manda"),
            (r"^envies\b", "envia"), (r"^escribas\b", "escribe"), (r"^me\s+leas\b", "leeme"), (r"^leas\b", "lee"),
            (r"^me\s+resumas\b", "resumeme"), (r"^resumas\b", "resume"), (r"^respondas\b", "responde"),
            (r"^mandarle\b", "mandale"), (r"^enviarle\b", "enviale"), (r"^escribirle\b", "escribele"), (r"^decirle\b", "dile")]
COMMS_HINT = re.compile(rf"\b(?:{WA}|mensaje|mensajito|correo|mail|email|chat|manda\w*|envia\w*|escrib\w*|dile|responde\w*|lee\w*|resum\w*)\b")
CONFIRM_WORDS = {"si", "ok", "okay", "va", "dale", "claro", "perfecto", "sale", "orale", "listo", "correcto", "esta", "bien", "asi",
                 "envialo", "enviala", "envialos", "enviaselo", "enviasela", "mandalo", "mandala", "mandaselo", "mandasela",
                 "mandale", "enviale", "envia", "manda", "enviar", "mandar", "confirmo", "adelante", "hazlo", "ya", "ahora",
                 "por", "favor", "porfa", "whatsapp", "whats", "app", "wasap", "correo", "mail", "eso", "pues", "el", "mensaje",
                 "lo", "asi", "tal", "cual", "como", "esta", "edi", "y", "ese", "crealo", "creala", "muevelo", "muevela",
                 "comentalo", "publicalo", "subelo", "ticket", "slack", "jira", "hazlo", "procede", "ejecuta", "ejecutalo", "aplica", "aplicalo"}
CONFIRM_KEY = {"si", "ok", "okay", "dale", "va", "sale", "listo", "perfecto", "correcto", "envialo", "enviala", "enviaselo",
               "enviasela", "mandalo", "mandala", "mandaselo", "mandasela", "mandale", "enviale", "envia", "manda", "enviar",
               "mandar", "confirmo", "adelante", "hazlo", "orale", "crealo", "creala", "muevelo", "muevela", "comentalo",
               "publicalo", "subelo", "procede", "ejecuta", "ejecutalo", "aplica", "aplicalo"}
P_EDIT = re.compile(r"^(?:cambia(?:lo|la)?|corrige(?:lo|la)?|reemplaza(?:lo)?|mejor|ponle|pon|que diga|dile mejor|mejor dile|en vez de eso)"
                    r"\s+(?:(?:el mensaje|el texto|el correo)\s+)?(?:a|por|que diga|que|dile|di|pon)?\s*(?P<msg>.+)$")
P_REWRITE = re.compile(r"^(?:mejor\s+)?(?:hazlo|hazla|ponlo|ponla|que sea|que suene|escribelo|redactalo|dejalo|mas|menos)\s+(?:mas|menos|un poco|muy)?\s*"
                       r"(?:carinos|formal|corto|largo|amable|serio|bonito|romantic|chistos|educad|profesional|informal|tierno|breve)")
P_ADD = re.compile(r"^(?:agregale|agrega|anadele|anade|ponle tambien|y ponle|incluye)\s+(?:al final\s+)?(?:que\s+)?(?P<msg>.+)$")
P_WA_BARE = re.compile(rf"^(?:manda|envia|escribe|enviar|mandar)(?:le|me)?\s+(?:un\s+)?(?:{WA}|mensaje|mensajito|msj)(?:\s+(?:de|por)\s+{WA})?$")
P_MAIL_BARE = re.compile(r"^(?:manda|envia|escribe|redacta|enviar|mandar)(?:le|me)?\s+(?:un\s+)?(?:correo|mail|email|gmail)(?:\s+electronico)?$")
P_WHO_MSG = re.compile(rf"^(?:a\s+|para\s+)?(?P<who>.+?)(?:\s+(?:{SAY})\s+(?P<msg>.+))?$")


def _sub_pair(t: str, f: str, pattern: str, repl: str) -> tuple[str, str]:
    """Reemplaza en el texto doblado y en el original en la misma posición (mantiene alineados ambos)."""
    m = re.search(pattern, f)
    if not m:
        return t, f
    a, b = m.span()
    return t[:a] + repl + t[b:], f[:a] + repl + f[b:]


def handle(text: str, session_id: int) -> dict | None:
    """Reglas (0 tokens)."""
    return _handle(text, session_id)


def has_context(session_id: int) -> bool:
    """¿Hay un mensaje en curso en esta conversación (borrador o pregunta pendiente)?"""
    return bool(session_id and (db.pending_draft(session_id) or _get_await(session_id)))


def fallback(text: str, session_id: int) -> dict | None:
    """IA con contexto del chat, sólo si las reglas no entendieron y la frase suena a mensajería."""
    t = re.sub(r"^\s*(oye\s+|hey\s+)?(edi|eddie|edy)\b[\s,.:!]*", "", text.strip(), flags=re.I).strip(" ¿?¡!.")
    try:
        return _fallback(t, fold(t), session_id)
    except Exception as e:
        log.warning("fallback: %s", e)
        return None


def _is_confirm(f: str) -> bool:
    w = re.sub(r"[^\w\s]", " ", f).split()
    return bool(w) and len(w) <= 8 and all(x in CONFIRM_WORDS for x in w) and any(x in CONFIRM_KEY for x in w)


def _handle(text: str, session_id: int) -> dict | None:
    """Intenciones de comunicación con seguimiento de la conversación abierta. Regresa respuesta o None."""
    t = re.sub(r"^\s*(oye\s+|hey\s+)?(edi|eddie|edy)\b[\s,.:!]*", "", text.strip(), flags=re.I).strip(" ¿?¡!.")
    f = fold(t)
    m = POLITE.match(f)
    if m and m.end() < len(f):
        t, f = t[m.end():], f[m.end():]
    for pat, rep in VERB_FIX:
        t, f = _sub_pair(t, f, pat, rep)

    # --- borrador pendiente: confirmar, cancelar o corregir ---
    pend = db.pending_draft(session_id) if session_id else None
    if pend:  # los borradores caducan a los 15 minutos para no enviar algo viejo por accidente
        from datetime import datetime, timedelta
        if db.now() - datetime.fromisoformat(pend["created"]) > timedelta(minutes=15):
            db.update_draft(pend["id"], status="expired")
            pend = None
    if pend:
        if _is_confirm(f):
            res = send_draft(pend["id"])
            return {"reply": res["message"], "data": {"draft": db.get_draft(pend["id"])}, "intent": "draft_sent"}
        if P_CANCEL.match(f):
            db.update_draft(pend["id"], status="cancelled")
            return {"reply": "Cancelado, no envié nada.", "data": {"draft": db.get_draft(pend["id"])}, "intent": "draft_cancelled"}
        mr = P_REWRITE.match(f)
        if mr:  # "hazlo más cariñoso", "mejor más formal" → la IA reescribe el texto
            out, _ = providers.chat(f"Reescribe este mensaje siguiendo la instrucción «{t}». Responde sólo con el mensaje final, "
                                    f"mismo idioma, sin comillas.", context=pend["body"], max_tokens=200)
            if out:
                db.update_draft(pend["id"], body=out.strip().strip('"«»'))
                d = db.get_draft(pend["id"])
                return {"reply": f"Así queda: «{d['body'][:300]}». ¿Lo envío?", "data": {"draft": d}, "intent": "draft_edit"}
        me, ma = P_EDIT.match(f), P_ADD.match(f)
        if (me or ma) and not _looks_like_command(f):
            new = _clean_msg(_slice(t, me or ma, "msg"))
            if pend["channel"] == "jira_create":   # en un ticket: «cámbialo a …» = título; «agrégale …» = descripción
                if me:
                    db.update_draft(pend["id"], subject=new)
                else:
                    db.update_draft(pend["id"], body=(pend["body"] + "\n" + new).strip())
                d = db.get_draft(pend["id"])
                return {"reply": f"Listo. Ticket: «{d['subject']}»" + (f", descripción: {d['body'][:160]}" if d["body"] else "") + ". ¿Lo creo?",
                        "data": {"draft": d}, "intent": "draft_edit"}
            body = new if me else (pend["body"].rstrip() + " " + new)
            if pend["channel"] == "email" and me:
                _, body = _compose_email(new)
            db.update_draft(pend["id"], body=body)
            d = db.get_draft(pend["id"])
            return {"reply": f"Listo, ahora dice: «{body if pend['channel'] != 'email' else new}». ¿Lo envío?",
                    "data": {"draft": d}, "intent": "draft_edit"}

    # --- seguimiento: "¿A quién?" / "¿Qué le digo?" ---
    aw = _get_await(session_id)
    if aw:
        if P_CANCEL.match(f):
            _clear_await(session_id)
            return {"reply": "Va, no le mando nada.", "data": {}, "intent": "draft_cancelled"}
        if not _looks_like_command(f):
            _clear_await(session_id)
            pick = _pick(f, aw.get("cands") or [])
            if aw.get("need") == "read":
                if pick:
                    return _wa_summary(pick) if aw.get("summary") else _wa_read(pick, aw.get("n") or 5)
                return _read_who(session_id, t, aw.get("n") or 5, aw.get("summary"))
            if aw.get("need") == "who" and pick:
                target = {"channel": "whatsapp", "to": pick["jid"], "name": pick["name"]}
                if aw.get("msg"):
                    return _make_draft(session_id, target, aw["msg"])
                _set_await(session_id, {**target, "need": "msg"})
                return {"reply": f"¿Qué le digo a {pick['name']}?", "data": {}, "intent": "ask_msg"}
            if aw.get("need") == "who":
                mm = P_WHO_MSG.match(f)
                who = _slice(t, mm, "who")
                msg = _clean_msg(_slice(t, mm, "msg")) if mm.group("msg") else aw.get("msg", "")
                return _with_recipient(session_id, aw["channel"], who, msg)
            msg = re.sub(r"^(?:dile|escribele|ponle|que le digas|di|que diga|el mensaje es)\s+(?:que\s+)?", "", t, flags=re.I).strip()
            return _make_draft(session_id, aw, _clean_msg(msg))
        _clear_await(session_id)

    # --- pedir mensaje sin decir a quién ---
    if P_WA_BARE.match(f) or P_MAIL_BARE.match(f):
        ch = "email" if P_MAIL_BARE.match(f) else "whatsapp"
        if ch == "whatsapp" and not _wa_ready():
            return _wa_not_ready("wa_send")
        _set_await(session_id, {"channel": ch, "need": "who"})
        return {"reply": "¿A quién se lo mando?", "data": {}, "intent": "ask_who"}

    # --- trabajo: Jira, GitHub, Slack ---
    from . import work_voice
    wr = work_voice.handle(t, f, session_id)
    if wr:
        return wr

    # --- marcar correos como leídos ---
    if P_MAIL_ALLREAD.search(f) and ("correo" in f or "mail" in f or "todo" in f):
        from . import agent
        n = mail.mark_all_read()
        agent.invalidate_mail()
        return {"reply": f"Listo, marqué {n} correo{'s' if n != 1 else ''} como leído{'s' if n != 1 else ''}." if n
                else "No había correos sin leer.", "data": {}, "intent": "mail_read"}

    # --- responder correo ---
    m = P_MAIL_REPLY.match(f)
    if m:
        who, msg = _slice(t, m, "who"), _slice(t, m, "msg")
        it = _find_mail_item(who)
        if not it:
            return {"reply": f"No encontré un correo reciente de {who}. Ábrelo en la sección Correo y presiona Responder.", "data": {}, "intent": "mail_reply"}
        original = mail.get_message(it["uid"])
        subject, body = _compose_email(msg, original)
        subject = subject if subject.lower().startswith("re:") else "Re: " + original["subject"]
        did = db.add_draft(session_id, "email", account_id=original["account_id"], to_addr=original["from_addr"],
                           to_name=original["from"], subject=subject, body=body, reply_uid=it["uid"])
        return _draft_reply(did, f"Preparé la respuesta a {original['from']}.")

    # --- nuevo correo ("manda un correo a …" = correo, Gmail primero) ---
    m = P_MAIL_SEND.match(f)
    if m:
        who, msg = _slice(t, m, "who"), (_slice(t, m, "msg") if m.group("msg") else "")
        return _with_recipient(session_id, "email", who, msg)

    # --- WhatsApp: enviar ("mándale un mensaje a …" = WhatsApp siempre) ---
    m = P_WA_SEND.match(f) or P_WA_SEND2.match(f) or (P_WA_REPLY.match(f) if not P_MAIL_REPLY.match(f) else None)
    if m:
        who = _slice(t, m, "who")
        msg = _clean_msg(_slice(t, m, "msg")) if m.groupdict().get("msg") else ""
        return _with_recipient(session_id, "whatsapp", who, msg)

    # --- WhatsApp: leer / resumir un chat ---
    if P_WA_LATEST.match(f) and not P_WA_READ3.match(f):
        if not _wa_ready():
            return _wa_not_ready("wa_read")
        ml = P_WA_LATEST.match(f)
        return _wa_latest(_num(ml.group("n"), 5), session_id)

    m = P_WA_SUM.match(f) or P_WA_READ3.match(f) or P_WA_READ.match(f) or P_WA_READ2.match(f)
    if m:
        who = _slice(t, m, "who")
        if not _wa_ready():
            return _wa_not_ready("wa_read")
        gd = m.groupdict()
        return _read_who(session_id, who, _num(gd.get("n") or gd.get("n2"), 5), m.re is P_WA_SUM)

    # --- WhatsApp: resumen ---
    if P_WA_CHECK.search(f):
        st = whatsapp.status(start=True)
        if st.get("state") != "open":
            return {"reply": "WhatsApp no está vinculado todavía. Te abro la sección para escanear el código con tu teléfono.",
                    "data": {}, "intent": "wa_check", "action": {"open": "whatsapp"}}
        total, cs = whatsapp.unread_summary()
        if not total:
            return {"reply": "No tienes mensajes nuevos en WhatsApp.", "data": {}, "intent": "wa_check"}
        parts = ", ".join(f"{c['unread']} de {c['name']}" for c in cs[:4])
        last = (cs[0].get("last") or {}).get("text") or ""
        tail = _end(f"Lo último de {cs[0]['name']}: {last}") if last else ""
        return {"reply": f"Tienes {total} mensaje{'s' if total != 1 else ''} sin leer en WhatsApp: {parts}. {tail} "
                         "Puedes decirme «lee los mensajes de …» o «resume el chat de …».".replace("  ", " "),
                "data": {"wa_unread": total}, "intent": "wa_check"}
    return None


def _fallback(t: str, f: str, session_id: int) -> dict | None:
    pend = db.pending_draft(session_id) if session_id else None
    aw = _get_await(session_id)
    if not (COMMS_HINT.search(f) or pend or aw):
        return None
    j = _llm_extract(t, session_id, pend, aw)
    if not j:
        return None
    act, who, msg = j.get("action"), (j.get("who") or "").strip(), (j.get("message") or "").strip()
    if act == "confirm" and pend:
        res = send_draft(pend["id"])
        return {"reply": res["message"], "data": {"draft": db.get_draft(pend["id"])}, "intent": "draft_sent"}
    if act == "cancel" and (pend or aw):
        if pend:
            db.update_draft(pend["id"], status="cancelled")
        _clear_await(session_id)
        return {"reply": "Cancelado, no envié nada.", "data": {}, "intent": "draft_cancelled"}
    if act == "edit" and pend and msg:
        db.update_draft(pend["id"], body=msg)
        return {"reply": f"Listo, ahora dice: «{msg}». ¿Lo envío?", "data": {"draft": db.get_draft(pend["id"])}, "intent": "draft_edit"}
    if act in ("wa_send", "email_send"):
        ch = "whatsapp" if act == "wa_send" else "email"
        if not who and aw and aw.get("to"):
            return _make_draft(session_id, aw, msg) if msg else None
        if not who:
            _set_await(session_id, {"channel": ch, "need": "who", "msg": msg})
            return {"reply": "¿A quién se lo mando?", "data": {}, "intent": "ask_who"}
        _clear_await(session_id)
        return _with_recipient(session_id, ch, who, msg)
    if act in ("wa_read", "wa_summary"):
        if not _wa_ready():
            return _wa_not_ready("wa_read")
        if not who:
            return _wa_latest(int(j.get("n") or 5), session_id)
        return _read_who(session_id, who, int(j.get("n") or 5), act == "wa_summary")
    return None


def send_email(account_id: int, to: str, subject: str, body: str, reply_uid: str = "") -> dict:
    in_reply_to = references = ""
    if reply_uid:
        try:
            orig = mail.get_message(reply_uid)
            in_reply_to, references = orig.get("message_id", ""), orig.get("references", "")
        except Exception as e:
            log.warning("original: %s", e)
    mail.send(account_id, to, subject, body, in_reply_to, references)
    if reply_uid:
        try:
            mail.mark_read([reply_uid])
        except Exception:
            pass
    return {"ok": True, "message": f"Listo, envié el correo a {to}."}


def send_draft(did: int) -> dict:
    d = db.get_draft(did)
    if not d or d["status"] != "pending":
        return {"ok": False, "message": "Ese borrador ya no está pendiente."}
    try:
        if d["channel"] in ("jira_create", "jira_move", "jira_comment", "slack"):
            from . import work_voice
            res = work_voice.send(d)
            db.update_draft(did, status="sent")
            return res
        if d["channel"] == "email":
            if not d["to_addr"]:
                raise RuntimeError("Falta el correo del destinatario.")
            res = send_email(d["account_id"], d["to_addr"], d["subject"], d["body"], d["reply_uid"] or "")
        else:
            whatsapp.send(d["to_addr"], d["body"])
            res = {"ok": True, "message": f"Listo, le mandé el WhatsApp a {d['to_name'] or d['to_addr']}."}
        db.update_draft(did, status="sent")
        return res
    except Exception as e:
        db.update_draft(did, error=str(e)[:200])
        return {"ok": False, "message": f"No pude enviarlo: {e}"}


# ---------------- utilidades de contactos y borradores ----------------
def _with_recipient(session_id: int, channel: str, who: str, msg: str) -> dict:
    """Resuelve el destinatario y sigue la conversación: pregunta lo que falte (a quién / qué le digo)."""
    if channel == "whatsapp":
        if not _wa_ready():
            return _wa_not_ready("wa_send")
        target, problem = _resolve_wa(who)
        if not target and not problem.get("data", {}).get("wa_candidates"):
            # "chabelita con un corazón rojo hola" → el contacto es el inicio y lo demás es el mensaje
            words = who.split()
            for k in range(min(len(words) - 1, 4), 0, -1):
                t2, p2 = _resolve_wa(" ".join(words[:k]))
                if t2:
                    target, problem = t2, None
                    msg = msg or _clean_msg(" ".join(words[k:]))
                    break
        if not target:
            _set_await(session_id, {"channel": channel, "need": "who", "msg": msg,
                                    "cands": [{"jid": c["jid"], "name": c["name"]} for c in problem["data"].get("cands", [])]})
            return problem
    else:
        acc = _sender_account()
        if not acc:
            return {"reply": "Primero registra una cuenta con contraseña de aplicación en Ajustes → Correos.", "data": {},
                    "intent": "mail_send", "action": {"open": "settings", "tab": "mail"}}
        to, name, acc_id = _resolve_email(who)
        target = {"channel": "email", "to": to, "name": name or who, "account_id": acc_id or acc["id"]}
    if not msg:
        _set_await(session_id, {**target, "need": "msg"})
        extra = "" if target.get("to") else " (no encontré su correo; lo podrás escribir en el borrador)"
        return {"reply": f"¿Qué le {'escribo' if channel == 'email' else 'digo'} a {target['name']}{extra}?",
                "data": {}, "intent": "ask_msg"}
    return _make_draft(session_id, target, msg)


def _llm_extract(t: str, session_id: int, pend: dict | None, aw: dict | None) -> dict | None:
    """Cuando las reglas no entienden una frase de mensajería, la IA la interpreta con el contexto del chat."""
    import json
    hist = db.session_messages(session_id, 8)[:-1] if session_id else []
    ctx = "\n".join(f"{'Usuario' if h['role'] == 'user' else 'EDI'}: {h['text'][:200]}" for h in hist[-6:])
    state = ""
    if pend:
        state += f"\nHay un borrador pendiente de {pend['channel']} para {pend['to_name'] or pend['to_addr']}: «{pend['body'][:200]}»."
    if aw:
        state += f"\nEDI está esperando que el usuario diga {'a quién enviar' if aw.get('need') == 'who' else 'qué mensaje enviar'}."
    out, _ = providers.chat(
        "Interpreta la ÚLTIMA frase del usuario para un asistente que envía WhatsApp y correos. Responde SOLO JSON con: "
        '{"action": "wa_send|email_send|wa_read|wa_summary|confirm|cancel|edit|none", "who": "nombre o vacío", '
        '"message": "texto exacto a enviar (convierte descripciones de emojis en emojis) o vacío", "n": número de mensajes a leer o 0}. '
        "Reglas: 'mensaje' sin decir correo = WhatsApp. 'correo' = email_send. Si confirma enviar el borrador = confirm. "
        "Si corrige el texto del borrador = edit con message. Si no es de mensajería = none.\n"
        f"Conversación reciente:\n{ctx}{state}\nÚltima frase: {t}", max_tokens=120)
    if not out:
        return None
    try:
        return json.loads(out[out.index("{"): out.rindex("}") + 1])
    except Exception:
        return None

def _set_await(session_id: int, target: dict):
    import json
    db.run("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
           (f"_await_{session_id}", json.dumps({**target, "at": db.iso()})))


def _get_await(session_id: int) -> dict | None:
    import json
    from datetime import datetime, timedelta
    r = db.one("SELECT value FROM settings WHERE key=?", (f"_await_{session_id}",)) if session_id else None
    if not r:
        return None
    try:
        d = json.loads(r["value"])
        if db.now() - datetime.fromisoformat(d["at"]) > timedelta(minutes=5):
            _clear_await(session_id)
            return None
        return d
    except Exception:
        return None


def _clear_await(session_id: int):
    db.run("DELETE FROM settings WHERE key=?", (f"_await_{session_id}",))


def _looks_like_command(f: str) -> bool:
    return bool(P_WA_SEND.match(f) or P_MAIL_SEND.match(f) or P_WA_READ.match(f) or P_WA_SUM.match(f) or P_WA_READ3.match(f)
                or P_WA_LATEST.match(f)
                or re.match(r"^(?:recuerdame|que tengo|tengo correos|busca|cual es|como esta|agrega una|agrega un pendiente|anota|cancela la tarea)\b", f))


def _make_draft(session_id: int, target: dict, msg: str) -> dict:
    if target["channel"] == "email":
        subject, body = _compose_email(msg)
        did = db.add_draft(session_id, "email", account_id=target.get("account_id"), to_addr=target.get("to") or "",
                           to_name=target.get("name") or "", subject=subject, body=body)
        extra = "" if target.get("to") else " No tengo su dirección: escríbela en el borrador."
        return _draft_reply(did, f"Preparé un correo para {target.get('name')}.{extra}")
    did = db.add_draft(session_id, "whatsapp", to_addr=target["to"], to_name=target["name"], body=msg)
    return _draft_reply(did, f"WhatsApp para {target['name']}: «{msg}».")


def _names(found: list) -> str:
    ns = [c["name"] for c in found]
    return ", ".join(ns[:-1]) + " o " + ns[-1] if len(ns) > 1 else ns[0]


def _wa_ready() -> bool:
    return whatsapp.status(start=True).get("state") == "open"


def _wa_not_ready(intent: str) -> dict:
    return {"reply": "WhatsApp no está vinculado todavía. Te abro la sección para vincularlo.", "data": {},
            "intent": intent, "action": {"open": "whatsapp"}}


def _resolve_wa(who: str) -> tuple[dict | None, dict | None]:
    digits = re.sub(r"\D", "", who)
    if len(digits) >= 10:
        return {"channel": "whatsapp", "to": digits, "name": who}, None
    found = whatsapp.find_contacts(who)
    if not found:
        sug = whatsapp.suggest(who)
        hint = f" ¿Quisiste decir {_names(sug)}?" if sug else " Dime su nombre como lo tienes guardado o su número con lada."
        return None, {"reply": f"No encontré a {who} en tus contactos de WhatsApp.{hint}", "data": {"cands": sug}, "intent": "wa_send"}
    if len(found) > 1:
        return None, {"reply": "Encontré varios contactos: " + _names(found) + ". ¿A cuál?",
                      "data": {"wa_candidates": found, "cands": found}, "intent": "wa_send"}
    c = found[0]
    return {"channel": "whatsapp", "to": c["jid"], "name": c["name"]}, None


def _resolve_email(who: str) -> tuple[str, str, int | None]:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", who.replace(" arroba ", "@").replace(" punto ", "."))
    if m:
        return m.group(0), m.group(0), None
    it = _find_mail_item(who)
    if it:
        return it["from_addr"], it.get("from") or who, None
    return mail.find_address(re.sub(r"^(?:a\s+)?(?:mi|mis|el|la)\s+", "", who, flags=re.I))


ORD = {"primero": 0, "primera": 0, "1": 0, "uno": 0, "segundo": 1, "segunda": 1, "2": 1, "dos": 1,
       "tercero": 2, "tercera": 2, "3": 2, "tres": 2, "cuarto": 3, "cuarta": 3, "4": 3}
YES = {"si", "ese", "esa", "ese mero", "esa misma", "ese mismo", "correcto", "ok", "exacto", "eso", "simon", "sip", "aja", "ese es", "esa es"}


def _pick(f: str, cands: list) -> dict | None:
    """Elige entre las opciones que EDI acaba de ofrecer: 'sí', 'el segundo', 'Chino Birrias'…"""
    if not cands:
        return None
    w = re.sub(r"[^\w\s]", " ", f).split()
    for x in w:
        if x in ORD and ORD[x] < len(cands) and len(w) <= 4:
            return cands[ORD[x]]
    if " ".join(w) in YES or (w and w[0] in ("si", "ese", "esa", "simon") and len(w) <= 3):
        return cands[0]
    q = whatsapp._norm(f)
    q = re.sub(r"^(?:a\s+|de\s+|el\s+|la\s+|con\s+)", "", q)
    hits = [c for c in cands if q and (q in whatsapp._norm(c["name"]) or whatsapp._norm(c["name"]) in q)]
    return hits[0] if len(hits) == 1 else None


def _read_who(session_id: int, who: str, n: int, summary: bool) -> dict:
    found = whatsapp.find_contacts(who)
    if len(found) == 1:
        return _wa_summary(found[0]) if summary else _wa_read(found[0], n)
    cands = found or whatsapp.suggest(who)
    if cands:
        _set_await(session_id, {"need": "read", "n": n, "summary": summary,
                                "cands": [{"jid": c["jid"], "name": c["name"]} for c in cands]})
    if found:
        return {"reply": "Encontré varios: " + _names(found) + ". ¿De cuál?", "data": {}, "intent": "wa_read"}
    return {"reply": f"No encontré a {who} en tu WhatsApp." + (f" ¿Quisiste decir {_names(cands)}?" if cands else ""),
            "data": {}, "intent": "wa_read"}


def _num(raw: str | None, default: int) -> int:
    n = int(raw) if raw and raw.isdigit() else WORDNUM.get(raw or "", default)
    return max(1, min(n, 15))


def _wa_latest(n: int, session_id: int | None = None) -> dict:
    """Lo más reciente que te escribieron, de todos tus chats (primero los no leídos)."""
    cs = [c for c in whatsapp.chats(300) if c.get("last") and not c["last"].get("fromMe")]
    cs.sort(key=lambda c: (-(1 if c.get("unread") else 0), -(c["last"].get("ts") or 0)))
    if not cs:
        return {"reply": "No tengo mensajes recientes guardados.", "data": {}, "intent": "wa_latest"}
    parts = []
    for c in cs[:n]:
        who = c["name"] + (f" ({c['unread']} sin leer)" if c.get("unread") else "")
        parts.append(_end(f"{who}: {c['last']['text']}"))
    if session_id:
        _set_await(session_id, {"need": "read", "n": 5, "summary": False,
                                "cands": [{"jid": c["jid"], "name": c["name"]} for c in cs[:n]]})
    more = len([c for c in cs if c.get("unread")]) - n
    tail = f" Y {more} chats más con mensajes sin leer." if more > 0 else ""
    return {"reply": "Lo más reciente: " + " ".join(parts) + tail + " ¿Quieres que te lea alguno completo?",
            "data": {}, "intent": "wa_latest"}


def _fmt_msgs(msgs: list, name: str) -> str:
    return " ".join(_end(f"{'Tú' if x['fromMe'] else (x.get('name') or name)}: {x['text']}") for x in msgs)


def _wa_read(chat: dict, n: int) -> dict:
    msgs = [x for x in whatsapp.messages(chat["jid"], 40) if x.get("text")][-n:]
    if not msgs:
        return {"reply": f"Todavía no tengo mensajes guardados del chat con {chat['name']}. Aparecerán en cuanto se escriban.",
                "data": {"wa_chat": chat}, "intent": "wa_read"}
    try:
        whatsapp.read(chat["jid"])
    except Exception:
        pass
    head = f"Último mensaje con {chat['name']}:" if len(msgs) == 1 else f"Los últimos {len(msgs)} mensajes con {chat['name']}:"
    return {"reply": f"{head} {_fmt_msgs(msgs, chat['name'])}", "data": {"wa_chat": chat}, "intent": "wa_read"}


def _wa_summary(chat: dict) -> dict:
    msgs = [x for x in whatsapp.messages(chat["jid"], 40) if x.get("text")][-25:]
    if not msgs:
        return _wa_read(chat, 5)
    convo = "\n".join(f"{'Yo' if x['fromMe'] else (x.get('name') or chat['name'])}: {x['text']}" for x in msgs)
    out, _ = providers.chat(f"Resume en 2 o 3 frases, en español y hablando de tú, esta conversación de WhatsApp con {chat['name']}. "
                            "Menciona si me están pidiendo algo o esperan respuesta.", context=convo, max_tokens=180)
    if not out:
        return _wa_read(chat, 5)
    try:
        whatsapp.read(chat["jid"])
    except Exception:
        pass
    return {"reply": out, "data": {"wa_chat": chat}, "intent": "wa_summary"}
