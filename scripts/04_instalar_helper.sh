#!/bin/bash
# FASE 5 - EDI Helper: ícono en la barra de menú + "Hey EDI" + ⌥Espacio, siempre activo.
# Compila la app nativa con swiftc (Command Line Tools), la instala en ~/Applications y la abre al iniciar sesión.
set -e
EDI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$EDI_DIR/data/helper-build.log"
APP="$HOME/Applications/EDI Helper.app"
mkdir -p "$EDI_DIR/data" "$HOME/Applications"
exec > >(tee "$LOG") 2>&1
echo "=== EDI Helper: compilando ($(date)) ==="
command -v swiftc >/dev/null || { echo "❌ Falta swiftc. Ejecuta: xcode-select --install"; exit 1; }
swiftc --version | head -1

BUILD="$(mktemp -d)"
ARCH="$(uname -m)"
swiftc -O -swift-version 5 -target "$ARCH-apple-macos11.0" \
  "$EDI_DIR/helper/EDIHelper.swift" -o "$BUILD/EDI Helper"
echo "✔ Compilado"

pkill -x "EDI Helper" 2>/dev/null || true
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BUILD/EDI Helper" "$APP/Contents/MacOS/"
sed "s|__EDI_DIR__|$EDI_DIR|g" "$EDI_DIR/helper/Info.plist" > "$APP/Contents/Info.plist"

# Ícono (usa el de EDI si existe)
ICON_SVG="$EDI_DIR/app/static/icon.svg"
W="$(mktemp -d)"
if qlmanage -t -s 1024 -o "$W" "$ICON_SVG" >/dev/null 2>&1 && [ -f "$W/icon.svg.png" ]; then
  sips -s format icns "$W/icon.svg.png" --out "$APP/Contents/Resources/AppIcon.icns" >/dev/null 2>&1 || true
fi
rm -rf "$W" "$BUILD"

# Firma local (necesaria para que macOS pida permisos de micrófono y voz)
codesign --force --deep --sign - "$APP"
echo "✔ Instalado en $APP"

# Abrir al iniciar sesión
PLIST="$HOME/Library/LaunchAgents/com.edi.helper.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.edi.helper</string>
  <key>ProgramArguments</key><array><string>/usr/bin/open</string><string>-a</string><string>$APP</string></array>
  <key>RunAtLoad</key><true/>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST" 2>/dev/null || true
open "$APP"
echo
echo "✅ EDI Helper listo. Busca el ícono ◎ en la barra de menú (arriba a la derecha)."
echo "   La primera vez macOS pedirá permiso de Micrófono y Reconocimiento de voz: acepta ambos."
echo "   Di “Hey EDI, ¿qué hora es?” o pulsa ⌥ + Espacio."
