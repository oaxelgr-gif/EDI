// Arranque de la interfaz: enrutador por hash, menú lateral, estado y avisos en vivo.
import { api } from "./api.js";
import { store } from "./store.js";
import { $, $$, html, hydrateIcons, icon, raw, relTime } from "./ui/dom.js";
import { toast } from "./ui/toast.js";
import * as chat from "./views/chat.js";
import * as mail from "./views/mail.js";
import * as memory from "./views/memory.js";
import * as settings from "./views/settings.js";
import * as tasks from "./views/tasks.js";

const VIEWS = { chat, tasks, memory, mail, settings };
const TITLES = { tasks: "Pendientes", memory: "Memoria", mail: "Correo", settings: "Ajustes" };
const shell = $("#shell"), view = $("#view");
const wide = matchMedia("(min-width: 1101px)");
let currentView = null;

const app = {
  setTitle: (t) => ($("#topTitle").textContent = t || "EDI"),
  setTaskCount: (n) => { const c = $("#countTasks"); c.textContent = n || ""; },
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
      <button class="icon-btn del" data-del="${s.id}" aria-label="Borrar conversación">${raw(icon("x"))}</button></li>`).join("")
      : `<li class="session-empty">Tus conversaciones aparecerán aquí.</li>`;
    markSession(parseHash().name === "chat" ? Number(parseHash().arg) || store.sessionId : -1);
  } catch { list.innerHTML = `<li class="session-empty">Sin conexión con EDI.</li>`; }
}
function markSession(id) { $$("#sessionList a").forEach((a) => a.classList.toggle("active", Number(a.dataset.sid) === id)); }

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

function connectEvents() {
  const es = new EventSource("/api/events");
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "mail" && ev.mail) app.setMailCount(ev.mail.total);
    if (ev.type === "reminder") api.tasks().then((t) => app.setTaskCount(t.length));
    chat.announce(ev.text);
    if (currentView !== chat) toast(ev.text, "info", 7000);
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) new Notification("EDI", { body: ev.text });
  };
}

/* ---------- eventos globales ---------- */
document.addEventListener("click", async (e) => {
  const a = e.target.closest("[data-action]");
  if (a) {
    const act = a.dataset.action;
    if (act === "toggle-drawer") toggleDrawer();
    if (act === "close-drawer") setDrawer(false);
    if (act === "new-chat") { store.set({ sessionId: null }); location.hash = "#/chat"; if (parseHash().name === "chat") route(); }
  }
  const del = e.target.closest("[data-del]");
  if (del && del.closest("#sessionList")) {
    e.preventDefault();
    const id = Number(del.dataset.del);
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
  if (wide.matches && !store.drawerOpen) shell.classList.add("drawer-closed");
  try { store.set({ settings: await api.settings() }); } catch {}
  await health();
  loadSessions();
  api.tasks().then((t) => app.setTaskCount(t.length)).catch(() => {});
  await route();
  connectEvents();
  setInterval(health, 60000);
  if ("Notification" in window && Notification.permission === "default") {
    window.addEventListener("pointerdown", () => Notification.requestPermission(), { once: true });
  }
})();
