// Correo: sin leer de todas las cuentas, con ver, marcar leído, responder y redactar.
import { api } from "../api.js";
import { $, el, esc, html, icon, raw } from "../ui/dom.js";
import { openComposer } from "../ui/composer.js";
import { toast } from "../ui/toast.js";

let root, app, data = null;

export async function render(container, _params, ctx) {
  root = container; app = ctx;
  root.innerHTML = html`
    <section class="page">
      <header class="page-head">
        <div><h1>Correo</h1><p>Lo que no has leído en todas tus cuentas. Nada se envía sin que tú lo confirmes.</p></div>
        <div class="row">
          <button class="btn btn-primary" id="compose">${raw(icon("pen"))}Redactar</button>
          <button class="btn" id="refresh" title="Revisar ahora" aria-label="Revisar ahora">${raw(icon("refresh"))}</button>
        </div>
      </header>
      <div class="row" style="margin:-8px 0 16px">
        <button class="btn btn-quiet" id="allRead">${raw(icon("checks"))}Marcar todo como leído</button>
        <a class="btn btn-quiet" href="#/settings/mail">${raw(icon("gear"))}Cuentas</a>
      </div>
      <div id="mailBody"><div class="empty">Revisando tus cuentas…</div></div>
    </section>`;
  $("#refresh", root).onclick = () => load(true);
  $("#compose", root).onclick = () => openComposer({ onSent: () => load(true) });
  $("#allRead", root).onclick = async () => {
    if (!confirm("¿Marcar como leídos todos los correos sin leer de tus cuentas?")) return;
    try { const r = await api.markAllRead(); toast(`${r.count} correos marcados como leídos`); load(true); } catch (e) { toast(e.message, "error"); }
  };
  $("#mailBody", root).addEventListener("click", onClick);
  load(false);
}

async function load(force) {
  const body = $("#mailBody", root);
  if (force) body.innerHTML = `<div class="empty">Revisando tus cuentas…</div>`;
  try {
    data = await api.mail(force);
    app.setMailCount?.(data.total);
    if (!data.accounts.length) {
      body.innerHTML = `<div class="empty">No hay cuentas registradas.<br><a class="btn btn-primary" href="#/settings/mail?new=1">Registrar un correo</a></div>`;
      return;
    }
    body.innerHTML = data.accounts.map((a) => html`
      <div class="acc-block card glass">
        <div class="acc-head"><h2>${a.name}</h2><span class="n">${a.error ? "" : a.unread_total + " sin leer"}</span><span class="muted">${a.user}</span></div>
        ${a.error ? raw(html`<div class="acc-error">No pude entrar: ${a.error}</div>`) : ""}
        ${a.items.length ? raw(html`<ul class="items">${a.items.map((i) => raw(html`
          <li class="item mail-item" data-uid="${i.uid}" data-acc="${a.id}">
            <div class="item-body">
              <div class="item-title">${i.subject}</div>
              <div class="item-sub"><span class="mail-from">${i.from}</span><span class="sep">${i.date}</span></div>
              <div class="item-sub snippet">${i.snippet}</div>
              <div class="mail-full" hidden></div>
            </div>
            <div class="item-actions">
              <button class="icon-btn" data-act="view" title="Ver completo" aria-label="Ver completo">${raw(icon("eye"))}</button>
              <button class="icon-btn" data-act="reply" title="Responder" aria-label="Responder">${raw(icon("reply"))}</button>
              <button class="icon-btn" data-act="read" title="Marcar como leído" aria-label="Marcar como leído">${raw(icon("check"))}</button>
            </div>
          </li>`))}</ul>`) : a.error ? "" : raw(`<div class="item-sub" style="padding:4px 2px 12px">Bandeja al día.</div>`)}
      </div>`).join("");
  } catch (e) {
    body.innerHTML = html`<div class="empty">No pude revisar el correo: ${e.message}</div>`;
  }
}

async function onClick(e) {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  const li = b.closest(".mail-item"), uid = li.dataset.uid;
  if (b.dataset.act === "read") {
    b.disabled = true;
    try { await api.markRead([uid]); li.remove(); app.setMailCount?.(Math.max(0, (data?.total || 1) - 1)); data.total--; }
    catch (err) { toast(err.message, "error"); b.disabled = false; }
  }
  if (b.dataset.act === "view") {
    const full = li.querySelector(".mail-full");
    if (!full.hidden) { full.hidden = true; return; }
    full.hidden = false; full.textContent = "Cargando…";
    try { const m = await api.mailMessage(uid); full.textContent = m.text || "(sin texto)"; } catch (err) { full.textContent = err.message; }
  }
  if (b.dataset.act === "reply") {
    try {
      const m = await api.mailMessage(uid);
      const quote = (m.text || "").split("\n").slice(0, 12).map((l) => "> " + l).join("\n");
      openComposer({ to: m.from_addr, subject: m.subject.toLowerCase().startsWith("re:") ? m.subject : "Re: " + m.subject,
                     body: `\n\n—\nEl ${m.date}, ${m.from} escribió:\n${quote}`, reply_uid: uid, account_id: m.account_id,
                     onSent: () => load(true) });
    } catch (err) { toast(err.message, "error"); }
  }
}
export { esc, el };
