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

## 5. Ajustes
- **General:** tu nombre, tu ciudad (clima), cada cuánto revisar correo y el consumo de tokens.
- **Voz:** voz (Dalia, Jorge, Ava multilingüe…), velocidad y tono.
- **Inteligencia:** OmniRoute, Groq, OpenRouter, Gemini o cualquier API compatible con OpenAI. Si uno falla o retira su modelo, EDI cambia solo.
- **Correos:** registra cada cuenta con su contraseña de aplicación y pruébala.
- **Dispositivos:** dirección, QR y PIN para tu red.
- **Tema:** botón ☾/☀ arriba a la derecha (automático → oscuro → claro).

## 6. Si algo falla
| Síntoma | Solución |
|---|---|
| “Mis proveedores de IA no respondieron” | Ajustes → Inteligencia → **Probar**. Revisa la llave o agrega otro proveedor. |
| No se oye | Revisa 🔊 del Mac; toca la pantalla una vez (el navegador exige un clic antes del primer audio). |
| “Hey EDI” no responde | Menú ◎ → *Responder a “Hey EDI”* debe estar marcado; Ajustes del Sistema → Privacidad → Micrófono y Reconocimiento de voz → EDI Helper activado. |
| El celular no abre EDI | Mismo Wi‑Fi; usa la dirección `https://…:8766` exacta de Ajustes → Dispositivos. |
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
