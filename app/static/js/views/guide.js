// Guía de uso sencilla, dentro de EDI.
import { html, icon, raw } from "../ui/dom.js";

const SECTIONS = [
  ["mic", "Hablar con EDI", [
    "Toca el anillo o el botón del micrófono y habla. También puedes escribir abajo.",
    "Con la app <b>EDI Helper</b> (barra de menú) basta con decir <q>Hey EDI</q> o pulsar <kbd>⌥</kbd> + <kbd>Espacio</kbd>, aunque estés en otra app.",
    "<b>Modo conversación:</b> después de cada respuesta EDI sigue escuchando unos segundos (oirás un tono), así contestas <q>envíalo</q> o <q>el segundo</q> sin repetir <q>Hey EDI</q>.",
    "<b>En el iPhone:</b> crea el atajo <q>Oye Siri, EDI</q> desde Ajustes → Dispositivos; funciona aunque el teléfono esté bloqueado.",
    "Di <q>repite</q> o toca <span class='muted'>↻</span> para volver a escuchar una respuesta.",
  ]],
  ["list", "Pendientes y recordatorios", [
    "<q>Recuérdame pagar la luz mañana a las 5</q> · <q>Tengo que ir al banco el viernes</q>",
    "<q>Mis tareas</q> para escucharlas, <q>ya hice pagar la luz</q> para tacharla.",
    "A la hora indicada EDI te avisa en voz alta (con la ventana o el Helper abiertos).",
  ]],
  ["brain", "Memoria", [
    "<q>Recuerda que el wifi está debajo del módem</q> y después <q>¿qué te dije del wifi?</q>",
    "Todo queda en la sección Memoria; ahí puedes buscar o borrar.",
  ]],
  ["globe", "Buscar en internet", [
    "<q>Hey EDI, búscame el precio del dólar</q> · <q>¿Cómo está el clima en Querétaro?</q>",
    "<q>Busca quién ganó el partido del América</q> · <q>Noticias de tecnología</q>",
    "Debajo de la respuesta verás las fuentes que consultó.",
  ]],
  ["mail", "Correo", [
    "Registra tus cuentas en Ajustes → Correos (o di <q>agrega una cuenta de correo</q>).",
    "<q>¿Tengo correos?</q> te dice cuántos y cuáles parecen importantes.",
    "<q>Manda un correo a juan@gmail.com diciendo que mañana no voy</q> · <q>Responde el correo de CFE diciendo que ya pagué</q>",
    "EDI prepara un <b>borrador</b>: revísalo y di <q>envíalo</q> (o toca Enviar). <q>Cancela</q> lo descarta. Nunca envía sin tu confirmación.",
    "<q>Marca todos mis correos como leídos</q>. En la sección Correo también puedes ver, responder, redactar y marcar cada uno.",
  ]],
  ["chat", "WhatsApp", [
    "Abre la sección WhatsApp y escanea el código QR desde tu celular: WhatsApp → <b>Dispositivos vinculados</b> → <b>Vincular un dispositivo</b>.",
    "<b>«Mándale un mensaje a…» siempre es WhatsApp</b>; <b>«Manda un correo a…»</b> siempre es correo (Gmail primero).",
    "<q>Mándale un mensaje a mi jefa</q> → EDI pregunta <q>¿Qué le digo?</q> → <q>Que llego en 10 minutos</q> → <q>Envíalo</q>.",
    "<q>Mándale un mensaje a mamá diciendo que llego tarde</q> (todo en una frase también funciona). Usa los nombres como los tienes guardados en tu celular.",
    "<q>Lee los últimos 5 mensajes de Juan</q> · <q>¿Qué me dijo mamá?</q> · <q>Resume el chat del trabajo</q> · <q>¿Tengo mensajes de WhatsApp?</q>",
    "En la sección WhatsApp ves todos tus chats, puedes buscar cualquier contacto y escribirle con <b>Nuevo mensaje</b>.",
    "Usa un puente no oficial (Baileys): úsalo con moderación y para tus propios chats. Puedes desvincular cuando quieras.",
  ]],
  ["list", "Trabajo: Jira, GitHub y Slack", [
    "Conéctalos en <b>Ajustes → Conexiones</b>. Lo asignado a ti aparece en <b>Pendientes → Trabajo</b> con recordatorios; lo personal queda en <b>Personales</b>.",
    "<q>¿Qué tickets tengo?</q> · <q>¿Cómo va EDI-12?</q> · <q>Sincroniza Jira</q> · <q>¿Qué PRs tengo?</q> · <q>¿Pasó el build de la app?</q>",
    "<q>Crea un ticket arreglar el login para el viernes</q> · <q>Mueve EDI-12 a en curso</q> · <q>Termina EDI-12</q> · <q>Comenta en EDI-12 que ya quedó</q>",
    "<q>Mándale un Slack a Ana diciendo que ya subí el cambio</q> · <q>¿Tengo mensajes en Slack?</q> · reacciona con ✅ a un mensaje para volverlo pendiente.",
    "Todo lo que cambia algo en Jira o Slack te muestra un borrador: revisa y di <q>sí</q> o <q>créalo</q>. Si editas o terminas un pendiente de Jira en EDI, también se actualiza en Jira.",
    "<q>Agrega un pendiente de trabajo revisar el contrato</q> lo guarda como trabajo; sin decirlo, queda como personal.",
  ]],
  ["phone", "En tu celular u otra computadora", [
    "Abre Ajustes → Dispositivos y escanea el código QR con el celular (misma red Wi‑Fi).",
    "La primera vez el navegador avisará que el certificado no es de confianza: elige <b>Avanzado → Continuar</b>. Es tu propia Mac.",
    "Escribe el PIN de 6 dígitos. En el celular puedes usar <b>Compartir → Agregar a inicio</b> para tenerla como app.",
  ]],
  ["globe", "Usar EDI fuera de casa", [
    "Con <b>Tailscale</b> (gratis) abres EDI desde tu iPhone con datos móviles o en cualquier Wi‑Fi, sin abrir puertos de tu módem: sólo tus dispositivos lo ven.",
    "Instálalo en la Mac y en el iPhone con <b>la misma cuenta</b> y vuelve a abrir EDI.app. En Ajustes → Dispositivos aparece <b>Desde cualquier lugar (Tailscale)</b> con su QR.",
    "Si activas <b>HTTPS Certificates</b> en tu cuenta de Tailscale, la dirección <b>…ts.net</b> abre sin el aviso de “conexión no privada”.",
    "Usa el mismo PIN. Tras 5 intentos fallidos la entrada se bloquea 5 minutos. ¿Perdiste el celular? En la Mac: <b>Cerrar sesión en todos los dispositivos</b>.",
    "Todo se sincroniza al instante: lo que agregas, editas o borras en el celular aparece en la Mac (y al revés) sin recargar.",
    "La Mac debe estar encendida, con EDI abierto y sin dormir.",
  ]],
  ["key", "Inteligencia y consumo", [
    "En Ajustes → Inteligencia agrega OmniRoute, Groq, OpenRouter o Gemini y ordénalos. Si uno falla, EDI usa el siguiente.",
    "Si un proveedor retira un modelo, EDI elige otro disponible automáticamente.",
    "Tareas, notas, hora, clima y tipo de cambio no gastan tokens de IA.",
  ]],
  ["bolt", "Encender y apagar", [
    "Doble clic en <b>EDI.app</b> en el Escritorio: verás una ventana con el progreso.",
    "<b>Apagar EDI.app</b> apaga todo y libera memoria.",
    "Atajos en esta ventana: <kbd>Ctrl</kbd> + <kbd>Espacio</kbd> dictar, <kbd>Esc</kbd> callar, <kbd>⌘</kbd> + <kbd>K</kbd> nueva conversación.",
  ]],
];

export function render(container) {
  container.innerHTML = html`
    <section class="page">
      <header class="page-head"><div>
        <h1>Guía de uso</h1>
        <p>Lo esencial para sacarle provecho a EDI. Puedes pedirle casi todo hablando normal.</p>
      </div></header>
      <div class="guide">${SECTIONS.map(([ic, title, items]) => raw(`
        <div class="panel glass">
          <h2>${icon(ic)}${title}</h2>
          <ul>${items.map((t) => `<li>${t}</li>`).join("")}</ul>
        </div>`))}</div>
    </section>`;
}
