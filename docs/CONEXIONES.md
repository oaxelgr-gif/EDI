# Conexiones de trabajo (v0.5)

EDI une tus herramientas de trabajo con tus pendientes. Se configuran en **Ajustes → Conexiones**.

| Herramienta | Qué hace EDI | Qué necesitas |
|---|---|---|
| **Jira Cloud** (empresa.atlassian.net) | Trae lo asignado a ti como pendientes de trabajo (con fecha y prioridad), marca hechos los que se cierran, crea / mueve / comenta tickets por voz. | Tu correo + API token: https://id.atlassian.com/manage-profile/security/api-tokens |
| **Jira Server / Data Center** (jira.empresa.com) | Lo mismo. | Token personal (PAT) en tu perfil de Jira, o usuario + contraseña. Si es por VPN, conéctate a la VPN. |
| **GitHub** (y Lovable vía su repo) | PRs que te piden revisar e issues asignados como pendientes; estado de tus PRs y del último build. | Token personal: https://github.com/settings/tokens |
| **Slack** | Lee menciones y mensajes directos, envía mensajes con confirmación, y cada mensaje que marques con ✅ se vuelve pendiente. | Token de usuario (xoxp-) de una app propia en https://api.slack.com/apps con permisos `search:read reactions:read users:read channels:read groups:read im:read im:history channels:history groups:history chat:write im:write`. Si tu Slack lo administra otra persona, pídele que apruebe la app. |

## Reglas
- **Jira manda en los tickets.** Si editas (título, fecha, descripción) o terminas en EDI un pendiente que viene de Jira, el cambio también se hace en Jira.
- Todo lo que cambia algo afuera (crear/mover/comentar ticket, mandar Slack) se prepara como **borrador** y se ejecuta sólo cuando dices «sí / créalo / envíalo» o tocas el botón.
- La sincronización corre sola cada 10 minutos (configurable) y con «Sincronizar».
- Los tokens se guardan sólo en tu Mac (data/edi.sqlite3) y nunca se muestran en la interfaz.

## Comandos de voz
- «¿Qué tickets tengo?» · «¿Cómo va EDI-12?» · «Sincroniza Jira»
- «Crea un ticket arreglar el login para el viernes» · «Crea un ticket en el proyecto WEB …»
- «Mueve EDI-12 a en curso» · «Termina EDI-12» · «Inicia EDI-15» · «Comenta en EDI-12 que ya quedó»
- «¿Qué PRs tengo?» · «¿Pasó el build de la app?»
- «Mándale un Slack a Ana diciendo …» · «Escribe en el canal #general que …» · «¿Tengo mensajes en Slack?»
- «Agrega un pendiente de trabajo …» (si no dices «de trabajo», queda como personal)

## Para desarrolladores
- `app/edi/connectors/` — un módulo por herramienta (`jira.py`, `github.py`, `slack.py`) sobre `base.py`.
  Agregar otra = nueva clase `Connector` con `FIELDS`, `test()`, `sync()` y registrarla en `connectors/__init__.py`.
- `app/edi/work.py` — reglas pendientes ↔ Jira (editar, terminar, subir a Jira).
- `app/edi/work_voice.py` — comandos de voz y ejecución de borradores de trabajo.
- `app/edi/api/connections.py` — CRUD, prueba y sincronización.
