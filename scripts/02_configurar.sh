#!/bin/bash
# FASE 2 - Configuración guiada: nombre, IA gratuita y cuentas de correo.
set -e
cd "$(dirname "$0")/.."
[ -f .env ] || cp .env.example .env
[ -f config/accounts.yaml ] || cp config/accounts.example.yaml config/accounts.yaml

setvar() {  # setvar CLAVE valor  -> reemplaza en .env
  python3 - "$1" "$2" <<'PY'
import re,sys; k,v=sys.argv[1],sys.argv[2]; p=".env"; s=open(p).read()
s=re.sub(rf"^{k}=.*$", f"{k}={v}", s, flags=re.M) if re.search(rf"^{k}=", s, re.M) else s+f"\n{k}={v}\n"
open(p,"w").write(s)
PY
}

echo "=== EDI · Fase 2: configuración ==="
flush() { while read -r -t 0.2 _; do :; done; }   # descarta texto pegado de más
flush
read -r -p "¿Cómo quieres que EDI te llame? [jefe]: " NAME
if [ -z "$NAME" ] || [[ "$NAME" == *"/"* ]] || [[ "$NAME" == *"#"* ]] || [ ${#NAME} -gt 30 ]; then NAME="jefe"; fi
setvar EDI_USER_NAME "$NAME"; echo "  → Te llamaré: $NAME"

echo
if grep -qE "^GROQ_API_KEY=.+" .env; then
  read -r -p "Ya tienes llave de Groq guardada. ¿Cambiarla? [s/N]: " CH
  [[ "$CH" =~ ^[sS] ]] || SKIP_AI=1
fi
if [ -z "${SKIP_AI:-}" ]; then
echo "IA gratuita. Recomendado: Groq (crea tu llave gratis en https://console.groq.com/keys)"
read -r -p "¿Abrir la página de Groq ahora? [s/N]: " A; [[ "$A" =~ ^[sS] ]] && open "https://console.groq.com/keys"
flush; read -r -s -p "Pega tu GROQ_API_KEY (Enter para omitir): " KEY; echo
if [ -n "$KEY" ]; then setvar GROQ_API_KEY "$KEY"; setvar LLM_PROVIDER groq
else
  read -r -s -p "¿O una GEMINI_API_KEY de https://aistudio.google.com/apikey? (Enter para omitir): " GK; echo
  if [ -n "$GK" ]; then setvar GEMINI_API_KEY "$GK"; setvar LLM_PROVIDER gemini
  elif command -v ollama >/dev/null 2>&1; then setvar LLM_PROVIDER ollama
  else setvar LLM_PROVIDER none; echo "  (EDI funcionará sólo con comandos; puedes agregar IA después en .env)"; fi
fi
fi

echo
echo "Correo: necesitas una CONTRASEÑA DE APLICACIÓN por cuenta (ver docs/CUENTAS_CORREO.md)."
echo "Gmail → https://myaccount.google.com/apppasswords"
read -r -p "¿Configurar una cuenta Gmail ahora? [S/n]: " G
if [[ ! "$G" =~ ^[nN] ]]; then
  read -r -p "  Correo Gmail: " GU
  read -r -s -p "  Contraseña de aplicación (16 letras): " GP; echo
  setvar GMAIL_PERSONAL_PASS "${GP// /}"
  python3 - "$GU" <<'PY'
import sys,re; u=sys.argv[1]; p="config/accounts.yaml"; s=open(p).read()
s=s.replace("tu_correo@gmail.com", u, 1); open(p,"w").write(s)
PY
fi

echo
echo "Abriendo config/accounts.yaml para que agregues/actives más cuentas (enabled: true)…"
open -e config/accounts.yaml 2>/dev/null || true
chmod 600 .env config/accounts.yaml
echo "✅ Configuración guardada. Siguiente: ./scripts/03_crear_acceso_directo.sh"
