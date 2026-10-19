# EDI · Fases de implementación

> Equipo objetivo: MacBook Pro 2015 · Intel Core i7 4 núcleos · 16 GB RAM · macOS Sequoia · 100 GB libres.
> Restricciones: todo gratuito, lo más ligero posible, interacción por voz y texto, respuestas habladas + texto + botón repetir, varias cuentas de correo, memoria de lo que le dices, encendido/apagado con un clic vía Docker.

---

## Fase 0 · Análisis (≈10 min)

**Objetivo:** confirmar que la Mac aguanta y elegir las piezas más ligeras.

```bash
cd ~/Documents/GitHub/EDI
chmod +x scripts/*.sh
./scripts/00_analisis.sh
```

### Decisiones de arquitectura (y por qué)

| Necesidad | Elección | Por qué (vs. alternativas) |
|---|---|---|
| Motor Docker | **Colima** ([abiosoft/colima](https://github.com/abiosoft/colima)) | Gratis, CLI, VM de 2 CPU/3 GB. Docker Desktop consume ~2-4 GB de RAM sólo abierto. Si ya tienes Docker Desktop, EDI lo usa. |
| Servidor | **FastAPI + Uvicorn** ([fastapi/fastapi](https://github.com/fastapi/fastapi)) | Un solo contenedor Python slim (~180 MB), < 80 MB de RAM. |
| Oír (voz → texto) | **Web Speech API del navegador** (Chrome/Safari) | 0 MB, 0 CPU en tu Mac. Respaldo opcional: [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) dentro del contenedor (`WITH_WHISPER=true`). |
| Hablar (texto → voz) | **speechSynthesis** del navegador con voces de macOS (Paulina/Mónica es-MX) | Sin descargas. Docker en Mac **no** tiene acceso a micrófono ni bocinas, por eso la voz vive en el navegador. Alternativa futura: [OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl). |
| Cerebro (IA) | **Groq** gratis → respaldo **Ollama** local → o **sólo reglas** | Tu plan de Claude (Pro) no incluye API, así que se usan opciones gratuitas. Groq responde en < 1 s. [ollama/ollama](https://github.com/ollama/ollama) con `qwen2.5:3b` corre offline en CPU Intel (lento pero funcional). |
| Ahorro de tokens | **Reglas en español primero** (`intents.py`) | Tareas, notas, hora, correo y "repite" se resuelven sin IA. La IA sólo resume correos y conversa, con contexto recortado. |
| Correo multi-cuenta | **IMAP** con [ikvk/imap_tools](https://github.com/ikvk/imap_tools) | Gmail, Yahoo, iCloud, cualquier IMAP con contraseña de aplicación; Outlook con OAuth2 vía [AzureAD/microsoft-authentication-library-for-python](https://github.com/AzureAD/microsoft-authentication-library-for-python). Sólo lectura, nunca marca como leído. |
| Memoria | **SQLite + FTS5** (archivo `data/edi.sqlite3`) | Sin servidor extra; búsqueda de texto completo para "¿qué te dije de…?". |
| Acceso directo | **AppleScript compilado (`osacompile`)** → `EDI.app` en el Escritorio | Nativo de macOS, sin instalar nada. |

Proyectos de referencia que se evaluaron y **por qué no se usaron directamente**:
- [leon-ai/leon](https://github.com/leon-ai/leon): asistente open-source completo, pero pesado (Node + Python + modelos) para una Mac 2015.
- [KoljaB/RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) / [KoljaB/RealtimeTTS](https://github.com/KoljaB/RealtimeTTS): excelentes, pero necesitan audio nativo (no funciona dentro de Docker en Mac).
- [openai/whisper](https://github.com/openai/whisper): faster-whisper es 4× más rápido con la misma calidad en CPU.

### Diagrama

```
 [Tú] ──voz/texto──▶ Ventana EDI (Chrome modo app, localhost:8765)
                      │  SpeechRecognition (oír) · speechSynthesis (hablar) · botón ↻ repetir
                      ▼
            ┌──────── Contenedor Docker "edi" (Colima) ────────┐
            │ FastAPI ─▶ intents.py (reglas, 0 tokens)          │
            │            ├─▶ db.py   SQLite: tareas, notas      │
            │            ├─▶ mail.py IMAP: N cuentas            │
            │            └─▶ llm.py  Groq │ Gemini │ Ollama      │
            │ reminder_loop: recordatorios + correo nuevo (SSE) │
            └───────────────────────────────────────────────────┘
               volúmenes: ./data (memoria)  ./config (cuentas)
```

**Consumo esperado:** contenedor ~80 MB RAM · VM Colima ~600 MB-1 GB reales · ventana Chrome ~200 MB. Total ≈ 1-1.5 GB de tus 16 GB. Con Ollama activo suma ~2.5 GB mientras responde.

---

## Fase 1 · Dependencias (≈20-40 min, casi todo automático)

```bash
./scripts/01_instalar_dependencias.sh            # Homebrew + Colima + Docker CLI + build de EDI
# o, si además quieres IA 100% offline (~2 GB):
./scripts/01_instalar_dependencias.sh --ollama
```

Qué hace, paso a paso:
1. Xcode Command Line Tools (`xcode-select --install`).
2. Homebrew ([Homebrew/brew](https://github.com/Homebrew/brew)). Nota: en Intel, Homebrew 7 pasó a "Tier 3" (sigue funcionando; algunos paquetes pueden compilarse en vez de bajar binario, tarda más).
3. `brew install colima docker docker-compose` y registra el plugin `docker compose`.
4. `colima start --cpu 2 --memory 3 --disk 15`.
5. (Opcional) `brew install ollama && ollama pull qwen2.5:3b`.
6. `docker compose build` de la imagen `edi:latest`.

Verificación: `docker run --rm hello-world` debe imprimir "Hello from Docker!".

---

## Fase 2 · Configuración (≈15 min)

```bash
./scripts/02_configurar.sh
```

1. Tu nombre (cómo te dice EDI).
2. Llave gratis de IA: Groq (https://console.groq.com/keys) o Gemini (https://aistudio.google.com/apikey).
3. Cuentas de correo → contraseñas de aplicación. Guía completa: [CUENTAS_CORREO.md](CUENTAS_CORREO.md).
4. Edita `config/accounts.yaml` y pon `enabled: true` en cada cuenta lista.

Los secretos quedan en `.env` y `config/accounts.yaml` (permisos 600, ignorados por git).

---

## Fase 3 · Desarrollo (ya generado en este repo)

| Módulo | Archivo | Estado |
|---|---|---|
| Configuración | `app/edi/config.py` | ✅ |
| Memoria SQLite (tareas, notas, historial) | `app/edi/db.py` | ✅ |
| Intenciones en español sin IA + fechas naturales ("mañana a las 5", "en media hora", "el viernes") | `app/edi/intents.py` | ✅ probado |
| Correo multi-cuenta IMAP + Outlook OAuth | `app/edi/mail.py`, `app/edi/oauth_ms.py` | ✅ |
| Cliente IA multi-proveedor con respaldo | `app/edi/llm.py` | ✅ |
| Orquestador (cerebro) | `app/edi/agent.py` | ✅ |
| API + recordatorios + avisos en vivo (SSE) | `app/edi/main.py` | ✅ |
| Interfaz voz/texto, palabra clave "EDI", repetir, notificaciones | `app/static/*` | ✅ |
| Whisper local opcional | `app/edi/stt.py` | ✅ opcional |
| Pruebas | `tests/test_intents.py` | ✅ |

Probar: `./scripts/edi.sh test`

---

## Fase 4 · Acceso directo y uso diario

```bash
./scripts/03_crear_acceso_directo.sh
```

- **EDI.app** (Escritorio): enciende Colima → levanta el contenedor → abre la ventana de EDI.
- **Apagar EDI.app**: apaga contenedor + Colima (devuelve la RAM).
- Desde terminal: `./scripts/edi.sh start | stop | restart | status | logs | backup`.

Primera vez en la ventana: acepta el permiso de **micrófono**. Para una voz más natural:
Ajustes del Sistema → Accesibilidad → Contenido leído → Voz del sistema → Administrar voces → Español (México) → **Paulina (Mejorada)**.

### Qué le puedes decir

| Dices | EDI hace | ¿Usa IA? |
|---|---|---|
| "EDI" / "buenos días" / "dame mi resumen" | Saludo + pendientes + correos sin leer (resumen con IA en "resumen") | parcial |
| "¿Tengo correos?" / "revisa mis correos" | Cuenta por cuenta + qué parece importante | sí (resumen corto) |
| "Recuérdame pagar la luz mañana a las 5" | Tarea con aviso hablado a esa hora | no |
| "Tengo que ir al banco el viernes" | Tarea con fecha | no |
| "Recuerda que el wifi está en el cajón" | Lo guarda en memoria | no |
| "¿Qué te dije del wifi?" | Lo busca en memoria | no/poca |
| "Mis tareas" / "Ya hice pagar la luz" / "Borra la tarea 3" | Gestiona pendientes | no |
| "Repite" o botón ↻ | Repite la última respuesta | no |
| Cualquier otra pregunta | Conversa | sí |

---

## Fase 5 · Mejoras futuras (roadmap)

Cada una tiene un prompt listo para Claude Code en [`CLAUDE.md`](../CLAUDE.md).
1. Calendario (Google Calendar por CalDAV/ICS) en el resumen diario.
2. Clasificar correos importantes con reglas por remitente (sin IA).
3. "Lee el correo de X" y "crea tarea de este correo".
4. Voz neural local con Piper dentro del contenedor (sirve audio al navegador).
5. Resumen matutino automático al encender la Mac (LaunchAgent).
6. Telegram bot gratuito para hablar con EDI desde el celular.
