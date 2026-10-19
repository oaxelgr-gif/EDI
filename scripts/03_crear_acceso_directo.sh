#!/bin/bash
# FASE 4 - Crea "EDI.app" y "Apagar EDI.app" en el Escritorio.
# Doble clic en EDI.app → enciende Colima/Docker → levanta el contenedor → abre la ventana de EDI.
set -e
EDI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DESK="$HOME/Desktop"
chmod +x "$EDI_DIR"/scripts/*.sh

make_app() {  # make_app "Nombre" "comando"
  local name="$1" cmd="$2" tmp
  tmp="$(mktemp -t edi).applescript"
  cat > "$tmp" <<EOF
do shell script "/bin/bash '$EDI_DIR/scripts/edi.sh' $cmd >> '$EDI_DIR/data/edi-launcher.log' 2>&1 &"
EOF
  rm -rf "$DESK/$name.app"
  osacompile -o "$DESK/$name.app" "$tmp"
  rm -f "$tmp"
}

mkdir -p "$EDI_DIR/data"
make_app "EDI" "start"
make_app "Apagar EDI" "stop --all"

# Ícono propio (SVG → PNG → ICNS con herramientas de macOS)
ICON_SVG="$EDI_DIR/assets/edi-icon.svg"
if [ -f "$ICON_SVG" ]; then
  W="$(mktemp -d)"
  qlmanage -t -s 1024 -o "$W" "$ICON_SVG" >/dev/null 2>&1 || true
  PNG="$W/edi-icon.svg.png"
  if [ -f "$PNG" ]; then
    sips -s format icns "$PNG" --out "$EDI_DIR/assets/edi.icns" >/dev/null 2>&1 || true
    if [ -f "$EDI_DIR/assets/edi.icns" ]; then
      cp "$EDI_DIR/assets/edi.icns" "$DESK/EDI.app/Contents/Resources/applet.icns"
      touch "$DESK/EDI.app"
    fi
  fi
  rm -rf "$W"
fi

echo "✅ Accesos directos creados en el Escritorio:"
echo "   • EDI.app         → enciende todo y abre la ventana"
echo "   • Apagar EDI.app  → apaga el contenedor y Colima (libera RAM)"
echo
echo "La primera vez macOS puede preguntar si permites que la app controle 'System Events' o la terminal: acepta."
echo "Tip: arrastra EDI.app al Dock para tenerlo a un clic."
