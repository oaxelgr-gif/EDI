"""Proveedores de IA (todos compatibles con el formato OpenAI /chat/completions).

EDI los prueba en orden de prioridad: si uno se queda sin cuota (429), falla o tarda,
pasa al siguiente. Así puedes sumar varias llaves gratuitas y OmniRoute como pivote.
"""
import logging
import time

import httpx

from . import config, db

log = logging.getLogger("edi.providers")

KINDS = {
    "omniroute":  {"label": "OmniRoute (tu pivote local)", "base_url": "http://host.docker.internal:20128/v1",
                   "model": "auto/best-free", "key_url": "http://localhost:20128"},
    "groq":       {"label": "Groq", "base_url": "https://api.groq.com/openai/v1",
                   "model": "llama-3.1-8b-instant", "key_url": "https://console.groq.com/keys"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",
                   "model": "meta-llama/llama-3.3-70b-instruct:free", "key_url": "https://openrouter.ai/keys"},
    "gemini":     {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                   "model": "gemini-2.5-flash", "key_url": "https://aistudio.google.com/apikey"},
    "custom":     {"label": "Otro compatible con OpenAI", "base_url": "", "model": "", "key_url": ""},
}

SYSTEM = (
    "Eres EDI, la asistente personal de {user}, con el estilo de una IA de nave espacial: precisa, cálida, "
    "con humor seco ocasional. Responde SIEMPRE en español de México, en 1 a 4 frases cortas, sin markdown, "
    "listas ni emojis, porque se leerá en voz alta. Usa los datos que te den; nunca inventes correos ni tareas."
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


def add(name, kind, base_url, api_key, model, priority=10, enabled=1) -> int:
    k = KINDS.get(kind, KINDS["custom"])
    return db.run("INSERT INTO providers(name, kind, base_url, api_key, model, priority, enabled, created) "
                  "VALUES (?,?,?,?,?,?,?,?)",
                  (name or k["label"], kind, (base_url or k["base_url"]).rstrip("/"), api_key or "",
                   model or k["model"], int(priority), int(enabled), db.iso()))


def update(pid: int, data: dict) -> bool:
    fields = {k: data[k] for k in ("name", "kind", "base_url", "model", "priority", "enabled") if k in data}
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
    r = httpx.post(f"{p['base_url']}/chat/completions", headers=headers, timeout=timeout,
                   json={"model": p["model"], "messages": messages, "max_tokens": max_tokens, "temperature": temperature})
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    j = r.json()
    text = (j["choices"][0]["message"].get("content") or "").strip()
    return text, int((j.get("usage") or {}).get("total_tokens") or 0)


def active():
    return [p for p in list_all() if p["enabled"] and (p["api_key"] or p["kind"] in ("omniroute", "custom"))]


def chat(user_text: str, context: str = "", history=None, max_tokens: int | None = None) -> tuple[str | None, str | None]:
    """Regresa (respuesta, nombre_del_proveedor) o (None, None) si todos fallaron."""
    s = db.all_settings()
    messages = [{"role": "system", "content": SYSTEM.format(user=s["user_name"])}]
    if context:
        messages.append({"role": "system", "content": "Datos disponibles:\n" + context[:6000]})
    for m in (history or [])[-int(s["llm_history"] or 6):]:
        messages.append({"role": "assistant" if m["role"] == "edi" else "user", "content": m["text"][:500]})
    messages.append({"role": "user", "content": user_text})
    for p in active():
        t0 = time.time()
        try:
            text, tokens = call(p, messages, max_tokens or int(s["llm_max_tokens"]), float(s["llm_temperature"]))
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
        text, tokens = call(p, [{"role": "user", "content": "Responde sólo: Sistemas en línea."}], 20, 0, timeout=20)
        return {"ok": True, "reply": text, "ms": int((time.time() - t0) * 1000), "tokens": tokens}
    except Exception as e:
        return {"ok": False, "error": str(e)[:240], "ms": int((time.time() - t0) * 1000)}


def list_models(p: dict) -> list[str]:
    headers = {"Authorization": f"Bearer {p['api_key']}"} if p.get("api_key") else {}
    try:
        r = httpx.get(f"{p['base_url']}/models", headers=headers, timeout=15)
        r.raise_for_status()
        ids = [m.get("id", "") for m in r.json().get("data", [])]
        if p["kind"] == "openrouter":
            ids = [i for i in ids if i.endswith(":free")]
        return sorted(i for i in ids if i)[:300]
    except Exception as e:
        log.warning("models %s: %s", p["name"], e)
        return []
