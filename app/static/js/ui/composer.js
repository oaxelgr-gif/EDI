// Redactor de correo (nuevo o respuesta) y tarjeta de borrador para confirmar envíos.
import { api } from "../api.js";
import { $, el, esc, html, icon, raw } from "./dom.js";
import { toast } from "./toast.js";

/** Abre un panel flotante para escribir un correo. */
export async function openComposer({ to = "", subject = "", body = "", reply_uid = "", account_id = null, onSent } = {}) {
  const accounts = (await api.accounts()).filter((a) => a.enabled && a.has_password);
  if (!accounts.length) { toast("Registra una cuenta con contraseña de aplicación en Ajustes → Correos", "error"); location.hash = "#/settings/mail"; return; }
  document.querySelector(".composer-sheet")?.remove();
  const sheet = el(html`
    <div class="composer-sheet" role="dialog" aria-label="${reply_uid ? "Responder correo" : "Nuevo correo"}">
      <form class="panel glass sheet-body">
        <div class="sheet-head"><h2>${reply_uid ? "Responder" : "Nuevo correo"}</h2>
          <button type="button" class="icon-btn" data-close aria-label="Cerrar">${raw(icon("x"))}</button></div>
        <label class="field"><span>Desde</span><select class="input" name="account_id">
          ${accounts.map((a) => raw(`<option value="${a.id}" ${a.id === account_id ? "selected" : ""}>${esc(a.name)} · ${esc(a.user)}</option>`))}</select></label>
        <label class="field"><span>Para</span><input class="input" name="to" type="text" value="${to}" placeholder="nombre@correo.com" required></label>
        <label class="field"><span>Asunto</span><input class="input" name="subject" value="${subject}"></label>
        <label class="field"><span>Mensaje</span><textarea class="input" name="body" rows="9" required>${body}</textarea></label>
        <div class="panel-actions"><span class="result" data-out></span>
          <button type="button" class="btn btn-quiet" data-close>Cancelar</button>
          <button class="btn btn-primary">${raw(icon("send"))}Enviar</button></div>
      </form>
    </div>`);
  document.body.append(sheet);
  const f = $("form", sheet);
  const close = () => sheet.remove();
  sheet.querySelectorAll("[data-close]").forEach((b) => (b.onclick = close));
  sheet.addEventListener("click", (e) => { if (e.target === sheet) close(); });
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f));
    const btn = f.querySelector(".btn-primary"); btn.disabled = true;
    $("[data-out]", sheet).textContent = "Enviando…";
    try {
      const r = await api.sendMail({ ...d, account_id: Number(d.account_id), reply_uid });
      toast(r.message || "Enviado"); close(); onSent?.();
    } catch (err) { $("[data-out]", sheet).className = "result err"; $("[data-out]", sheet).textContent = err.message; btn.disabled = false; }
  });
  (to ? f.body : f.to).focus();
}

/** Tarjeta de borrador en la conversación: editar y confirmar (o cancelar) el envío. */
const DRAFT = {
  email: ["mail", "Borrador de correo"], whatsapp: ["chat", "Borrador de WhatsApp"], slack: ["chat", "Mensaje de Slack"],
  jira_create: ["list", "Nuevo ticket de Jira"], jira_move: ["list", "Mover ticket de Jira"], jira_comment: ["list", "Comentario en Jira"],
};

function draftFields(d) {
  const extra = (() => { try { return JSON.parse(d.extra || "{}"); } catch { return {}; } })();
  switch (d.channel) {
    case "email": return html`
      <label class="field"><span>Para</span><input class="input" name="to_addr" value="${d.to_addr || ""}" placeholder="nombre@correo.com"></label>
      <label class="field"><span>Asunto</span><input class="input" name="subject" value="${d.subject || ""}"></label>
      <textarea class="input" name="body" rows="6">${d.body || ""}</textarea>`;
    case "jira_create": return html`
      <div class="grid-2">
        <label class="field"><span>Proyecto</span><input class="input" name="to_name" value="${d.to_name || ""}" placeholder="EDI"></label>
        <label class="field"><span>Fecha límite</span><input class="input" type="datetime-local" data-extra="due" value="${extra.due || ""}"></label>
      </div>
      <label class="field"><span>Título</span><input class="input" name="subject" value="${d.subject || ""}"></label>
      <label class="field"><span>Descripción</span><textarea class="input" name="body" rows="3" placeholder="Opcional">${d.body || ""}</textarea></label>`;
    case "jira_move": return html`<div class="muted">${d.to_addr} → <b>${d.subject}</b></div>`;
    case "jira_comment": return html`<div class="muted">En ${d.to_addr}</div><textarea class="input" name="body" rows="3">${d.body || ""}</textarea>`;
    default: return html`<div class="muted">Para: ${d.to_name || d.to_addr}</div><textarea class="input" name="body" rows="2">${d.body || ""}</textarea>`;
  }
}

export function draftCard(d, { onDone } = {}) {
  const [ico, title] = DRAFT[d.channel] || DRAFT.whatsapp;
  const verb = d.channel.startsWith("jira") ? (d.channel === "jira_create" ? "Crear" : d.channel === "jira_move" ? "Mover" : "Comentar") : "Enviar";
  const card = el(html`
    <div class="draft glass ${d.status}">
      <div class="draft-head">${raw(icon(ico))}<b>${title}</b>
        <span class="draft-status">${statusLabel(d.status)}</span></div>
      ${raw(draftFields(d))}
      <div class="panel-actions"><span class="result" data-out>${d.error || ""}</span>
        <button class="btn btn-quiet" data-cancel>Cancelar</button>
        <button class="btn btn-primary" data-send>${raw(icon("send"))}${verb}</button></div>
    </div>`);
  const lock = (status) => {
    card.className = `draft glass ${status}`;
    card.querySelector(".draft-status").textContent = statusLabel(status);
    card.querySelectorAll("input,textarea,button").forEach((x) => (x.disabled = status !== "pending"));
  };
  lock(d.status);
  card.querySelector("[data-send]").onclick = async () => {
    const patch = {};
    card.querySelectorAll("[name]").forEach((x) => (patch[x.name] = x.value));
    const ex = {};
    card.querySelectorAll("[data-extra]").forEach((x) => (ex[x.dataset.extra] = x.value));
    if (Object.keys(ex).length) { const base = (() => { try { return JSON.parse(d.extra || "{}"); } catch { return {}; } })(); patch.extra = JSON.stringify({ ...base, ...ex }); }
    card.querySelector("[data-out]").textContent = "Enviando…";
    try {
      const r = await api.sendDraft(d.id, patch);
      card.querySelector("[data-out]").textContent = r.message;
      card.querySelector("[data-out]").className = `result ${r.ok ? "ok" : "err"}`;
      if (r.ok) lock("sent");
      onDone?.(r);
    } catch (e) { card.querySelector("[data-out]").textContent = e.message; card.querySelector("[data-out]").className = "result err"; }
  };
  card.querySelector("[data-cancel]").onclick = async () => { await api.cancelDraft(d.id); lock("cancelled"); onDone?.({ ok: false, message: "Cancelado" }); };
  card.update = (nd) => lock(nd.status);
  return card;
}

const statusLabel = (s) => ({ pending: "esperando tu confirmación", sent: "hecho", cancelled: "cancelado", replaced: "reemplazado", expired: "caducó" }[s] || s);
