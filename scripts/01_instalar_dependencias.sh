#!/bin/bash
# FASE 1 - Dependencias.
# Mac Intel: Homebrew ya NO se deja instalar en Intel, así que el motor es Docker Desktop.
#   ./scripts/01_instalar_dependencias.sh            -> verifica Docker y construye EDI
#   ./scripts/01_instalar_dependencias.sh --ollama   -> además descarga el modelo local qwen2.5:3b (~2 GB)
set -e
export PATH="$HOME/.docker/bin:/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
cd "$(dirname "$0")/.."
# ¿Responde el motor Docker? (consulta rápida al socket con límite de 3 s; `docker info` a veces se cuelga)
docker_ok() {
  for sock in "$HOME/.docker/run/docker.sock" "/var/run/docker.sock" "$HOME/.colima/default/docker.sock"; do
    [ -S "$sock" ] && curl -s --max-time 3 --unix-socket "$sock" http://localhost/_ping 2>/dev/null | grep -q OK && return 0
  done
  return 1
}

WITH_OLLAMA=false; [ "${1:-}" = "--ollama" ] && WITH_OLLAMA=true
echo "=== EDI · Fase 1: dependencias ==="

# 1) Motor Docker
if [ -d "/Applications/Docker.app" ]; then
  echo "▸ Docker Desktop encontrado ✔"
elif command -v colima >/dev/null 2>&1; then
  echo "▸ Colima encontrado ✔"
elif [ "$(uname -m)" = "arm64" ] && command -v brew >/dev/null 2>&1; then
  brew install colima docker docker-compose
else
  echo "❌ Falta Docker Desktop. Descarga la versión para Intel:"
  echo "   https://desktop.docker.com/mac/main/amd64/Docker.dmg"
  open "https://desktop.docker.com/mac/main/amd64/Docker.dmg" 2>/dev/null || true
  echo "   Instálalo, ábrelo una vez y vuelve a correr este script."; exit 1
fi

# 2) Encender Docker y esperar
if ! docker_ok; then
  echo "▸ Encendiendo Docker (puede tardar 1-2 min la primera vez)…"
  if [ -d "/Applications/Docker.app" ]; then open -ga Docker; else colima start --cpu 2 --memory 3 --disk 15; fi
  for _ in $(seq 1 90); do docker_ok && break; sleep 2; done
fi
docker_ok || { echo "❌ Docker no respondió. Ábrelo manualmente y reintenta."; exit 1; }
echo "▸ Docker listo ✔"

# 3) IA local opcional (Ollama ya instalado en tu Mac)
if $WITH_OLLAMA; then
  if command -v ollama >/dev/null 2>&1; then
    pgrep -x ollama >/dev/null || (open -ga Ollama 2>/dev/null || nohup ollama serve >/dev/null 2>&1 &)
    sleep 3; ollama pull qwen2.5:3b
  else
    echo "⚠️  Ollama no está instalado: descárgalo de https://ollama.com/download/mac"
  fi
fi

# 4) Construir EDI
[ -f .env ] || cp .env.example .env
[ -f config/accounts.yaml ] || cp config/accounts.example.yaml config/accounts.yaml
echo "▸ Construyendo imagen de EDI (2-5 min la primera vez)…"
if command -v docker-compose >/dev/null 2>&1; then docker-compose build; else docker compose build; fi
echo
echo "✅ Fase 1 lista. Siguiente: ./scripts/03_crear_acceso_directo.sh   (la Fase 2 ya la hiciste)"
