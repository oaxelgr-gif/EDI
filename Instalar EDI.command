#!/bin/bash
# Doble clic: prepara Docker, construye EDI y crea el acceso directo en el Escritorio.
cd "$(dirname "$0")"
echo "=========== Instalando EDI ==========="
./scripts/01_instalar_dependencias.sh && ./scripts/03_crear_acceso_directo.sh && {
  echo; echo "✅ Listo. Abriendo EDI…"; ./scripts/edi.sh start; }
echo; echo "Puedes cerrar esta ventana."
