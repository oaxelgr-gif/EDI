# ============================================================
#  EDI - control central para Windows (modo NATIVO, sin Docker: ~80-150 MB de RAM)
#  Uso: powershell -ExecutionPolicy Bypass -File scripts\windows\edi.ps1 [start|stop|restart|status|logs|rebuild|test|install-task|uninstall-task]
#  Pensado para una PC dedicada de 24/7 con poca RAM: nada de Docker Desktop/WSL2.
# ============================================================
param(
  [Parameter(Position=0)]
  [string]$Cmd = "start"
)

$ErrorActionPreference = "Stop"
$EdiDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $EdiDir

$Data   = Join-Path $EdiDir "data"
$Rt     = Join-Path $EdiDir ".runtime"
$SrvLog = Join-Path $Data "edi-server.log"
$PidF   = Join-Path $Data "edi.pid"
$Uv     = Join-Path $Rt "uv.exe"
$Venv   = Join-Path $EdiDir ".venv"
$Py     = Join-Path $Venv "Scripts\python.exe"
$ReqHash = Join-Path $Venv ".req-hash"

New-Item -ItemType Directory -Force -Path $Data, $Rt | Out-Null

function Say($msg) { Write-Host "> $msg" }

# ---- uv (gestor de Python de un solo archivo) + Python 3.12 + dependencias ----
function Ensure-Uv {
  if (Test-Path $Uv) { return }
  Say "Descargando uv (solo la primera vez)..."
  $env:UV_INSTALL_DIR = $Rt
  $env:UV_NO_MODIFY_PATH = "1"
  Invoke-Expression (Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1")
  # el instalador oficial deja uv.exe en $Rt porque UV_INSTALL_DIR lo apunta ahi
  if (-not (Test-Path $Uv)) { throw "No quedo instalado uv en $Rt. Revisa tu conexion a internet." }
}

function Ensure-Python {
  Ensure-Uv
  $env:UV_PYTHON_INSTALL_DIR = Join-Path $Rt "python"
  $env:UV_CACHE_DIR = Join-Path $Rt "cache"
  if (-not (Test-Path $Py)) {
    Say "Preparando Python 3.12 (solo la primera vez)..."
    & $Uv venv --python 3.12 $Venv
  }
  $want = (Get-FileHash (Join-Path $EdiDir "app\requirements.txt") -Algorithm SHA256).Hash
  $have = if (Test-Path $ReqHash) { Get-Content $ReqHash -Raw } else { "" }
  if ($want -ne $have) {
    Say "Instalando componentes de EDI (1-2 min la primera vez)..."
    & $Uv pip install --python $Py -r (Join-Path $EdiDir "app\requirements.txt")
    Set-Content -Path $ReqHash -Value $want -NoNewline
    & $Uv cache clean 2>$null
  }
}

function Ensure-Node {
  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    Write-Warning "No encuentro 'node' en el PATH. El puente de WhatsApp no va a poder arrancar hasta que instales Node.js 22 LTS (https://nodejs.org) y abras una terminal nueva."
  }
}

# ---- .env: carga CLAVE=valor como variables de entorno del proceso ----
function Load-Env {
  $envFile = Join-Path $EdiDir ".env"
  if (-not (Test-Path $envFile)) { return }
  Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
      $k = $Matches[1]; $v = $Matches[2].Trim('"').Trim("'")
      [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
    }
  }
}

function Lan-Ip {
  try {
    (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp,Manual -ErrorAction Stop |
      Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notmatch "Loopback|vEthernet" } |
      Select-Object -First 1 -ExpandProperty IPAddress)
  } catch { "" }
}

function Set-EnvFile($key, $val) {
  $envFile = Join-Path $EdiDir ".env"
  if (-not (Test-Path $envFile)) { New-Item -ItemType File -Path $envFile | Out-Null }
  $lines = Get-Content $envFile
  $found = $false
  $lines = $lines | ForEach-Object {
    if ($_ -match "^$key=") { $found = $true; "$key=$val" } else { $_ }
  }
  if (-not $found) { $lines += "$key=$val" }
  Set-Content -Path $envFile -Value $lines
}

function Is-Running {
  if (-not (Test-Path $PidF)) { return $false }
  $procId = Get-Content $PidF -ErrorAction SilentlyContinue
  if (-not $procId) { return $false }
  return [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
}

function Is-Healthy {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 2 -UseBasicParsing
    return $r.StatusCode -eq 200
  } catch { return $false }
}

function Start-Server {
  Load-Env
  $env:EDI_DATA_DIR    = $Data
  $env:EDI_CONFIG_DIR  = Join-Path $EdiDir "config"
  $env:EDI_HTTP_HOST   = "127.0.0.1"
  $env:EDI_HTTP_PORT   = "8765"
  $env:EDI_HTTPS_PORT  = "8766"
  $env:EDI_LAN_HOST    = Lan-Ip
  $env:PYTHONPATH      = Join-Path $EdiDir "app"
  $env:PYTHONDONTWRITEBYTECODE = "1"
  $env:PYTHONUNBUFFERED = "1"
  Remove-Item Env:EDI_WHATSAPP_URL -ErrorAction SilentlyContinue   # modo nativo: EDI arranca el puente el solo

  if ((Test-Path $SrvLog) -and ((Get-Item $SrvLog).Length -gt 2MB)) {
    Move-Item -Force $SrvLog "$SrvLog.old"
  }
  $p = Start-Process -FilePath $Py -ArgumentList "-m","edi.serve" `
        -WorkingDirectory (Join-Path $EdiDir "app") `
        -RedirectStandardOutput $SrvLog -RedirectStandardError "$SrvLog.err" `
        -WindowStyle Hidden -PassThru
  Set-Content -Path $PidF -Value $p.Id
}

function Stop-Server {
  if (Is-Running) {
    $procId = Get-Content $PidF
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
  }
  Remove-Item $PidF -ErrorAction SilentlyContinue
  # por si el puente de WhatsApp (node) se quedo colgado de una corrida anterior
  Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "whatsapp.*index\.mjs" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

switch ($Cmd) {
  "start" {
    if (Is-Healthy) { Say "EDI ya estaba en linea -> http://127.0.0.1:8765"; break }
    if (-not (Test-Path (Join-Path $EdiDir "config\accounts.yaml"))) {
      Copy-Item (Join-Path $EdiDir "config\accounts.example.yaml") (Join-Path $EdiDir "config\accounts.yaml") -ErrorAction SilentlyContinue
    }
    Ensure-Python
    Ensure-Node
    Stop-Server
    Say "Arrancando EDI..."
    Start-Server
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
      Start-Sleep -Milliseconds 500
      if (Is-Healthy) { $ok = $true; break }
      if (-not (Is-Running)) { break }
    }
    if ($ok) {
      $ip = Lan-Ip
      Say "EDI en linea."
      Say "  Esta PC:        http://127.0.0.1:8765"
      if ($ip) { Say "  Otros equipos:  https://${ip}:8766  (pide PIN)" }
    } else {
      Write-Error "El servidor no arranco. Revisa $SrvLog"
    }
  }
  "stop"    { Stop-Server; Say "EDI apagado." }
  "restart" { & $PSCommandPath stop; & $PSCommandPath start }
  "status"  {
    if (Is-Running) { Say "Proceso $(Get-Content $PidF) activo" } else { Say "Apagado" }
    if (Is-Healthy) { Say "Responde en /api/health" }
  }
  "logs"    { Get-Content -Path $SrvLog -Wait -Tail 100 }
  "rebuild" { Stop-Server; Remove-Item -Recurse -Force $Venv -ErrorAction SilentlyContinue; & $PSCommandPath start }
  "test"    {
    Ensure-Python
    & $Uv pip install --python $Py -q pytest
    Push-Location $EdiDir
    $env:PYTHONPATH = Join-Path $EdiDir "app"
    & $Py -m pytest -q tests
    Pop-Location
  }
  "install-task" {
    $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
                 -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" start"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName "EDI" -Action $action -Trigger $trigger -Settings $settings -Description "Arranca EDI al iniciar sesion de Windows" -Force | Out-Null
    Say "Tarea programada 'EDI' creada: arrancara solo cada vez que inicies sesion en Windows."
    Say "Tip: en esta PC, activa el inicio de sesion automatico (sin pedir contraseña) para que EDI arranque sin que nadie este presente."
  }
  "uninstall-task" {
    Unregister-ScheduledTask -TaskName "EDI" -Confirm:$false -ErrorAction SilentlyContinue
    Say "Tarea programada 'EDI' eliminada."
  }
  default { Write-Host "Uso: edi.ps1 [start|stop|restart|status|logs|rebuild|test|install-task|uninstall-task]" }
}
