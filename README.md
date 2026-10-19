# EDI — tu asistente personal (voz + texto), ligero y gratuito

EDI revisa **todas tus cuentas de correo**, te dice tus **pendientes**, **recuerda** lo que le pidas y te **avisa en voz alta** a la hora indicada. Le hablas o le escribes; responde con voz, texto en pantalla y botón **↻ repetir**.

Corre en un solo contenedor Docker (~80 MB de RAM) en tu Mac y se enciende con doble clic en el Escritorio.

## Instalación rápida (en Terminal)

```bash
cd ~/Documents/GitHub/EDI
chmod +x scripts/*.sh
./scripts/00_analisis.sh               # Fase 0: ¿mi Mac puede?
./scripts/01_instalar_dependencias.sh  # Fase 1: verifica Docker Desktop y construye EDI (--ollama para IA offline)
./scripts/02_configurar.sh             # Fase 2: nombre, IA gratis, cuentas de correo
./scripts/03_crear_acceso_directo.sh   # Fase 4: EDI.app y "Apagar EDI.app" en el Escritorio
```

Doble clic en **EDI.app** → acepta el micrófono → di *"EDI, dame mi resumen"*.

## Uso diario

| Acción | Cómo |
|---|---|
| Encender | Doble clic en `EDI.app` (o `./scripts/edi.sh start`) |
| Apagar y liberar RAM | Doble clic en `Apagar EDI.app` (o `./scripts/edi.sh stop --all`) |
| Hablar | Botón 🎙, `Ctrl+Espacio`, o activa **Escucha "EDI"** y di *"EDI, …"* |
| Repetir | Di *"repite"*, botón **↻ Repetir** o el ↻ de cada mensaje |
| Callar | `Esc` o 🔊 |
| Ver registros | `./scripts/edi.sh logs` |
| Respaldo | `./scripts/edi.sh backup` |

Ejemplos: *"recuérdame pagar la luz mañana a las 5"*, *"recuerda que el wifi está en el cajón"*, *"¿qué te dije del wifi?"*, *"¿tengo correos?"*, *"mis tareas"*, *"ya hice pagar la luz"*.

## Configurar desde la interfaz (v0.2)
- **Ajustes → Inteligencia:** agrega OmniRoute, Groq, OpenRouter, Gemini o cualquier API compatible con OpenAI. Ordena prioridades; si uno falla o se queda sin cuota, EDI usa el siguiente. Verás peticiones y tokens del día.
- **Ajustes → Correos:** formulario para registrar cada cuenta con su contraseña de aplicación y botón **Probar conexión**. También puedes decirle a EDI *"agrega una cuenta de correo"*.
- **Ajustes → Voz:** voz neural gratuita en línea (Dalia, Jorge y más) con velocidad ajustable.
- **Menú lateral:** conversaciones anteriores, Pendientes, Memoria y Correo.

## Documentación
- [docs/FASES.md](docs/FASES.md) — fases, arquitectura, decisiones y repos de referencia.
- [docs/CUENTAS_CORREO.md](docs/CUENTAS_CORREO.md) — Gmail, Yahoo, iCloud, Outlook, IMAP.
- [CLAUDE.md](CLAUDE.md) — guía para que Claude Code siga desarrollando EDI.

## Estructura
```
EDI/
├── app/edi/          # backend Python (FastAPI)
├── app/static/       # interfaz de voz/texto
├── config/           # accounts.yaml (tus cuentas, no se sube a git)
├── data/             # memoria SQLite y tokens (no se sube a git)
├── scripts/          # instalación, arranque, acceso directo
├── tests/
├── Dockerfile · docker-compose.yml · .env.example
```

## Solución de problemas
- **No oye:** usa Chrome o Safari; Ajustes del Sistema → Privacidad → Micrófono → permite Chrome.
- **No habla:** haz un clic en la ventana (los navegadores exigen un clic antes del primer audio) o revisa 🔊.
- **"No logro comunicarme con mi servidor":** `./scripts/edi.sh status` y `./scripts/edi.sh logs`.
- **Homebrew dice "only supported on Apple Silicon":** normal en Mac Intel; EDI usa Docker Desktop y no necesita Homebrew.
- **Colima no arranca:** `colima delete && colima start --cpu 2 --memory 3 --disk 15`.
- **Ollama no responde desde Docker:** `launchctl setenv OLLAMA_HOST 0.0.0.0` y reinicia Ollama (`brew services restart ollama`).
- **Error de permisos en `data/`:** en `~/.colima/default/colima.yaml` asegúrate de que tu carpeta de inicio esté montada con `writable: true` y ejecuta `colima restart`.
