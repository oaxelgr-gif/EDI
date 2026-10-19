// Correo sin leer de todas las cuentas registradas.
import { api } from "../api.js";
import { $, html, icon, raw } from "../ui/dom.js";

let root, app;

export async function render(container, _params, ctx) {
  root = container; app = ctx;
  root.innerHTML = html`
    <section class="page">
      <header class="page-head">
        <div><h1>Correo</h1><p>Lo que no has leído en todas tus cuentas. EDI sólo lee: nunca marca, borra ni envía.</p></div>
        <div class="row">
          <a class="btn btn-quiet" href="#/settings/mail">${raw(icon("gear"))}Cuentas</a>
          <button class="btn" id="refresh">${raw(icon("refresh"))}Revisar</button>
        </div>
      </header>
      <div id="mailBody"><div class="empty">Revisando tus cuentas…</div></div>
    </section>`;
  $("#refresh", root).addEventListener("click", () => load(true));
  load(false);
}

async function load(force) {
  const body = $("#mailBody", root);
  if (force) body.innerHTML = `<div class="empty">Revisando tus cuentas…</div>`;
  try {
    const m = await api.mail(force);
    app.setMailCount?.(m.total);
    if (!m.accounts.length) {
      body.innerHTML = `<div class="empty">No hay cuentas registradas.<br><a class="btn btn-primary" href="#/settings/mail?new=1">Registrar un correo</a></div>`;
      return;
    }
    body.innerHTML = m.accounts.map((a) => html`
      <div class="acc-block card glass">
        <div class="acc-head"><h2>${a.name}</h2><span class="n">${a.error ? "" : a.unread_total + " sin leer"}</span><span class="muted">${a.user}</span></div>
        ${a.error ? raw(html`<div class="acc-error">No pude entrar: ${a.error}</div>`) : ""}
        ${a.items.length ? raw(html`<ul class="items">${a.items.map((i) => raw(html`
          <li class="item"><div class="item-body">
            <div class="item-title">${i.subject}</div>
            <div class="item-sub"><span class="mail-from">${i.from}</span><span class="sep">${i.date}</span></div>
            <div class="item-sub">${i.snippet}</div>
          </div></li>`))}</ul>`) : a.error ? "" : raw(`<div class="item-sub">Bandeja al día.</div>`)}
      </div>`).join("");
  } catch (e) {
    body.innerHTML = html`<div class="empty">No pude revisar el correo: ${e.message}</div>`;
  }
}
