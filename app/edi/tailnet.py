"""Tailscale: usar EDI desde cualquier lugar (datos móviles, otra red) sin abrir puertos del módem.

- Detecta la IP 100.x y el nombre MagicDNS de la Mac con la CLI de Tailscale.app.
- Si se puede, publica EDI con «tailscale serve» → https://<mac>.<tailnet>.ts.net con certificado válido
  (sin el aviso de «conexión no privada»). Sólo lo ven tus dispositivos de Tailscale.
- Si Tailscale no está instalado o está apagado, todo devuelve vacío y EDI funciona igual que siempre.

Desde la terminal (lo usa scripts/edi.sh al arrancar):
    python -m edi.tailnet env      → líneas CLAVE=valor para .env
    python -m edi.tailnet off      → quita la publicación de «tailscale serve»
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

CLI_CANDIDATES = (
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",   # app de la Mac (App Store o descarga)
    "/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale",  # Homebrew / CLI instalada aparte
)
SERVE_PORT = int(os.getenv("EDI_TS_PORT", "8768") or 8768)   # puerto local (sólo 127.0.0.1) al que apunta «serve»
DIRECT_PORT = int(os.getenv("EDI_HTTPS_PORT", "8766") or 8766)
_cache: dict = {"t": 0.0, "v": None}


def cli() -> str:
    for p in (os.getenv("TAILSCALE_CLI", "").strip(), *CLI_CANDIDATES, shutil.which("tailscale") or ""):
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return ""


def _run(args: list[str], timeout: float = 6) -> tuple[int, str]:
    exe = cli()
    if not exe:
        return 127, "Tailscale no está instalado"
    try:
        p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = e.stdout or b""
        out = out.decode(errors="ignore") if isinstance(out, bytes) else out
        return 124, out
    except OSError as e:
        return 126, str(e)


def _run_until(args: list[str], timeout: float, stop: str) -> tuple[int, str]:
    """Como _run, pero corta en cuanto la salida contiene `stop` (p. ej. el enlace para activar HTTPS),
    para no esperar a que «tailscale serve» se canse de esperar."""
    exe = cli()
    if not exe:
        return 127, "Tailscale no está instalado"
    try:
        p = subprocess.Popen([exe, *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True)
    except OSError as e:
        return 126, str(e)
    out: list[str] = []
    t = threading.Thread(target=lambda: [out.append(line) for line in p.stdout], daemon=True)
    t.start()
    end = time.time() + timeout
    while time.time() < end and p.poll() is None and not re.search(stop, "".join(out)):
        time.sleep(0.1)
    if p.poll() is None:
        p.kill()
        p.wait(timeout=2)
        t.join(timeout=1)
        return 124, "".join(out)
    t.join(timeout=1)
    return p.returncode, "".join(out)


def status() -> dict:
    """{installed, running, ip, dns, tailnet, error}. No lanza excepciones."""
    st = {"installed": bool(cli()), "running": False, "ip": "", "dns": "", "tailnet": "", "error": ""}
    if not st["installed"]:
        return st
    code, out = _run(["status", "--json"])
    if code != 0:
        st["error"] = _clean(out) or "Tailscale no respondió"
        return st
    try:
        j = json.loads(out[out.index("{"):])
    except ValueError:
        st["error"] = "No entendí la respuesta de Tailscale"
        return st
    st["running"] = j.get("BackendState") == "Running"
    me = j.get("Self") or {}
    st["dns"] = (me.get("DNSName") or "").rstrip(".")
    st["tailnet"] = ((j.get("CurrentTailnet") or {}).get("Name") or "")
    if not ((j.get("CurrentTailnet") or {}).get("MagicDNSEnabled", True)):
        st["dns"] = ""   # sin MagicDNS el nombre no resuelve en el iPhone
    ips = [ip for ip in (me.get("TailscaleIPs") or []) if "." in ip]
    if st["running"]:
        code, out = _run(["ip", "-4"])
        first = out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""
        st["ip"] = first if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", first) else (ips[0] if ips else "")
    else:
        st["error"] = "Tailscale está instalado pero apagado o sin sesión"
    return st


def serve_status() -> dict:
    """{url, ours, other}: a dónde apunta hoy «tailscale serve» en el puerto 443."""
    code, out = _run(["serve", "status", "--json"])
    res = {"url": "", "ours": False, "other": False}
    if code != 0 or "{" not in out:
        return res
    try:
        j = json.loads(out[out.index("{"):])
    except ValueError:
        return res
    for hostport, cfg in (j.get("Web") or {}).items():
        host, _, port = hostport.rpartition(":")
        if port != "443":
            continue
        proxy = str(((cfg.get("Handlers") or {}).get("/") or {}).get("Proxy", ""))
        if proxy.rstrip("/").endswith(f":{SERVE_PORT}"):
            res.update(url=f"https://{host}", ours=True)
        elif proxy:
            res["other"] = True
    return res


def enable_serve() -> dict:
    """Publica EDI con certificado válido. {ok, url, enable_url, error}. No toca otra publicación tuya en 443."""
    cur = serve_status()
    if cur["ours"]:
        return {"ok": True, "url": cur["url"], "enable_url": "", "error": ""}
    if cur["other"]:
        return {"ok": False, "url": "", "enable_url": "", "error": "El puerto 443 de Tailscale ya lo usa otra app; EDI usará el acceso directo."}
    code, out = _run_until(["serve", "--bg", f"http://127.0.0.1:{SERVE_PORT}"], 15, r"https://login\.tailscale\.com/\S+\s")
    m = re.search(r"https://login\.tailscale\.com/\S+", out)
    cur = serve_status()
    if cur["ours"]:
        return {"ok": True, "url": cur["url"], "enable_url": "", "error": ""}
    if m:  # la primera vez Tailscale pide activar HTTPS/Serve en tu cuenta
        _run(["serve", "--https=443", "off"], timeout=6)   # no dejar una petición colgada
        return {"ok": False, "url": "", "enable_url": m.group(0).rstrip(".,"), "error": "Activa HTTPS en tu cuenta de Tailscale"}
    return {"ok": False, "url": "", "enable_url": "", "error": _clean(out) or "tailscale serve no respondió"}


def disable_serve() -> bool:
    if serve_status()["ours"]:
        return _run(["serve", "--https=443", "off"], timeout=8)[0] == 0
    return True


def info(fresh: bool = False) -> dict:
    """Estado para la interfaz (con caché de 30 s): lo leído de la CLI + lo guardado en .env."""
    if not fresh and _cache["v"] and time.time() - _cache["t"] < 30:
        return _cache["v"]
    st = status()
    serve_url = os.getenv("EDI_TS_URL", "").strip()
    if st["running"] and cli():
        s = serve_status()
        serve_url = s["url"] if s["ours"] else ""
    host = st["dns"] or st["ip"] or os.getenv("EDI_TS_DNS", "").strip() or os.getenv("EDI_TS_HOST", "").strip()
    st.update(serve_url=serve_url, direct_url=f"https://{host}:{DIRECT_PORT}" if host else "",
              enable_url=os.getenv("EDI_TS_ENABLE_URL", "").strip())
    st["url"] = st["serve_url"] or st["direct_url"]
    st["valid_cert"] = bool(st["serve_url"])
    _cache.update(t=time.time(), v=st)
    return st


def env_values(serve: bool = True) -> dict:
    """Valores para .env (vacíos si no hay Tailscale: así EDI sigue como hoy)."""
    st = status()
    vals = {"EDI_TS_HOST": st["ip"], "EDI_TS_DNS": st["dns"], "EDI_TS_URL": "", "EDI_TS_ENABLE_URL": ""}
    if st["running"] and serve and os.getenv("EDI_TS_SERVE", "1").strip() not in ("0", "no", "false"):
        pending = os.getenv("EDI_TS_ENABLE_URL", "").strip()
        # Si ya sabemos que falta activar HTTPS en la cuenta, no lo reintentamos en cada arranque:
        # se reintenta con «Ya lo activé» (Ajustes → Dispositivos) o con «edi.sh tailscale on».
        r = ({"url": serve_status()["url"] if serve_status()["ours"] else "", "enable_url": pending}
             if pending else enable_serve())
        vals["EDI_TS_URL"] = r["url"]
        vals["EDI_TS_ENABLE_URL"] = r["enable_url"]
    return vals


def _clean(out: str) -> str:
    return " ".join((out or "").split())[:200]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "env"
    if cmd == "env":
        for k, v in env_values(serve="--no-serve" not in sys.argv).items():
            print(f"{k}={v}")
    elif cmd == "off":
        print("ok" if disable_serve() else "error")
    elif cmd == "status":
        print(json.dumps(info(fresh=True), ensure_ascii=False, indent=2))
    else:
        print("Uso: python -m edi.tailnet [env|off|status]")
        sys.exit(1)
