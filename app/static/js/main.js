// Arranque de la interfaz: enrutador por hash, menú lateral, estado y avisos en vivo.
import { api, clientId } from "./api.js";
import { store } from "./store.js";
import { $, $$, html, hydrateIcons, icon, raw, relTime } from "./ui/dom.js";
import { toast } from "./ui/toast.js";
import { whenIdle } from "./ui/live.js";
import * as chat from "./views/chat.js";
import * as mail from "./views/mail.js";
import * as whatsapp from "./views/whatsapp.js";
import * as memory from "./views/memory.js";
import * as settings from "./views/settings.js";
import * as tasks from "./views/tasks.js";
import * as guide from "./views/guide.js";

const VIEWS = { chat, tasks, memory, mail, whatsapp, settings, guide };
const TITLES = { tasks: "Pendientes", memory: "Memoria", mail: "Correo", whatsapp: "WhatsApp", settings: "Ajustes", guide: "Guía de uso" };
const shell = $("#shell"), view = $("#view");
const wide = matchMedia("(min-width: 1101px)");
let currentView = null;

const app = {
  setTitle: (t) => ($("#topTitle").textContent = t || "EDI"),
  setTaskCount: (n) => { const c = $("#countTasks"); c.textContent = n || ""; },
  setWaCount: (n) => { const c = $("#countWa"); if (c) { c.textContent = n || ""; c.classList.toggle("hot", n > 0); } },
  setMailCount: (n) => { const c = $("#countMail"); c.textContent = n || ""; c.classList.toggle("hot", n > 0); },
  refreshSidebar: () => loadSessions(),
  refreshHealth: () => health(),
};

/* ---------- enrutador: #/chat, #/chat/12, #/tasks, #/settings/mail?new=1 ---------- */
function parseHash() {
  const [path, qs] = (location.hash.replace(/^#\/?/, "") || "chat").split("?");
  const [name, arg] = path.split("/");
  const query = Object.fromEntries(new URLSearchParams(qs || ""));
  return { name: VIEWS[name] ? name : "chat", arg, query };
}

async function route() {
  const { name, arg, query } = parseHash();
  document.querySelectorAll(".composer-sheet").forEach((x) => x.remove());   // cierra hojas abiertas al cambiar de sección
  if (currentView && currentView !== VIEWS[name]) currentView.destroy?.();
  currentView = VIEWS[name];
  app.setTitle(TITLES[name] || "EDI");
  $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
  markSession(name === "chat" ? Number(arg) || null : -1);
  if (!wide.matches) setDrawer(false);
  const params = name === "chat" ? { id: arg } : name === "settings" ? { tab: arg, query } : { query };
  try { await currentView.render(view, params, app); } catch (e) { console.error(e); toast(e.message || "Algo falló al abrir esta sección", "error"); }
  view.focus({ preventScroll: true });
}

/* ---------- menú lateral ---------- */
function setDrawer(open) {
  if (wide.matches) { shell.classList.toggle("drawer-closed", !open); store.set({ drawerOpen: open }); }
  else shell.classList.toggle("drawer-open", open);
}
function toggleDrawer() {
  const open = wide.matches ? shell.classList.contains("drawer-closed") : !shell.classList.contains("drawer-open");
  setDrawer(open);
}

async function loadSessions() {
  const list = $("#sessionList");
  try {
    const sessions = await api.sessions();
    list.innerHTML = sessions.length ? sessions.map((s) => html`
      <li><a href="#/chat/${s.id}" data-sid="${s.id}"><span class="t">${s.title || "Conversación"}</span><span class="when">${relTime(s.updated)}</span></a>
      <button class="icon-btn ren" data-ren="${s.id}" aria-label="Renombrar conversación" title="Renombrar">${raw(icon("pen"))}</button>
      <button class="icon-btn del" data-del="${s.id}" aria-label="Borrar conversación" title="Borrar">${raw(icon("x"))}</button></li>`).join("")
      : `<li class="session-empty">Tus conversaciones aparecerán aquí.</li>`;
    markSession(parseHash().name === "chat" ? Number(parseHash().arg) || store.sessionId : -1);
  } catch { list.innerHTML = `<li class="session-empty">Sin conexión con EDI.</li>`; }
}
function markSession(id) { $$("#sessionList a").forEach((a) => a.classList.toggle("active", Number(a.dataset.sid) === id)); }

/* ---------- tema: auto (sistema) → oscuro → claro ---------- */
const THEMES = ["auto", "dark", "light"];
const THEME_ICON = { auto: "auto", dark: "moon", light: "sun" };
const THEME_LABEL = { auto: "Tema: automático", dark: "Tema: oscuro", light: "Tema: claro" };
function applyTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  const b = $("#themeBtn");
  b.innerHTML = icon(THEME_ICON[t]); b.title = THEME_LABEL[t]; b.setAttribute("aria-label", THEME_LABEL[t]);
  window.ediLook?.apply();
}
export { applyTheme };
$("#themeBtn").addEventListener("click", () => {
  const next = THEMES[(THEMES.indexOf(store.theme) + 1) % THEMES.length];
  store.set({ theme: next }); applyTheme(next);
});

/* ---------- estado del servidor ---------- */
async function health() {
  const st = $("#status");
  try {
    const h = await api.health();
    store.set({ health: h });
    st.className = "status on";
    st.querySelector(".status-text").textContent = h.llm.length ? h.llm[0] : "sin IA";
    st.title = `En línea · IA: ${h.llm.join(" → ") || "ninguna"} · ${h.accounts} cuenta(s) de correo`;
  } catch {
    st.className = "status off";
    st.querySelector(".status-text").textContent = "sin conexión";
  }
}

/* ---------- sincronización al instante entre dispositivos ---------- */
// Qué tipos de dato le importan a cada vista (el servidor manda {"type":"changed","kinds":[...]}).
const VIEW_KINDS = {
  chat: ["messages", "sessions", "drafts"],
  tasks: ["tasks", "connections"],
  memory: ["notes"],
  mail: ["mail", "accounts", "drafts"],
  whatsapp: ["whatsapp", "drafts"],
  settings: ["settings", "providers", "connections", "accounts", "devices"],
};
const ALL_KINDS = [...new Set(Object.values(VIEW_KINDS).flat()), "tasks"];
const refreshTasks = () => api.tasks().then((t) => app.setTaskCount(t.length)).catch(() => {});
const refreshMail = () => api.mail(false).then((m) => app.setMailCount(m.total)).catch(() => {});
const waPoll = () => api.waStatus().then((st) => st.state === "open" ? api.waChats() : [])
  .then((cs) => app.setWaCount(cs.reduce((n, c) => n + (c.unread || 0), 0))).catch(() => {});

function onChanged(kinds, origin) {
  const has = (...ks) => ks.some((k) => kinds.includes(k));
  // Contadores del menú y lista de conversaciones: siempre (son baratos y no tocan lo que escribes)
  if (has("tasks")) refreshTasks();
  if (has("mail", "accounts")) refreshMail();
  if (has("whatsapp")) waPoll();
  if (has("sessions", "messages")) whenIdle($("#sessionList"), loadSessions);
  if (has("settings")) api.settings().then((st) => store.set({ settings: st })).catch(() => {});
  if (has("providers", "accounts")) health();
  // La vista abierta: sólo si el cambio vino de OTRO dispositivo/pestaña (ésta ya se actualizó sola)
  if (origin && origin === clientId) return;
  const { name } = parseHash();
  const mine = (VIEW_KINDS[name] || []).filter((k) => kinds.includes(k));
  if (mine.length && currentView === VIEWS[name]) {
    try { currentView.refresh?.(mine); } catch (e) { console.error(e); }
  }
}

function connectEvents() {
  const es = new EventSource("/api/events");
  let lost = false;
  es.onerror = () => { lost = true; };
  es.onopen = () => { if (lost) { lost = false; onChanged(ALL_KINDS, ""); } };   // se reconectó: ponte al día
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "changed") { onChanged(ev.kinds || [ev.kind], ev.origin || ""); return; }
    if (ev.type === "mail" && ev.mail) app.setMailCount(ev.mail.total);
    if (ev.type === "reminder" || ev.type === "tasks") {
      refreshTasks();
      if (currentView === tasks) tasks.refresh(["tasks"]);
    }
    if (!ev.text) return;
    chat.announce(ev.text);
    if (currentView !== chat) toast(ev.text, "info", 7000);
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification("EDI", { body: ev.text });
  };
}
// En el iPhone la conexión en vivo se corta al bloquear la pantalla: al volver, ponte al día
let hiddenAt = 0;
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { hiddenAt = Date.now(); return; }
  if (hiddenAt && Date.now() - hiddenAt > 5000) onChanged(ALL_KINDS, "");
  hiddenAt = 0;
});

/* ---------- eventos globales ---------- */
document.addEventListener("click", async (e) => {
  const a = e.target.closest("[data-action]");
  if (a) {
    const act = a.dataset.action;
    if (act === "toggle-drawer") toggleDrawer();
    if (act === "close-drawer") setDrawer(false);
    if (act === "new-chat") { store.set({ sessionId: null }); if (location.hash === "#/chat") route(); else location.hash = "#/chat"; }
  }
  const ren = e.target.closest("[data-ren]");
  if (ren && ren.closest("#sessionList")) {
    e.preventDefault();
    const li = ren.closest("li"), a = li.querySelector("a"), t = a.querySelector(".t");
    const inp = document.createElement("input");
    inp.className = "input ren-input"; inp.value = t.textContent; inp.maxLength = 80;
    a.replaceWith(inp); inp.focus(); inp.select();
    let done = false;
    const finish = async (save) => {
      if (done) return; done = true;
      if (save && inp.value.trim() && inp.value.trim() !== t.textContent) {
        try { await api.renameSession(Number(ren.dataset.ren), inp.value.trim()); } catch (err) { toast(err.message, "error"); }
      }
      loadSessions();
    };
    inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") finish(true); if (ev.key === "Escape") finish(false); });
    inp.addEventListener("blur", () => finish(true));
    return;
  }
  const del = e.target.closest("[data-del]");
  if (del && del.closest("#sessionList")) {
    e.preventDefault();
    const id = Number(del.dataset.del);
    if (!confirm("¿Borrar esta conversación?")) return;
    await api.deleteSession(id);
    if (store.sessionId === id) { store.set({ sessionId: null }); location.hash = "#/chat"; }
    loadSessions();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && shell.classList.contains("drawer-open")) setDrawer(false);
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("[data-action=new-chat]").click(); }
});
window.addEventListener("hashchange", route);

/* ---------- arranque ---------- */
(async function boot() {
  $("[data-action=new-chat]").innerHTML = `${icon("plus")}Nueva conversación`;
  $(".drawer-close").innerHTML = icon("x");
  hydrateIcons();
  applyTheme(store.theme);
  api.devices().then((d) => { if (d.lan_url && !d.remote) { $("#lanLink").textContent = d.lan_url.replace("https://", ""); $("#lanLink").title = "Ábrelo en tu celular (Ajustes → Dispositivos)"; } }).catch(() => {});
  if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js").catch(() => {});
  if (wide.matches && !store.drawerOpen) shell.classList.add("drawer-closed");
  try { store.set({ settings: await api.settings() }); } catch {}
  await health();
  loadSessions();
  refreshTasks();
  waPoll(); setInterval(waPoll, 60000);
  await route();
  connectEvents();
  setInterval(health, 60000);
  if ("Notification" in window && Notification.permission === "default") {
    window.addEventListener("pointerdown", () => Notification.requestPermission(), { once: true });
  }
})();

/* ---------- Gestos en el celular: deslizar desde el borde izquierdo abre el menú; hacia la izquierda lo cierra ---------- */
(() => {
  let x0 = null, y0 = 0, fromEdge = false;
  window.addEventListener("touchstart", (e) => {
    const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY; fromEdge = x0 < 28;
  }, { passive: true });
  window.addEventListener("touchend", (e) => {
    if (x0 === null || wide.matches) return;
    const t = e.changedTouches[0], dx = t.clientX - x0, dy = Math.abs(t.clientY - y0);
    if (dy < 60) {
      if (fromEdge && dx > 60) setDrawer(true);
      else if (dx < -70 && shell.classList.contains("drawer-open")) setDrawer(false);
    }
    x0 = null;
  }, { passive: true });
})();

/* ---------- Alto real de la pantalla en el celular (evita el hueco bajo el teclado en iPhone) ---------- */
(() => {
  const vv = window.visualViewport;
  const fit = () => {
    const h = vv ? vv.height : window.innerHeight;
    document.documentElement.style.setProperty("--app-h", `${Math.round(h)}px`);
    if (vv && vv.offsetTop) window.scrollTo(0, 0);
  };
  fit();
  // Con el teclado abierto: sin margen de la barra inferior ni sugerencias, para que no quede espacio vacío
  const typing = (e) => e.target.matches?.("textarea, input:not([type=range]):not([type=color]):not([type=checkbox])");
  document.addEventListener("focusin", (e) => { if (typing(e) && !wide.matches) document.body.classList.add("kb"); });
  document.addEventListener("focusout", (e) => { if (typing(e)) setTimeout(() => { if (!document.activeElement?.matches?.("textarea, input")) document.body.classList.remove("kb"); fit(); }, 50); });
  (vv || window).addEventListener("resize", fit);
  vv?.addEventListener("scroll", fit);
  window.addEventListener("orientationchange", () => setTimeout(fit, 300));
})();
