// Estado compartido de la interfaz + preferencias locales del navegador.
const local = {
  get(k, d) { try { const v = localStorage.getItem("edi." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("edi." + k, JSON.stringify(v)); } catch {} },
};

const listeners = new Set();

export const store = {
  sessionId: local.get("session", null),
  settings: {},
  health: null,
  muted: local.get("muted", false),
  wake: local.get("wake", false),
  drawerOpen: local.get("drawer", true),
  lastReply: "",

  set(patch) {
    Object.assign(this, patch);
    for (const k of ["muted", "wake"]) if (k in patch) local.set(k, patch[k]);
    if ("sessionId" in patch) local.set("session", patch.sessionId);
    if ("drawerOpen" in patch) local.set("drawer", patch.drawerOpen);
    listeners.forEach((fn) => fn(patch));
  },
  on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};
