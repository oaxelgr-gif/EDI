#!/bin/bash
# FASE 0 - Análisis del equipo: verifica que tu Mac puede correr EDI.
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
ok()   { echo "  ✅ $*"; }
warn() { echo "  ⚠️  $*"; }
bad()  { echo "  ❌ $*"; }

echo "=== EDI · Fase 0: análisis del sistema ==="
echo "macOS:      $(sw_vers -productVersion) ($(uname -m))"
echo "Modelo:     $(sysctl -n hw.model)"
echo "CPU:        $(sysctl -n machdep.cpu.brand_string)  ($(sysctl -n hw.physicalcpu) núcleos)"
RAM_GB=$(( $(sysctl -n hw.memsize) / 1073741824 )); echo "RAM:        ${RAM_GB} GB"
FREE_GB=$(df -g "$HOME" | awk 'NR==2{print $4}'); echo "Disco libre: ${FREE_GB} GB"
echo
echo "Requisitos:"
[ "$RAM_GB" -ge 8 ] && ok "RAM suficiente" || bad "Se recomiendan 8 GB+"
[ "$FREE_GB" -ge 10 ] && ok "Espacio suficiente (EDI usa ~3-6 GB con Colima)" || bad "Libera al menos 10 GB"
[ "$(sysctl -n kern.hv_support 2>/dev/null)" = "1" ] && ok "Virtualización (Hypervisor) disponible" || bad "Sin soporte de virtualización: Docker no funcionará"
xcode-select -p >/dev/null 2>&1 && ok "Xcode Command Line Tools" || warn "Faltan Command Line Tools (se instalan en la fase 1)"
echo
echo "Herramientas:"
for t in brew colima docker docker-compose git python3 ollama; do
  if command -v $t >/dev/null 2>&1; then ok "$t → $(command -v $t)"; else warn "$t no instalado"; fi
done
[ -d "/Applications/Docker.app" ] && ok "Docker Desktop presente (puedes usarlo en lugar de Colima)"
[ -d "/Applications/Google Chrome.app" ] && ok "Google Chrome (mejor reconocimiento de voz)" || warn "Sin Chrome: se usará Safari (también reconoce voz)"
echo
echo "Voces en español del sistema (para mejor voz instala 'Paulina (Mejorada)' en Ajustes > Accesibilidad > Contenido leído):"
say -v '?' 2>/dev/null | grep -E "es_(MX|ES|US)" | sed 's/^/   /' | head -8
echo
echo "Siguiente paso: ./scripts/01_instalar_dependencias.sh"
