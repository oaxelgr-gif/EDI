// Un solo AudioContext para medir volumen (anillo) de voz y micrófono.
// Los navegadores lo dejan "suspendido" hasta el primer clic o tecla: unlock() lo despierta.
let ctx = null;

export function audioCtx() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) ctx = new AC();
  }
  return ctx;
}

export function unlockAudio() {
  const c = audioCtx();
  if (c && c.state === "suspended") c.resume().catch(() => {});
}

export const audioReady = () => !!ctx && ctx.state === "running";

/** Nivel 0..1 a partir de un AnalyserNode. */
export function levelOf(analyser, buf) {
  if (!analyser) return 0;
  analyser.getByteTimeDomainData(buf);
  let sum = 0;
  for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
  return Math.min(1, Math.sqrt(sum / buf.length) * 3.2);
}

["pointerdown", "keydown", "touchstart"].forEach((ev) => window.addEventListener(ev, unlockAudio, { passive: true }));

// v0.8: sonidos muy tenues ("subliminales") para que la app se sienta viva — nunca una notificación de la nada.
// Un solo tono corto y suave por cada momento; cada uno tiene su propio timbre para distinguirse al oído sin ser invasivo.
function tone(freqFrom, freqTo, delay, peak, dur) {
  try {
    if (!audioReady()) return;
    const c = audioCtx(), o = c.createOscillator(), g = c.createGain(), t = c.currentTime + delay;
    o.type = "sine";
    o.frequency.setValueAtTime(freqFrom, t);
    if (freqTo !== freqFrom) o.frequency.exponentialRampToValueAtTime(freqTo, t + dur * 0.6);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(peak, t + dur * 0.15);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(c.destination);
    o.start(t); o.stop(t + dur + 0.02);
  } catch { /* sin sonido */ }
}

/** Micrófono abierto (tocaste el botón, o EDI está armada esperando tu orden): barrido breve hacia arriba o abajo. */
export function cueMic(up = true) { tone(up ? 660 : 880, up ? 990 : 520, 0, 0.1, 0.16); }
/** Un instante antes de que EDI empiece a hablar: "pop" muy corto y grave, casi imperceptible. */
export function cueSpeak() { tone(480, 480, 0, 0.055, 0.07); }
/** Aviso que EDI no pidió (recordatorio, correo nuevo): dos notas suaves para que no te tome totalmente desprevenido. */
export function cueAlert() { tone(740, 740, 0, 0.08, 0.1); tone(988, 988, 0.1, 0.08, 0.12); }
