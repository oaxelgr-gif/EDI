// Voz de salida. Primero voz neural del servidor (/api/tts, edge-tts); si falla, la del navegador.
import { api } from "../api.js";
import { store } from "../store.js";
import { audioCtx, audioReady, levelOf } from "./audio.js";

let current = null;          // { audio, url, analyser }
let analyser = null;
const buf = new Uint8Array(1024);
const listeners = new Set();
let state = "idle";
let pending = null;          // texto bloqueado por el navegador (falta un clic)

function setState(s) { state = s; listeners.forEach((fn) => fn(s)); }
export const onSpeakState = (fn) => (listeners.add(fn), () => listeners.delete(fn));
export const speakState = () => state;
export const speakLevel = () => (state === "speaking" ? (analyser ? levelOf(analyser, buf) : 0.35 + Math.random() * 0.3) : 0);
export const hasPending = () => !!pending;

export function stop() {
  if (current) { current.audio.pause(); URL.revokeObjectURL(current.url); current = null; }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  analyser = null;
  if (state !== "idle") setState("idle");
}

export async function speak(text) {
  if (!text) return;
  stop();
  if (store.muted) return;
  store.lastReply = text;
  const s = store.settings || {};
  const useServer = (s.tts_engine || "edge") === "edge" && store.health?.tts !== false;
  if (useServer) {
    try {
      setState("loading");
      const blob = await api.tts(text, s.tts_voice, s.tts_rate, s.tts_pitch);
      return await playBlob(blob, text);
    } catch (e) {
      if (e && e.name === "NotAllowedError") return;
      console.warn("Voz en línea no disponible, uso la del navegador", e);
    }
  }
  speakBrowser(text);
}

async function playBlob(blob, text) {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  current = { audio, url };
  analyser = null;
  if (audioReady()) {
    const c = audioCtx();
    const src = c.createMediaElementSource(audio);
    analyser = c.createAnalyser();
    analyser.fftSize = 1024;
    src.connect(analyser);
    analyser.connect(c.destination);
  }
  audio.onended = () => { if (current?.audio === audio) stop(); };
  audio.onerror = () => { if (current?.audio === audio) stop(); };
  try {
    await audio.play();
    pending = null;
    setState("speaking");
  } catch (e) {
    if (e.name === "NotAllowedError") {     // el navegador exige un clic antes del primer audio
      pending = text;
      current = null;
      setState("blocked");
      e.name = "NotAllowedError";
    }
    throw e;
  }
}

export function playPending() {
  if (pending) { const t = pending; pending = null; speak(t); }
}

function speakBrowser(text) {
  if (!("speechSynthesis" in window)) { setState("idle"); return; }
  const voices = speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("es"));
  const voice = voices.find((v) => /Paulina|Mónica|Google español/.test(v.name)) || voices.find((v) => v.lang === "es-MX") || voices[0];
  const parts = text.match(/[^.!?;]+[.!?;]*/g) || [text];
  parts.forEach((p, i) => {
    const u = new SpeechSynthesisUtterance(p.trim());
    u.lang = voice?.lang || "es-MX";
    if (voice) u.voice = voice;
    if (i === 0) u.onstart = () => setState("speaking");
    if (i === parts.length - 1) u.onend = u.onerror = () => setState("idle");
    speechSynthesis.speak(u);
  });
}
