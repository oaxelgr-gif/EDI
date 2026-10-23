// Voz de salida. Primero voz neural del servidor (/api/tts, edge-tts); si falla, la del navegador.
import { api } from "../api.js";
import { store } from "../store.js";
import { audioCtx, audioReady, levelOf, cueSpeak } from "./audio.js";

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
  if (current) { const c = current; current = null; c.audio.pause(); c.audio.removeAttribute("src"); if (c.url?.startsWith("blob:")) URL.revokeObjectURL(c.url); }
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  analyser = null;
  if (state !== "idle") setState("idle");
}

/**
 * Habla un texto. Si el servidor ya empezó a generar la voz (ttsId de /api/ask), se reproduce en streaming:
 * suena casi al mismo tiempo que aparece el texto.
 */
export async function speak(text, ttsId = null) {
  if (!text) return;
  stop();
  if (store.muted) return;
  store.lastReply = text;
  const s = store.settings || {};
  const useServer = (s.tts_engine || "edge") === "edge" && store.health?.tts !== false;
  if (useServer) {
    setState("loading");
    try {
      const id = ttsId || (await api.ttsStart(text, s.tts_voice, s.tts_rate, s.tts_pitch)).id;
      return await playUrl(`/api/tts/stream/${id}`, text);
    } catch (e) {
      if (e && e.name === "NotAllowedError") return;
      console.warn("Streaming de voz no disponible, intento completo", e);
    }
    try {
      const blob = await api.tts(text, s.tts_voice, s.tts_rate, s.tts_pitch);
      return await playUrl(URL.createObjectURL(blob), text);
    } catch (e) {
      if (e && e.name === "NotAllowedError") return;
      console.warn("Voz en línea no disponible, uso la del navegador", e);
    }
  }
  speakBrowser(text);
}

const MSE = window.MediaSource && MediaSource.isTypeSupported?.("audio/mpeg");

/** Alimenta el audio fragmento por fragmento (MediaSource): suena en cuanto llega el primer pedazo,
 *  sin esperar a que el navegador "junte" suficiente audio. */
function feed(audio, url) {
  const ms = new MediaSource();
  const objUrl = URL.createObjectURL(ms);
  audio.src = objUrl;
  ms.addEventListener("sourceopen", async () => {
    let sb;
    try { sb = ms.addSourceBuffer("audio/mpeg"); sb.mode = "sequence"; } catch { audio.dispatchEvent(new Event("error")); return; }
    const queue = []; let ended = false;
    const pump = () => {
      if (sb.updating || ms.readyState !== "open") return;
      if (queue.length) { try { sb.appendBuffer(queue.shift()); } catch { /* cuota: reintenta */ setTimeout(pump, 50); } }
      else if (ended) { try { ms.endOfStream(); } catch {} }
    };
    sb.addEventListener("updateend", pump);
    try {
      const r = await fetch(url);
      if (!r.ok || !r.body) throw new Error("tts");
      const reader = r.body.getReader();
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        if (current?.audio !== audio) { reader.cancel(); return; }
        queue.push(value); pump();
      }
      ended = true; pump();
    } catch { if (!audio.currentTime) audio.dispatchEvent(new Event("error")); else { ended = true; pump(); } }
  }, { once: true });
  return objUrl;
}

function playUrl(url, text) {
  const audio = new Audio();
  audio.preload = "auto";
  current = { audio, url };
  if (MSE && url.startsWith("/api/tts/stream/")) current.url = feed(audio, url);
  else audio.src = url;
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
  return new Promise((resolve, reject) => {
    let started = false;
    audio.onplaying = () => { started = true; pending = null; cueSpeak(); setState("speaking"); resolve(); };
    audio.onerror = () => {
      if (current?.audio !== audio) return;
      if (!started) { current = null; reject(new Error("audio")); } else stop();
    };
    audio.play().catch((e) => {
      if (e.name === "NotAllowedError") {     // el navegador exige un toque antes del primer audio
        pending = text; current = null; setState("blocked");
      }
      if (!started) reject(e);
    });
  });
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
    if (i === 0) u.onstart = () => { cueSpeak(); setState("speaking"); };
    if (i === parts.length - 1) u.onend = u.onerror = () => setState("idle");
    speechSynthesis.speak(u);
  });
}
