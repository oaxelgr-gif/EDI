"""Configuración base. Los valores del .env son sólo el arranque inicial:
todo lo que cambies en Ajustes (interfaz) se guarda en SQLite y tiene prioridad."""
import os
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DATA_DIR = Path(_env("EDI_DATA_DIR", "/data"))
CONFIG_DIR = Path(_env("EDI_CONFIG_DIR", "/config"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "edi.sqlite3"
ACCOUNTS_FILE = CONFIG_DIR / "accounts.yaml"
MS_TOKEN_CACHE = DATA_DIR / "ms_token_cache.json"
TTS_CACHE = DATA_DIR / "tts"

TIMEZONE = _env("TZ", "America/Mexico_City")
MS_CLIENT_ID = _env("MS_CLIENT_ID")
WHISPER_MODEL = _env("WHISPER_MODEL", "base")

# Valores por defecto de los ajustes editables desde la interfaz
DEFAULT_SETTINGS = {
    "user_name": _env("EDI_USER_NAME", "jefe"),
    "llm_max_tokens": _env("LLM_MAX_TOKENS", "350"),
    "llm_history": "6",
    "llm_temperature": "0.4",
    "mail_max_per_account": _env("MAIL_MAX_PER_ACCOUNT", "15"),
    "mail_check_minutes": _env("MAIL_CHECK_MINUTES", "15"),
    "tts_engine": "edge",                # edge (voz neural en línea) | browser
    "tts_voice": "es-MX-DaliaNeural",
    "tts_rate": "+0%",
}

# Proveedores que se crean solos la primera vez si hay llave en .env
ENV_PROVIDERS = [
    {"name": "OmniRoute", "kind": "omniroute", "base_url": _env("OMNIROUTE_URL", "http://host.docker.internal:20128/v1"),
     "api_key": _env("OMNIROUTE_API_KEY"), "model": _env("OMNIROUTE_MODEL", "auto/best-free")},
    {"name": "Groq", "kind": "groq", "api_key": _env("GROQ_API_KEY"), "model": _env("GROQ_MODEL", "llama-3.1-8b-instant")},
    {"name": "OpenRouter", "kind": "openrouter", "api_key": _env("OPENROUTER_API_KEY"),
     "model": _env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")},
    {"name": "Gemini", "kind": "gemini", "api_key": _env("GEMINI_API_KEY"), "model": _env("GEMINI_MODEL", "gemini-2.5-flash")},
]
