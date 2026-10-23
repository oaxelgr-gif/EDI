// WhatsApp: vincular con QR, ver chats, leer y responder (puente Baileys en el contenedor edi-whatsapp).
import { api } from "../api.js";
import { $, esc, html, icon, raw } from "../ui/dom.js";
import { toast } from "../ui/toast.js";

let root, app, timer = null, openJid = null, lastState = "", filter = "", contactsCache = null;

export async function render(container, _params, ctx) {
  root = container; app = ctx; openJid = null; lastState = "";
  root.innerHTML = html`
    <section class="page">
      <header class="page-head">
        <div><h1>WhatsApp</h1><p>Todos tus chats y contactos. EDI sólo envía cuando tú lo confirmas.</p></div>
        <div class="row">
          <button class="btn" id="waRefresh" title="Actualizar" aria-label="Actualizar">${raw(icon("refresh"))}</button>
          <button class="btn btn-quiet" id="waLogout" hidden>${raw(icon("out"))}Desvincular</button>
        </div>
      </header>
      <div id="waBody"><div class="empty">Conectando con WhatsApp…</div></div>
    </section>`;
  $("#waRefresh", root).onclick = () => tick(true);
  $("#waLogout", root).onclick = async () => {
    if (!confirm("¿Desvincular WhatsApp de EDI? Tendrás que escanear el QR de nuevo.")) return;
    try { await api.waLogout(); toast("WhatsApp desvinculado"); lastState = ""; tick(true); } catch (e) { toast(e.message, "error"); }
  };
  tick(true);
  timer = setInterval(() => tick(false), 5000);
}

export function destroy() { clearInterval(timer); timer = null; }

/** Se envió o leyó algo desde otro dispositivo: el mismo refresco silencioso de cada 5 s, pero ya. */
export function refresh() { if (root?.isConnected) tick(false); }

async function tick(force) {
  if (!root?.isConnected) return destroy();
  let st;
  try { st = await api.waStatus(true); } catch (e) { st = { state: "offline", error: e.message }; }
  $("#waLogout", root).hidden = st.state !== "open";
  const body = $("#waBody", root);
  if (st.state === "open") {
    if (lastState !== "open" || force) await showChats(body);
    else if (!openJid) await showChats(body, true);
    else await loadMessages(true);
  } else if (st.has_qr) {
    if (lastState !== "qr" || force) {
      body.innerHTML = html`
        <div class="card glass wa-link">
          <img class="qr" alt="Código QR para vincular WhatsApp" src="/api/whatsapp/qr.svg?t=${Date.now()}">
          <div class="wa-steps"><h2>Vincula tu WhatsApp</h2>
            <ol><li>Abre WhatsApp en tu celular.</li>
              <li>Ve a <b>Ajustes → Dispositivos vinculados</b> (en Android: menú ⋮).</li>
              <li>Toca <b>Vincular un dispositivo</b> y escanea este código.</li></ol>
            <details class="adv wa-pair" ${st.code ? "open" : ""}><summary>¿No funciona el QR? Vincular con número de teléfono</summary>
              <form class="row" id="waPairForm" style="margin-top:10px">
                <input class="input" name="phone" inputmode="tel" placeholder="Tu número con lada, ej. 52 442 123 4567" required style="flex:1;min-width:200px">
                <button class="btn btn-primary">Obtener código</button>
              </form>
              <div class="wa-code" id="waCode">${st.code || ""}</div>
              <p class="muted">En el celular, en <b>Vincular un dispositivo</b>, toca <b>Vincular con el número de teléfono</b> y escribe el código.</p>
            </details>
            <p class="muted">El código QR se renueva solo. Usa un puente no oficial (Baileys): úsalo con moderación y sólo para tus propios chats.</p></div>
        </div>`;
      $("#waPairForm", body).addEventListener("submit", async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector("button"); btn.disabled = true;
        $("#waCode", body).textContent = "Pidiendo código…";
        try { const r = await api.waPair(e.target.phone.value); $("#waCode", body).textContent = r.code; }
        catch (err) { $("#waCode", body).textContent = ""; toast(err.message, "error"); }
        btn.disabled = false;
      });
    } else { const img = $("img.qr", body); if (img) img.src = `/api/whatsapp/qr.svg?t=${Date.now()}`; }
    lastState = "qr"; return;
  } else {
    body.innerHTML = html`<div class="empty">${st.state === "offline"
      ? (st.error || "El servicio de WhatsApp no responde.") + " Reinicia EDI desde el Escritorio."
      : (st.detail || "Iniciando WhatsApp…")}</div>`;
  }
  lastState = st.state;
}

const fold = (x) => (x || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

async function showChats(body, quiet = false) {
  openJid = null;
  let cs;
  try { cs = await api.waChats(); } catch (e) { if (!quiet) body.innerHTML = html`<div class="empty">${e.message}</div>`; return; }
  app.setWaCount?.(cs.reduce((n, c) => n + (c.unread || 0), 0));
  if (!$("#waList", body)) {
    body.innerHTML = html`
      <div class="wa-tools">
        <input class="input" id="waSearch" type="search" placeholder="Buscar chat o contacto…" autocomplete="off" value="${filter}">
        <button class="btn btn-primary" id="waNew">${raw(icon("pen"))}Nuevo mensaje</button>
      </div>
      <ul class="items card glass wa-chats" id="waList"></ul>
      <p class="muted wa-tip">Por voz: «mándale un mensaje a mamá», «lee los últimos 5 mensajes de Juan», «resume el chat del trabajo».</p>`;
    const inp = $("#waSearch", body);
    inp.addEventListener("input", () => { filter = inp.value; renderList(body, body._chats); });
    $("#waNew", body).onclick = () => { inp.focus(); inp.placeholder = "Escribe el nombre del contacto…"; loadContacts().then(() => renderList(body, body._chats)); };
  }
  body._chats = cs;
  renderList(body, cs);
}

async function loadContacts() {
  if (!contactsCache) { try { contactsCache = await api.waContacts(); } catch { contactsCache = []; } }
  return contactsCache;
}

function renderList(body, cs) {
  const ul = $("#waList", body); if (!ul) return;
  const q = fold(filter.trim());
  let items = cs;
  if (q) {
    items = cs.filter((c) => fold(c.name).includes(q));
    if (contactsCache) {
      const have = new Set(items.map((c) => c.jid));
      items = items.concat(contactsCache.filter((c) => !have.has(c.jid) && fold(c.name).includes(q)).slice(0, 30));
    } else loadContacts().then(() => q === fold(filter.trim()) && renderList(body, cs));
  }
  if (!items.length) {
    ul.innerHTML = `<li class="item muted" style="padding:16px">${q ? "Sin resultados." : "Vinculado ✓. Si no ves tus chats, desvincula y vuelve a vincular una vez para cargar tu historial."}</li>`;
    return;
  }
  ul.innerHTML = items.map((c) => html`
    <li class="item wa-chat ${c.unread ? "unread" : ""}" data-jid="${c.jid}" data-name="${c.name}" tabindex="0">
      <div class="avatar">${(c.name || "?").trim().charAt(0).toUpperCase()}</div>
      <div class="item-body"><div class="item-title">${c.name}</div>
        <div class="item-sub snippet">${c.last ? (c.last.fromMe ? "Tú: " : "") + (c.last.text || "") : c.group ? "Grupo" : "Contacto"}</div></div>
      <div class="wa-meta"><span class="muted">${c.last?.ts ? when(c.last.ts) : c.ts ? when(c.ts) : ""}</span>${c.unread ? raw(`<span class="count hot">${c.unread}</span>`) : ""}</div>
    </li>`).join("");
  ul.querySelectorAll(".wa-chat").forEach((li) => {
    const open = () => openChat(li.dataset.jid, li.dataset.name);
    li.onclick = open; li.onkeydown = (e) => e.key === "Enter" && open();
  });
}

async function openChat(jid, name) {
  openJid = jid;
  const body = $("#waBody", root);
  body.innerHTML = html`
    <div class="card glass wa-thread">
      <div class="wa-thread-head">
        <button class="icon-btn" id="waBack" aria-label="Volver">${raw(icon("back"))}</button>
        <h2>${name}</h2>
        <button class="btn btn-quiet" id="waRead">${raw(icon("checks"))}Marcar leído</button>
      </div>
      <ul class="wa-msgs" id="waMsgs"><li class="muted">Cargando…</li></ul>
      <form class="wa-reply" id="waForm">
        <textarea class="input" name="text" rows="1" placeholder="Escribe una respuesta…" required></textarea>
        <button class="btn btn-primary" aria-label="Enviar">${raw(icon("send"))}</button>
      </form>
    </div>`;
  $("#waBack", body).onclick = () => showChats(body);
  $("#waRead", body).onclick = async () => { try { await api.waRead(jid); toast("Marcado como leído"); } catch (e) { toast(e.message, "error"); } };
  const f = $("#waForm", body);
  f.text.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); f.requestSubmit(); } });
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = f.text.value.trim(); if (!text) return;
    const btn = f.querySelector("button"); btn.disabled = true;
    try { await api.waSend(jid, text); f.text.value = ""; await loadMessages(false); }
    catch (err) { toast(err.message, "error"); }
    btn.disabled = false;
  });
  await loadMessages(false);
  api.waRead(jid).catch(() => {});
}

async function loadMessages(quiet) {
  const ul = $("#waMsgs", root); if (!ul || !openJid) return;
  try {
    const ms = await api.waMessages(openJid);
    const atBottom = ul.scrollHeight - ul.scrollTop - ul.clientHeight < 40;
    ul.innerHTML = ms.length ? ms.map((m) => html`
      <li class="wa-msg ${m.fromMe ? "me" : ""}">${!m.fromMe && m.name && openJid.endsWith("@g.us") ? raw(`<b>${esc(m.name)}</b>`) : ""}<p>${m.text || "(adjunto)"}</p><time>${when(m.ts)}</time></li>`).join("")
      : `<li class="muted">Aún no hay mensajes guardados de este chat.</li>`;
    if (!quiet || atBottom) ul.scrollTop = ul.scrollHeight;
  } catch (e) { if (!quiet) ul.innerHTML = html`<li class="muted">${e.message}</li>`; }
}

function when(ts) {
  const d = new Date(ts * (ts < 1e12 ? 1000 : 1)), now = new Date();
  return d.toDateString() === now.toDateString()
    ? d.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}
