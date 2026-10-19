// Guía de uso sencilla, dentro de EDI.
import { html, icon, raw } from "../ui/dom.js";

const SECTIONS = [
  ["mic", "Hablar con EDI", [
    "Toca el anillo o el botón del micrófono y habla. También puedes escribir abajo.",
    "Con la app <b>EDI Helper</b> (barra de menú) basta con decir <q>Hey EDI</q> o pulsar <kbd>⌥</kbd> + <kbd>Espacio</kbd>, aunque estés en otra app.",
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
    "<q>¿Tengo correos?</q> te dice cuántos y cuáles parecen importantes. EDI sólo lee: nunca envía ni borra.",
  ]],
  ["phone", "En tu celular u otra computadora", [
    "Abre Ajustes → Dispositivos y escanea el código QR con el celular (misma red Wi‑Fi).",
    "La primera vez el navegador avisará que el certificado no es de confianza: elige <b>Avanzado → Continuar</b>. Es tu propia Mac.",
    "Escribe el PIN de 6 dígitos. En el celular puedes usar <b>Compartir → Agregar a inicio</b> para tenerla como app.",
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
