// Voz de entrada con el reconocimiento del navegador (Chrome/Safari): no gasta nada en tu Mac.
// Modos: "once" (botón de micrófono) y "wake" (escucha continua; responde cuando dices "EDI, ...").
import { audioCtx, audioReady, levelOf } from "./audio.js";

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
export const canListen = !!SR;
// "Hey EDI", "Oye EDI", "EDI" y cómo lo suele escribir el dictado (Eddie, Heidi, Jedi, E.D.I., Edy…)
const WAKE = /^\s*(?:(?:oye|hey|hei|ey|ei|ok|okay|hola|a ver)[\s,]+)?(?:edi|eddie|eddy|edy|edie|edith|eddi|hedi|hedy|heidi|jedi|e\.?\s?d\.?\s?i\.?)(?=$|[\s,.:!?¿¡])[\s,.:!?]*/i;
const FOLLOW_MS = 8000;   // tras una respuesta, 8 s para seguir hablando sin decir "EDI"

let rec = null, mode = null, armedUntil = 0, paused = false, startedAt = 0, quickEnds = 0, watchdog = null;
let micStream = null, micAnalyser = null;
const buf = new Uint8Array(1024);
const handlers = { result: () => {}, interim: () => {}, state: () => {}, error: () => {} };

export function on(evt, fn) { handlers[evt] = fn; }

/** Tono corto: "te escucho". */
export function chime(up = true) {
  try {
    if (!audioReady()) return;
    const c = audioCtx(), o = c.createOscillator(), g = c.createGain(), t = c.currentTime;
    o.type = "sine";
    o.frequency.setValueAtTime(up ? 660 : 880, t);
    o.frequency.exponentialRampToValueAtTime(up ? 990 : 520, t + 0.12);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.12, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
    o.connect(g).connect(c.destination);
    o.start(t); o.stop(t + 0.2);
  } catch { /* sin sonido */ }
}
const arm = (ms = FOLLOW_MS) => { armedUntil = Date.now() + ms; handlers.state("armed"); chime(true); };
export const isArmed = () => Date.now() < armedUntil;
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
  rec.maxAlternatives = 1;
  rec.onstart = () => {
    startedAt = Date.now();
    handlers.state(m === "once" ? "listening" : (Date.now() < armedUntil ? "armed" : "wake"));
    if (m === "once") openMicMeter();
  };
  rec.onresult = (e) => {
    let interim = "", final = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      r.isFinal ? (final += r[0].transcript) : (interim += r[0].transcript);
    }
    if (interim && Date.now() < armedUntil) armedUntil = Math.max(armedUntil, Date.now() + 4000);  // sigue hablando
    if (mode === "once" || Date.now() < armedUntil || WAKE.test(interim)) handlers.interim(interim.replace(WAKE, ""));
    if (!final) return;
    if (mode === "once") return handlers.result(final.trim());
    if (WAKE.test(final)) {
      const cmd = final.replace(WAKE, "").trim();
      if (cmd) { armedUntil = 0; chime(true); handlers.result(cmd); }
      else arm();
    } else if (Date.now() < armedUntil) { armedUntil = 0; handlers.result(final.trim()); }
  };
  rec.onerror = (e) => {
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      handlers.error("Permite el micrófono para EDI (icono del candado en la barra del navegador).");
      mode = null;
    } else if (e.error === "network") handlers.error("El dictado necesita internet.");
    // "no-speech" y "aborted" son normales: se reinicia solo
  };
  rec.onend = () => {
    closeMicMeter();
    const wasWake = mode === "wake";
    rec = null;
    if (wasWake && !paused) {
      // Safari (sobre todo en iPhone) corta la escucha seguido: reinicio con espera creciente si termina muy rápido
      quickEnds = Date.now() - startedAt < 1500 ? quickEnds + 1 : 0;
      const wait = Math.min(250 * 2 ** Math.min(quickEnds, 4), 4000);
      setTimeout(() => mode === "wake" && !paused && !rec && start("wake"), wait);
    } else { mode = null; handlers.state("idle"); }
  };
  clearInterval(watchdog);
  if (m === "wake") watchdog = setInterval(() => { if (mode === "wake" && !paused && !rec) start("wake"); }, 5000);
  try { rec.start(); } catch { /* ya estaba iniciado */ }
}

export function stop(notify = true) {
  if (notify) { clearInterval(watchdog); armedUntil = 0; }
  if (rec) { const r = rec; rec = null; mode = notify ? null : mode; try { r.abort(); } catch {} }
  closeMicMeter();
  if (notify) handlers.state("idle");
}

// Mientras EDI habla, la escucha continua se pausa para no oírse a sí misma.
export function pauseWake() { if (mode === "wake") { paused = true; if (rec) { try { rec.abort(); } catch {} } } }
// Al terminar de hablar: modo conversación (puedes contestar sin volver a decir "EDI").
export function resumeWake(followUp = true) {
  if (mode === "wake" && paused) {
    paused = false;
    setTimeout(() => { if (followUp) arm(); start("wake"); }, 300);
  }
}
