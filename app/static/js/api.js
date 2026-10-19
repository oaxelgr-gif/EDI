// Cliente de la API de EDI. Todas las llamadas pasan por aquí.
async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const r = await fetch(url, opts);
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
  addTask: (text, due) => req("POST", "/api/tasks", { text, due }),
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

  voices: () => req("GET", "/api/tts/voices"),
  tts: async (text, voice, rate) => {
    const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, voice, rate }) });
    if (!r.ok) throw new Error("tts");
    return r.blob();
  },
};
