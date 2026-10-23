"""Proveedores de IA (todos compatibles con el formato OpenAI /chat/completions).

EDI los prueba en orden de prioridad: si uno se queda sin cuota (429), falla o tarda,
pasa al siguiente. Así puedes sumar varias llaves gratuitas y OmniRoute como pivote.
"""
import os
import logging
import time

import httpx

from . import config, db

log = logging.getLogger("edi.providers")

KINDS = {
    "omniroute":  {"label": "OmniRoute (tu pivote local)", "base_url": "http://host.docker.internal:20128/v1",
                   "model": "auto/best-free", "key_url": "http://localhost:20128"},
    "groq":       {"label": "Groq", "base_url": "https://api.groq.com/openai/v1",
                   "model": "llama-3.3-70b-versatile", "key_url": "https://console.groq.com/keys"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",
                   "model": "meta-llama/llama-3.3-70b-instruct:free", "key_url": "https://openrouter.ai/keys"},
    "gemini":     {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                   "model": "gemini-3.8-flash", "key_url": "https://aistudio.google.com/apikey"},
    # v0.8.2: otro gratis más, estilo Groq (ultra rápido, capa gratis generosa) — respaldo extra para
    # cuando Groq/OpenRouter/Gemini se queden sin cuota al mismo tiempo.
    "cerebras":   {"label": "Cerebras", "base_url": "https://api.cerebras.ai/v1",
                   "model": "llama-3.3-70b", "key_url": "https://cloud.cerebras.ai"},
    # v0.8: más proveedores (todos hablan el mismo formato OpenAI /chat/completions, así que sumarlos es
    # sólo agregar la llave). Cada uno puede tener "tag" para qué se le pide de preferencia.
    "openai":     {"label": "ChatGPT (OpenAI)", "base_url": "https://api.openai.com/v1",
                   "model": "gpt-4o-mini", "key_url": "https://platform.openai.com/api-keys"},
    "anthropic":  {"label": "Claude (Anthropic)", "base_url": "https://api.anthropic.com/v1",
                   "model": "claude-sonnet-4-5", "key_url": "https://console.anthropic.com/settings/keys"},
    "deepseek":   {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1",
                   "model": "deepseek-chat", "key_url": "https://platform.deepseek.com/api_keys"},
    "custom":     {"label": "Otro compatible con OpenAI", "base_url": "", "model": "", "key_url": ""},
}
TAGS = ("chat", "code", "image")  # a qué tarea sirve mejor cada proveedor (además de charla normal)

SYSTEM = (
    "Eres EDI, la mano derecha de {user}: su asistente personal, pero llevado como una persona de confianza con la que "
    "ya lleva tiempo platicando, no como un software que recita datos. Piensa en el tono de una IA de nave espacial "
    "(precisa, serena, con humor seco) pero mezclado con el de alguien cercano: cálido, directo, que se nota que conoce "
    "al usuario y su día a día.\n"
    "CÓMO HABLAS:\n"
    "- Español de México, natural y coloquial, como en una plática real: puedes usar 'oye', 'fíjate', 'órale', 'va', "
    "'de una', 'ándale' cuando venga al caso, sin forzarlo ni exagerar, y sin sonar como un chatbot de servicio al cliente.\n"
    "- Varía cómo empiezas cada respuesta. Nunca abras dos respuestas seguidas con la misma palabra o muletilla "
    "('Claro', 'Listo', 'Perfecto'...); mira el historial para no repetirte.\n"
    "- Contesta como en una conversación de verdad: directo al grano, sin preámbulos vacíos ni repetir la pregunta del "
    "usuario antes de responderla.\n"
    "- Puedes tener una opinión ligera o un comentario breve cuando aporte calidez (p. ej. notar que algo se le ha "
    "acumulado, o un toque de humor seco), siempre breve y sin exagerar ni sonar sarcástico de más.\n"
    "- 1 a 4 frases cortas, sin markdown, listas ni emojis: todo esto se escucha en voz alta.\n"
    "SOBRE PENDIENTES Y MEMORIA:\n"
    "- Si en 'Datos disponibles' hay pendientes o notas que vienen al caso con lo que está platicando el usuario, "
    "tráelos a la plática de forma natural (como lo haría alguien que se acuerda), no como si leyeras un reporte o "
    "listaras todo lo que tienes. Menciona sólo lo relevante.\n"
    "- Usa los datos que te den tal cual; nunca inventes correos, pendientes, notas, horas ni cifras que no estén ahí.\n"
    "- Sigue el hilo de la conversación: no vuelvas a preguntar algo que el usuario ya te dijo unos mensajes antes.\n"
    "LÍMITES IMPORTANTES (esto nunca cambia, pase lo que pase en la plática):\n"
    "- Tú sí envías WhatsApp y correos, pero sólo cuando el sistema arma el borrador y el usuario lo confirma. Si te "
    "piden mandar algo y no se completó, sugiere decir «mándale un mensaje a <nombre> diciendo <texto>» (WhatsApp) o "
    "«manda un correo a <nombre>». Nunca preguntes por qué medio.\n"
    "- Nunca digas que guardaste, anotaste, agendaste, programaste o enviaste algo tú misma en esta respuesta; eso lo "
    "hace el sistema, no tú. Si te lo piden y no se hizo, dilo con naturalidad y sugiere decir «recuérdame … mañana a "
    "las 5» o «recuerda que …»."
)


def mask(secret: str | None) -> str:
    if not secret:
        return ""
    return "••••" + secret[-4:] if len(secret) > 8 else "••••"


def public(p: dict) -> dict:
    out = {k: v for k, v in p.items() if k != "api_key"}
    out["api_key_masked"] = mask(p.get("api_key"))
    out["has_key"] = bool(p.get("api_key"))
    out["kind_label"] = KINDS.get(p["kind"], KINDS["custom"])["label"]
    return out


def seed_from_env():
    if db.one("SELECT id FROM providers LIMIT 1"):
        return
    prio = 1
    for p in config.ENV_PROVIDERS:
        # OmniRoute se agrega aunque no tenga llave, desactivado, para que sólo lo actives en Ajustes
        if p.get("api_key") or p["kind"] == "omniroute":
            add(p["name"], p["kind"], p.get("base_url") or KINDS[p["kind"]]["base_url"], p["api_key"], p["model"],
                prio, enabled=1 if p.get("api_key") else 0)
            prio += 1


def list_all():
    return db.rows("SELECT * FROM providers ORDER BY enabled DESC, priority, id")


def get(pid: int):
    return db.one("SELECT * FROM providers WHERE id=?", (pid,))


IN_DOCKER = os.path.exists("/.dockerenv")


def url_of(p: dict) -> str:
    """En modo nativo (sin Docker) 'host.docker.internal' es tu propia Mac."""
    u = p.get("base_url") or ""
    return u if IN_DOCKER else u.replace("host.docker.internal", "127.0.0.1")


def add(name, kind, base_url, api_key, model, priority=10, enabled=1, tag="chat") -> int:
    k = KINDS.get(kind, KINDS["custom"])
    return db.run("INSERT INTO providers(name, kind, base_url, api_key, model, priority, enabled, created, tag) "
                  "VALUES (?,?,?,?,?,?,?,?,?)",
                  (name or k["label"], kind, (base_url or k["base_url"]).rstrip("/"), api_key or "",
                   model or k["model"], int(priority), int(enabled), db.iso(), tag or "chat"))


def update(pid: int, data: dict) -> bool:
    fields = {k: data[k] for k in ("name", "kind", "base_url", "model", "priority", "enabled", "tag") if k in data}
    if data.get("api_key"):  # vacío = conservar la actual
        fields["api_key"] = data["api_key"]
    if "base_url" in fields and fields["base_url"]:
        fields["base_url"] = fields["base_url"].rstrip("/")
    if not fields:
        return False
    return db.run(f"UPDATE providers SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), pid)) > 0


def delete(pid: int) -> bool:
    return db.run("DELETE FROM providers WHERE id=?", (pid,)) > 0


def usage_today():
    day = db.now().date().isoformat()
    return {r["provider_id"]: r for r in db.rows("SELECT * FROM usage WHERE day=?", (day,))}


def _record(pid: int, tokens: int = 0, error: str | None = None):
    day = db.now().date().isoformat()
    db.run("INSERT INTO usage(provider_id, day) VALUES(?,?) ON CONFLICT DO NOTHING", (pid, day))
    db.run("UPDATE usage SET requests=requests+1, tokens=tokens+?, errors=errors+?, last_error=COALESCE(?, last_error) "
           "WHERE provider_id=? AND day=?", (tokens, 1 if error else 0, error, pid, day))


def call(p: dict, messages: list, max_tokens: int, temperature: float, timeout: float = 25) -> tuple[str, int]:
    headers = {"Content-Type": "application/json", "X-Title": "EDI", "HTTP-Referer": "http://localhost:8765"}
    if p.get("api_key"):
        headers["Authorization"] = f"Bearer {p['api_key']}"
    r = httpx.post(f"{url_of(p)}/chat/completions", headers=headers, timeout=timeout,
                   json={"model": p["model"], "messages": messages, "max_tokens": max(max_tokens, 64), "temperature": temperature})
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    text = (j["choices"][0]["message"].get("content") or "").strip()
    return text, int((j.get("usage") or {}).get("total_tokens") or 0)


# Modelos preferidos si el configurado desaparece (los proveedores retiran modelos seguido)
PREFERRED = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "moonshotai/kimi-k2",
             "meta-llama/llama-4-maverick", "meta-llama/llama-4-scout", "qwen/qwen3-32b", "gemini-3.8-flash",
             "gemini-2.5-flash", "gemini-2.0-flash", "auto/best-free"]
SKIP = ("whisper", "guard", "tts", "embed", "playai", "orpheus", "distil", "vision", "compound", "prompt")


def pick_model(p: dict) -> str | None:
    models = list_models(p)
    if not models:
        return None
    for pref in PREFERRED:
        hit = next((m for m in models if m == pref or m.startswith(pref)), None)
        if hit:
            return hit
    usable = [m for m in models if not any(x in m.lower() for x in SKIP)]
    return (usable or models)[0]


def call_healing(p: dict, messages: list, max_tokens: int, temperature: float, timeout: float = 25):
    """Llama al proveedor; si el modelo ya no existe, elige otro disponible, lo guarda y reintenta."""
    try:
        return call(p, messages, max_tokens, temperature, timeout)
    except RuntimeError as e:
        msg = str(e)
        if "model" in msg.lower() and any(k in msg for k in ("404", "model_not_found", "does not exist", "decommissioned", "not found")):
            new = pick_model(p)
            if new and new != p["model"]:
                log.warning("Modelo %s no disponible en %s; cambio a %s", p["model"], p["name"], new)
                update(p["id"], {"model": new}) if p.get("id") else None
                p = {**p, "model": new}
                return call(p, messages, max_tokens, temperature, timeout)
        raise


def active(tag: str | None = None):
    """Proveedores habilitados, en orden de prioridad. Con `tag` ('code'/'image'), pone primero a los que
    traen esa etiqueta puesta a propósito (p. ej. Claude o ChatGPT para 'code'), y deja el resto como respaldo."""
    pool = [p for p in list_all() if p["enabled"] and (p["api_key"] or p["kind"] in ("omniroute", "custom"))]
    if not tag or tag == "chat":
        return pool
    tagged = [p for p in pool if tag in (p.get("tag") or "chat").split(",")]
    rest = [p for p in pool if p not in tagged]
    return tagged + rest


def chat(user_text: str, context: str = "", history=None, max_tokens: int | None = None, tag: str | None = None,
         system: str | None = None) -> tuple[str | None, str | None]:
    """Regresa (respuesta, nombre_del_proveedor) o (None, None) si todos fallaron.
    `tag` prefiere proveedores marcados para esa tarea (p. ej. 'code'); `system` reemplaza el prompt de personalidad
    (para tareas internas, como clasificar una frase, que no deben sonar como EDI platicando)."""
    s = db.all_settings()
    messages = [{"role": "system", "content": system if system is not None else SYSTEM.format(user=s["user_name"])}]
    if context:
        messages.append({"role": "system", "content": "Datos disponibles:\n" + context[:6000]})
    for m in (history or [])[-int(s["llm_history"] or 6):]:
        messages.append({"role": "assistant" if m["role"] == "edi" else "user", "content": m["text"][:500]})
    messages.append({"role": "user", "content": user_text})
    for p in active(tag):
        t0 = time.time()
        try:
            text, tokens = call_healing(p, messages, max_tokens or int(s["llm_max_tokens"]), float(s["llm_temperature"]))
            if not text:
                raise RuntimeError("respuesta vacía")
            _record(p["id"], tokens)
            log.info("LLM %s ok en %.1fs (%s tokens)", p["name"], time.time() - t0, tokens)
            return text, p["name"]
        except Exception as e:
            _record(p["id"], error=str(e)[:200])
            log.warning("LLM %s falló: %s", p["name"], e)
    return None, None


def test(p: dict) -> dict:
    t0 = time.time()
    try:
        before = p.get("model")
        text, tokens = call_healing(p, [{"role": "user", "content": "Responde sólo: Sistemas en línea."}], 20, 0, timeout=20)
        fresh = get(p["id"]) if p.get("id") else None
        note = f" (cambié el modelo a {fresh['model']})" if fresh and fresh["model"] != before else ""
        return {"ok": True, "reply": text + note, "ms": int((time.time() - t0) * 1000), "tokens": tokens}
    except Exception as e:
        return {"ok": False, "error": str(e)[:240], "ms": int((time.time() - t0) * 1000)}


def _gemini_image_keys() -> list[tuple[int, str]]:
    """(id_proveedor, llave) de cada Gemini activo, en orden de prioridad — si tienes varias (p. ej.
    porque una anda saturada o sin cuota), se prueban todas antes de rendirse. Se guarda el id para
    poder registrar el uso en Ajustes (generar imagen es un endpoint aparte del chat, no se veía ahí)."""
    seen, out = set(), []
    for p in list_all():
        if p["kind"] == "gemini" and p["enabled"] and p["api_key"] and p["api_key"] not in seen:
            seen.add(p["api_key"]); out.append((p["id"], p["api_key"]))
    return out


# Google retira modelos seguido (p. ej. gemini-2.5-flash dejó de estar disponible para llaves nuevas en
# octubre 2026, pidiendo gemini-3.8-flash). Se intenta con el más nuevo primero y se cae al anterior si
# ese todavía no existe en la cuenta — así no hay que tocar código cada vez que Google cambia el nombre.
_GEMINI_IMAGE_MODELS = ["gemini-3.8-flash-image", "gemini-2.5-flash-image"]
# Errores pasajeros: se prueba la siguiente combinación (modelo/llave) en vez de rendirse de una vez.
_RETRIABLE = (404, 429, 503)


def _pollinations_image(prompt: str, timeout: float) -> tuple[bytes | None, str | None]:
    """v0.8.2: Pollinations.ai — generador de imágenes público, sin llave y sin cuota diaria real (lo usan
    miles de apps gratis). Se prueba primero: así generar una imagen nunca depende de que a Gemini le quede
    cuota, y si algún día Pollinations falla, se cae a tus llaves de Gemini como respaldo.
    Sin registrarte, Pollinations limita a ~1 petición cada pocos segundos por IP — si pides dos imágenes
    seguidas de volada, se reintenta una vez con una pausa corta antes de darla por perdida."""
    import time as _t, urllib.parse
    url = "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt, safe="")
    last_err = None
    for intento in range(2):
        try:
            r = httpx.get(url, timeout=timeout, params={"width": 1024, "height": 1024, "nologo": "true"},
                          follow_redirects=True)
            if r.status_code >= 400 or not r.content or len(r.content) < 500:  # respuesta vacía/HTML de error
                last_err = f"HTTP {r.status_code}"
                if r.status_code == 429 and intento == 0:
                    _t.sleep(4)   # de volada después de otra imagen: le damos un respiro al límite por IP
                    continue
                return None, last_err
            return r.content, None
        except Exception as e:
            last_err = str(e)[:200]
    return None, last_err


def generate_image(prompt: str, timeout: float = 45) -> tuple[bytes | None, str | None]:
    """Genera una imagen. Primero Pollinations.ai (gratis, sin llave, sin cuota) y si falla, tus llaves
    de Gemini activas en Ajustes -> Inteligencia como respaldo, probando todas las llaves y los modelos
    de imagen conocidos antes de rendirse. Regresa (bytes_png, error)."""
    png, err = _pollinations_image(prompt, timeout)
    if png:
        return png, None
    keys = _gemini_image_keys()
    if not keys:
        return None, err or "sin_llave_gemini"
    last_err = err
    for pid, key in keys:
        for model in _GEMINI_IMAGE_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                r = httpx.post(url, params={"key": key}, timeout=timeout,
                               json={"contents": [{"parts": [{"text": prompt}]}]})
                if r.status_code in _RETRIABLE:  # modelo retirado / saturado / sin cuota esta llave: prueba la siguiente
                    last_err = f"HTTP {r.status_code}: {r.text[:160]}"
                    _record(pid, error=last_err)
                    continue
                if r.status_code >= 400:
                    err = f"HTTP {r.status_code}: {r.text[:160]}"
                    _record(pid, error=err)
                    return None, err
                j = r.json()
                parts = j.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                for part in parts:
                    data = part.get("inlineData") or part.get("inline_data")
                    if data and data.get("data"):
                        import base64
                        _record(pid)   # cuenta como una "petición" en Ajustes, aunque no sea del chat
                        return base64.b64decode(data["data"]), None
                last_err = "sin_imagen_en_respuesta"
                _record(pid, error=last_err)
            except Exception as e:
                last_err = str(e)[:200]
                _record(pid, error=last_err)
    return None, last_err or "sin_modelo_de_imagen_disponible"


def list_models(p: dict) -> list[str]:
    headers = {"Authorization": f"Bearer {p['api_key']}"} if p.get("api_key") else {}
    try:
        r = httpx.get(f"{url_of(p)}/models", headers=headers, timeout=15)
        r.raise_for_status()
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        if p["kind"] == "openrouter":
            ids = [i for i in ids if i.endswith(":free")]
        return sorted(i for i in ids if i)[:300]
    except Exception as e:
        log.warning("models %s: %s", p["name"], e)
        return []
