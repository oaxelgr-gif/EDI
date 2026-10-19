// Voz de entrada con el reconocimiento del navegador (Chrome/Safari): no gasta nada en tu Mac.
// Modos: "once" (botón de micrófono) y "wake" (escucha continua; responde cuando dices "EDI, ...").
import { audioCtx, audioReady, levelOf } from "./audio.js";

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
export const canListen = !!SR;
const WAKE = /^\s*(oye\s+|hey\s+|ok\s+)?(edi|eddie|edy|eddy|heidi|e\.d\.i\.)\b[\s,.:!]*/i;

let rec = null, mode = null, armedUntil = 0, paused = false;
let micStream = null, micAnalyser = null;
const buf = new Uint8Array(1024);
const handlers = { result: () => {}, interim: () => {}, state: () => {}, error: () => {} };

export function on(evt, fn) { handlers[evt] = fn; }
export const listenMode = () => mode;
export const micLevel = () => (micAnalyser ? levelOf(micAnalyser, buf) : 0);

async function openMicMeter() {
  if (micStream || !audioReady()) return;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const c = audioCtx();
    micAnalyser = c.createAnalyser();
    micAnalyser.fftSize = 1024;
    c.createMediaStreamSource(micStream).connect(micAnalyser);
  } catch { /* sin medidor; el reconocimiento sigue funcionando */ }
}
function closeMicMeter() {
  micStream?.getTracks().forEach((t) => t.stop());
  micStream = null; micAnalyser = null;
}

export function start(m = "once") {
  if (!SR) { handlers.error("Tu navegador no reconoce voz. Abre EDI en Chrome o Safari."); return; }
  stop(false);
  mode = m; paused = false;
  rec = new SR();
  rec.lang = "es-MX";
  rec.interimResults = true;
  rec.continuous = m === "wake";
  rec.onstart = () => { handlers.state(m === "once" ? "listening" : "wake"); if (m === "once") openMicMeter(); };
  rec.onresult = (e) => {
    let interim = "", final = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      r.isFinal ? (final += r[0].transcript) : (interim += r[0].transcript);
    }
    if (mode === "once" || Date.now() < armedUntil || WAKE.test(interim)) handlers.interim(interim.replace(WAKE, ""));
    if (!final) return;
    if (mode === "once") return handlers.result(final.trim());
    if (WAKE.test(final)) {
      const cmd = final.replace(WAKE, "").trim();
      if (cmd) handlers.result(cmd);
      else { armedUntil = Date.now() + 8000; handlers.state("armed"); }
    } else if (Date.now() < armedUntil) { armedUntil = 0; handlers.result(final.trim()); }
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      handlers.error("Permite el micrófono para EDI (icono del candado en la barra del navegador).");
      mode = null;
    } else if (e.error === "network") handlers.error("El dictado necesita internet.");
  };
  rec.onend = () => {
    closeMicMeter();
    const wasWake = mode === "wake";
    rec = null;
    if (wasWake && !paused) setTimeout(() => mode === "wake" && !paused && start("wake"), 300);
    else { mode = null; handlers.state("idle"); }
  };
  try { rec.start(); } catch { /* ya estaba iniciado */ }
}

export function stop(notify = true) {
  if (rec) { const r = rec; rec = null; mode = notify ? null : mode; try { r.abort(); } catch {} }
  closeMicMeter();
  if (notify) handlers.state("idle");
}

// Mientras EDI habla, la escucha continua se pausa para no oírse a sí misma.
export function pauseWake() { if (mode === "wake") { paused = true; if (rec) { try { rec.abort(); } catch {} } } }
export function resumeWake() { if (mode === "wake" && paused) { paused = false; setTimeout(() => start("wake"), 350); } }
