// Memoria: lo que le pediste a EDI que recordara.
import { api } from "../api.js";
import { $, html, icon, raw, relTime } from "../ui/dom.js";
import { toast } from "../ui/toast.js";
import { whenIdle } from "../ui/live.js";

let root, timer;

export async function render(container) {
  root = container;
  root.innerHTML = html`
    <section class="page">
      <header class="page-head"><div>
        <h1>Memoria</h1>
        <p>Todo lo que le dices a EDI con “recuerda que…”. Pregúntale después “¿qué te dije de…?”.</p>
      </div></header>
      <form class="add-bar glass" id="addNote">
        <input class="input" name="text" placeholder="Algo que EDI debe recordar" aria-label="Nueva nota" autocomplete="off" required>
        <button class="btn btn-primary">Guardar</button>
      </form>
      <input class="input glass" id="search" type="search" placeholder="Buscar en la memoria" aria-label="Buscar" style="margin-bottom:14px">
      <div id="noteList"></div>
    </section>`;
  $("#addNote", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api.addNote(e.target.text.value); e.target.reset(); load(); } catch (err) { toast(err.message, "error"); }
  });
  $("#search", root).addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => load(e.target.value), 250); });
  $("#noteList", root).addEventListener("click", async (e) => {
    const b = e.target.closest("[data-del]");
    if (b) {
      if (!confirm("¿Olvidar esta nota?")) return;
      await api.deleteNote(b.dataset.del); load($("#search", root).value); return;
    }
    const ed = e.target.closest("[data-edit]");
    if (ed) {
      const li = ed.closest("li"), title = li.querySelector(".item-title");
      if (li.querySelector("textarea")) return;
      const ta = document.createElement("textarea");
      ta.className = "input note-edit"; ta.rows = 2; ta.value = title.textContent;
      title.replaceWith(ta); ta.focus();
      let done = false;
      const finish = async (save) => {
        if (done) return; done = true;
        if (save && ta.value.trim() && ta.value.trim() !== title.textContent) {
          try { await api.patchNote(ed.dataset.edit, ta.value.trim()); toast("Nota actualizada"); } catch (err) { toast(err.message, "error"); }
        }
        load($("#search", root).value);
      };
      ta.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); finish(true); } if (ev.key === "Escape") finish(false); });
      ta.addEventListener("blur", () => finish(true));
    }
  });
  load();
}

/** Cambió la memoria en otro dispositivo: recarga respetando la búsqueda y la nota que estés editando. */
export function refresh() {
  if (!root?.isConnected) return;
  whenIdle($("#noteList", root), () => load($("#search", root)?.value || ""));
}

async function load(q = "") {
  const notes = await api.notes(q.trim());
  $("#noteList", root).innerHTML = notes.length
    ? groupByDate(notes).map(([title, items]) => html`
      <div class="agenda-sec">
        <div class="agenda-head"><h2>${title}</h2><span class="n">${items.length}</span></div>
        <div class="card glass"><ul class="items">${items.map((n) => raw(html`
          <li class="item" data-nid="${n.id}"><div class="item-body"><div class="item-title">${n.text}</div><div class="item-sub">${relTime(n.created)}</div></div>
          <div class="item-actions"><button class="icon-btn" data-edit="${n.id}" aria-label="Editar" title="Editar">${raw(icon("pen"))}</button>
          <button class="icon-btn" data-del="${n.id}" aria-label="Olvidar" title="Olvidar">${raw(icon("trash"))}</button></div></li>`))}</ul></div>
      </div>`).join("")
    : `<div class="empty">${q ? "Nada coincide con esa búsqueda." : "Aún no hay nada guardado. Escribe arriba o dile a EDI “recuerda que…”."}</div>`;
}

/** Agrupa por fecha en que se guardó: Hoy, Ayer, Esta semana, Este mes y por mes. */
function groupByDate(notes) {
  const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  const now = new Date(), today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const order = [], map = {};
  for (const n of notes) {
    const d = new Date(n.created), days = Math.floor((today - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    const key = days <= 0 ? "Hoy" : days === 1 ? "Ayer" : days < 7 ? "Esta semana"
      : d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear() ? "Este mes"
      : MONTHS[d.getMonth()][0].toUpperCase() + MONTHS[d.getMonth()].slice(1) + (d.getFullYear() !== now.getFullYear() ? ` ${d.getFullYear()}` : "");
    if (!map[key]) { map[key] = []; order.push(key); }
    map[key].push(n);
  }
  return order.map((k) => [k, map[k]]);
}
