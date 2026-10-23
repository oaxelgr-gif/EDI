# Guía de uso de EDI

## 1. Encender y apagar
| Qué | Cómo |
|---|---|
| Encender | Doble clic en **EDI.app** (Escritorio). Verás una ventana con el progreso y el tiempo restante. |
| Apagar | Doble clic en **Apagar EDI.app**, o menú ◎ → *Apagar servidor*. |
| Siempre disponible | Instala **EDI Helper** una vez (doble clic en `Instalar EDI Helper.command`). Queda el ícono ◎ en la barra de menú y se abre solo al iniciar sesión. |

## 2. Hablarle
- **Desde cualquier app:** di **“Hey EDI”** (o solo “EDI”) y tu orden, o pulsa **⌥ + Espacio**. Aparece una burbuja arriba a la derecha y EDI contesta en voz alta.
- **En la ventana de EDI:** toca el anillo o el micrófono, o escribe.
- **Repetir:** di “repite” o toca ↻.

## 3. Qué le puedes pedir
| Dices | EDI |
|---|---|
| “Dame mi resumen” | Pendientes + correos sin leer |
| “Recuérdame pagar la luz mañana a las 5” | Crea el pendiente y te avisa a esa hora |
| “Quiero que me recuerdes el viernes ver lo del regalo” | Igual, con lenguaje natural |
| “Mis tareas” / “Ya hice pagar la luz” | Lista / tacha |
| “Recuerda que el wifi está debajo del módem” | Lo guarda en Memoria |
| “¿Qué te dije del wifi?” | Lo busca |
| “¿Tengo correos?” | Revisa todas tus cuentas |
| “Búscame el precio del dólar” | Tipo de cambio al momento |
| “¿Cómo está el clima en Querétaro?” / “¿Va a llover mañana?” | Clima actual o de mañana |
| “Busca quién ganó el partido del América” | Busca en la web y resume, con fuentes |
| “Agrega una cuenta de correo” | Abre el formulario de correos |
| “Agrega una llave de OmniRoute” | Abre Ajustes → Inteligencia |

## 4. Usarlo en el celular u otra computadora
1. En EDI: **Ajustes → Dispositivos** (o menú ◎ → *Usar en el celular…*).
2. Escanea el **QR** con el celular conectado al mismo Wi‑Fi.
3. El navegador avisará que la conexión “no es privada”: es tu Mac con un certificado local. Elige **Avanzado → Continuar** (iPhone: *Mostrar detalles → visitar este sitio*).
4. Escribe el **PIN** de 6 dígitos.
5. Para tenerlo como app: Safari → Compartir → *Agregar a pantalla de inicio* · Chrome → *Instalar app*.

## 4b. Usar EDI fuera de casa (Tailscale)
Con **Tailscale** (gratis, hasta 100 dispositivos) tu iPhone llega a EDI por datos móviles o desde cualquier Wi‑Fi, **sin abrir puertos del módem**: la conexión va cifrada y sólo la ven los dispositivos de tu cuenta.

**Una sola vez**
1. **Mac:** instala Tailscale desde <https://tailscale.com/download/mac> (o la App Store), ábrelo y en el ícono de la barra de menú toca **Log in** (Google, Apple o Microsoft).
2. **iPhone:** instala **Tailscale** desde la App Store, inicia sesión con **la misma cuenta**, permite la configuración VPN y deja el interruptor encendido.
3. **Sin aviso de “no es privada” (recomendado):** en <https://login.tailscale.com/admin/dns> deja **MagicDNS** activado y activa **HTTPS Certificates**.
4. En la Mac: **Apagar EDI** → abre **EDI.app**. EDI detecta Tailscale, publica `https://<tu-mac>.<tu-red>.ts.net` con certificado válido (`tailscale serve`) y guarda la dirección en `.env` (`EDI_TS_HOST`, `EDI_TS_DNS`, `EDI_TS_URL`).
5. **Ajustes → Dispositivos → Desde cualquier lugar (Tailscale)**: escanea el QR con el iPhone, escribe el PIN y agrégalo a la pantalla de inicio (Safari → Compartir → *Agregar a pantalla de inicio*).

**Bueno saber**
- Si en el paso 3 no activaste HTTPS, EDI usa `https://<IP-100.x>:8766` con su certificado local (aviso sólo la primera vez). Después de activarlo toca **Ya lo activé** en Ajustes → Dispositivos.
- La dirección de Tailscale también funciona en casa: usa esa en la pantalla de inicio y tendrás un solo ícono para todo.
- El PIN es el mismo. **5 intentos fallidos = 5 minutos de espera.** En Ajustes → Dispositivos ves cada dispositivo con su último acceso, puedes quitar uno o **Cerrar sesión en todos los dispositivos** (crea un PIN nuevo; sólo desde la Mac).
- **Sincronización al instante:** pendientes, notas, conversaciones, mensajes, borradores, ajustes y conexiones se actualizan solos en la Mac y el celular, sin recargar ni perder lo que estás escribiendo.
- El atajo **“Oye Siri, EDI”** también funciona fuera de casa: en Ajustes → Dispositivos copia la *dirección de Tailscale* del atajo.
- La Mac tiene que estar encendida (sin dormir) con EDI abierto. Sin Tailscale instalado EDI funciona igual que antes, sólo en tu Wi‑Fi.
- Terminal: `./scripts/edi.sh tailscale` (estado), `tailscale on` (reintentar), `tailscale off` (quitar la publicación). Para no usar `tailscale serve`, pon `EDI_TS_SERVE=0` en `.env`.

## 5. Ajustes
- **General:** tu nombre, tu ciudad (clima), cada cuánto revisar correo y el consumo de tokens.
- **Voz:** voz (Dalia, Jorge, Ava multilingüe…), velocidad y tono.
- **Inteligencia:** OmniRoute, Groq, OpenRouter, Gemini o cualquier API compatible con OpenAI. Si uno falla o retira su modelo, EDI cambia solo.
- **Correos:** registra cada cuenta con su contraseña de aplicación y pruébala.
- **Dispositivos:** accesos “En casa (Wi‑Fi)” y “Desde cualquier lugar (Tailscale)” con QR, PIN, dispositivos conectados y atajo de Siri.
- **Tema:** botón ☾/☀ arriba a la derecha (automático → oscuro → claro).

## 6. Si algo falla
| Síntoma | Solución |
|---|---|
| “Mis proveedores de IA no respondieron” | Ajustes → Inteligencia → **Probar**. Revisa la llave o agrega otro proveedor. |
| No se oye | Revisa 🔊 del Mac; toca la pantalla una vez (el navegador exige un clic antes del primer audio). |
| “Hey EDI” no responde | Menú ◎ → *Responder a “Hey EDI”* debe estar marcado; Ajustes del Sistema → Privacidad → Micrófono y Reconocimiento de voz → EDI Helper activado. |
| El celular no abre EDI | En casa: mismo Wi‑Fi y la dirección `https://…:8766` exacta de Ajustes → Dispositivos. Fuera: Tailscale encendido en el iPhone (interruptor VPN) y la Mac despierta. |
| “Demasiados intentos” | Espera los 5 minutos o, en la Mac, *Cerrar sesión en todos los dispositivos* (quita el bloqueo y crea PIN nuevo). |
| EDI.app se queda en un paso | Pulsa *Ver registro* en el aviso, o revisa `data/edi-launcher.log`. |

## Enviar y responder correos (v0.4)

- Di o escribe: «Manda un correo a juan@gmail.com diciendo que mañana no voy» o «Responde el correo de CFE diciendo que ya pagué».
- EDI muestra un **borrador** que puedes editar. Di «envíalo» (o toca **Enviar**) para mandarlo; «cancela» lo descarta. Caduca a los 15 minutos.
- «Marca todos mis correos como leídos». En la sección **Correo** cada mensaje tiene Ver, Responder y Marcar leído, y arriba está **Redactar**.
- Para enviar se usa la misma contraseña de aplicación de la cuenta (SMTP automático; puedes cambiarlo en Ajustes → Correos → Servidor y carpetas).

## WhatsApp (v0.4)

1. Abre la sección **WhatsApp** del menú. Verás un código QR.
2. En tu celular: WhatsApp → **Dispositivos vinculados** → **Vincular un dispositivo** y escanéalo.
3. Listo: verás tus chats con mensajes nuevos, podrás leerlos y responder.
- Por voz: «¿Tengo mensajes de WhatsApp?», «Lee los mensajes de mamá», «Mándale un WhatsApp a mamá diciendo que llego tarde» → «envíalo».
- Funciona con un puente no oficial (Baileys). Úsalo con moderación, sólo para tus chats. Puedes **Desvincular** cuando quieras.
