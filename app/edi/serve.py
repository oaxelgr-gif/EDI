"""Arranca EDI en varios puertos dentro del mismo proceso (comparten memoria y avisos en vivo):
  - HTTP  (EDI_HTTP_PORT)  → sólo tu Mac (localhost:8765), sin PIN
  - HTTPS (EDI_HTTPS_PORT) → otros dispositivos por Wi‑Fi o por la IP/nombre de Tailscale, con PIN
  - HTTP  (EDI_TS_PORT, sólo 127.0.0.1) → destino de «tailscale serve» (HTTPS válido de Tailscale), con PIN
  - HTTP  (EDI_SHORTCUT_PORT) → atajo de Siri, sólo /api/shortcut con llave
El certificado autofirmado incluye localhost, la IP del Wi‑Fi y la IP + nombre MagicDNS de Tailscale; se regenera
solo si cambian (al arrancar y cada 2 minutos mientras EDI está encendido, sin reiniciar)."""
import asyncio
import datetime
import ipaddress
import logging
import os
import subprocess
import sys

import uvicorn

from . import config

log = logging.getLogger("edi.serve")
CERT = config.DATA_DIR / "tls" / "edi.crt"
KEY = config.DATA_DIR / "tls" / "edi.key"
STAMP = config.DATA_DIR / "tls" / "hosts.txt"
ENV_FILE = config.DATA_DIR.parent / ".env"
WATCH_SECONDS = 120


def cert_hosts() -> list[str]:
    extra = [os.getenv(k, "").strip() for k in ("EDI_LAN_HOST", "EDI_TS_HOST", "EDI_TS_DNS")]
    return sorted({"localhost", "127.0.0.1", *[h for h in extra if h]})


def ensure_cert() -> bool:
    hosts = cert_hosts()
    if CERT.exists() and KEY.exists() and STAMP.exists() and STAMP.read_text() == ",".join(hosts):
        return True
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        log.warning("Sin 'cryptography': el acceso por red (HTTPS) queda desactivado")
        return False
    CERT.parent.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sans = []
    for h in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            sans.append(x509.DNSName(h))
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EDI"), x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EDI local")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    STAMP.write_text(",".join(hosts))
    log.info("Certificado HTTPS generado para %s", hosts)
    return True


# ---------------- vigilar cambios de red mientras EDI está encendido ----------------
def lan_ip() -> str:
    if sys.platform != "darwin":
        return os.getenv("EDI_LAN_HOST", "").strip()
    for i in ("en0", "en1", "en2", "en3", "en4"):
        try:
            ip = subprocess.run(["ipconfig", "getifaddr", i], capture_output=True, text=True, timeout=2).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            ip = ""
        if ip:
            return ip
    return ""


def save_env(values: dict):
    """Como set_env de scripts/edi.sh: reemplaza CLAVE=… en .env o la agrega al final."""
    if not ENV_FILE.exists():
        return
    lines = ENV_FILE.read_text().splitlines()
    for k, v in values.items():
        for i, line in enumerate(lines):
            if line.startswith(f"{k}="):
                lines[i] = f"{k}={v}"
                break
        else:
            lines.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(lines) + "\n")


def detect_network() -> dict:
    from . import tailnet
    vals = {"EDI_LAN_HOST": lan_ip()}
    st = tailnet.status()
    vals.update(EDI_TS_HOST=st["ip"], EDI_TS_DNS=st["dns"])
    came_up = st["running"] and not os.getenv("EDI_TS_HOST", "").strip()
    if came_up and os.getenv("EDI_TS_SERVE", "1").strip() not in ("0", "no", "false"):
        r = tailnet.enable_serve()   # Tailscale se encendió después que EDI (sólo se intenta una vez)
        vals.update(EDI_TS_URL=r["url"], EDI_TS_ENABLE_URL=r["enable_url"])
    elif not st["running"]:
        vals.update(EDI_TS_URL="")
    return vals


def apply_network(vals: dict, https_servers) -> bool:
    """Guarda lo que cambió y recarga el certificado en caliente. → True si hubo cambios."""
    changed = {k: v for k, v in vals.items() if os.getenv(k, "").strip() != (v or "")}
    if not changed:
        return False
    os.environ.update({k: v or "" for k, v in changed.items()})
    save_env(changed)
    log.info("Red cambió: %s", ", ".join(f"{k}={v or '—'}" for k, v in changed.items()))
    if ensure_cert():
        for s in https_servers:
            ctx = getattr(s.config, "ssl", None)
            if ctx is not None:
                ctx.load_cert_chain(str(CERT), str(KEY))   # las conexiones nuevas usan el certificado nuevo
    from . import live, tailnet
    tailnet.info(fresh=True)
    live.notify("devices")
    return True


async def watch_network(https_servers):
    while True:
        await asyncio.sleep(WATCH_SECONDS)
        try:
            vals = await asyncio.to_thread(detect_network)
            apply_network(vals, https_servers)
        except Exception as e:
            log.warning("watch_network: %s", e)


async def main():
    from .main import app
    http_host = os.getenv("EDI_HTTP_HOST", "0.0.0.0")
    http_port = int(os.getenv("EDI_HTTP_PORT", "8000"))
    https_port = int(os.getenv("EDI_HTTPS_PORT", "8443"))
    servers = [uvicorn.Server(uvicorn.Config(app, host=http_host, port=http_port, log_level="warning"))]
    https = []
    if ensure_cert():
        https.append(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=https_port, log_level="warning",
                                                   ssl_certfile=str(CERT), ssl_keyfile=str(KEY))))
        servers += https
    ts_port = int(os.getenv("EDI_TS_PORT", "0") or 0)
    if ts_port:  # «tailscale serve» entrega aquí (sólo desde esta Mac); el middleware exige PIN
        servers.append(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=ts_port, log_level="warning",
                                                     proxy_headers=False)))
    sc_port = int(os.getenv("EDI_SHORTCUT_PORT", "0") or 0)
    if sc_port:  # atajo de Siri desde el iPhone (sólo /api/shortcut con llave)
        servers.append(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=sc_port, log_level="warning")))
    # Un solo manejador de señales para todos los servidores
    for s in servers[1:]:
        s.install_signal_handlers = lambda: None
    tasks = [s.serve() for s in servers]
    if os.getenv("EDI_WATCH_NETWORK", "1") != "0":
        watcher = asyncio.ensure_future(watch_network(https))
        try:
            await asyncio.gather(*tasks)
        finally:
            watcher.cancel()
    else:
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
