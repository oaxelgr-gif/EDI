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
