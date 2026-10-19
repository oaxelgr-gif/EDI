// Memoria: lo que le pediste a EDI que recordara.
import { api } from "../api.js";
import { $, html, icon, raw, relTime } from "../ui/dom.js";
import { toast } from "../ui/toast.js";

let root, timer;

export async function render(container) {
  root = container;
  root.innerHTML = html`
    <section class="page">
      <header class="page-head"><div>
        <h1>Memoria</h1>
        <p>Todo lo que le dices a EDI con “recuerda que…”. Pregúntale después “¿qué te dije de…?”.</p>
      </div></header>
      <form class="add-bar" id="addNote">
        <input class="input" name="text" placeholder="Algo que EDI debe recordar" aria-label="Nueva nota" autocomplete="off" required>
        <button class="btn btn-primary">Guardar</button>
      </form>
      <input class="input" id="search" type="search" placeholder="Buscar en la memoria" aria-label="Buscar" style="margin-bottom:14px">
      <div id="noteList"></div>
    </section>`;
  $("#addNote", root).addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api.addNote(e.target.text.value); e.target.reset(); load(); } catch (err) { toast(err.message, "error"); }
  });
  $("#search", root).addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => load(e.target.value), 250); });
  $("#noteList", root).addEventListener("click", async (e) => {
    const b = e.target.closest("[data-del]");
    if (b) { await api.deleteNote(b.dataset.del); load($("#search", root).value); }
  });
  load();
}

async function load(q = "") {
  const notes = await api.notes(q.trim());
  $("#noteList", root).innerHTML = notes.length
    ? html`<ul class="items">${notes.map((n) => raw(html`
        <li class="item"><div class="item-body"><div class="item-title">${n.text}</div><div class="item-sub">${relTime(n.created)}</div></div>
        <div class="item-actions"><button class="icon-btn" data-del="${n.id}" aria-label="Olvidar">${raw(icon("trash"))}</button></div></li>`))}</ul>`
    : `<div class="empty">${q ? "Nada coincide con esa búsqueda." : "Aún no hay nada guardado. Escribe arriba o dile a EDI “recuerda que…”."}</div>`;
}
