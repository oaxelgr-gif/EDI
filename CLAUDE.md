# CLAUDE.md — Guía para que Claude (Code) desarrolle EDI

Este archivo lo lee Claude Code automáticamente al abrir el repo. Contiene el contexto, las reglas y prompts listos para seguir construyendo EDI.

## Contexto del proyecto
- **EDI**: asistente personal estilo JARVIS, en español de México. Voz + texto de entrada; respuesta hablada + texto + opción de repetir.
- **Funciones núcleo:** pendientes/tareas con recordatorios, memoria de lo que el usuario le dice, lectura de VARIAS cuentas de correo (sólo lectura), conversación.
- **Equipo:** MacBook Pro 2015, Intel i7 4 núcleos, 16 GB RAM, macOS Sequoia, ~100 GB libres. Docker vía **Colima**.
- **Presupuesto:** $0. El usuario tiene Claude Pro (sin API). IA en runtime: sólo modelos gratuitos EN LÍNEA (nada local/Ollama): OmniRoute (pivote del usuario, puerto 20128) → Groq → OpenRouter :free → Gemini.
- **Diseño UI:** consola de la Normandy (Mass Effect): tinta violeta `#16141f`, ámbar `#f2b661` = EDI habla, verde agua `#8fd3c7` = escucha. Newsreader (respuestas de EDI) + Onest (interfaz). El anillo de voz es el único elemento protagonista.
- **Arranque:** `EDI.app` en el Escritorio → `scripts/edi.sh start` → Colima → `docker compose up` → Chrome en modo app en `http://localhost:8765`.

## Reglas de diseño (respetarlas siempre)
1. **Ligero primero.** Nada de frameworks pesados (LangChain, Electron, React build). Sin dependencias nuevas salvo que sean pequeñas y puras.
2. **0 tokens cuando se pueda.** Toda orden reconocible va a `app/edi/intents.py` (regex en español). La IA sólo para resumir o conversar, con contexto recortado (`mail.compact_for_llm`, máx. 6 mensajes de historial, `LLM_MAX_TOKENS`).
3. **Audio en el navegador.** Docker en Mac no tiene micrófono/bocinas. STT = Web Speech API; TTS = MP3 de `/api/tts` (edge-tts) reproducido por el navegador, con respaldo speechSynthesis.
4. **Respuestas para oírse:** 1-4 frases, sin markdown ni emojis, en español de México.
5. **Correo sólo lectura:** `mark_seen=False` siempre. Una cuenta con error nunca rompe a las demás.
6. **Secretos** sólo en `.env` y `config/accounts.yaml` (ignorados por git). Nunca imprimirlos en logs.
7. **Todo en la carpeta del repo**; datos persistentes en `./data`.

## v0.3 (estado actual)
- **Red local:** `edi.serve` levanta 8000 (HTTP, sólo localhost:8765) y 8443 (HTTPS autofirmado, publicado en :8766). `security.PinMiddleware` exige PIN en HTTPS. `EDI_LAN_HOST` lo pone `scripts/edi.sh` en `.env`.
- **Herramientas web sin llave:** `web.py` (tipo de cambio open.er-api, clima open-meteo, búsqueda DuckDuckGo + Wikipedia). Intents `exchange`, `weather`, `search`.
- **Modelos retirados:** `providers.call_healing` cambia de modelo solo si el proveedor responde model_not_found.
- **UI:** liquid glass morado neón, tema auto/oscuro/claro (`data-theme`), vistas en `static/js/views/*`, guía en `views/guide.js`.
- **EDI Helper:** `helper/EDIHelper.swift` (AppKit + Speech + AVFoundation + Carbon). Barra de menú, “Hey EDI”, ⌥Espacio, HUD. Se compila en la Mac con `scripts/04_instalar_helper.sh` (log en `data/helper-build.log`).

## Mapa del código
| Archivo | Responsabilidad |
|---|---|
| `app/edi/config.py` | Variables de entorno |
| `app/edi/db.py` | SQLite: `tasks`, `notes` (+FTS5), `messages`, `mail_seen` |
| `app/edi/intents.py` | `detect(text, now) -> Intent`, `parse_when()` fechas en español |
| `app/edi/agent.py` | `handle(text) -> {reply, intent, data}` — orquestador |
| `app/edi/mail.py` | `load_accounts()`, `fetch_unread()`, presets IMAP |
| `app/edi/oauth_ms.py` | OAuth2 device-code para Outlook |
| `app/edi/providers.py` | Proveedores IA en BD (OmniRoute/Groq/OpenRouter/Gemini/custom), rotación por prioridad, uso diario |
| `app/edi/tts.py` | Voz neural en línea con edge-tts + caché |
| `app/edi/api/*.py` | Rutas por área: chat (sesiones), memory, mail (cuentas), settings (proveedores), voice, events (SSE) |
| `app/edi/main.py` | Ensambla routers y arranque |
| `app/static/js/` | ES modules sin build: `main.js` (router hash), `api.js`, `store.js`, `voice/*` (speaker, listener, orb), `views/*` |
| `app/static/css/` | `tokens.css` (paleta/tipos), `base`, `shell`, `chat`, `views` |
| `scripts/edi.sh` | start/stop/logs/rebuild/outlook/test/backup |

## Cómo agregar una capacidad nueva (receta)
1. Regla en `RULES` de `intents.py` (y `STRIP` si hay que limpiar el texto).
2. Rama `elif n == "nueva":` en `agent.handle()` que devuelva `reply` corto.
3. Si necesita datos, función en un módulo nuevo `app/edi/<tema>.py`.
4. Prueba en `tests/test_intents.py`.
5. `./scripts/edi.sh rebuild && ./scripts/edi.sh test`.

## Comandos útiles
```bash
./scripts/edi.sh start|stop|restart|status|logs|rebuild|test
docker compose run --rm edi python -c "from edi import mail; print(mail.fetch_unread())"
```

## Roadmap con prompts listos (cópialos a Claude Code)

**R1 · Calendario**
> Agrega a EDI lectura de Google Calendar usando la URL privada ICS (variable `CALENDAR_ICS_URLS`, varias separadas por coma) con la librería `icalendar`. Nueva intención "qué tengo en mi agenda (hoy|mañana|esta semana)" e inclúyelo en el resumen del día. Sin OAuth, sin IA.

**R2 · Correos importantes sin IA**
> En `config/accounts.yaml` agrega `vip: [correos o dominios]` y `ignorar: [...]`. En `mail.py` marca `important=True` por remitente/palabras ("urgente", "factura", "pago", "entrega"). EDI menciona primero los importantes y omite los ignorados.

**R3 · Leer y convertir correos en tareas**
> Intención "lee el correo de <remitente>" (lee asunto + 300 caracteres) y "crea una tarea de ese correo" (usa el último correo leído, `source='correo'`).

**R4 · Voz neural local**
> Servicio opcional en docker-compose con Piper (https://github.com/OHF-Voice/piper1-gpl) y la voz `es_MX-claude-high` o `es_MX-ald-medium`. Endpoint `/api/tts` que devuelve WAV; en `app.js` un ajuste "Voz: navegador | Piper". Mantener el navegador como predeterminado.

**R5 · Resumen al iniciar sesión**
> Crea `scripts/04_autoarranque.sh` que instale un LaunchAgent (`~/Library/LaunchAgents/com.edi.start.plist`) para ejecutar `edi.sh start` al iniciar sesión, con opción para desinstalarlo.

**R6 · EDI en el celular (Telegram, gratis)**
> Agrega `app/edi/telegram_bot.py` usando sólo httpx (long polling a la Bot API) con `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`. Reenvía cada mensaje a `agent.handle()` y manda los recordatorios también por Telegram. Arráncalo como tarea asyncio en `main.py` si hay token.

**R7 · Memoria más inteligente**
> Cuando el usuario diga algo con "mi/mis" + dato ("mi cumpleaños es…", "mi jefe se llama…"), sugiere guardarlo como nota. Agrega comando "olvida todo sobre X".

## v0.4 — envío de correo y WhatsApp
- `app/edi/drafts.py`: intenciones de enviar/responder correo y WhatsApp → borrador en tabla `drafts`; sólo se envía con «envíalo»/botón (caduca 15 min).
- `app/edi/mail.py`: `mark_read`, `mark_all_read`, `send` (SMTP con la contraseña de aplicación).
- `whatsapp/` (Node 22 + Baileys) es un segundo servicio de compose; `app/edi/whatsapp.py` es su cliente. Sesión en `data/whatsapp/`.
- Interfaz: `ui/composer.js` (redactor + tarjeta de borrador), `views/whatsapp.js`.

## v0.5 — trabajo (Jira, GitHub, Slack) y CRUD completo
- Pendientes con `category` (personal/trabajo), `notes`, `priority`, `link`, y enlace externo (`conn_id`, `ext_key`, `ext_status`).
- `app/edi/connectors/` (Jira Cloud y Server/DC, GitHub, Slack) · `work.py` · `work_voice.py` · `api/connections.py`. Ver docs/CONEXIONES.md.
- Notas editables (FTS con trigger de UPDATE), conversaciones renombrables, borradores con canales jira_create/jira_move/jira_comment/slack.
