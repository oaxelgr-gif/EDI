// Pendientes tipo agenda: secciones por fecha (atrasados, hoy, mañana, esta semana, después, sin fecha)
// y un calendario del mes para ver qué días tienes cosas.
import { api } from "../api.js";
import { $, esc, html, icon, raw } from "../ui/dom.js";
import { toast } from "../ui/toast.js";

let root, app, tasks = [], view = "agenda", month = startOfMonth(new Date()), pickDay = null, conns = [];
let cat = (() => { try { return localStorage.getItem("edi.taskCat") || "all"; } catch { return "all"; } })();
let newCat = "personal";
const jiraConn = () => conns.find((c) => c.kind === "jira" && c.enabled);
const shownText = (t) => (t.ext_key && t.text.startsWith(t.ext_key + " · ") ? t.text.slice(t.ext_key.length + 3) : t.text);
const SRC = { jira: "Jira", github: "GitHub", slack: "Slack" };
const DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function dayKey(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const sameDay = (a, b) => dayKey(a) === dayKey(b);
const hhmm = (d) => d.toLocaleTimeString("es-MX", { hour: "numeric", minute: "2-digit" });
const cap = (s) => s[0].toUpperCase() + s.slice(1);
const dayLabel = (d) => `${DAYS[d.getDay()]} ${d.getDate()} de ${MONTHS[d.getMonth()]}`;

export async function render(container, _params, ctx) {
  root = container; app = ctx; pickDay = null;
  root.innerHTML = html`
    <section class="page">
      <header class="page-head">
        <div><h1>Pendientes</h1>
          <p>Escríbelos como se los dirías a EDI: “pagar la luz mañana a las 5”. La fecha se entiende sola y te aviso en voz alta.</p></div>
        <div class="seg" id="viewSeg">
          <button data-view="agenda" aria-pressed="${view === "agenda"}">Agenda</button>
          <button data-view="month" aria-pressed="${view === "month"}">Calendario</button>
        </div>
      </header>
      <div class="task-toolbar">
        <div class="seg" id="catSeg">
          <button data-cat="all" aria-pressed="${cat === "all"}">Todos</button>
          <button data-cat="personal" aria-pressed="${cat === "personal"}">Personales</button>
          <button data-cat="trabajo" aria-pressed="${cat === "trabajo"}">Trabajo</button>
        </div>
        <button class="btn btn-quiet" id="syncBtn" hidden>${raw(icon("refresh"))}Sincronizar</button>
      </div>
      <form class="add-bar glass" id="addTask">
        <button type="button" class="cat-chip" id="newCat" title="Cambiar tipo">Personal</button>
        <input class="input" name="text" placeholder="Nuevo: “dentista el jueves a las 4”" aria-label="Nuevo pendiente" autocomplete="off" required>
        <label class="jira-check" id="jiraCheck" hidden><input type="checkbox" name="to_jira"> también en Jira</label>
        <button class="btn btn-primary">Agregar</button>
      </form>
      <div id="calWrap"></div>
      <div id="taskList"></div>
    </section>`;
  $("#addTask", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try {
      const r = await api.addTask(f.text.value, null, { category: newCat, to_jira: !!f.to_jira?.checked });
      if (r.jira) toast(`Creado ${r.jira.key} en Jira`);
      f.text.value = ""; load();
    } catch (err) { toast(err.message, "error"); }
  });
  const setNewCat = (c) => {
    newCat = c;
    $("#newCat", root).textContent = c === "trabajo" ? "Trabajo" : "Personal";
    $("#newCat", root).className = `cat-chip ${c}`;
    $("#jiraCheck", root).hidden = !(c === "trabajo" && jiraConn());
  };
  $("#newCat", root).onclick = () => setNewCat(newCat === "personal" ? "trabajo" : "personal");
  $("#catSeg", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-cat]"); if (!b) return;
    cat = b.dataset.cat;
    try { localStorage.setItem("edi.taskCat", cat); } catch {}
    root.querySelectorAll("[data-cat]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    if (cat !== "all") setNewCat(cat);
    draw();
  });
  $("#syncBtn", root).onclick = async (e) => {
    const b = e.currentTarget; b.disabled = true; b.classList.add("spin");
    try {
      const res = await api.syncAll();
      const vals = Object.values(res), bad = vals.find((r) => !r.ok);
      const added = vals.reduce((n, r) => n + (r.added || 0), 0), done = vals.reduce((n, r) => n + (r.done || 0), 0);
      toast(bad ? bad.error : `Sincronizado: ${added} nuevos, ${done} cerrados`, bad ? "error" : "info");
      load();
    } catch (err) { toast(err.message, "error"); }
    b.disabled = false; b.classList.remove("spin");
  };
  if (cat !== "all") setNewCat(cat);
  api.connections().then((c) => { conns = c; $("#syncBtn", root).hidden = !c.some((x) => x.enabled); setNewCat(newCat); }).catch(() => {});
  $("#viewSeg", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-view]"); if (!b) return;
    view = b.dataset.view; pickDay = null;
    root.querySelectorAll("[data-view]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    draw();
  });
  $("#taskList", root).addEventListener("click", onClick);
  $("#taskList", root).addEventListener("change", onDateChange);
  $("#calWrap", root).addEventListener("click", onCalClick);
  load();
}

export function refresh() { if (root?.isConnected) load(); }

async function load() {
  tasks = await api.tasks(true);
  app.setTaskCount?.(tasks.filter((t) => !t.done).length);
  draw();
}

/* ---------- agenda por secciones ---------- */
function sections(list) {
  const now = new Date(), today = midnight(now), tomorrow = addDays(today, 1), weekEnd = addDays(today, 7);
  const out = [];
  const push = (key, title, sub, items, cls = "") => { if (items.length) out.push({ key, title, sub, items, cls }); };
  const open = list.filter((t) => !t.done);
  const dated = open.filter((t) => t.due).map((t) => ({ ...t, d: new Date(t.due) })).sort((a, b) => a.d - b.d);
  push("late", "Atrasados", "ya pasó la fecha", dated.filter((t) => midnight(t.d) < today), "late");
  push("today", "Hoy", dayLabel(today), dated.filter((t) => sameDay(t.d, today)), "today");
  push("tomorrow", "Mañana", dayLabel(tomorrow), dated.filter((t) => sameDay(t.d, tomorrow)));
  for (let d = addDays(today, 2); d < weekEnd; d = addDays(d, 1)) {
    push(dayKey(d), cap(DAYS[d.getDay()]), `${d.getDate()} de ${MONTHS[d.getMonth()]}`, dated.filter((t) => sameDay(t.d, d)));
  }
  const byDay = {};
  dated.filter((t) => t.d >= weekEnd).forEach((t) => (byDay[dayKey(t.d)] ||= []).push(t));
  Object.keys(byDay).sort().forEach((k) => {
    const d = byDay[k][0].d;
    push(k, `${d.getDate()} de ${MONTHS[d.getMonth()]}`, DAYS[d.getDay()] + (d.getFullYear() !== today.getFullYear() ? ` · ${d.getFullYear()}` : ""), byDay[k]);
  });
  push("nodate", "Sin fecha", "cuando puedas", open.filter((t) => !t.due));
  push("done", "Hechos recientemente", "", list.filter((t) => t.done).slice(-10).reverse(), "done");
  return out;
}

function row(t) {
  const d = t.due ? new Date(t.due) : null;
  const late = d && !t.done && d < new Date();
  const local = d ? new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  return html`
    <li class="item agenda-item ${t.done ? "done" : ""}" data-id="${t.id}">
      <div class="when-col ${late ? "late" : ""}">${d ? hhmm(d) : "—"}</div>
      <button class="check" data-act="toggle" aria-label="${t.done ? "Marcar como pendiente" : "Marcar como hecho"}">${raw(icon("check"))}</button>
      <div class="item-body" data-act="edit" role="button" tabindex="0" title="Editar">
        <div class="item-title">${t.priority === "alta" ? raw('<span class="prio alta">Alta</span>') : t.priority === "baja" ? raw('<span class="prio baja">Baja</span>') : ""}${shownText(t)}</div>
        <div class="task-tags">
          ${cat === "all" && t.category === "trabajo" && !t.ext_key ? raw('<span class="tag work">Trabajo</span>') : ""}
          ${t.ext_key ? raw(`<a class="tag src ${esc(t.source)}" href="${esc(t.link || "#")}" target="_blank" rel="noopener">${esc(SRC[t.source] || t.source)} · ${esc(t.ext_key)}</a>`) : ""}
          ${t.ext_status ? raw(`<span class="tag status">${esc(t.ext_status)}</span>`) : ""}
        </div>
        ${t.notes ? raw(`<div class="item-sub task-notes">${esc(t.notes)}</div>`) : ""}
        ${late && midnight(d) < midnight(new Date()) ? raw(`<div class="item-sub"><span class="due late">era para el ${esc(dayLabel(d))}</span></div>`) : ""}
        ${t.link && !t.ext_key ? raw(`<a class="task-link" href="${esc(t.link)}" target="_blank" rel="noopener">${esc(hostOf(t.link))}</a>`) : ""}
      </div>
      <div class="item-actions">
        <button class="icon-btn" data-act="edit" title="Editar" aria-label="Editar">${raw(icon("pen"))}</button>
        <label class="icon-btn date-btn" title="${d ? "Cambiar fecha" : "Ponerle fecha"}" aria-label="Cambiar fecha">${raw(icon("calendar"))}
          <input type="datetime-local" data-due="${t.id}" value="${local}"></label>
        ${t.due && !t.done ? raw(`<button class="icon-btn" data-act="undate" title="Quitar fecha" aria-label="Quitar fecha">${icon("x")}</button>`) : ""}
        <button class="icon-btn" data-act="delete" aria-label="Borrar">${raw(icon("trash"))}</button>
      </div>
    </li>`;
}

const visible = () => (cat === "all" ? tasks : tasks.filter((t) => (t.category || "personal") === cat));

function draw() {
  const list = $("#taskList", root), cal = $("#calWrap", root);
  if (!list) return;
  cal.innerHTML = view === "month" ? calendar() : "";
  let secs;
  if (view === "month" && pickDay) {
    const items = visible().filter((t) => t.due && dayKey(new Date(t.due)) === pickDay).sort((a, b) => new Date(a.due) - new Date(b.due));
    secs = items.length ? [{ key: pickDay, title: cap(dayLabel(new Date(pickDay + "T12:00"))), sub: "", items }] : [];
  } else secs = sections(visible());
  if (!secs.length) {
    list.innerHTML = `<div class="empty">${pickDay ? "Nada agendado ese día." : "No tienes pendientes. Agrega uno arriba o dile a EDI “recuérdame…”."}</div>`;
    return;
  }
  list.innerHTML = secs.map((s) => html`
    <div class="agenda-sec ${s.cls}">
      <div class="agenda-head"><h2>${s.title}</h2>${s.sub ? raw(`<span class="sub">${esc(s.sub)}</span>`) : ""}<span class="n">${s.items.length}</span></div>
      <div class="card glass"><ul class="items">${s.items.map((t) => raw(row(t)))}</ul></div>
    </div>`).join("");
}

/* ---------- calendario del mes ---------- */
function calendar() {
  const first = month, start = addDays(first, -((first.getDay() + 6) % 7));  // la semana empieza en lunes
  const today = dayKey(new Date());
  const count = {};
  visible().filter((t) => t.due && !t.done).forEach((t) => { const k = dayKey(new Date(t.due)); count[k] = (count[k] || 0) + 1; });
  let cells = "";
  for (let i = 0; i < 42; i++) {
    const d = addDays(start, i), k = dayKey(d), n = count[k] || 0;
    cells += `<button class="cal-day${d.getMonth() !== first.getMonth() ? " out" : ""}${k === today ? " today" : ""}${k === pickDay ? " sel" : ""}" data-day="${k}"
      aria-label="${esc(dayLabel(d))}${n ? `, ${n} pendientes` : ""}"><span>${d.getDate()}</span><i>${n ? (n > 3 ? "•••" : "•".repeat(n)) : ""}</i></button>`;
  }
  return html`
    <div class="card glass cal">
      <div class="cal-head">
        <button class="icon-btn" data-cal="-1" aria-label="Mes anterior">${raw(icon("back"))}</button>
        <h2>${cap(MONTHS[first.getMonth()])} ${first.getFullYear()}</h2>
        <button class="icon-btn flip" data-cal="1" aria-label="Mes siguiente">${raw(icon("back"))}</button>
      </div>
      <div class="cal-grid">${raw(["L", "M", "M", "J", "V", "S", "D"].map((x) => `<b>${x}</b>`).join(""))}${raw(cells)}</div>
      ${pickDay ? raw(`<button class="btn btn-quiet" data-cal="all">Ver toda la agenda</button>`) : raw(`<p class="muted cal-tip">Toca un día para ver lo que tienes.</p>`)}
    </div>`;
}

function onCalClick(e) {
  const nav = e.target.closest("[data-cal]");
  if (nav) {
    if (nav.dataset.cal === "all") pickDay = null;
    else month = new Date(month.getFullYear(), month.getMonth() + Number(nav.dataset.cal), 1);
    return draw();
  }
  const day = e.target.closest("[data-day]");
  if (day) { pickDay = pickDay === day.dataset.day ? null : day.dataset.day; draw(); }
}

/* ---------- acciones ---------- */
async function onClick(e) {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const li = btn.closest(".item"), id = Number(li.dataset.id);
  try {
    if (btn.dataset.act === "toggle") {
      const r = await api.patchTask(id, { done: !li.classList.contains("done") });
      if (r.message) toast(r.message, /no pude|no acept/i.test(r.message) ? "error" : "info", 6000);
    }
    if (btn.dataset.act === "delete") await api.deleteTask(id);
    if (btn.dataset.act === "undate") await api.patchTask(id, { due: "" });
    if (btn.dataset.act === "edit") { if (e.target.closest("a")) return; return editTask(tasks.find((t) => t.id === id)); }
  } catch (err) { toast(err.message, "error"); }
  load();
}

function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } }

/** Hoja para editar un pendiente: título, descripción, fecha, prioridad y enlace. */
function editTask(t) {
  if (!t) return;
  document.querySelector(".composer-sheet")?.remove();
  const d = t.due ? new Date(t.due) : null;
  const local = d ? new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  const sheet = document.createElement("div");
  sheet.className = "composer-sheet";
  sheet.innerHTML = html`
    <form class="panel glass sheet-body" role="dialog" aria-label="Editar pendiente">
      <div class="sheet-head"><h2>Editar pendiente</h2>
        <button type="button" class="icon-btn" data-close aria-label="Cerrar">${raw(icon("x"))}</button></div>
      <label class="field"><span>Título</span><input class="input" name="text" value="${shownText(t)}" required maxlength="200"></label>
      <label class="field"><span>Descripción</span><textarea class="input" name="notes" rows="5" placeholder="Detalles, pasos, a quién llamar…">${t.notes || ""}</textarea></label>
      <div class="grid-2">
        <label class="field"><span>Fecha y hora</span><input class="input" type="datetime-local" name="due" value="${local}"></label>
        <div class="field"><span>Prioridad</span>
          <div class="seg" id="prioSeg">${raw(["baja", "normal", "alta"].map((p) => `<button type="button" data-p="${p}" aria-pressed="${(t.priority || "normal") === p}">${p[0].toUpperCase() + p.slice(1)}</button>`).join(""))}</div></div>
      </div>
      <div class="grid-2">
        <div class="field"><span>Tipo</span>
          <div class="seg" id="catEdit">${raw(["personal", "trabajo"].map((c) => `<button type="button" data-c="${c}" aria-pressed="${(t.category || "personal") === c}">${c === "personal" ? "Personal" : "Trabajo"}</button>`).join(""))}</div></div>
        <label class="field"><span>Enlace (opcional)</span><input class="input" name="link" type="url" value="${t.link || ""}" placeholder="https://… (Jira, GitHub, documento)" ${t.ext_key ? "readonly" : ""}></label>
      </div>
      ${t.ext_key && t.source === "jira" ? raw(html`
        <div class="field jira-box"><span>Estado en Jira · ${t.ext_key}</span>
          <div class="row"><select class="input" id="jiraMove"><option>Cargando estados…</option></select>
            <button type="button" class="btn" id="jiraMoveBtn">Mover</button></div>
          <small>Los cambios de título, fecha y descripción también se guardan en Jira.</small></div>`) : ""}
      ${!t.ext_key && jiraConn() ? raw(`<button type="button" class="btn btn-quiet" id="toJira">${icon("send")}Crear como ticket en Jira</button>`) : ""}
      <div class="panel-actions">
        <button type="button" class="btn btn-quiet" data-close>Cancelar</button>
        <button class="btn btn-primary">${raw(icon("check"))}Guardar</button></div>
    </form>`;
  document.body.append(sheet);
  const f = sheet.querySelector("form");
  let prio = t.priority || "normal";
  sheet.querySelector("#prioSeg").addEventListener("click", (e) => {
    const b = e.target.closest("[data-p]"); if (!b) return;
    prio = b.dataset.p;
    sheet.querySelectorAll("[data-p]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
  let tcat = t.category || "personal";
  sheet.querySelector("#catEdit").addEventListener("click", (e) => {
    const b = e.target.closest("[data-c]"); if (!b) return;
    tcat = b.dataset.c;
    sheet.querySelectorAll("[data-c]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
  const sel = sheet.querySelector("#jiraMove");
  if (sel) {
    api.taskTransitions(t.id).then((ts) => {
      sel.innerHTML = `<option value="">${esc(t.ext_status || "Estado actual")} (actual)</option>` +
        ts.map((x) => `<option value="${esc(x.id)}">→ ${esc(x.to || x.name)}</option>`).join("");
    }).catch((err) => { sel.innerHTML = `<option value="">${esc(err.message)}</option>`; });
    sheet.querySelector("#jiraMoveBtn").onclick = async () => {
      if (!sel.value) return;
      try { const r = await api.taskMove(t.id, sel.value); toast(r.message); close(); load(); } catch (err) { toast(err.message, "error"); }
    };
  }
  sheet.querySelector("#toJira")?.addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    try { const r = await api.taskToJira(t.id); toast(`Creado ${r.key} en Jira`); close(); load(); }
    catch (err) { toast(err.message, "error"); e.currentTarget.disabled = false; }
  });
  const close = () => sheet.remove();
  sheet.querySelectorAll("[data-close]").forEach((b) => (b.onclick = close));
  sheet.addEventListener("click", (e) => { if (e.target === sheet) close(); });
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(f));
    try {
      const title = t.ext_key ? `${t.ext_key} · ${v.text.trim()}` : v.text.trim();
      const r = await api.patchTask(t.id, { text: title, notes: v.notes.trim(), due: v.due || "", priority: prio, link: v.link.trim(), category: tcat });
      toast(r.message || "Pendiente actualizado", r.message ? "error" : "info", r.message ? 7000 : 3000); close(); load();
    } catch (err) { toast(err.message, "error"); }
  });
  f.text.focus();
}

async function onDateChange(e) {
  const inp = e.target.closest("[data-due]");
  if (!inp) return;
  try { await api.patchTask(Number(inp.dataset.due), { due: inp.value || "" }); toast("Fecha actualizada"); }
  catch (err) { toast(err.message, "error"); }
  load();
}
