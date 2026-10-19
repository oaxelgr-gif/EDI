#!/bin/bash
# FASE 4 - Crea "EDI.app" (con ventana de progreso) y "Apagar EDI.app" en el Escritorio.
set -e
EDI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DESK="$HOME/Desktop"
chmod +x "$EDI_DIR"/scripts/*.sh
mkdir -p "$EDI_DIR/data"

# EDI.app: AppleScript con barra de progreso nativa de macOS
TMP="$(mktemp -t edi).applescript"
sed "s|__EDI_DIR__|$EDI_DIR|g" "$EDI_DIR/scripts/launcher.applescript" > "$TMP"
rm -rf "$DESK/EDI.app"
osacompile -o "$DESK/EDI.app" "$TMP"
rm -f "$TMP"

# Apagar EDI.app
TMP="$(mktemp -t edi).applescript"
cat > "$TMP" <<EOS
do shell script "/bin/bash '$EDI_DIR/scripts/edi.sh' stop --all >> '$EDI_DIR/data/edi-launcher.log' 2>&1"
display notification "EDI apagado" with title "EDI"
EOS
rm -rf "$DESK/Apagar EDI.app"
osacompile -o "$DESK/Apagar EDI.app" "$TMP"
rm -f "$TMP"

# Ícono propio (SVG → PNG → ICNS con herramientas de macOS)
ICON_SVG="$EDI_DIR/assets/edi-icon.svg"
if [ -f "$ICON_SVG" ]; then
  W="$(mktemp -d)"
  qlmanage -t -s 1024 -o "$W" "$ICON_SVG" >/dev/null 2>&1 || true
  if [ -f "$W/edi-icon.svg.png" ] && sips -s format icns "$W/edi-icon.svg.png" --out "$W/edi.icns" >/dev/null 2>&1; then
    cp "$W/edi.icns" "$DESK/EDI.app/Contents/Resources/applet.icns"; touch "$DESK/EDI.app"
  fi
  rm -rf "$W"
fi
echo "✅ Listo: EDI.app (con ventana de progreso) y Apagar EDI.app en tu Escritorio."
