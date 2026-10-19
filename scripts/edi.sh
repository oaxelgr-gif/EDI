#!/bin/bash
# ============================================================
#  EDI - control central
#  Uso: ./scripts/edi.sh [start|stop|restart|status|logs|open|rebuild|outlook correo|test|backup]
# ============================================================
set -euo pipefail

# Rutas típicas de Homebrew (Intel = /usr/local) para que funcione también desde el acceso directo
export PATH="$HOME/.docker/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

EDI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$EDI_DIR"
URL="http://localhost:8765"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
LOG="$EDI_DIR/data/edi-launcher.log"
mkdir -p "$EDI_DIR/data"

say_msg() { echo "▸ $*"; }
notify() { osascript -e "display notification \"$1\" with title \"EDI\"" >/dev/null 2>&1 || true; }

# ¿Responde el motor Docker? (consulta rápida al socket con límite de 3 s; `docker info` a veces se cuelga)
docker_ok() {
  for sock in "$HOME/.docker/run/docker.sock" "/var/run/docker.sock" "$HOME/.colima/default/docker.sock"; do
    [ -S "$sock" ] && curl -s --max-time 3 --unix-socket "$sock" http://localhost/_ping 2>/dev/null | grep -q OK && return 0
  done
  return 1
}

compose() {
  if [ -x "$HOME/.docker/bin/docker-compose" ] || command -v docker-compose >/dev/null 2>&1; then docker-compose "$@"
  else docker compose "$@"; fi
}

ensure_docker() {
  if docker_ok; then return 0; fi
  if [ -d "/Applications/Docker.app" ]; then
    say_msg "Abriendo Docker Desktop…"; notify "Encendiendo Docker…"
    open -ga Docker
  elif command -v colima >/dev/null 2>&1; then
    say_msg "Encendiendo Colima…"; notify "Encendiendo motor Docker…"
    colima start --cpu 2 --memory 3 --disk 15 >>"$LOG" 2>&1 || colima start >>"$LOG" 2>&1
  else
    echo "❌ No encontré Docker. Ejecuta primero: ./scripts/01_instalar_dependencias.sh"; notify "Falta Docker"; exit 1
  fi
  for _ in $(seq 1 90); do docker_ok && return 0; sleep 2; done
  echo "❌ Docker no respondió a tiempo. Revisa $LOG"; exit 1
}

wait_healthy() {
  for _ in $(seq 1 60); do curl -fs "$URL/api/health" >/dev/null 2>&1 && return 0; sleep 1; done
  echo "❌ EDI no respondió. Mira: ./scripts/edi.sh logs"; return 1
}

open_ui() {
  if [ -x "$CHROME" ]; then
    # Ventana dedicada tipo app, con su propio perfil (recuerda el permiso de micrófono)
    nohup "$CHROME" --app="$URL" --user-data-dir="$HOME/.edi-chrome" \
      --autoplay-policy=no-user-gesture-required --window-size=1200,820 \
      --no-first-run --no-default-browser-check >/dev/null 2>&1 &
  else
    open "$URL"   # Safari u otro navegador predeterminado
  fi
}

check_config() {
  [ -f .env ] || { echo "❌ Falta .env. Ejecuta ./scripts/02_configurar.sh"; notify "Falta configurar EDI"; exit 1; }
  [ -f config/accounts.yaml ] || cp config/accounts.example.yaml config/accounts.yaml
}

cmd="${1:-start}"
case "$cmd" in
  start)
    check_config; ensure_docker
    say_msg "Levantando EDI (aplica cambios si los hay)…"; notify "Preparando EDI… (la primera vez tarda unos minutos)"
    if ! compose up -d --build >>"$LOG" 2>&1; then notify "No se pudo levantar EDI. Revisa data/edi-launcher.log"; exit 1; fi
    wait_healthy || { notify "EDI no respondió. Revisa data/edi-launcher.log"; exit 1; }
    notify "EDI en línea"; say_msg "EDI en línea → $URL"; open_ui ;;
  stop)
    compose down >>"$LOG" 2>&1 || true
    if [ "${2:-}" = "--all" ]; then
      if command -v colima >/dev/null 2>&1 && colima status >/dev/null 2>&1; then colima stop
      elif [ -d "/Applications/Docker.app" ]; then osascript -e 'quit app "Docker"' >/dev/null 2>&1 || true; fi
    fi
    pkill -f "user-data-dir=$HOME/.edi-chrome" 2>/dev/null || true
    notify "EDI apagado"; say_msg "EDI apagado." ;;
  restart) "$0" stop; "$0" start ;;
  status) compose ps; curl -s "$URL/api/health" && echo ;;
  logs) compose logs -f --tail=100 ;;
  open) open_ui ;;
  rebuild) ensure_docker; compose build --no-cache && compose up -d ;;
  outlook)
    [ -n "${2:-}" ] || { echo "Uso: $0 outlook correo@outlook.com"; exit 1; }
    ensure_docker; compose run --rm edi python -m edi.oauth_ms "$2" ;;
  test) ensure_docker; compose run --rm -v "$EDI_DIR/tests:/app/tests:ro" edi sh -c "pip install -q pytest && python -m pytest -q tests" ;;
  backup)
    f="$HOME/Documents/edi-backup-$(date +%Y%m%d-%H%M).tar.gz"
    tar czf "$f" data config .env && say_msg "Respaldo en $f" ;;
  *) echo "Uso: $0 [start|stop [--all]|restart|status|logs|open|rebuild|outlook correo|test|backup]"; exit 1 ;;
esac
