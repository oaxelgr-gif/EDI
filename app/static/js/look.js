// Apariencia personalizable: paleta de colores, transparencia y desenfoque del vidrio.
// Script clásico (no módulo) cargado en <head> para aplicar el color antes de pintar, sin parpadeo.
(function () {
  var PALETTES = [
    { id: "neon", name: "Morado neón", a: "#b266ff", b: "#e879f9", c: "#4cc9f0" },
    { id: "ocean", name: "Azul océano", a: "#3b82f6", b: "#22d3ee", c: "#a78bfa" },
    { id: "mint", name: "Verde menta", a: "#10b981", b: "#5eead4", c: "#a3e635" },
    { id: "rose", name: "Rosa", a: "#ec4899", b: "#f9a8d4", c: "#a78bfa" },
    { id: "sunset", name: "Atardecer", a: "#f97316", b: "#f43f5e", c: "#facc15" },
    { id: "ruby", name: "Rubí", a: "#ef4444", b: "#fb7185", c: "#f97316" },
    { id: "gold", name: "Dorado", a: "#eab308", b: "#f59e0b", c: "#fde68a" },
    { id: "aqua", name: "Turquesa", a: "#06b6d4", b: "#2dd4bf", c: "#818cf8" },
    { id: "graphite", name: "Grafito", a: "#94a3b8", b: "#cbd5e1", c: "#64748b" },
    { id: "rainbow", name: "Multicolor", a: "#22d3ee", b: "#e879f9", c: "#facc15", multi: true },
  ];
  var DEFAULT = { palette: "neon", a: null, b: null, c: null, glass: 100, blur: 22 };

  function get() {
    try { return Object.assign({}, DEFAULT, JSON.parse(localStorage.getItem("edi.look") || "{}")); } catch (e) { return Object.assign({}, DEFAULT); }
  }
  function set(look) {
    try { localStorage.setItem("edi.look", JSON.stringify(look)); } catch (e) {}
    apply(look);
  }
  function hex2rgb(h) {
    h = (h || "#000").replace("#", "");
    if (h.length === 3) h = h.split("").map(function (x) { return x + x; }).join("");
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(c1, c2, t) { return c1.map(function (v, i) { return Math.round(v * (1 - t) + c2[i] * t); }); }
  function css(rgb, a) { return a === undefined ? "rgb(" + rgb.join(",") + ")" : "rgba(" + rgb.join(",") + "," + a + ")"; }
  function isDark() {
    var t = document.documentElement.dataset.theme;
    return t === "dark" || (!t && !(window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches));
  }

  function apply(look) {
    look = look || get();
    var p = PALETTES.filter(function (x) { return x.id === look.palette; })[0] || PALETTES[0];
    var A = hex2rgb(look.a || p.a), B = hex2rgb(look.b || p.b), C = hex2rgb(look.c || p.c);
    var dark = isDark(), s = document.documentElement.style;
    var g = Math.max(0.2, Math.min(2.2, (look.glass || 100) / 100));
    // En claro se oscurece el acento para que se lea bien
    var a = dark ? A : mix(A, [0, 0, 0], 0.18), b = dark ? B : mix(B, [0, 0, 0], 0.18);
    var al = function (x) { return Math.min(0.96, +(x * g).toFixed(3)); };
    var vars = {
      "--accent": css(a), "--accent-2": css(b), "--accent-rgb": a.join(", "),
      "--glow": "0 0 24px " + css(a, dark ? 0.55 : 0.35),
      "--blob-1": css(A, dark ? 0.38 : 0.42), "--blob-2": css(B, dark ? 0.24 : 0.36), "--blob-3": css(C, dark ? (p.multi ? 0.22 : 0.12) : 0.28),
      "--bg": css(dark ? mix([8, 8, 12], A, 0.05) : mix([246, 246, 250], A, 0.06)),
      "--text-2": css(dark ? mix([205, 205, 215], A, 0.18) : mix([62, 62, 76], A, 0.18)),
      "--dim": css(dark ? mix([140, 140, 155], A, 0.15) : mix([120, 120, 135], A, 0.12)),
      "--text": css(dark ? mix([246, 246, 250], A, 0.05) : mix([22, 20, 32], A, 0.08)),
      "--shadow": dark ? "0 10px 40px rgba(0,0,0,.45)" : "0 10px 34px " + css(mix(A, [0, 0, 0], 0.5), 0.12),
      "--glass": dark ? css([255, 255, 255], al(0.055)) : css([255, 255, 255], al(0.5)),
      "--glass-2": dark ? css([255, 255, 255], al(0.09)) : css([255, 255, 255], al(0.66)),
      "--glass-3": dark ? css([255, 255, 255], al(0.14)) : css([255, 255, 255], al(0.85)),
      "--glass-line": dark ? css([255, 255, 255], al(0.12)) : css([255, 255, 255], al(0.85)),
      "--blur": "saturate(170%) blur(" + (look.blur == null ? 22 : look.blur) + "px)",
    };
    for (var k in vars) s.setProperty(k, vars[k]);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = vars["--bg"];
    try { window.dispatchEvent(new CustomEvent("edi:look")); } catch (e) {}
  }

  window.ediLook = { PALETTES: PALETTES, DEFAULT: DEFAULT, get: get, set: set, apply: apply };
  apply();
  if (window.matchMedia) {
    var mq = matchMedia("(prefers-color-scheme: light)");
    (mq.addEventListener ? mq.addEventListener.bind(mq, "change") : mq.addListener.bind(mq))(function () { apply(); });
  }
})();
