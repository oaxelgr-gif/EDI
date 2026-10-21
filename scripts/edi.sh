#!/bin/bash
# ============================================================
#  EDI - control central (modo NATIVO, sin Docker: arranca en segundos y usa ~80 MB de RAM)
#  Uso: ./scripts/edi.sh [start|stop|restart|status|logs|open|rebuild|test|backup]
#  Para volver a Docker: pon EDI_MODE=docker en .env (usa scripts/edi-docker.sh).
# ============================================================
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

EDI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$EDI_DIR"
if grep -qs '^EDI_MODE=docker' .env; then exec /bin/bash "$EDI_DIR/scripts/edi-docker.sh" "$@"; fi

URL="http://localhost:8765"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DATA="$EDI_DIR/data"
LOG="$DATA/edi-launcher.log"
SRV_LOG="$DATA/edi-server.log"
PIDF="$DATA/edi.pid"
RT="$EDI_DIR/.runtime"
UV="$RT/bin/uv"
PY="$EDI_DIR/.venv/bin/python"
mkdir -p "$DATA" "$RT/bin"

say_msg() { echo "▸ $*"; }

# ---- Progreso para la ventana de EDI.app: data/launch-status = "porcentaje|mensaje|segundos_restantes" ----
STATUS="$DATA/launch-status"
LAST_DUR="$DATA/last-launch-seconds"
[ -f "$DATA/.native" ] || { rm -f "$LAST_DUR"; touch "$DATA/.native"; }   # tiempos viejos de Docker ya no sirven
START_TS=$(date +%s)
progress() {
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
notify() { osascript -e "display notification \"$1\" with title \"EDI\"" >/dev/null 2>&1 || true; }
fail() { printf -- '-1|%s|0\n' "$1" > "$STATUS"; echo "ERROR: $1" >> "$LOG"; notify "$1"; exit 1; }

healthy() { curl -fs --max-time 2 "$URL/api/health" >/dev/null 2>&1; }
running() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }

# ---- Instalación única: uv (gestor de Python, 1 archivo) + Python 3.12 + dependencias ----
ensure_uv() {
  [ -x "$UV" ] && return 0
  progress 8 "Descargando uv (sólo la primera vez)"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$RT/bin" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >>"$LOG" 2>&1 \
    || fail "No pude descargar uv. ¿Hay internet?"
  [ -x "$UV" ] || fail "uv no quedó instalado. Revisa data/edi-launcher.log"
}

ensure_python() {
  ensure_uv
  export UV_PYTHON_INSTALL_DIR="$RT/python" UV_CACHE_DIR="$RT/cache"
  if [ ! -x "$PY" ]; then
    progress 20 "Preparando Python 3.12 (sólo la primera vez, ~30 MB)"
    "$UV" venv --python 3.12 "$EDI_DIR/.venv" >>"$LOG" 2>&1 || fail "No pude preparar Python. Revisa data/edi-launcher.log"
  fi
  local want have
  want=$(shasum app/requirements.txt | cut -d' ' -f1)
  have=$(cat "$EDI_DIR/.venv/.req-hash" 2>/dev/null || true)
  if [ "$want" != "$have" ]; then
    progress 45 "Instalando componentes de EDI (sólo la primera vez, 1–2 min)"
    "$UV" pip install --python "$PY" -r app/requirements.txt >>"$LOG" 2>&1 || fail "Falló la instalación. Revisa data/edi-launcher.log"
    echo "$want" > "$EDI_DIR/.venv/.req-hash"
    "$UV" cache clean >/dev/null 2>&1 || true   # libera espacio
  fi
}

load_env() {  # exporta las variables de .env (CLAVE=valor)
  [ -f .env ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    [[ "$line" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]] || continue
    local k=${line%%=*} v=${line#*=}
    v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}
    export "$k=$v"
  done < .env
}

lan_ip() {
  local ip=""
  for i in en0 en1 en2 en3 en4; do ip=$(ipconfig getifaddr "$i" 2>/dev/null || true); [ -n "$ip" ] && break; done
  echo "$ip"
}
set_env() {
  touch .env
  if grep -q "^$1=" .env; then sed -i '' "s|^$1=.*|$1=$2|" .env; else printf '\n%s=%s\n' "$1" "$2" >> .env; fi
}

# Si quedó corriendo la versión de Docker, la apaga para liberar los puertos
stop_old_docker() {
  for sock in "$HOME/.docker/run/docker.sock" "/var/run/docker.sock"; do
    if [ -S "$sock" ] && curl -s --max-time 2 --unix-socket "$sock" http://localhost/_ping 2>/dev/null | grep -q OK; then
      for c in edi edi-whatsapp; do
        curl -s --max-time 10 --unix-socket "$sock" -X POST "http://localhost/containers/$c/stop?t=3" >/dev/null 2>&1 || true
      done
    fi
  done
}

start_server() {
  load_env
  export EDI_DATA_DIR="$DATA" EDI_CONFIG_DIR="$EDI_DIR/config" EDI_HTTP_HOST=127.0.0.1 EDI_HTTP_PORT=8765 EDI_HTTPS_PORT=8766 EDI_SHORTCUT_PORT=8767 \
         PYTHONPATH="$EDI_DIR/app" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
  unset EDI_WHATSAPP_URL
  [ -f "$SRV_LOG" ] && [ "$(wc -c < "$SRV_LOG")" -gt 2000000 ] && mv "$SRV_LOG" "$SRV_LOG.old"
  (cd "$EDI_DIR/app" && nohup "$PY" -m edi.serve >>"$SRV_LOG" 2>&1 & echo $! > "$PIDF")
}

wait_healthy() {
  for i in $(seq 1 60); do
    healthy && return 0
    running || return 1
    progress $((82 + i * 16 / 60)) "Encendiendo el servidor de EDI"
    sleep 0.5
  done
  return 1
}

# Navegador: Safari (por defecto). Para volver a Chrome pon EDI_BROWSER=chrome en .env
open_ui() {
  if grep -qs '^EDI_BROWSER=chrome' .env && [ -x "$CHROME" ]; then
    rm -rf "$HOME/.edi-chrome/Default/Cache" "$HOME/.edi-chrome/Default/Code Cache" 2>/dev/null || true
    nohup "$CHROME" --app="$URL" --user-data-dir="$HOME/.edi-chrome" \
      --autoplay-policy=no-user-gesture-required --window-size=1200,820 \
      --no-first-run --no-default-browser-check >/dev/null 2>&1 &
    return
  fi
  # Safari: si ya hay una pestaña de EDI la trae al frente y la recarga; si no, abre una ventana nueva
  osascript >/dev/null 2>&1 <<OSA || open -a Safari "$URL"
tell application "Safari"
  activate
  set found to false
  repeat with w in windows
    repeat with t in tabs of w
      if (URL of t as text) starts with "$URL" then
        set current tab of w to t
        set index of w to 1
        set URL of t to "$URL"
        set found to true
        exit repeat
      end if
    end repeat
    if found then exit repeat
  end repeat
  if not found then make new document with properties {URL:"$URL"}
end tell
OSA
}

# Cierra las pestañas de EDI en Safari (sin cerrar tus otras pestañas)
close_ui() {
  pkill -f "user-data-dir=$HOME/.edi-chrome" 2>/dev/null || true
  pgrep -x Safari >/dev/null 2>&1 || return 0
  osascript >/dev/null 2>&1 <<OSA || true
tell application "Safari"
  repeat with w in (every window)
    repeat with t in (every tab of w)
      if (URL of t as text) starts with "$URL" then close t
    end repeat
  end repeat
end tell
OSA
}

stop_server() {
  if running; then
    kill "$(cat "$PIDF")" 2>/dev/null || true
    for _ in 1 2 3 4 5 6; do running || break; sleep 0.5; done
    running && kill -9 "$(cat "$PIDF")" 2>/dev/null || true
  fi
  rm -f "$PIDF"
  pkill -f "$EDI_DIR/.venv/bin/python -m edi.serve" 2>/dev/null || true
  pkill -f "$RT/node/bin/node index.mjs" 2>/dev/null || true
}

cmd="${1:-start}"
case "$cmd" in
  start)
    progress 2 "Iniciando EDI"
    stop_old_docker
    if healthy; then progress 100 "EDI ya estaba en línea"; open_ui; exit 0; fi
    [ -f config/accounts.yaml ] || cp config/accounts.example.yaml config/accounts.yaml 2>/dev/null || true
    set_env EDI_LAN_HOST "$(lan_ip)"
    ensure_python
    stop_server
    progress 80 "Arrancando EDI"
    start_server
    wait_healthy || fail "El servidor no arrancó. Revisa data/edi-server.log"
    echo $(( $(date +%s) - START_TS )) > "$LAST_DUR"
    progress 100 "EDI en línea"
    say_msg "EDI en línea → $URL"; open_ui ;;
  stop)
    stop_server
    close_ui
    notify "EDI apagado"; say_msg "EDI apagado." ;;
  restart) "$0" stop; "$0" start ;;
  status) running && echo "Proceso $(cat "$PIDF") activo" || echo "Apagado"; curl -s "$URL/api/health" && echo ;;
  logs) tail -n 100 -f "$SRV_LOG" ;;
  open) open_ui ;;
  rebuild) stop_server; rm -rf "$EDI_DIR/.venv"; "$0" start ;;
  test) ensure_python; "$UV" pip install --python "$PY" -q pytest && (cd "$EDI_DIR" && PYTHONPATH=app "$PY" -m pytest -q tests) ;;
  backup)
    f="$HOME/Documents/edi-backup-$(date +%Y%m%d-%H%M).tar.gz"
    tar czf "$f" data config .env && say_msg "Respaldo en $f" ;;
  *) echo "Uso: $0 [start|stop|restart|status|logs|open|rebuild|test|backup]"; exit 1 ;;
esac
