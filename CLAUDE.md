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

## v0.6 — acceso remoto por Tailscale y sincronización al instante
- `app/edi/tailnet.py`: CLI de Tailscale.app (`ip -4`, `status --json`, `serve`). `python -m edi.tailnet env|status|off`. Sin Tailscale todo queda vacío.
- `scripts/edi.sh start` guarda `EDI_TS_HOST`, `EDI_TS_DNS`, `EDI_TS_URL`, `EDI_TS_ENABLE_URL` en `.env`. `tailscale serve` → `127.0.0.1:8768` (`EDI_TS_PORT`, siempre con PIN).
- `serve.py`: certificado con IP Wi‑Fi + IP/MagicDNS de Tailscale; vigila la red cada 2 min y recarga el certificado en caliente.
- `security.py`: cookie `<dispositivo>.<firma>`, tabla `devices`, 5 fallos = 5 min, `logout_all()`; la cookie anterior se acepta y se actualiza.
- `live.py`: `db.conn()` detecta las tablas escritas (autorizador de SQLite) y emite `{"type":"changed","kinds":[...],"origin":<X-EDI-Client>}` por `/api/events`. En el front, `main.js → onChanged` refresca contadores y `view.refresh(kinds)`; `ui/live.js → whenIdle` no redibuja mientras escribes.
- Pruebas: `tests/test_remote.py`.

## v0.7 — logo definitivo y plática más humana (0 tokens extra)
- **Logo:** nuevo ícono (toro plateado estilizado con "E"/"I" integradas) sobre fondo degradado violeta, generado a partir del arte final del usuario. Reemplaza `app/static/icon.svg`, `app/static/icon-512.png`, `app/static/icon-192.png`, `app/static/apple-touch-icon.png`, `assets/edi-icon.svg`, y suma `app/static/favicon.ico` como respaldo. Como `icon.svg`/`edi-icon.svg` son la fuente única para el favicon, el login y los íconos nativos (`scripts/03_crear_acceso_directo.sh`, `scripts/04_instalar_helper.sh` vía qlmanage+sips), basta con haber reemplazado esos dos SVG — vuelve a correr esos scripts (o reinstala) para que el Dock/menú recojan el ícono nuevo.
- **`app/edi/phrasing.py` (nuevo, 0 tokens):** banco de variantes de frase para las respuestas de reglas (guardar/duplicar/completar/borrar pendiente, guardar/olvidar nota, sin proveedores de IA, seguimiento de fecha). `phrasing.pick_for(session_id, categoria, opciones)` elige al azar sin repetir la frase anterior en esa sesión+categoría. Cableado en `agent.py` en todos esos puntos para que EDI no conteste siempre con la misma oración exacta.
- **`app/edi/providers.py` → `SYSTEM`:** prompt reescrito para que la plática con IA suene menos robotizada: español de México coloquial, sin repetir muletillas de apertura, sin preámbulos vacíos, puede traer pendientes/notas relevantes a la plática de forma natural en vez de leer un reporte. Los límites de seguridad (nunca decir que ya envió/guardó algo ella misma, WhatsApp/correo sólo con borrador confirmado, nunca preguntar el canal) se mantienen igual.
- **`app/edi/config.py` + `db.py`:** `llm_history` 6→10 y `llm_temperature` 0.4→0.65 (más memoria de conversación y más calidez); migración en `db.init()` que sube instalaciones ya existentes sólo si nunca cambiaste esos ajustes a mano.
- Pruebas: `tests/test_phrasing.py`.

## v0.8 — los 7 frentes: cerebro sin reglas fijas, memoria automática, voz fluida, imágenes, archivos y multi-IA
- **F1 · Cerebro sin reglas fijas (`agent._brain`):** cuando el texto no cae en una regla fija de `intents.py` ni en un borrador pendiente, `agent.handle()` llama a `_brain(text, session_id, now)` en vez del viejo `_memo_fallback`. `_brain` construye contexto (`profile.context_snippet()` + pendientes + notas + apodos + historial) y hace **una sola llamada** a `providers.chat(text, context=ctx, system=BRAIN_PROMPT, max_tokens=320)` con un prompt que pide JSON: `{"action": "...", ...}` donde `action` es uno de `add_task|add_note|complete_task|delete_task|wa_read|wa_summary|image|file_summary|file_edit|chat`. Si `action=="chat"`, el propio campo `reply` del JSON es la respuesta — así una plática normal sigue costando 1 llamada, no 2. Esto resuelve el bug de "lee lo que me escribió apa": antes dependía de que el regex de WhatsApp reconociera la frase exacta; ahora el cerebro entiende la intención con contexto.
- **F2 · Memoria automática + entrevista inicial (`app/edi/profile.py`, nuevo):** tabla `profile_facts` (nombre/ocupación/proyectos/notas_perfil). La primera vez que no hay nada guardado, EDI hace 3 preguntas cortas (`profile.onboarding_step`), saltables diciendo "paso"/"después" (`SKIP_ONBOARD`). Además, **0 tokens**: `profile.learn_from_text()` detecta por regex frases tipo "soy programador" o "mi proyecto es X" en cualquier charla normal y las guarda solas, sin IA. `profile.context_snippet()` inyecta esos datos al prompt del cerebro para que EDI hable con contexto real del usuario.
- **F3 · Voz fluida (`views/chat.js`):** si la respuesta real tarda más de 700 ms, EDI dice una muletilla corta al azar ("mmm, déjame ver...", "a ver, un segundo...") mientras llega — nunca silencio absoluto. Se cancela sola en cuanto llega la respuesta real o hay error.
- **F4 · Rediseño:** logo (`icon.svg`) ahora arriba a la izquierda en la barra superior (`.brand-logo`) y en el drawer como imagen, no un círculo CSS. Tipografía Newsreader (serif, itálica en el saludo vacío) para las respuestas de EDI, dándole más carácter frente a la interfaz Onest.
- **F5 · Generación de imágenes (`providers.generate_image`):** llama directo a `gemini-2.5-flash-image:generateContent` (no el endpoint OpenAI-compatible, que no expone imagen) con la misma `GEMINI_API_KEY`. El cerebro detecta `action=="image"`, guarda el PNG en `IMAGES_DIR` (servido en `/api/images/...`) y la respuesta incluye `data.image_url`; el frontend la pinta inline en el chat (`img.generated`). Sin llave de Gemini, responde pidiendo configurarla en Ajustes → Inteligencia.
- **F6 · Acceso a archivos de la Mac (`app/edi/files.py`, nuevo):** una sola carpeta autorizada (`EDI_FILES_DIR`, por defecto `./data/files` dentro del repo — cámbiala en `docker-compose.yml` por una carpeta real como `~/Documents/EDI-files`). `_safe()` bloquea cualquier intento de salir de esa carpeta. Lee PDF/Word/texto/código, resume con IA (`files.summarize`), y las ediciones (`files.propose_edit`) **nunca tocan el original**: generan un diff y una tabla `file_edits` pendiente; sólo al confirmar («sí»/«adelante») se escribe un archivo hermano `<nombre>_EDI.<ext>` — el original queda intacto siempre, incluso si se descarta.
- **F7 · Varios proveedores de IA con enrutador por tarea (`providers.py`):** se pueden agregar ChatGPT/OpenAI, Claude/Anthropic y DeepSeek desde Ajustes → Inteligencia (todos hablan el formato `/chat/completions` tipo OpenAI). Cada proveedor tiene un `tag` (`chat`/`code`/`image`) y `providers.active(tag=...)` prioriza el proveedor marcado para esa tarea antes de caer en la rotación normal (OmniRoute → Groq → OpenRouter → Gemini). Siguen sin ser gratis como los de siempre, pero si ya tienes cuenta en alguno EDI lo puede usar igual, sobre todo para código.
- **Pendiente de tu parte (no se pudo probar fuera de tu Mac):** `./scripts/edi.sh rebuild` (nuevas dependencias `pypdf` y `python-docx`); una `GEMINI_API_KEY` configurada si quieres imágenes; revisar visualmente el logo/tipografía nueva y el timing de las muletillas de voz; y, si quieres que EDI lea archivos reales, editar el volumen `./data/files:/files` en `docker-compose.yml` apuntando a tu carpeta.
- Pruebas: `tests/test_brain.py` (cerebro, onboarding, imágenes, edición de archivos).
