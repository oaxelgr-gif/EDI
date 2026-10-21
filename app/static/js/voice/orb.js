// Anillo de voz: 96 marcas radiales, estilo lectura de omni-tool.
// Ámbar cuando EDI habla, verde agua cuando escucha, respiración lenta en reposo.
const TICKS = 96;
// Colores tomados del tema activo (--accent-rgb y --listen-rgb), así funciona en claro y oscuro
function themeColors() {
  const cs = getComputedStyle(document.documentElement);
  const rgb = (v, d) => (cs.getPropertyValue(v).trim() || d).split(",").map(Number);
  const accent = rgb("--accent-rgb", "178,102,255"), listen = rgb("--listen-rgb", "125,211,252");
  return { idle: accent, speaking: accent, loading: accent, blocked: accent, listening: listen, wake: listen, armed: listen };
}
let COLORS = themeColors();
new MutationObserver(() => (COLORS = themeColors())).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", () => (COLORS = themeColors()));
window.addEventListener("edi:look", () => (COLORS = themeColors()));
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function mountOrb(canvas, getState, getLevel) {
  const ctx = canvas.getContext("2d");
  let raf = 0, smooth = 0, t0 = performance.now();
  const history = new Float32Array(TICKS);

  function size() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.round(r.width * dpr);
    canvas.height = Math.round(r.height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function frame(now) {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w) { raf = requestAnimationFrame(frame); return; }
    const state = getState();
    const lvl = getLevel();
    smooth += (lvl - smooth) * 0.25;
    const t = (now - t0) / 1000;
    // desplaza el historial para que la onda recorra el anillo
    history.copyWithin(1, 0);
    history[0] = smooth;

    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.34;
    const [r, g, b] = COLORS[state] || COLORS.idle;
    const breathing = reduce ? 0 : (Math.sin(t * 1.4) + 1) * 0.5;
    const active = state !== "idle";

    for (let i = 0; i < TICKS; i++) {
      const a = (i / TICKS) * Math.PI * 2 - Math.PI / 2;
      const mirror = history[Math.min(i, TICKS - i)] || 0;
      const amp = active ? mirror : 0.04 + breathing * 0.05 * (i % 2 ? 1 : 0.6);
      const len = 3 + amp * R * 0.55 + (state === "loading" && !reduce ? 4 * Math.max(0, Math.sin(a * 3 - t * 6)) : 0);
      const inner = R - 2;
      const alpha = active ? 0.5 + Math.min(0.5, amp * 1.2) : 0.32 + breathing * 0.18;
      ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
      ctx.shadowColor = `rgba(${r},${g},${b},${active ? 0.9 : 0.5})`;
      ctx.shadowBlur = active ? 10 : 5;
      ctx.lineWidth = i % 4 === 0 ? 2 : 1.25;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner);
      ctx.lineTo(cx + Math.cos(a) * (inner + len), cy + Math.sin(a) * (inner + len));
      ctx.stroke();
    }
    ctx.shadowBlur = 0;
    // núcleo
    const core = R * (0.42 + smooth * 0.12 + (active ? 0 : breathing * 0.02));
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, core);
    grad.addColorStop(0, `rgba(${r},${g},${b},${active ? 0.95 : 0.55})`);
    grad.addColorStop(0.7, `rgba(${r},${g},${b},${active ? 0.35 : 0.14})`);
    grad.addColorStop(1, `rgba(${r},${g},${b},0)`);
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(cx, cy, core, 0, Math.PI * 2); ctx.fill();
    // anillo interior punteado
    ctx.setLineDash([2, 5]);
    ctx.strokeStyle = `rgba(${r},${g},${b},.35)`;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, R * 0.72, reduce ? 0 : t * 0.2, (reduce ? 0 : t * 0.2) + Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);

    raf = requestAnimationFrame(frame);
  }

  size();
  const ro = new ResizeObserver(size);
  ro.observe(canvas);
  raf = requestAnimationFrame(frame);
  return () => { cancelAnimationFrame(raf); ro.disconnect(); };
}
