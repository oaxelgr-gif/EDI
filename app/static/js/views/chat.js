// Vista principal: hablar con EDI.
import { api } from "../api.js";
import { store } from "../store.js";
import { $, el, esc, html, icon, raw } from "../ui/dom.js";
import { toast } from "../ui/toast.js";
import * as listener from "../voice/listener.js";
import { mountOrb } from "../voice/orb.js";
import { hasPending, onSpeakState, playPending, speak, speakLevel, speakState, stop as stopSpeaking } from "../voice/speaker.js";

const STATE_LABEL = { idle: "", speaking: "hablando", loading: "preparando voz", listening: "te escucho", wake: "di “EDI” y tu orden", armed: "¿sí?", blocked: "" };
const SUGGESTIONS = ["Dame mi resumen", "¿Tengo correos?", "Precio del dólar", "¿Cómo está el clima?", "Mis tareas"];

let root, cleanup = [], listenState = "idle", ctx = {}, queued = null, renderId = 0;

const orbState = () => {
  const s = speakState();
  return s !== "idle" ? s : listenState;
};

export async function render(container, params, app) {
  ctx = app;
  root = container;
  const myRender = ++renderId;   // evita saludos duplicados si se navega dos veces rápido
  cleanup.forEach((fn) => fn()); cleanup = [];
  root.innerHTML = html`
    <section class="chat">
      <div class="orb-wrap">
        <canvas class="orb" id="orb" role="button" tabindex="0" aria-label="Hablar con EDI"></canvas>
        <div class="orb-state" id="orbState" aria-live="polite"></div>
      </div>
      <div class="chat-scroll"><ol class="transcript" id="transcript"></ol></div>
      <div class="composer-wrap">
        <form class="composer" id="composer">
          <button type="button" class="mic glass" id="mic" aria-label="Dictar">${raw(icon("mic"))}</button>
          <div class="prompt glass">
            <textarea id="input" rows="1" placeholder="Escribe o dicta a EDI" aria-label="Mensaje para EDI"></textarea>
            <button type="submit" class="send" id="send" aria-label="Enviar" disabled>${raw(icon("send"))}</button>
          </div>
        </form>
        <div class="suggestions" id="suggestions">${SUGGESTIONS.map((s) => raw(`<button type="button">${esc(s)}</button>`))}</div>
        <label class="wake ${store.wake ? "on" : ""}" id="wakeLabel" ${listener.canListen ? "" : "hidden"}>
          <span class="switch"><input type="checkbox" id="wake" ${store.wake ? "checked" : ""}></span>
          Escucha continua en esta ventana (para todo el sistema usa EDI Helper)
        </label>
      </div>
    </section>`;

  const input = $("#input", root), send = $("#send", root);
  cleanup.push(mountOrb($("#orb", root), orbState, () => speakLevel() || listener.micLevel()));
  cleanup.push(onSpeakState(updateState));

  input.addEventListener("input", () => {
    send.disabled = !input.value.trim();
    input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px";
  });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#composer", root).requestSubmit(); } });
  $("#composer", root).addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });
  $("#mic", root).addEventListener("click", toggleMic);
  $("#orb", root).addEventListener("click", () => (speakState() === "speaking" ? stopSpeaking() : toggleMic()));
  $("#orb", root).addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleMic(); } });
  $("#suggestions", root).addEventListener("click", (e) => { if (e.target.matches("button")) ask(e.target.textContent); });
  $("#wake", root)?.addEventListener("change", (e) => {
    store.set({ wake: e.target.checked });
    $("#wakeLabel", root).classList.toggle("on", e.target.checked);
    e.target.checked ? listener.start("wake") : listener.stop();
  });

  listener.on("interim", (t) => { if (t) $("#orbState", root).textContent = t; });
  listener.on("result", (t) => ask(t));
  listener.on("state", (s) => { listenState = s; updateState(); });
  listener.on("error", (m) => toast(m, "error", 5000));
  if (store.wake && !listener.listenMode()) listener.start("wake");

  const sid = params.id ? Number(params.id) : null;
  store.set({ sessionId: sid });
  if (sid) await loadSession(sid);
  else if (!queued) await greet(myRender);
  else $("#transcript", root).innerHTML = "";
  if (queued) { const q = queued; queued = null; ask(q); }
  if (!matchMedia("(max-width: 640px)").matches) input.focus();
}

function updateState() {
  const s = orbState();
  const label = $("#orbState", root);
  if (!label) return;
  label.className = `orb-state ${s === "loading" ? "speaking" : s === "armed" || s === "wake" ? "listening" : s}`;
  label.textContent = STATE_LABEL[s] ?? "";
  $("#mic", root)?.classList.toggle("on", s === "listening" || s === "armed");
  if (s === "speaking") listener.pauseWake(); else if (s === "idle") listener.resumeWake();
}

function toggleMic() {
  stopSpeaking();
  if (listener.listenMode() === "once") listener.stop();
  else listener.start("once");
}

function addLine(role, text, { meta = "", alert = false, speakNow = false, sources = null } = {}) {
  const list = $("#transcript", root);
  if (!list) return null;
  list.querySelector(".empty-hello")?.remove();
  list.querySelectorAll(".line.edi:not(.past)").forEach((n) => n.classList.add("past"));
  const li = el(role === "edi"
    ? html`<li class="line edi ${alert ? "alert" : ""}"><p>${text}</p>
        <div class="line-meta">
          <button class="icon-btn" data-repeat title="Repetir" aria-label="Repetir en voz alta">${raw(icon("repeat"))}</button>
          ${meta ? raw(`<span>vía ${esc(meta)}</span>`) : ""}
        </div></li>`
    : html`<li class="line user"><p>${text}</p></li>`);
  li.querySelector("[data-repeat]")?.addEventListener("click", () => speak(text));
  if (sources?.length) {
    li.append(el(`<div class="sources">${sources.slice(0, 4).map((s) => {
      let host = ""; try { host = new URL(s.url).hostname.replace(/^www\./, ""); } catch {}
      return `<a href="${esc(s.url)}" target="_blank" rel="noopener" title="${esc(s.title)}">${esc(host || s.title)}</a>`;
    }).join("")}</div>`));
  }
  list.append(li);
  li.scrollIntoView({ block: "end", behavior: "smooth" });
  if (role === "edi") { store.lastReply = text; if (speakNow) speakWithFallbackHint(li, text); }
  return li;
}

async function speakWithFallbackHint(li, text) {
  await speak(text);
  if (hasPending()) {
    const b = el(`<button class="tap">Toca para escuchar</button>`);
    b.addEventListener("click", () => { b.remove(); playPending(); });
    li.querySelector(".line-meta").append(b);
    window.addEventListener("pointerdown", () => { if (hasPending()) { b.remove(); playPending(); } }, { once: true });
  }
}

function typing() {
  const li = el(`<li class="line edi typing-line"><div class="typing" aria-label="EDI está pensando"><i></i><i></i><i></i></div></li>`);
  $("#transcript", root)?.append(li);
  li.scrollIntoView({ block: "end" });
  return li;
}

async function greet(token = renderId) {
  const list = $("#transcript", root);
  list.innerHTML = `<li class="empty-hello"><h1>Hola, ${esc(store.settings.user_name || "jefe")}.</h1><p>Habla con el micrófono, escribe abajo o toca el anillo.</p></li>`;
  try {
    const r = await api.greeting();
    if (token !== renderId) return;
    addLine("edi", r.reply, { speakNow: true });
    if (r.data?.mail) ctx.setMailCount?.(r.data.mail.total);
  } catch { /* sin conexión: queda el saludo estático */ }
}

async function loadSession(id) {
  try {
    const s = await api.session(id);
    ctx.setTitle?.(s.title);
    const list = $("#transcript", root);
    list.innerHTML = "";
    s.messages.forEach((m) => addLine(m.role, m.text, { meta: m.meta }));
    if (!s.messages.length) await greet();
  } catch (e) {
    toast(e.message, "error");
    location.hash = "#/chat";
  }
}

export async function ask(text) {
  text = (text || "").trim();
  if (!text) return;
  if (!root) {  // llegó por voz desde otra sección: vuelve a la conversación y pregunta ahí
    queued = text;
    location.hash = store.sessionId ? `#/chat/${store.sessionId}` : "#/chat";
    return;
  }
  const input = $("#input", root);
  if (input) { input.value = ""; input.style.height = "auto"; $("#send", root).disabled = true; }
  if (/^(edi[, ]*)?(repite|repítelo|otra vez|qué dijiste)\b/i.test(text)) { speak(store.lastReply); return; }
  stopSpeaking();
  addLine("user", text);
  const t = typing();
  try {
    const r = await api.ask(text, store.sessionId);
    t.remove();
    if (r.session_id !== store.sessionId) {
      store.set({ sessionId: r.session_id });
      history.replaceState(null, "", `#/chat/${r.session_id}`);
    }
    if (r.repeat) { speak(r.reply); return; }
    addLine("edi", r.reply, { meta: r.provider, speakNow: true, sources: r.data?.sources });
    ctx.refreshSidebar?.();
    if (r.data?.mail) ctx.setMailCount?.(r.data.mail.total);
    if (r.data?.tasks) ctx.setTaskCount?.(r.data.tasks.length);
    if (r.action?.open) setTimeout(() => { location.hash = `#/${r.action.open}/${r.action.tab || ""}${r.action.new ? "?new=1" : ""}`; }, 1600);
  } catch (e) {
    t.remove();
    addLine("edi", "No logro comunicarme con mi servidor. Revisa que Docker esté encendido.", { alert: true });
  }
}

/** Avisos en vivo (recordatorios, correo nuevo) cuando esta vista está abierta. */
export function announce(text) {
  if (root && $("#transcript", root)) addLine("edi", text, { alert: true, speakNow: true });
  else speak(text);
}

export function destroy() { cleanup.forEach((fn) => fn()); cleanup = []; root = null; }
