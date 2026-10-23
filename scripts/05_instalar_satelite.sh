#!/bin/bash
# v0.9 (frente 8): deja el satélite de EDI (satellite/edi_satellite.py) corriendo solo, siempre, en esta
# Mac, igual que EDI Helper. Uso: ./scripts/05_instalar_satelite.sh [uninstall]
set -euo pipefail
EDI_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SAT_DIR="$EDI_DIR/satellite"
PLIST="$HOME/Library/LaunchAgents/com.edi.satellite.plist"
LOG="$EDI_DIR/data/satellite.log"
mkdir -p "$EDI_DIR/data"

if [ "${1:-}" = "uninstall" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✔ Satélite desinstalado (el config.json y la carpeta autorizada no se tocan)."
  exit 0
fi

[ -f "$SAT_DIR/config.json" ] || {
  echo "❌ Falta satellite/config.json. Primero:"
  echo "   cd satellite && cp config.example.json config.json && nano config.json"
  echo "   (pon tu propia clave secreta y la carpeta que quieres autorizar)"
  exit 1
}
PY="$(command -v python3)"
[ -n "$PY" ] || { echo "❌ No encuentro python3 en el PATH."; exit 1; }

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.edi.satellite</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$SAT_DIR/edi_satellite.py</string><string>--config</string><string>$SAT_DIR/config.json</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PL
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
sleep 1
echo "✅ Satélite instalado y corriendo (arranca solo cada vez que inicies sesión)."
echo "   Log: $LOG"
tail -n 5 "$LOG" 2>/dev/null || true
