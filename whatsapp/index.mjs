// Puente WhatsApp para EDI.
// Se vincula a tu WhatsApp como "dispositivo vinculado" (igual que WhatsApp Web) usando Baileys
// (https://github.com/WhiskeySockets/Baileys). No abre navegador. Sólo escucha en la red interna de Docker.
// API (JSON):
//   GET  /status                 → { state: "starting|qr|connecting|open|logged_out", qr, me }
//   GET  /chats                  → [{ jid, name, unread, last: {text, fromMe, ts} }]
//   GET  /messages?jid=…&limit=  → [{ id, fromMe, text, ts, name }]
//   GET  /contacts               → [{ jid, name, group }]  (contactos de tu agenda + grupos)
//   POST /send   { to, text }    → to = jid o número (con lada, ej. 5214421234567)
//   POST /read   { jid }         → marca como leído
//   POST /logout                 → desvincula
//   POST /pair   { phone }       → código de 8 caracteres para vincular con número (sin QR)
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { randomBytes } from "node:crypto";
import pino from "pino";

const AUTH = process.env.WA_AUTH_DIR || "/auth";
const STORE = path.join(AUTH, "edi-store.json");
const PORT = Number(process.env.PORT || 3000);
const MAX_PER_CHAT = 40, MAX_CHATS = 800;
const logger = pino({ level: process.env.WA_LOG || "warn" });

const baileys = await import("@whiskeysockets/baileys");
const makeWASocket = baileys.default?.default || baileys.default || baileys.makeWASocket;
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, fetchLatestWaWebVersion, Browsers } = baileys;
let authRef = null;

let sock = null;
let state = { state: "starting", qr: null, me: null, error: null, code: null };

// ---------- almacén mínimo (persistido) ----------
let store = { chats: {}, names: {}, saved: {}, lid2pn: {} };
try { store = { ...store, ...JSON.parse(fs.readFileSync(STORE, "utf8")) }; } catch {}
store.saved ||= {}; store.lid2pn ||= {};
const { jidNormalizedUser } = baileys;
const pnOf = (lid) => store.lid2pn[lid];

// WhatsApp usa dos identificadores por persona (@lid y su número @s.whatsapp.net). Unimos todo en el número.
function canon(jid) { return jid?.endsWith("@lid") && pnOf(jid) ? pnOf(jid) : jid; }
function mergeChat(from, to) {
  const a = store.chats[from]; if (!a || from === to) return;
  const b = chatEntry(to);
  const ids = new Set(b.msgs.map((x) => x.id));
  b.msgs = b.msgs.concat(a.msgs.filter((x) => !ids.has(x.id))).sort((x, y) => x.ts - y.ts).slice(-MAX_PER_CHAT);
  b.unread = Math.max(b.unread || 0, a.unread || 0); b.ts = Math.max(b.ts || 0, a.ts || 0);
  if (!store.names[to] && store.names[from]) store.names[to] = store.names[from];
  delete store.chats[from];
}
function linkLid(lid, pn) {
  if (!lid?.endsWith("@lid") || !pn?.endsWith("@s.whatsapp.net")) return;
  pn = jidNormalizedUser ? jidNormalizedUser(pn) : pn;
  store.lid2pn[lid] = pn;
  if (store.saved[pn] && !store.saved[lid]) store.saved[lid] = store.saved[pn];
  if (store.saved[lid] && !store.saved[pn]) store.saved[pn] = store.saved[lid];
  mergeChat(lid, pn);
}
async function resolveLids() {
  const repo = sock?.signalRepository?.lidMapping;
  for (const jid of Object.keys(store.chats)) {
    if (!jid.endsWith("@lid") || pnOf(jid)) continue;
    try { const pn = repo?.getPNForLID ? await repo.getPNForLID(jid) : null; if (pn) linkLid(jid, pn); } catch {}
  }
  for (const [lid, pn] of Object.entries(store.lid2pn)) mergeChat(lid, pn);
  save();
}
const save = () => { try { fs.writeFileSync(STORE, JSON.stringify(store)); } catch (e) { logger.warn(e); } };
setInterval(save, 20000);

function textOf(m) {
  const msg = m.message || {};
  const inner = msg.ephemeralMessage?.message || msg.viewOnceMessage?.message || msg.viewOnceMessageV2?.message || msg;
  return inner.conversation || inner.extendedTextMessage?.text || inner.imageMessage?.caption && `📷 ${inner.imageMessage.caption}`
    || (inner.imageMessage && "📷 Foto") || inner.videoMessage?.caption && `🎬 ${inner.videoMessage.caption}`
    || (inner.videoMessage && "🎬 Video") || (inner.audioMessage && "🎤 Nota de voz") || (inner.stickerMessage && "Sticker")
    || (inner.documentMessage && `📄 ${inner.documentMessage.fileName || "Documento"}`) || (inner.locationMessage && "📍 Ubicación")
    || (inner.contactMessage && `👤 ${inner.contactMessage.displayName || "Contacto"}`) || inner.reactionMessage && null || null;
}

const okJid = (j) => j && j !== "status@broadcast" && !j.endsWith("@newsletter") && !j.endsWith("@broadcast");
function chatEntry(jid) { return store.chats[jid] || (store.chats[jid] = { jid, unread: 0, msgs: [] }); }

// Contacto (Baileys 7 trae id, lid y phoneNumber). "name" = como lo tienes guardado en tu agenda.
function learnContact(c) {
  const name = c.name || c.verifiedName || c.notify;
  if (!name) return;
  const pnJid = c.phoneNumber && (c.phoneNumber.includes("@") ? c.phoneNumber : `${c.phoneNumber}@s.whatsapp.net`);
  const lid = c.lid || (c.id?.endsWith("@lid") ? c.id : null);
  const pn = pnJid || (c.id?.endsWith("@s.whatsapp.net") ? c.id : null);
  if (lid && pn) linkLid(lid, pn);
  const ids = [c.id, c.lid, pnJid].filter(Boolean);
  for (const id of ids) {
    if (c.name) store.saved[id] = c.name;           // de tu agenda: tiene prioridad
    if (c.name || !store.names[id]) store.names[id] = name;
  }
}

function learnChat(c) {
  if (!okJid(c.id)) return;
  if (c.id.endsWith("@lid") && c.pnJid) linkLid(c.id, c.pnJid);
  const id = canon(c.id);
  const e = chatEntry(id);
  if (c.name || c.subject) store.names[id] = c.name || c.subject;
  if (typeof c.unreadCount === "number") e.unread = Math.max(0, c.unreadCount);
  const ts = Number(c.conversationTimestamp?.low ?? c.conversationTimestamp ?? 0);
  if (ts) e.ts = Math.max(e.ts || 0, ts);
}

function remember(m, { history = false } = {}) {
  const raw = m.key?.remoteJid;
  if (raw?.endsWith("@lid") && m.key?.remoteJidAlt?.endsWith("@s.whatsapp.net")) linkLid(raw, m.key.remoteJidAlt);
  const jid = canon(raw);
  if (!okJid(jid)) return;
  const text = textOf(m);
  if (!text) return;
  const ts = Number(m.messageTimestamp?.low ?? m.messageTimestamp ?? Date.now() / 1000);
  const c = chatEntry(jid);
  if (c.msgs.some((x) => x.id === m.key.id)) return;
  if (!m.key.fromMe && m.pushName && !jid.endsWith("@g.us")) store.names[jid] = m.pushName;
  c.msgs.push({ id: m.key.id, rj: raw !== jid ? raw : undefined, fromMe: !!m.key.fromMe, text, ts, name: m.key.fromMe ? "Tú" : (m.pushName || store.names[m.key.participant || jid] || ""),
                participant: m.key.participant || null });
  if (history) c.msgs.sort((a, b) => a.ts - b.ts);
  if (c.msgs.length > MAX_PER_CHAT) c.msgs.splice(0, c.msgs.length - MAX_PER_CHAT);
  if (!history) { if (!m.key.fromMe) c.unread = (c.unread || 0) + 1; else c.unread = 0; }
  c.ts = Math.max(c.ts || 0, ts);
  const ids = Object.keys(store.chats);
  if (ids.length > MAX_CHATS) {
    ids.sort((a, b) => (store.chats[a].ts || 0) - (store.chats[b].ts || 0)).slice(0, ids.length - MAX_CHATS).forEach((k) => delete store.chats[k]);
  }
}

function chatName(jid) {
  return store.saved[jid] || store.names[jid] || store.chats[jid]?.subject || jid.split("@")[0];
}

// ---------- conexión ----------
async function connect() {
  const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH);
  authRef = auth;
  const advOrig = auth.creds.advSecretKey;  // la que Baileys mete en cada QR de esta conexión
  // Versión VIVA de WhatsApp Web: la "latest" de Baileys está desactualizada y el teléfono rechaza la vinculación
  // (https://github.com/WhiskeySockets/Baileys/issues/2679).
  let version;
  try { if (fetchLatestWaWebVersion) ({ version } = await fetchLatestWaWebVersion()); } catch (e) { logger.warn({ e: String(e) }, "fetchLatestWaWebVersion"); }
  if (!version) { try { ({ version } = await fetchLatestBaileysVersion()); } catch {} }
  logger.warn({ version }, "Versión de WhatsApp Web");
  sock = makeWASocket({
    ...(version ? { version } : {}), auth, logger, printQRInTerminal: false,
    browser: Browsers.macOS("Chrome"), markOnlineOnConnect: false, syncFullHistory: false,
  });
  sock.ev.on("creds.update", saveCreds);

  // Desde jul-2026 WhatsApp manda <notification type="companion_reg_refresh"> al escanear; Baileys la ignora y el
  // teléfono dice "No se pudo vincular… revisa tu conexión". Igual que WhatsApp Web: rotar advSecretKey y redibujar
  // el QR (https://github.com/WhiskeySockets/Baileys/issues/2737, PR #2765, aún sin publicar).
  sock.ws.on("CB:notification,type:companion_reg_refresh", () => {
    if (auth.creds.me) return;
    const adv = randomBytes(32).toString("base64");
    auth.creds.advSecretKey = adv;
    sock.ev.emit("creds.update", { advSecretKey: adv });
    if (state.qr) state = { ...state, qr: fixAdv(state.qr, advOrig, adv) };
    logger.warn("companion_reg_refresh: clave rotada, QR actualizado");
  });
  sock.ev.on("connection.update", async (u) => {
    if (u.qr) state = { ...state, state: "qr", qr: fixAdv(u.qr, advOrig, auth.creds.advSecretKey) };
    if (u.connection === "connecting") state = { ...state, state: state.qr ? "qr" : "connecting" };
    if (u.connection === "open") {
      state = { state: "open", qr: null, code: null, me: sock.user ? { id: sock.user.id, name: sock.user.name || "" } : null, error: null };
      logger.warn("WhatsApp vinculado");
      setTimeout(resolveLids, 4000);
    }
    if (u.connection === "close") {
      const code = u.lastDisconnect?.error?.output?.statusCode;
      logger.warn({ code, msg: String(u.lastDisconnect?.error?.message || "") }, "conexión cerrada");
      if (code === DisconnectReason.loggedOut) {
        state = { state: "logged_out", qr: null, code: null, me: null, error: "Sesión cerrada desde el teléfono" };
        try { for (const f of fs.readdirSync(AUTH)) if (f !== "edi-store.json") fs.rmSync(path.join(AUTH, f), { recursive: true, force: true }); } catch {}
      } else {
        state = { ...state, state: "connecting", error: String(u.lastDisconnect?.error?.message || "") };
      }
      // 515 = WhatsApp pide reiniciar justo después de vincular: reconectar de inmediato
      setTimeout(connect, code === DisconnectReason.restartRequired ? 200 : 3000);
    }
  });
  sock.ev.on("messages.upsert", ({ messages, type }) => { for (const m of messages) remember(m, { history: type !== "notify" }); });
  // Historial inicial al vincular: todos tus chats recientes, contactos y últimos mensajes
  sock.ev.on("messaging-history.set", ({ chats = [], contacts = [], messages = [] }) => {
    for (const c of contacts) learnContact(c);
    for (const c of chats) learnChat(c);
    for (const m of messages) remember(m, { history: true });
    logger.warn({ chats: chats.length, contacts: contacts.length, messages: messages.length }, "historial recibido");
    resolveLids();
  });
  sock.ev.on("contacts.upsert", (cs) => { for (const c of cs) learnContact(c); });
  sock.ev.on("contacts.update", (cs) => { for (const c of cs) learnContact(c); });
  sock.ev.on("groups.upsert", (gs) => { for (const g of gs) { store.names[g.id] = g.subject; } });
  sock.ev.on("chats.upsert", (cs) => { for (const c of cs) learnChat(c); });
  sock.ev.on("chats.update", (cs) => { for (const c of cs) if (store.chats[c.id] || c.unreadCount) learnChat(c); });
}

// El QR incluye la clave adv; si fue rotada, poner la vigente
function fixAdv(qr, oldAdv, adv) { return oldAdv && adv && oldAdv !== adv ? qr.split(",").map((x) => (x === oldAdv ? adv : x)).join(",") : qr; }

async function toJid(to) {
  if (to.includes("@")) return to;
  const digits = to.replace(/\D/g, "");
  if (digits.length < 8) throw new Error("Número inválido: incluye la lada del país (ej. 52 para México).");
  const [r] = await sock.onWhatsApp(digits);
  if (!r?.exists) throw new Error("Ese número no tiene WhatsApp.");
  return r.jid;
}

// ---------- HTTP ----------
const json = (res, code, obj) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(obj)); };
const body = (req) => new Promise((ok) => { let d = ""; req.on("data", (c) => (d += c)); req.on("end", () => { try { ok(JSON.parse(d || "{}")); } catch { ok({}); } }); });

http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  try {
    if (req.method === "GET" && url.pathname === "/status") return json(res, 200, state);
    if (req.method === "GET" && url.pathname === "/chats") {
      const list = Object.values(store.chats).filter((c) => okJid(c.jid))
        .sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, Number(url.searchParams.get("limit") || 300))
        .map((c) => ({ jid: c.jid, name: chatName(c.jid), group: c.jid.endsWith("@g.us"), unread: c.unread || 0, last: c.msgs[c.msgs.length - 1] }));
      return json(res, 200, list);
    }
    if (req.method === "GET" && url.pathname === "/contacts") {
      const seen = new Set(), out = [];
      const add = (jid, name) => { jid = canon(jid); if (!name || !okJid(jid) || seen.has(jid)) return; seen.add(jid); out.push({ jid, name, group: jid.endsWith("@g.us"), saved: !!store.saved[jid] }); };
      for (const [jid, name] of Object.entries(store.saved)) if (jid.endsWith("@s.whatsapp.net")) add(jid, name);
      for (const [jid, name] of Object.entries(store.saved)) add(jid, name);
      for (const jid of Object.keys(store.chats)) add(jid, chatName(jid));
      for (const [jid, name] of Object.entries(store.names)) if (jid.endsWith("@g.us") || jid.endsWith("@s.whatsapp.net")) add(jid, name);
      return json(res, 200, out);
    }
    if (req.method === "GET" && url.pathname === "/messages") {
      const c = store.chats[canon(url.searchParams.get("jid"))];
      const n = Number(url.searchParams.get("limit") || 30);
      return json(res, 200, c ? c.msgs.slice(-n) : []);
    }
    if (req.method === "POST" && url.pathname === "/pair") {
      const b = await body(req);
      const digits = String(b.phone || "").replace(/\D/g, "");
      if (digits.length < 10) return json(res, 400, { error: "Escribe tu número con lada de país, ej. 524421234567." });
      if (state.state === "open") return json(res, 409, { error: "WhatsApp ya está vinculado." });
      if (authRef?.creds?.registered) return json(res, 409, { error: "Ya hay una vinculación en curso; desvincula y vuelve a intentar." });
      for (let i = 0; i < 20 && state.state !== "qr"; i++) await new Promise((r) => setTimeout(r, 500));  // socket listo
      const code = await sock.requestPairingCode(digits);
      const pretty = code.length === 8 ? `${code.slice(0, 4)}-${code.slice(4)}` : code;
      state = { ...state, code: pretty };
      return json(res, 200, { ok: true, code: pretty });
    }
    if (state.state !== "open" && req.method === "POST" && url.pathname !== "/logout") return json(res, 409, { error: "WhatsApp no está vinculado." });
    if (req.method === "POST" && url.pathname === "/send") {
      const b = await body(req);
      if (!b.to || !b.text) return json(res, 400, { error: "Falta destinatario o mensaje." });
      const jid = await toJid(String(b.to));
      const sent = await sock.sendMessage(jid, { text: String(b.text) });
      remember({ ...sent, message: { conversation: String(b.text) } });
      return json(res, 200, { ok: true, jid, name: chatName(jid) });
    }
    if (req.method === "POST" && url.pathname === "/read") {
      const b = await body(req);
      const c = store.chats[canon(b.jid)];
      if (c) {
        const keys = c.msgs.filter((m) => !m.fromMe).slice(-Math.max(c.unread || 0, 1))
          .map((m) => ({ remoteJid: m.rj || c.jid, id: m.id, fromMe: false, ...(m.participant ? { participant: m.participant } : {}) }));
        if (keys.length) await sock.readMessages(keys);
        c.unread = 0;
      }
      return json(res, 200, { ok: true });
    }
    if (req.method === "POST" && url.pathname === "/logout") {
      try { await sock?.logout(); } catch {}
      return json(res, 200, { ok: true });
    }
    json(res, 404, { error: "no encontrado" });
  } catch (e) {
    logger.warn(e);
    json(res, 500, { error: String(e.message || e) });
  }
}).listen(PORT, () => logger.warn(`Puente WhatsApp en :${PORT}`));

process.on("SIGTERM", () => { save(); process.exit(0); });
connect().catch((e) => { state = { ...state, state: "error", error: String(e) }; logger.error(e); });
