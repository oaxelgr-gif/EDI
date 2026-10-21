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

# ---- Progreso para la ventana de EDI.app: data/launch-status = "porcentaje|mensaje|segundos_restantes" ----
STATUS="$EDI_DIR/data/launch-status"
LAST_DUR="$EDI_DIR/data/last-launch-seconds"
START_TS=$(date +%s)
progress() {  # progress 42 "Mensaje"
  local pct=$1 msg=$2 now el last eta=-1
  now=$(date +%s); el=$((now - START_TS))
  last=$(cat "$LAST_DUR" 2>/dev/null || echo 0)
  if [ "$pct" -ge 100 ]; then eta=0
  elif [ "$last" -gt 0 ] && [ "$el" -lt "$last" ]; then eta=$((last - el))
  elif [ "$pct" -gt 8 ]; then eta=$(( el * (100 - pct) / pct ))
  fi
  printf '%s|%s|%s\n' "$pct" "$msg" "$eta" > "$STATUS.tmp" && mv "$STATUS.tmp" "$STATUS"
  [ "$msg" != "${LAST_MSG:-}" ] && echo "[$pct%] $msg" >> "$LOG"
  LAST_MSG=$msg
}
fail() { printf -- '-1|%s|0\n' "$1" > "$STATUS"; echo "ERROR: $1" >> "$LOG"; notify "$1"; exit 1; }
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
  progress 8 "Revisando el motor Docker"
  if docker_ok; then progress 30 "Docker listo"; return 0; fi
  if [ -d "/Applications/Docker.app" ]; then
    progress 10 "Encendiendo Docker Desktop"; open -ga Docker
  elif command -v colima >/dev/null 2>&1; then
    progress 10 "Encendiendo Colima"
    (colima start --cpu 2 --memory 3 --disk 15 >>"$LOG" 2>&1 || colima start >>"$LOG" 2>&1) &
  else
    fail "No encontré Docker. Ejecuta scripts/01_instalar_dependencias.sh"
  fi
  for i in $(seq 1 120); do
    docker_ok && { progress 30 "Docker listo"; return 0; }
    progress $((10 + i * 19 / 120)) "Esperando a que Docker termine de encender"
    sleep 2
  done
  fail "Docker no respondió en 4 minutos. Ábrelo manualmente y vuelve a intentar."
}

wait_healthy() {
  for i in $(seq 1 90); do
    curl -fs --max-time 2 "$URL/api/health" >/dev/null 2>&1 && return 0
    progress $((86 + i * 12 / 90)) "Encendiendo el servidor de EDI"
    sleep 1
  done
  return 1
}

# Construye y levanta el contenedor leyendo el avance real de Docker ([paso/total])
build_up() {
  local before; before=$(wc -l < "$LOG")
  progress 32 "Preparando la imagen de EDI"
  BUILDKIT_PROGRESS=plain compose up -d --build >>"$LOG" 2>&1 &
  local pid=$! pct=32 line step total
  while kill -0 "$pid" 2>/dev/null; do
    line=$(tail -n +"$((before + 1))" "$LOG" | grep -oE '\[[0-9]+/[0-9]+\][^"]*' | tail -1 || true)
    if [ -n "$line" ]; then
      step=$(echo "$line" | sed -E 's/^\[([0-9]+)\/([0-9]+)\].*/\1/'); total=$(echo "$line" | sed -E 's/^\[([0-9]+)\/([0-9]+)\].*/\2/')
      [ "$total" -gt 0 ] && pct=$((32 + step * 48 / total))
      case "$line" in *"pip install"*) msg="Instalando dependencias de Python (paso $step de $total)";;
                      *) msg="Construyendo EDI (paso $step de $total)";; esac
    else msg="Preparando la imagen de EDI"; fi
    tail -n +"$((before + 1))" "$LOG" | grep -q "Container edi.*Start" && { pct=84; msg="Arrancando el contenedor"; }
    progress "$pct" "$msg"
    sleep 1
  done
  wait "$pid"
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

# IP de la Mac en la red (para abrir EDI desde el celular u otra computadora)
lan_ip() {
  local ip=""
  for i in en0 en1 en2 en3 en4; do ip=$(ipconfig getifaddr "$i" 2>/dev/null || true); [ -n "$ip" ] && break; done
  echo "$ip"
}
set_env() {  # set_env CLAVE valor  (en .env)
  if grep -q "^$1=" .env; then sed -i '' "s|^$1=.*|$1=$2|" .env; else printf '\n%s=%s\n' "$1" "$2" >> .env; fi
}

check_config() {
  [ -f .env ] || return 1
  [ -f config/accounts.yaml ] || cp config/accounts.example.yaml config/accounts.yaml
}

cmd="${1:-start}"
case "$cmd" in
  start)
    progress 2 "Iniciando EDI"
    check_config || fail "Falta configurar EDI (.env)"
    set_env EDI_LAN_HOST "$(lan_ip)"
    ensure_docker
    build_up || fail "No se pudo construir EDI. Revisa data/edi-launcher.log"
    progress 85 "Contenedor en marcha"
    wait_healthy || fail "El servidor de EDI no respondió. Revisa data/edi-launcher.log"
    echo $(( $(date +%s) - START_TS )) > "$LAST_DUR"
    progress 100 "EDI en línea"
    say_msg "EDI en línea → $URL"; open_ui ;;
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
