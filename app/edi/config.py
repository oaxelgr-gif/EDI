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
IMAGES_DIR = DATA_DIR / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# v0.8: carpeta autorizada para que EDI lea/resuma/edite archivos y programe (nunca el disco completo).
# Por defecto una carpeta propia dentro de data/; en docker-compose puedes montar ahí la carpeta real que
# quieras darle, p.ej. ~/Documents/EDI-files, con EDI_FILES_DIR.
FILES_DIR = Path(_env("EDI_FILES_DIR", str(DATA_DIR / "files")))
FILES_DIR.mkdir(parents=True, exist_ok=True)

TIMEZONE = _env("TZ", "America/Mexico_City")
MS_CLIENT_ID = _env("MS_CLIENT_ID")
WHISPER_MODEL = _env("WHISPER_MODEL", "base")

# Valores por defecto de los ajustes editables desde la interfaz
DEFAULT_SETTINGS = {
    "sync_minutes": "10",          # cada cuánto se sincronizan Jira/GitHub/Slack (0 = sólo manual)
    "user_name": _env("EDI_USER_NAME", "jefe"),
    "llm_max_tokens": _env("LLM_MAX_TOKENS", "350"),
    "llm_history": "10",        # mensajes de contexto que recuerda en la plática (antes 6: más memoria = charla más natural)
    "llm_temperature": "0.65",  # antes 0.4: más calidez y variedad en cómo contesta, menos "de manual"
    "mail_max_per_account": _env("MAIL_MAX_PER_ACCOUNT", "15"),
    "mail_check_minutes": _env("MAIL_CHECK_MINUTES", "15"),
    "home_city": _env("EDI_CITY", "Querétaro"),
    "theme": "auto",
    "tts_pitch": "+2Hz",
    "tts_engine": "edge",                # edge (voz neural en línea) | browser
    "tts_voice": "es-MX-DaliaNeural",
    "tts_rate": "+6%",
}

# Proveedores que se crean solos la primera vez si hay llave en .env
ENV_PROVIDERS = [
    {"name": "OmniRoute", "kind": "omniroute", "base_url": _env("OMNIROUTE_URL", "http://host.docker.internal:20128/v1"),
     "api_key": _env("OMNIROUTE_API_KEY"), "model": _env("OMNIROUTE_MODEL", "auto/best-free")},
    {"name": "Groq", "kind": "groq", "api_key": _env("GROQ_API_KEY"), "model": _env("GROQ_MODEL", "llama-3.3-70b-versatile")},
    {"name": "OpenRouter", "kind": "openrouter", "api_key": _env("OPENROUTER_API_KEY"),
     "model": _env("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")},
    {"name": "Gemini", "kind": "gemini", "api_key": _env("GEMINI_API_KEY"), "model": _env("GEMINI_MODEL", "gemini-2.5-flash")},
]
