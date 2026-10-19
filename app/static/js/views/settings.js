// Ajustes: General, Voz, Inteligencia (llaves y proveedores) y Correos (registro de cuentas).
import { api } from "../api.js";
import { store } from "../store.js";
import { $, esc, html, icon, raw } from "../ui/dom.js";
import { toast } from "../ui/toast.js";
import { speak } from "../voice/speaker.js";

const TABS = [["general", "General"], ["voice", "Voz"], ["ai", "Inteligencia"], ["mail", "Correos"]];
let root, app, kinds = {}, presets = {};

export async function render(container, params, ctx) {
  root = container; app = ctx;
  const tab = TABS.some(([k]) => k === params.tab) ? params.tab : "general";
  root.innerHTML = html`
    <section class="page">
      <header class="page-head"><div><h1>Ajustes</h1></div></header>
      <div class="tabs" role="tablist">${TABS.map(([k, label]) => raw(`<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${label}</button>`))}</div>
      <div id="tabBody"></div>
    </section>`;
  $(".tabs", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (b) location.hash = `#/settings/${b.dataset.tab}`;
  });
  const body = $("#tabBody", root);
  ({ general: renderGeneral, voice: renderVoice, ai: renderAI, mail: renderMail })[tab](body, params);
}

/* ---------------- General ---------------- */
async function renderGeneral(body) {
  const s = await api.settings();
  body.innerHTML = html`
    <form class="section" id="genForm">
      <h2>Tú y EDI</h2>
      <label class="field"><span>¿Cómo te llama EDI?</span><input class="input" name="user_name" value="${s.user_name}" maxlength="30"></label>
      <h2 style="margin-top:12px">Correo</h2>
      <div class="kv">
        <label for="mcm">Avisar de correo nuevo cada (minutos, 0 = nunca)</label><input class="input" id="mcm" name="mail_check_minutes" type="number" min="0" max="240" value="${s.mail_check_minutes}">
        <label for="mmx">Correos a revisar por cuenta</label><input class="input" id="mmx" name="mail_max_per_account" type="number" min="3" max="50" value="${s.mail_max_per_account}">
      </div>
      <h2 style="margin-top:12px">Consumo de IA</h2>
      <p>Menos tokens por respuesta y menos historial = más peticiones dentro de los límites gratuitos.</p>
      <div class="kv">
        <label for="mt">Tokens máximos por respuesta</label><input class="input" id="mt" name="llm_max_tokens" type="number" min="60" max="2000" step="10" value="${s.llm_max_tokens}">
        <label for="lh">Mensajes de historial que recuerda en la conversación</label><input class="input" id="lh" name="llm_history" type="number" min="0" max="20" value="${s.llm_history}">
        <label for="tp">Creatividad (0 = precisa, 1 = creativa)</label><input class="input" id="tp" name="llm_temperature" type="number" min="0" max="1" step="0.1" value="${s.llm_temperature}">
      </div>
      <div class="panel-actions"><button class="btn btn-primary">Guardar cambios</button></div>
    </form>`;
  $("#genForm", body).addEventListener("submit", async (e) => {
    e.preventDefault();
    const saved = await api.saveSettings(Object.fromEntries(new FormData(e.target)));
    store.set({ settings: saved });
    toast("Cambios guardados");
  });
}

/* ---------------- Voz ---------------- */
async function renderVoice(body) {
  const [s, voices] = await Promise.all([api.settings(), api.voices().catch(() => [])]);
  const rate = parseInt(s.tts_rate) || 0;
  body.innerHTML = html`
    <form class="section" id="voiceForm">
      <h2>Cómo suena EDI</h2>
      <p>La voz neural se genera en línea y gratis; suena natural en cualquier Mac. Si no hay internet, EDI usa la voz del navegador.</p>
      <label class="field"><span>Motor de voz</span>
        <select class="input" name="tts_engine">
          <option value="edge" ${s.tts_engine === "edge" ? "selected" : ""}>Voz neural en línea (recomendada)</option>
          <option value="browser" ${s.tts_engine === "browser" ? "selected" : ""}>Voz del navegador</option>
        </select></label>
      <label class="field"><span>Voz</span>
        <select class="input" name="tts_voice">${voices.map((v) => raw(`<option value="${esc(v.id)}" ${v.id === s.tts_voice ? "selected" : ""}>${esc(v.label)}</option>`))}</select></label>
      <label class="field"><span>Velocidad: <b id="rateOut">${rate > 0 ? "+" : ""}${rate}%</b></span>
        <input type="range" name="rate" min="-25" max="40" step="5" value="${rate}"></label>
      <div class="panel-actions">
        <button type="button" class="btn" id="tryVoice">${raw(icon("volume"))}Probar</button>
        <button class="btn btn-primary">Guardar voz</button>
      </div>
    </form>`;
  const f = $("#voiceForm", body);
  const values = () => { const r = Number(f.rate.value); return { tts_engine: f.tts_engine.value, tts_voice: f.tts_voice.value, tts_rate: `${r >= 0 ? "+" : ""}${r}%` }; };
  f.rate.addEventListener("input", () => ($("#rateOut", body).textContent = values().tts_rate));
  $("#tryVoice", body).addEventListener("click", () => {
    store.set({ settings: { ...store.settings, ...values() } });
    speak(`Hola, ${store.settings.user_name || "jefe"}. Así sonaré a partir de ahora.`);
  });
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    store.set({ settings: await api.saveSettings(values()) });
    toast("Voz guardada");
  });
}

/* ---------------- Inteligencia ---------------- */
async function renderAI(body, params) {
  kinds = await api.kinds();
  body.innerHTML = `
    <div class="section">
      <h2>Proveedores de IA</h2>
      <p>EDI los usa en este orden. Si uno se queda sin cuota o falla, pasa al siguiente. Las tareas, notas y la hora no gastan tokens.</p>
      <div id="provList"></div>
      <div><button class="btn" id="addProv">${icon("plus")}Agregar proveedor</button></div>
      <div id="provForm"></div>
    </div>`;
  $("#addProv", body).addEventListener("click", () => providerForm($("#provForm", body)));
  await loadProviders(body);
  if (params.query?.new) providerForm($("#provForm", body));
}

async function loadProviders(body) {
  const list = await api.providers();
  const box = $("#provList", body);
  if (!list.length) { box.innerHTML = `<div class="empty">Sin proveedores. Agrega OmniRoute o una llave gratuita.</div>`; return; }
  box.innerHTML = list.map((p, i) => {
    const u = p.usage || {};
    return html`
    <div class="prov ${p.enabled ? "" : "off"}" data-id="${p.id}">
      <div class="prov-order">
        <button class="icon-btn" data-act="up" aria-label="Subir prioridad" ${i === 0 ? "disabled" : ""}>${raw(icon("up"))}</button>
        <button class="icon-btn" data-act="down" aria-label="Bajar prioridad" ${i === list.length - 1 ? "disabled" : ""}>${raw(icon("down"))}</button>
      </div>
      <div>
        <div class="prov-name"><strong>${p.name}</strong>${p.enabled && i === 0 ? raw(`<span class="badge">principal</span>`) : ""}<span class="muted">${p.model}</span></div>
        <div class="prov-meta">
          <span>${p.has_key ? "Llave " + p.api_key_masked : "Sin llave"}</span>
          <span>Hoy: ${u.requests || 0} peticiones, ${u.tokens || 0} tokens</span>
          ${u.errors ? raw(html`<span class="err" title="${u.last_error || ""}">${u.errors} fallos</span>`) : ""}
          <span class="test-out"></span>
        </div>
      </div>
      <div class="prov-actions">
        <button class="btn btn-quiet" data-act="test">Probar</button>
        <button class="icon-btn" data-act="edit" aria-label="Editar">${raw(icon("edit"))}</button>
        <button class="icon-btn" data-act="del" aria-label="Eliminar">${raw(icon("trash"))}</button>
        <span class="switch" title="${p.enabled ? "Activo" : "Inactivo"}"><input type="checkbox" data-act="toggle" ${p.enabled ? "checked" : ""} aria-label="Activar ${p.name}"></span>
      </div>
    </div>`;
  }).join("");
  box.onclick = async (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const row = b.closest(".prov"), id = Number(row.dataset.id), act = b.dataset.act;
    const ids = list.map((p) => p.id), idx = ids.indexOf(id);
    if (act === "toggle") { await api.patchProvider(id, { enabled: b.checked ? 1 : 0 }); }
    else if (act === "up" || act === "down") {
      const j = act === "up" ? idx - 1 : idx + 1;
      [ids[idx], ids[j]] = [ids[j], ids[idx]];
      await api.orderProviders(ids);
    } else if (act === "del") {
      if (!confirm(`¿Eliminar ${list[idx].name}?`)) return;
      await api.deleteProvider(id);
    } else if (act === "edit") { return providerForm($("#provForm", body), list[idx]); }
    else if (act === "test") {
      const out = row.querySelector(".test-out");
      out.textContent = "probando…";
      const r = await api.testSavedProvider(id);
      out.innerHTML = r.ok ? `<span style="color:var(--ok)">Responde en ${r.ms} ms</span>` : `<span class="err">${esc(r.error)}</span>`;
      return;
    }
    loadProviders(body);
    refreshHealth();
  };
}

function providerForm(box, p = null) {
  const kind = p?.kind || "omniroute";
  box.innerHTML = html`
    <form class="panel" id="pf">
      <h2 style="font-size:var(--fs-lg)">${p ? `Editar ${p.name}` : "Nuevo proveedor"}</h2>
      <div class="grid-2">
        <label class="field"><span>Tipo</span>
          <select class="input" name="kind">${Object.entries(kinds).map(([k, v]) => raw(`<option value="${k}" ${k === kind ? "selected" : ""}>${esc(v.label)}</option>`))}</select></label>
        <label class="field"><span>Nombre</span><input class="input" name="name" value="${p?.name || ""}" placeholder="Se llena solo"></label>
      </div>
      <label class="field"><span>Llave (API key)</span>
        <input class="input" name="api_key" type="password" autocomplete="off" placeholder="${p?.has_key ? "Guardada · escribe sólo para cambiarla" : "Pega tu llave"}">
        <small id="keyHelp"></small></label>
      <div class="grid-2">
        <label class="field"><span>URL base</span><input class="input" name="base_url" value="${p?.base_url || ""}"></label>
        <label class="field"><span>Modelo</span><input class="input" name="model" value="${p?.model || ""}" list="modelList">
          <datalist id="modelList"></datalist>
          ${p ? raw(`<small><a href="#" id="loadModels">Ver modelos disponibles</a></small>`) : ""}</label>
      </div>
      <div class="panel-actions">
        <span class="result" id="pfResult"></span>
        <button type="button" class="btn btn-quiet" id="pfCancel">Cancelar</button>
        <button type="button" class="btn" id="pfTest">Probar</button>
        <button class="btn btn-primary">${p ? "Guardar cambios" : "Agregar"}</button>
      </div>
    </form>`;
  const f = $("#pf", box);
  const syncKind = (first) => {
    const k = kinds[f.kind.value] || {};
    if (!first || !p) { f.base_url.value = p && first ? p.base_url : k.base_url || ""; f.model.value = p && first ? p.model : k.model || ""; }
    f.base_url.placeholder = k.base_url || "https://…/v1";
    const help = f.kind.value === "omniroute"
      ? `OmniRoute corre en tu Mac: ábrelo en <a href="http://localhost:20128" target="_blank" rel="noopener">localhost:20128</a>, crea una llave y usa el modelo <b>auto/best-free</b> o un combo tuyo.`
      : k.key_url ? `Consigue tu llave gratis en <a href="${k.key_url}" target="_blank" rel="noopener">${k.key_url.replace("https://", "")}</a>.` : "Cualquier servicio compatible con OpenAI (/v1/chat/completions).";
    $("#keyHelp", box).innerHTML = help;
  };
  syncKind(true);
  f.kind.addEventListener("change", () => syncKind(false));
  const data = () => Object.fromEntries(new FormData(f));
  $("#pfCancel", box).onclick = () => (box.innerHTML = "");
  $("#loadModels", box)?.addEventListener("click", async (e) => {
    e.preventDefault();
    const models = await api.models(p.id);
    $("#modelList", box).innerHTML = models.map((m) => `<option value="${esc(m)}">`).join("");
    toast(models.length ? `${models.length} modelos: escribe en el campo para filtrarlos` : "Ese proveedor no devolvió la lista de modelos");
  });
  $("#pfTest", box).onclick = async () => {
    const out = $("#pfResult", box);
    out.className = "result"; out.textContent = "Probando…";
    const d = data();
    if (p && !d.api_key) { const r = await api.testSavedProvider(p.id); return show(r); }
    show(await api.testProvider(d));
    function show(r) { out.className = `result ${r.ok ? "ok" : "err"}`; out.textContent = r.ok ? `Funciona (${r.ms} ms): “${r.reply}”` : r.error; }
  };
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const d = data();
      if (p) await api.patchProvider(p.id, d); else await api.addProvider({ ...d, priority: 99 });
      box.innerHTML = "";
      toast(p ? "Proveedor actualizado" : "Proveedor agregado");
      loadProviders(root); refreshHealth();
    } catch (err) { toast(err.message, "error"); }
  });
  f.scrollIntoView({ behavior: "smooth", block: "center" });
  (p ? f.api_key : f.kind).focus();
}

/* ---------------- Correos ---------------- */
async function renderMail(body, params) {
  presets = await api.mailPresets();
  body.innerHTML = `
    <div class="section">
      <h2>Cuentas de correo</h2>
      <p>EDI revisa estas cuentas en modo sólo lectura. Usa una contraseña de aplicación, nunca tu contraseña normal.</p>
      <div id="accList"></div>
      <div><button class="btn" id="addAcc">${icon("plus")}Registrar correo</button></div>
      <div id="accForm"></div>
    </div>`;
  $("#addAcc", body).addEventListener("click", () => accountForm($("#accForm", body)));
  await loadAccounts(body);
  if (params.query?.new) accountForm($("#accForm", body));
}

async function loadAccounts(body) {
  const list = await api.accounts();
  const box = $("#accList", body);
  if (!list.length) { box.innerHTML = `<div class="empty">Todavía no hay cuentas.</div>`; return; }
  box.innerHTML = list.map((a) => html`
    <div class="prov acc ${a.enabled ? "" : "off"}" data-id="${a.id}">
      <div>
        <div class="prov-name"><strong>${a.name}</strong><span class="muted">${a.user}</span></div>
        <div class="prov-meta"><span>${a.provider_label}</span><span class="test-out"></span></div>
      </div>
      <div class="prov-actions">
        <button class="btn btn-quiet" data-act="test">Probar</button>
        <button class="icon-btn" data-act="edit" aria-label="Editar">${raw(icon("edit"))}</button>
        <button class="icon-btn" data-act="del" aria-label="Eliminar">${raw(icon("trash"))}</button>
        <span class="switch"><input type="checkbox" data-act="toggle" ${a.enabled ? "checked" : ""} aria-label="Revisar ${a.name}"></span>
      </div>
    </div>`).join("");
  box.onclick = async (e) => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const row = b.closest(".prov"), id = Number(row.dataset.id), a = list.find((x) => x.id === id);
    if (b.dataset.act === "toggle") await api.patchAccount(id, { enabled: b.checked ? 1 : 0 });
    else if (b.dataset.act === "del") { if (!confirm(`¿Quitar ${a.user} de EDI?`)) return; await api.deleteAccount(id); }
    else if (b.dataset.act === "edit") return accountForm($("#accForm", body), a);
    else if (b.dataset.act === "test") {
      const out = row.querySelector(".test-out");
      out.textContent = "conectando…";
      const r = await api.testSavedAccount(id);
      out.innerHTML = r.ok ? `<span style="color:var(--ok)">Conectada, ${r.unread} sin leer</span>` : `<span class="err">${esc(r.error)}</span>`;
      return;
    }
    loadAccounts(body); refreshHealth();
  };
}

function accountForm(box, a = null) {
  const prov = a?.provider || "gmail";
  box.innerHTML = html`
    <form class="panel" id="af">
      <h2 style="font-size:var(--fs-lg)">${a ? `Editar ${a.name}` : "Registrar correo"}</h2>
      <label class="field"><span>Proveedor</span>
        <select class="input" name="provider">${Object.entries(presets).map(([k, v]) => raw(`<option value="${k}" ${k === prov ? "selected" : ""}>${esc(v.label)}</option>`))}</select></label>
      <div class="hint" id="provHelp"></div>
      <div class="grid-2">
        <label class="field"><span>Correo</span><input class="input" name="user" type="email" value="${a?.user || ""}" placeholder="nombre@gmail.com" required autocomplete="off"></label>
        <label class="field"><span>Nombre corto</span><input class="input" name="name" value="${a?.name || ""}" placeholder="Personal, Escuela, Trabajo…"></label>
      </div>
      <label class="field"><span>Contraseña de aplicación</span>
        <input class="input" name="password" type="password" autocomplete="new-password" placeholder="${a?.has_password ? "Guardada · escribe sólo para cambiarla" : "16 letras, con o sin espacios"}" ${a ? "" : "required"}></label>
      <details class="adv"><summary>Servidor y carpetas</summary>
        <div class="grid-2">
          <label class="field"><span>Servidor IMAP</span><input class="input" name="host" value="${a?.host || ""}" placeholder="Automático"></label>
          <label class="field"><span>Puerto</span><input class="input" name="port" type="number" value="${a?.port || 993}"></label>
        </div>
        <label class="field" style="margin-top:12px"><span>Carpetas a revisar</span><input class="input" name="folders" value="${a?.folders || "INBOX"}"><small>Separadas por comas. INBOX es la bandeja de entrada.</small></label>
      </details>
      <div class="panel-actions">
        <span class="result" id="afResult"></span>
        <button type="button" class="btn btn-quiet" id="afCancel">Cancelar</button>
        <button type="button" class="btn" id="afTest">Probar conexión</button>
        <button class="btn btn-primary">${a ? "Guardar cambios" : "Registrar"}</button>
      </div>
    </form>`;
  const f = $("#af", box);
  const sync = () => {
    const p = presets[f.provider.value] || {};
    $("#provHelp", box).innerHTML = esc(p.help || "") + (p.help_url ? ` <a href="${esc(p.help_url)}" target="_blank" rel="noopener">Abrir la página</a>` : "");
    f.querySelector("details").open = f.provider.value === "imap";
  };
  sync();
  f.provider.addEventListener("change", sync);
  const data = () => { const d = Object.fromEntries(new FormData(f)); d.port = Number(d.port) || 993; if (!d.name) d.name = (presets[d.provider]?.label || "").split(" ")[0]; return d; };
  $("#afCancel", box).onclick = () => (box.innerHTML = "");
  $("#afTest", box).onclick = async () => {
    const out = $("#afResult", box);
    out.className = "result"; out.textContent = "Conectando…";
    const d = data();
    const r = a && !d.password ? await api.testSavedAccount(a.id) : await api.testAccount(d);
    out.className = `result ${r.ok ? "ok" : "err"}`;
    out.textContent = r.ok ? `Conectada: ${r.unread} sin leer` : r.error;
  };
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const d = data();
      if (a) await api.patchAccount(a.id, d); else await api.addAccount(d);
      box.innerHTML = "";
      toast(a ? "Cuenta actualizada" : "Correo registrado. EDI ya lo revisa.");
      loadAccounts(root); refreshHealth();
    } catch (err) { toast(err.message, "error"); }
  });
  f.scrollIntoView({ behavior: "smooth", block: "center" });
  (a ? f.password : f.user).focus();
}

function refreshHealth() { app.refreshHealth?.(); }
