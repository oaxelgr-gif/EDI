// Refrescos en vivo sin perder lo que estás escribiendo.
// whenIdle(zona, fn): si tienes el cursor en un campo DENTRO de la zona que se va a redibujar, espera a que salgas
// de ella (o a que cierres la hoja de edición) y entonces refresca una sola vez. Si no, refresca de inmediato.
const waiting = new WeakMap();

export const editing = (scope) => {
  const a = document.activeElement;
  return !!(scope && a && scope.contains(a) && a.matches?.("input, textarea, select, [contenteditable=true]"));
};

export function whenIdle(scope, fn) {
  if (!scope?.isConnected) return;
  if (!editing(scope)) { fn(); return; }
  if (waiting.has(scope)) return;   // ya hay un refresco pendiente para esta zona
  const go = () => {
    setTimeout(() => {
      if (editing(scope)) return;   // pasó a otro campo de la misma zona: sigue esperando
      scope.removeEventListener("focusout", go);
      waiting.delete(scope);
      if (scope.isConnected) fn();
    }, 120);
  };
  waiting.set(scope, go);
  scope.addEventListener("focusout", go);
}

/** ¿Hay una hoja de edición abierta (pendiente, correo, conexión…)? Esas viven fuera de la vista y no se tocan. */
export const sheetOpen = () => !!document.querySelector(".composer-sheet");
