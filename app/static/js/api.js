// Cliente de la API de EDI. Todas las llamadas pasan por aquí.
// clientId identifica esta pestaña: el servidor lo devuelve en los avisos "changed" para que la pestaña que hizo
// el cambio no se refresque dos veces (las demás —Mac o celular— sí lo hacen).
export const clientId = (() => {
  try { if (crypto.randomUUID) return crypto.randomUUID().slice(0, 18); } catch {}
  return Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
})();

async function req(method, url, body) {
  const opts = { method, headers: { "X-EDI-Client": clientId } };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(url, opts);
  if (r.status === 401 && location.protocol === "https:") { location.href = "/login"; return new Promise(() => {}); }   // se va a /login: no hay nada más que hacer
  if (!r.ok) {
    let msg = `Error ${r.status}`;
    try { const j = await r.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r;
}

export const api = {
  health: () => req("GET", "/api/health"),
  ask: (text, session_id) => req("POST", "/api/ask", { text, session_id }),
  greeting: () => req("GET", "/api/greeting"),

  sessions: () => req("GET", "/api/sessions"),
  session: (id) => req("GET", `/api/sessions/${id}`),
  deleteSession: (id) => req("DELETE", `/api/sessions/${id}`),
  renameSession: (id, title) => req("PATCH", `/api/sessions/${id}`, { title }),

  tasks: (all = false) => req("GET", `/api/tasks${all ? "?all=true" : ""}`),
  addTask: (text, due, extra = {}) => req("POST", "/api/tasks", { text, due, ...extra }),
  taskTransitions: (id) => req("GET", `/api/tasks/${id}/transitions`),
  taskMove: (id, transition_id) => req("POST", `/api/tasks/${id}/move`, { transition_id }),
  taskToJira: (id, project = "") => req("POST", `/api/tasks/${id}/to-jira`, { project }),
  patchNote: (id, text) => req("PATCH", `/api/notes/${id}`, { text }),
  connections: () => req("GET", "/api/connections"),
  connectionKinds: () => req("GET", "/api/connections/kinds"),
  addConnection: (d) => req("POST", "/api/connections", d),
  patchConnection: (id, d) => req("PATCH", `/api/connections/${id}`, d),
  deleteConnection: (id, keepTasks = true) => req("DELETE", `/api/connections/${id}?keep_tasks=${keepTasks}`),
  testConnection: (d) => req("POST", "/api/connections/test", d),
  testSavedConnection: (id) => req("POST", `/api/connections/${id}/test`),
  syncConnection: (id) => req("POST", `/api/connections/${id}/sync`),
  syncAll: () => req("POST", "/api/connections/sync"),
  patchTask: (id, data) => req("PATCH", `/api/tasks/${id}`, data),
  deleteTask: (id) => req("DELETE", `/api/tasks/${id}`),

  notes: (q = "") => req("GET", `/api/notes${q ? "?q=" + encodeURIComponent(q) : ""}`),
  addNote: (text) => req("POST", "/api/notes", { text }),
  deleteNote: (id) => req("DELETE", `/api/notes/${id}`),

  mail: (force = false) => req("GET", `/api/mail${force ? "?force=true" : ""}`),
  mailPresets: () => req("GET", "/api/mail/presets"),
  accounts: () => req("GET", "/api/accounts"),
  addAccount: (d) => req("POST", "/api/accounts", d),
  patchAccount: (id, d) => req("PATCH", `/api/accounts/${id}`, d),
  deleteAccount: (id) => req("DELETE", `/api/accounts/${id}`),
  testAccount: (d) => req("POST", "/api/accounts/test", d),
  testSavedAccount: (id) => req("POST", `/api/accounts/${id}/test`),

  settings: () => req("GET", "/api/settings"),
  saveSettings: (d) => req("PUT", "/api/settings", d),
  kinds: () => req("GET", "/api/providers/kinds"),
  providers: () => req("GET", "/api/providers"),
  addProvider: (d) => req("POST", "/api/providers", d),
  patchProvider: (id, d) => req("PATCH", `/api/providers/${id}`, d),
  deleteProvider: (id) => req("DELETE", `/api/providers/${id}`),
  orderProviders: (ids) => req("PUT", "/api/providers/order", { ids }),
  testProvider: (d) => req("POST", "/api/providers/test", d),
  testSavedProvider: (id) => req("POST", `/api/providers/${id}/test`),
  models: (id) => req("GET", `/api/providers/${id}/models`),

  mailMessage: (uid) => req("GET", `/api/mail/message?uid=${encodeURIComponent(uid)}`),
  markRead: (uids, seen = true) => req("POST", "/api/mail/read", { uids, seen }),
  markAllRead: () => req("POST", "/api/mail/read", { all: true }),
  sendMail: (d) => req("POST", "/api/mail/send", d),
  draft: (id) => req("GET", `/api/drafts/${id}`),
  sendDraft: (id, patch = {}) => req("POST", `/api/drafts/${id}/send`, patch),
  cancelDraft: (id) => req("DELETE", `/api/drafts/${id}`),

  waStatus: (start = false) => req("GET", `/api/whatsapp/status${start ? "?start=true" : ""}`),
  waChats: () => req("GET", "/api/whatsapp/chats"),
  waContacts: () => req("GET", "/api/whatsapp/contacts"),
  waMessages: (jid) => req("GET", `/api/whatsapp/messages?jid=${encodeURIComponent(jid)}`),
  waSend: (to, text) => req("POST", "/api/whatsapp/send", { to, text }),
  waRead: (jid) => req("POST", "/api/whatsapp/read", { jid }),
  waPair: (phone) => req("POST", "/api/whatsapp/pair", { phone }),
  waLogout: () => req("POST", "/api/whatsapp/logout"),

  voices: () => req("GET", "/api/tts/voices"),
  siri: () => req("GET", "/api/devices/siri"),
  siriRotate: () => req("POST", "/api/devices/siri/rotate"),
  ttsStart: (text, voice, rate, pitch) => req("POST", "/api/tts/start", { text, voice, rate, pitch }),
  devices: (fresh = false) => req("GET", `/api/devices${fresh ? "?fresh=true" : ""}`),
  rotatePin: () => req("POST", "/api/devices/pin"),
  deviceList: () => req("GET", "/api/devices/list"),
  removeDevice: (id) => req("DELETE", `/api/devices/list/${encodeURIComponent(id)}`),
  logoutAll: () => req("POST", "/api/devices/logout-all"),
  tailscaleServe: () => req("POST", "/api/devices/tailscale/serve"),
  tts: async (text, voice, rate, pitch) => {
    const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json", "X-EDI-Client": clientId }, body: JSON.stringify({ text, voice, rate, pitch }) });
    if (!r.ok) throw new Error("tts");
    return r.blob();
  },
};
