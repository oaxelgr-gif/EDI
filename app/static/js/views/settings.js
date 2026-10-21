// Ajustes: General, Voz, Inteligencia (llaves y proveedores) y Correos (registro de cuentas).
import { api } from "../api.js";
import { store } from "../store.js";
import { $, esc, html, icon, raw, relTime } from "../ui/dom.js";
import { toast } from "../ui/toast.js";
import { speak } from "../voice/speaker.js";

const TABS = [["general", "General"], ["look", "Diseño"], ["voice", "Voz"], ["ai", "Inteligencia"], ["mail", "Correos"], ["connections", "Conexiones"], ["devices", "Dispositivos"]];
let root, app, kinds = {}, presets = {};

export async function render(container, params, ctx) {
  root = container; app = ctx;
  const tab = TABS.some(([k]) => k === params.tab) ? params.tab : "general";
  root.innerHTML = html`
    <section class="page">
      <header class="page-head"><div><h1>Ajustes</h1></div></header>
      <div class="tabs glass" role="tablist">${TABS.map(([k, label]) => raw(`<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${label}</button>`))}</div>
      <div id="tabBody"></div>
    </section>`;
  $(".tabs", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (b) location.hash = `#/settings/${b.dataset.tab}`;
  });
  const body = $("#tabBody", root);
  ({ general: renderGeneral, look: renderLook, voice: renderVoice, ai: renderAI, mail: renderMail, connections: renderConnections, devices: renderDevices })[tab](body, params);
}

/* ---------------- Diseño: colores, transparencia y tema ---------------- */
function renderLook(body) {
  const L = window.ediLook;
  let look = L.get();
  const pal = () => L.PALETTES.find((p) => p.id === look.palette) || L.PALETTES[0];
  body.innerHTML = html`
    <div class="panel glass">
      <h2>Tema</h2>
      <div class="seg" id="themeSeg">
        ${raw([["auto", "Automático"], ["dark", "Oscuro"], ["light", "Claro"]].map(([k, l]) =>
          `<button data-theme-opt="${k}" aria-pressed="${store.theme === k}">${l}</button>`).join(""))}
      </div>
    </div>
    <div class="panel glass">
      <h2>Paleta de colores</h2>
      <p class="muted">Cambia el color de botones, anillo de voz, brillos y fondo en toda la app.</p>
      <div class="swatches" id="swatches">
        ${raw(L.PALETTES.map((p) => `<button class="swatch" data-pal="${p.id}" aria-pressed="${p.id === look.palette && !look.a}" title="${esc(p.name)}">
          <span class="chip" style="background:linear-gradient(135deg, ${p.a}, ${p.b}${p.multi ? ", " + p.c : ""})"></span><span>${esc(p.name)}</span></button>`).join(""))}
      </div>
      <h3 style="margin-top:18px">Colores propios</h3>
      <div class="grid-2 colors">
        <label class="field"><span>Principal</span><input type="color" id="colA" value="${look.a || pal().a}"></label>
        <label class="field"><span>Secundario (degradados)</span><input type="color" id="colB" value="${look.b || pal().b}"></label>
      </div>
    </div>
    <div class="panel glass">
      <h2>Vidrio</h2>
      <label class="field"><span>Opacidad de los paneles · <b id="glassV">${look.glass}%</b></span>
        <input type="range" id="glass" min="30" max="220" step="10" value="${look.glass}"></label>
      <label class="field" style="margin-top:12px"><span>Desenfoque · <b id="blurV">${look.blur}px</b></span>
        <input type="range" id="blur" min="0" max="40" step="2" value="${look.blur}"></label>
      <div class="panel-actions" style="margin-top:14px"><span class="result muted">Se guarda en este dispositivo.</span>
        <button class="btn btn-quiet" id="lookReset">Restablecer</button></div>
    </div>`;
  const save = () => { L.set(look); body.querySelectorAll(".swatch").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.pal === look.palette && !look.a))); };
  $("#swatches", body).addEventListener("click", (e) => {
    const b = e.target.closest("[data-pal]"); if (!b) return;
    look = { ...look, palette: b.dataset.pal, a: null, b: null, c: null };
    $("#colA", body).value = pal().a; $("#colB", body).value = pal().b; save();
  });
  $("#colA", body).addEventListener("input", (e) => { look = { ...look, a: e.target.value, b: look.b || pal().b }; save(); });
  $("#colB", body).addEventListener("input", (e) => { look = { ...look, b: e.target.value, a: look.a || pal().a }; save(); });
  $("#glass", body).addEventListener("input", (e) => { look = { ...look, glass: +e.target.value }; $("#glassV", body).textContent = look.glass + "%"; save(); });
  $("#blur", body).addEventListener("input", (e) => { look = { ...look, blur: +e.target.value }; $("#blurV", body).textContent = look.blur + "px"; save(); });
  $("#lookReset", body).onclick = () => { look = { ...L.DEFAULT }; save(); renderLook(body); };
  $("#themeSeg", body).addEventListener("click", async (e) => {
    const b = e.target.closest("[data-theme-opt]"); if (!b) return;
    store.set({ theme: b.dataset.themeOpt });
    (await import("../main.js")).applyTheme?.(b.dataset.themeOpt);
    body.querySelectorAll("[data-theme-opt]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  });
}

/* ---------------- General ---------------- */
async function renderGeneral(body) {
  const s = await api.settings();
  body.innerHTML = html`
    <form class="section panel glass" id="genForm">
      <h2>Tú y EDI</h2>
      <div class="grid-2">
        <label class="field"><span>¿Cómo te llama EDI?</span><input class="input" name="user_name" value="${s.user_name}" maxlength="30"></label>
        <label class="field"><span>Tu ciudad (para el clima)</span><input class="input" name="home_city" value="${s.home_city || ""}" placeholder="Querétaro"></label>
      </div>
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
  const pitch = parseInt(s.tts_pitch) || 0;
  body.innerHTML = html`
    <form class="section panel glass" id="voiceForm">
      <h2>Cómo suena EDI</h2>
      <p>Voz neural gratuita en línea. Para una voz más cálida prueba Dalia con tono +2 a +4 Hz, o las voces multilingües (Ava, Emma, Vivienne), que son muy expresivas.</p>
      <label class="field"><span>Motor de voz</span>
        <select class="input" name="tts_engine">
          <option value="edge" ${s.tts_engine === "edge" ? "selected" : ""}>Voz neural en línea (recomendada)</option>
          <option value="browser" ${s.tts_engine === "browser" ? "selected" : ""}>Voz del navegador</option>
        </select></label>
      <label class="field"><span>Voz</span>
        <select class="input" name="tts_voice">${voices.map((v) => raw(`<option value="${esc(v.id)}" ${v.id === s.tts_voice ? "selected" : ""}>${esc(v.label)}</option>`))}</select></label>
      <label class="field"><span>Velocidad: <b id="rateOut">${rate > 0 ? "+" : ""}${rate}%</b></span>
        <input type="range" name="rate" min="-25" max="40" step="2" value="${rate}"></label>
      <label class="field"><span>Tono: <b id="pitchOut">${pitch > 0 ? "+" : ""}${pitch} Hz</b></span>
        <input type="range" name="pitch" min="-20" max="20" step="1" value="${pitch}"></label>
      <div class="panel-actions">
        <button type="button" class="btn" id="tryVoice">${raw(icon("volume"))}Probar</button>
        <button class="btn btn-primary">Guardar voz</button>
      </div>
    </form>`;
  const f = $("#voiceForm", body);
  const values = () => {
    const r = Number(f.rate.value), p = Number(f.pitch.value);
    return { tts_engine: f.tts_engine.value, tts_voice: f.tts_voice.value, tts_rate: `${r >= 0 ? "+" : ""}${r}%`, tts_pitch: `${p >= 0 ? "+" : ""}${p}Hz` };
  };
  f.rate.addEventListener("input", () => ($("#rateOut", body).textContent = values().tts_rate));
  f.pitch.addEventListener("input", () => ($("#pitchOut", body).textContent = values().tts_pitch.replace("Hz", " Hz")));
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
      <div id="provList" class="card glass"></div>
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
    <form class="panel glass" id="pf">
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
/* ---------------- Conexiones de trabajo (Jira, GitHub, Slack) ---------------- */
let connKinds = {};
const CONN_ICON = { jira: "list", github: "bolt", slack: "chat" };

async function renderConnections(body, params) {
  connKinds = await api.connectionKinds();
  const s = await api.settings();
  body.innerHTML = html`
    <div class="section">
      <h2>Conexiones de trabajo</h2>
      <p>Lo que tienes asignado en Jira y GitHub (y lo que marques con ✅ en Slack) aparece en tus <b>pendientes de trabajo</b>, con recordatorios.
        Crear, mover o comentar tickets y mandar mensajes por voz siempre te pide confirmación.</p>
      <div id="connList" class="card glass"></div>
      <div class="row conn-add">${raw(Object.entries(connKinds).map(([k, c]) => `<button class="btn" data-add="${k}">${icon("plus")}${esc(c.label)}</button>`).join(""))}</div>
      <div id="connForm"></div>
      <div class="panel glass">
        <div class="grid-2">
          <label class="field"><span>Sincronizar automáticamente</span>
            <select class="input" id="syncMin">${raw([["0", "Sólo manual"], ["5", "Cada 5 minutos"], ["10", "Cada 10 minutos"], ["30", "Cada 30 minutos"], ["60", "Cada hora"]]
              .map(([v, l]) => `<option value="${v}" ${String(s.sync_minutes) === v ? "selected" : ""}>${l}</option>`).join(""))}</select></label>
          <div class="field"><span>&nbsp;</span><button class="btn" id="syncNow">${raw(icon("refresh"))}Sincronizar todo ahora</button></div>
        </div>
      </div>
    </div>`;
  body.querySelectorAll("[data-add]").forEach((b) => (b.onclick = () => connectionForm($("#connForm", body), b.dataset.add, null, body)));
  $("#syncMin", body).onchange = async (e) => { await api.saveSettings({ sync_minutes: e.target.value }); toast("Guardado"); };
  $("#syncNow", body).onclick = async (e) => {
    const b = e.currentTarget; b.disabled = true;
    try { const r = await api.syncAll(); const bad = Object.values(r).find((x) => !x.ok); toast(bad ? bad.error : "Sincronizado", bad ? "error" : "info"); }
    catch (err) { toast(err.message, "error"); }
    b.disabled = false; loadConnections(body);
  };
  $("#connList", body).addEventListener("click", (e) => onConnClick(e, body));
  $("#connList", body).addEventListener("change", (e) => onConnClick(e, body));
  await loadConnections(body);
  if (params.query?.new && connKinds[params.query.new]) connectionForm($("#connForm", body), params.query.new, null, body);
}

async function loadConnections(body) {
  const list = await api.connections();
  const box = $("#connList", body);
  if (!list.length) { box.innerHTML = `<div class="empty">Aún no conectas nada. Empieza con Jira o GitHub.</div>`; return; }
  box.innerHTML = list.map((c) => html`
    <div class="prov conn ${c.enabled ? "" : "off"}" data-id="${c.id}">
      <div>
        <div class="prov-name"><span class="conn-ico ${c.kind}">${raw(icon(CONN_ICON[c.kind] || "globe"))}</span><strong>${c.name}</strong>
          <span class="muted">${c.label}${c.me ? " · " + c.me : ""}</span></div>
        <div class="prov-meta">
          ${c.last_error ? raw(`<span class="result err">${esc(c.last_error)}</span>`) : c.last_sync ? raw(`<span class="result ok">Sincronizado ${esc(relTime(c.last_sync))}</span>`) : raw(`<span class="muted">Sin sincronizar</span>`)}
          <span>${c.open_tasks} pendiente${c.open_tasks === 1 ? "" : "s"}</span><span class="test-out"></span>
        </div>
      </div>
      <div class="prov-actions">
        <button class="btn btn-quiet" data-act="sync" title="Sincronizar">${raw(icon("refresh"))}</button>
        <button class="btn btn-quiet" data-act="test">Probar</button>
        <button class="icon-btn" data-act="edit" aria-label="Editar">${raw(icon("edit"))}</button>
        <button class="icon-btn" data-act="del" aria-label="Eliminar">${raw(icon("trash"))}</button>
        <span class="switch"><input type="checkbox" data-act="toggle" ${c.enabled ? "checked" : ""} aria-label="Activar ${c.name}"></span>
      </div>
    </div>`).join("");
  box._list = list;
}

async function onConnClick(e, body) {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  if (el.type === "checkbox" && e.type === "click") return;
  const row = el.closest("[data-id]"), id = Number(row.dataset.id), out = row.querySelector(".test-out");
  const c = ($("#connList", body)._list || []).find((x) => x.id === id);
  try {
    if (el.dataset.act === "toggle") { await api.patchConnection(id, { enabled: el.checked }); return loadConnections(body); }
    if (el.dataset.act === "edit") return connectionForm($("#connForm", body), c.kind, c, body);
    if (el.dataset.act === "del") {
      if (!confirm(`¿Quitar la conexión ${c.name}? Tus pendientes abiertos se conservan.`)) return;
      await api.deleteConnection(id); toast("Conexión eliminada"); return loadConnections(body);
    }
    out.className = "test-out muted"; out.textContent = el.dataset.act === "sync" ? "Sincronizando…" : "Probando…";
    const r = el.dataset.act === "sync" ? await api.syncConnection(id) : await api.testSavedConnection(id);
    out.className = `test-out result ${r.ok ? "ok" : "err"}`;
    out.textContent = r.ok ? (r.message || `${r.added || 0} nuevos · ${r.updated || 0} actualizados · ${r.done || 0} cerrados`) : (r.error || r.message);
    setTimeout(() => loadConnections(body), 2500);
  } catch (err) { out.className = "test-out result err"; out.textContent = err.message; }
}

function connectionForm(box, kind, c, body) {
  const k = connKinds[kind];
  const val = (f) => (f.target === "config" ? (c?.config?.[f.key] ?? "") : f.target === "secret" ? "" : (c?.[f.target] ?? ""));
  const field = (f) => {
    const id = `cf_${f.key}`;
    const help = f.help ? raw(`<small>${esc(f.help)}</small>`) : "";
    if (f.type === "select") return html`<label class="field"><span>${f.label}</span><select class="input" id="${id}" name="${f.key}">
      ${raw(f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(val(f) || f.options[0][0]) === v ? "selected" : ""}>${esc(l)}</option>`).join(""))}</select>${help}</label>`;
    if (f.type === "textarea") return html`<label class="field"><span>${f.label}</span><textarea class="input" rows="2" id="${id}" name="${f.key}" placeholder="${f.placeholder || ""}">${val(f)}</textarea>${help}</label>`;
    const ph = f.type === "password" && c?.has_secret ? "Guardado · escribe sólo para cambiarlo" : (f.placeholder || "");
    return html`<label class="field"><span>${f.label}</span><input class="input" id="${id}" name="${f.key}" type="${f.type === "password" ? "password" : f.type === "url" ? "url" : "text"}"
      value="${val(f)}" placeholder="${ph}" autocomplete="off" ${f.required && !(f.type === "password" && c?.has_secret) ? "required" : ""}>${help}</label>`;
  };
  box.innerHTML = html`
    <form class="panel glass" id="cf">
      <div class="sheet-head"><h2 style="font-size:var(--fs-lg)">${c ? "Editar" : "Conectar"} ${k.label}</h2>
        <button type="button" class="icon-btn" id="cfClose" aria-label="Cerrar">${raw(icon("x"))}</button></div>
      <p class="hint">${k.help} ${k.help_url ? raw(`<a href="${esc(k.help_url)}" target="_blank" rel="noopener">Obtener token</a>`) : ""}</p>
      <label class="field"><span>Nombre</span><input class="input" name="name" value="${c?.name || k.label}" placeholder="${k.label} trabajo"></label>
      ${raw(k.fields.map(field).join(""))}
      <div class="panel-actions"><span class="result" id="cfOut"></span>
        <button type="button" class="btn btn-quiet" id="cfTest">Probar</button>
        <button class="btn btn-primary">${c ? "Guardar cambios" : "Conectar"}</button></div>
    </form>`;
  const f = $("#cf", box), out = $("#cfOut", box);
  const data = () => ({ kind, ...(c ? { id: c.id } : {}), ...Object.fromEntries(new FormData(f)) });
  $("#cfClose", box).onclick = () => (box.innerHTML = "");
  $("#cfTest", box).onclick = async () => {
    out.className = "result muted"; out.textContent = "Probando…";
    try { const r = await api.testConnection(data()); out.className = `result ${r.ok ? "ok" : "err"}`; out.textContent = r.message; }
    catch (err) { out.className = "result err"; out.textContent = err.message; }
  };
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    out.className = "result muted"; out.textContent = c ? "Guardando…" : "Conectando y sincronizando…";
    try {
      if (c) { await api.patchConnection(c.id, data()); toast("Conexión actualizada"); box.innerHTML = ""; }
      else {
        const r = await api.addConnection(data());
        if (!r.ok) { out.className = "result err"; out.textContent = r.message + " (se guardó; corrígela con Editar)"; loadConnections(body); return; }
        toast(r.message); box.innerHTML = "";
      }
      loadConnections(body);
    } catch (err) { out.className = "result err"; out.textContent = err.message; }
  });
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function renderMail(body, params) {
  presets = await api.mailPresets();
  body.innerHTML = `
    <div class="section">
      <h2>Cuentas de correo</h2>
      <p>EDI lee estas cuentas y puede enviar o responder correos sólo cuando tú lo confirmas. Usa una contraseña de aplicación, nunca tu contraseña normal.</p>
      <div id="accList" class="card glass"></div>
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
    <form class="panel glass" id="af">
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
          <label class="field"><span>Servidor SMTP (para enviar)</span><input class="input" name="smtp_host" value="${a?.smtp_host || ""}" placeholder="Automático"></label>
          <label class="field"><span>Puerto SMTP</span><input class="input" name="smtp_port" type="number" value="${a?.smtp_port || ""}" placeholder="465"></label>
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
  const data = () => { const d = Object.fromEntries(new FormData(f)); d.port = Number(d.port) || 993; d.smtp_port = Number(d.smtp_port) || 0; if (!d.name) d.name = (presets[d.provider]?.label || "").split(" ")[0]; return d; };
  const appPwdProblem = (d) => (d.provider === "gmail" && d.password && d.password.replace(/\s/g, "").length !== 16)
    ? "Eso parece tu contraseña normal. Gmail necesita una contraseña de aplicación de 16 letras: ábrela con el enlace de arriba." : "";
  $("#afCancel", box).onclick = () => (box.innerHTML = "");
  $("#afTest", box).onclick = async () => {
    const out = $("#afResult", box);
    out.className = "result"; out.textContent = "Conectando…";
    const d = data();
    const warn = appPwdProblem(d);
    if (warn) { out.className = "result err"; out.textContent = warn; return; }
    const r = a && !d.password ? await api.testSavedAccount(a.id) : await api.testAccount(d);
    out.className = `result ${r.ok ? "ok" : "err"}`;
    out.textContent = r.ok ? `Conectada: ${r.unread} sin leer` : r.error;
  };
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const d = data();
      const warn = appPwdProblem(d);
      if (warn) { $("#afResult", box).className = "result err"; $("#afResult", box).textContent = warn; return; }
      if (a) await api.patchAccount(a.id, d); else await api.addAccount(d);
      box.innerHTML = "";
      toast(a ? "Cuenta actualizada" : "Correo registrado. EDI ya lo revisa.");
      loadAccounts(root); refreshHealth();
    } catch (err) { toast(err.message, "error"); }
  });
  f.scrollIntoView({ behavior: "smooth", block: "center" });
  (a ? f.password : f.user).focus();
}

/* ---------------- Dispositivos ---------------- */
async function renderDevices(body) {
  const d = await api.devices();
  body.innerHTML = html`
    <div class="section">
      <h2>Usar EDI en otros dispositivos</h2>
      <p>Celulares, tablets y otras computadoras conectadas a la misma red Wi‑Fi que esta Mac.</p>
      ${d.lan_url ? raw(html`
      <div class="panel glass device">
        <div class="qr" id="qr" aria-label="Código QR">…</div>
        <div style="display:grid;gap:10px">
          <div class="muted">Escanea el código o abre:</div>
          <div class="big-url">${d.lan_url}</div>
          <div class="muted" style="margin-top:6px">PIN de acceso</div>
          <div class="pin">${d.pin}</div>
          <div class="row">${d.remote ? "" : raw(`<button class="btn" id="newPin">${icon("refresh")}Cambiar PIN</button>`)}
            <button class="btn btn-quiet" id="copyUrl">Copiar dirección</button></div>
        </div>
      </div>`) : raw(`<div class="panel glass"><div class="hint">No encontré la IP de tu Mac en la red. Conéctate a Wi‑Fi y vuelve a abrir EDI.app.</div></div>`)}
      <div class="panel glass">
        <h2 style="font-size:var(--fs-lg)">Primera vez en cada dispositivo</h2>
        <ul style="margin:0;padding-left:20px;color:var(--text-2);display:grid;gap:6px">
          <li>El navegador dirá que la conexión “no es privada”: es tu propia Mac con un certificado local. Elige <b>Avanzado → Continuar</b> (en iPhone: <b>Mostrar detalles → visitar este sitio</b>).</li>
          <li>Escribe el PIN y listo: el dispositivo queda recordado.</li>
          <li>Para tenerlo como app: Safari → Compartir → <b>Agregar a pantalla de inicio</b>; Chrome → menú → <b>Instalar app</b>.</li>
          <li>El micrófono funciona en Chrome (Android) y Safari (iPhone).</li>
        </ul>
      </div>
      <div class="panel glass" id="siriPanel">
        <h2 style="font-size:var(--fs-lg)">“Oye Siri, EDI” en tu iPhone</h2>
        <p class="muted">El iPhone no deja que una página escuche con la pantalla apagada. Con este atajo le hablas a EDI desde cualquier lugar del teléfono —incluso bloqueado— y Siri te lee la respuesta. Sigue la misma conversación: puedes decir “Oye Siri, EDI” → “envíalo”.</p>
        <div id="siriBody" class="muted">Cargando…</div>
      </div>
    </div>`;
  loadSiri($("#siriBody", body), d.remote);
  if (d.lan_url) {
    $("#qr", body).innerHTML = `<img src="/api/devices/qr.svg?t=${Date.now()}" alt="Código QR para abrir EDI en el celular">`;
    $("#copyUrl", body).onclick = async () => { try { await navigator.clipboard.writeText(d.lan_url); toast("Dirección copiada"); } catch { toast(d.lan_url); } };
    $("#newPin", body)?.addEventListener("click", async () => {
      if (!confirm("Los dispositivos conectados tendrán que escribir el PIN nuevo. ¿Cambiarlo?")) return;
      await api.rotatePin(); renderDevices(body);
    });
  }
}

async function loadSiri(box, remote) {
  let s;
  try { s = await api.siri(); } catch (e) { box.textContent = e.message; return; }
  if (!s.url) { box.textContent = "Reinicia EDI (Apagar EDI → EDI.app) para activar el atajo de Siri."; return; }
  box.innerHTML = html`
    <div class="big-url" style="font-size:var(--fs-sm);word-break:break-all">${s.url}</div>
    <div class="row" style="margin:10px 0 14px">
      <button class="btn btn-primary" id="copySiri">Copiar dirección del atajo</button>
      ${remote ? "" : raw(`<button class="btn btn-quiet" id="rotSiri">${icon("refresh")}Nueva llave</button>`)}
    </div>
    <ol style="margin:0;padding-left:20px;color:var(--text-2);display:grid;gap:8px;line-height:1.5">
      <li>Abre esta misma pantalla en tu iPhone (la app EDI) y toca <b>Copiar dirección del atajo</b>.</li>
      <li>Abre la app <b>Atajos</b> → <b>+</b>. Agrega la acción <b>Dictar texto</b> (Idioma: Español (México); Dejar de escuchar: <i>Después de una pausa</i>).</li>
      <li>Agrega <b>Obtener contenido de URL</b>, pega la dirección y toca la flecha: <b>Método: POST</b>, <b>Cuerpo de solicitud: JSON</b>, agrega un campo de <b>Texto</b> con clave <code>text</code> y valor <b>Texto dictado</b>.</li>
      <li>Agrega <b>Hablar texto</b> con <b>Contenido de la URL</b>.</li>
      <li>Nombra el atajo <b>EDI</b>. Listo: di <b>“Oye Siri, EDI”</b>, espera el tono y habla.</li>
    </ol>
    <p class="muted" style="margin-top:10px">Funciona con tu iPhone en el mismo Wi‑Fi que la Mac y EDI encendido. La llave es privada: si la compartiste por error, toca “Nueva llave” y actualiza el atajo.</p>`;
  $("#copySiri", box).onclick = async () => { try { await navigator.clipboard.writeText(s.url); toast("Dirección copiada"); } catch { prompt("Copia la dirección:", s.url); } };
  $("#rotSiri", box)?.addEventListener("click", async () => {
    if (!confirm("El atajo actual dejará de funcionar hasta que pegues la nueva dirección. ¿Continuar?")) return;
    await api.siriRotate(); loadSiri(box, remote);
  });
}

function refreshHealth() { app.refreshHealth?.(); }
