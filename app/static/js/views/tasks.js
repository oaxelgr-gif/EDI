// Pendientes: agregar con lenguaje natural, marcar, borrar.
import { api } from "../api.js";
import { $, el, fmtDue, html, icon, raw } from "../ui/dom.js";
import { toast } from "../ui/toast.js";

let root, app;

export async function render(container, _params, ctx) {
  root = container; app = ctx;
  root.innerHTML = html`
    <section class="page">
      <header class="page-head"><div>
        <h1>Pendientes</h1>
        <p>Escríbelos como se los dirías a EDI: “pagar la luz mañana a las 5”. La fecha se entiende sola y te aviso en voz alta.</p>
      </div></header>
      <form class="add-bar glass" id="addTask">
        <input class="input" name="text" placeholder="Nuevo pendiente" aria-label="Nuevo pendiente" autocomplete="off" required>
        <button class="btn btn-primary">Agregar</button>
      </form>
      <div id="taskList"></div>
    </section>`;
  $("#addTask", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    try { await api.addTask(f.text.value); f.reset(); load(); } catch (err) { toast(err.message, "error"); }
  });
  $("#taskList", root).addEventListener("click", onClick);
  load();
}

async function load() {
  const all = await api.tasks(true);
  const open = all.filter((t) => !t.done), done = all.filter((t) => t.done).slice(-15).reverse();
  app.setTaskCount?.(open.length);
  const now = new Date();
  const row = (t) => html`
    <li class="item ${t.done ? "done" : ""}" data-id="${t.id}">
      <button class="check" data-act="toggle" aria-label="${t.done ? "Marcar como pendiente" : "Marcar como hecho"}">${raw(icon("check"))}</button>
      <div class="item-body">
        <div class="item-title">${t.text}</div>
        ${t.due ? raw(`<div class="item-sub"><span class="due ${!t.done && new Date(t.due) < now ? "late" : ""}">${fmtDue(t.due)}</span></div>`) : ""}
      </div>
      <div class="item-actions">
        <button class="icon-btn" data-act="delete" aria-label="Borrar">${raw(icon("trash"))}</button>
      </div>
    </li>`;
  $("#taskList", root).innerHTML = open.length
    ? html`<div class="card glass"><ul class="items">${open.map((t) => raw(row(t)))}</ul></div>`
    : `<div class="empty">No tienes pendientes. Agrega uno arriba o dile a EDI “recuérdame…”.</div>`;
  if (done.length) $("#taskList", root).append(el(html`<div><div class="group-title">Hechos recientemente</div><div class="card glass"><ul class="items">${done.map((t) => raw(row(t)))}</ul></div></div>`));
}

async function onClick(e) {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const li = btn.closest(".item"), id = Number(li.dataset.id);
  if (btn.dataset.act === "toggle") await api.patchTask(id, { done: !li.classList.contains("done") });
  if (btn.dataset.act === "delete") await api.deleteTask(id);
  load();
}
