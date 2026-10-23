# EDI en Windows (servidor dedicado, sin Docker)

Pensado para una PC de bajos recursos (4 GB RAM) que se queda prendida 24/7. Corre EDI
directo con Python + Node (sin Docker Desktop/WSL2), igual que el modo nativo de la Mac,
usando ~80-150 MB de RAM en reposo.

## 1. Lo que hay que instalar una sola vez

1. **Git para Windows** → https://git-scm.com (opciones por defecto). Te da Git Bash y `git`.
2. **Node.js 22 LTS** → https://nodejs.org (instalador .msi, opciones por defecto). Es para
   el puente de WhatsApp — EDI lo arranca solo, nada más necesita `node`/`npm` en el PATH.
3. **PowerShell** ya viene con Windows 10 Pro, no hay que instalar nada más (ni Python: lo
   instala `uv` solo, aislado, sin tocar nada del sistema).

## 2. Clonar y configurar

Abre **PowerShell** (no hace falta administrador):

```powershell
cd C:\
git clone https://github.com/oaxelgr-gif/EDI.git
cd EDI
copy .env.example .env
notepad .env
```

En el `.env` pon al menos tu `GROQ_API_KEY` (gratis en https://console.groq.com/keys) y
revisa `EDI_USER_NAME`. Lo demás lo puedes ajustar después desde Ajustes dentro de EDI.

Si vas a pasar tu carpeta `data\` (memoria, pendientes, sesión de WhatsApp) desde la Mac
para no empezar de cero, cópiala completa a `C:\EDI\data` antes del primer arranque.

## 3. Primer arranque

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\edi.ps1 start
```

La primera vez tarda 1-2 min (instala Python 3.12 aislado + las librerías). Al terminar
te da la URL de esta PC y la URL para otros dispositivos (con PIN). Pruébala abriendo
`http://127.0.0.1:8765` en el navegador de esa misma Windows.

## 4. Que arranque solo al prender la PC

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\edi.ps1 install-task
```

Esto crea una Tarea Programada de Windows ("EDI") que arranca el servidor cada vez que
inicias sesión. Como es una PC dedicada, conviene además:

- **Activar inicio de sesión automático** (sin pedir contraseña al prender): busca
  "netplwiz" en el menú de inicio → desmarca "Los usuarios deben escribir su nombre y
  contraseña..." → aplica con la cuenta que uses.
- En **Configuración → Sistema → Energía**, pon que nunca se vaya a dormir ni apague la
  pantalla (en una torre/mini-PC esto no gasta casi nada extra).
- En el **BIOS/UEFI**, si la placa lo permite, activa "Restaurar el último estado" o
  "Power On after power loss", para que si hay un corte de luz la PC vuelva a prender sola.

## 5. Comandos del día a día

```powershell
scripts\windows\edi.ps1 status     # ¿está corriendo?
scripts\windows\edi.ps1 logs       # ver el log en vivo
scripts\windows\edi.ps1 restart
scripts\windows\edi.ps1 stop
scripts\windows\edi.ps1 rebuild    # después de que yo cambie dependencias
scripts\windows\edi.ps1 test       # corre las pruebas
```

(Puedes omitir el `powershell -ExecutionPolicy Bypass -File` de ejemplos anteriores una
vez que estés parado en la carpeta y uses siempre `scripts\windows\edi.ps1 <comando>`.)

## 6. Actualizar cuando yo te pase cambios nuevos

```powershell
git pull
scripts\windows\edi.ps1 rebuild
```

## Notas

- **Tailscale** (acceso desde fuera de tu red) no está incluido todavía en este script de
  Windows — el de la Mac usa comandos específicos de macOS. Si lo quieres en el Windows
  dime y lo armamos aparte; mientras tanto, dentro de tu Wi-Fi ya funciona con
  `https://IP-de-esta-PC:8766` (pide PIN).
- Si `edi.ps1` se queja de política de ejecución, es normal: Windows bloquea scripts por
  default. El `-ExecutionPolicy Bypass` en cada llamado (o en la tarea programada, que ya
  lo trae) lo resuelve sin tener que cambiar nada a nivel sistema.
