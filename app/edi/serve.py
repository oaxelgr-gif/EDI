"""Arranca EDI en dos puertos dentro del mismo proceso (comparten memoria y avisos en vivo):
  - 8000 HTTP  → sólo tu Mac (localhost:8765)
  - 8443 HTTPS → cualquier dispositivo de tu red (https://IP-de-tu-Mac:8766), protegido con PIN.
El certificado es autofirmado y se regenera solo si cambia la IP de la Mac."""
import asyncio
import datetime
import ipaddress
import logging
import os

import uvicorn

from . import config

log = logging.getLogger("edi.serve")
CERT = config.DATA_DIR / "tls" / "edi.crt"
KEY = config.DATA_DIR / "tls" / "edi.key"
STAMP = config.DATA_DIR / "tls" / "hosts.txt"


def ensure_cert() -> bool:
    lan = os.getenv("EDI_LAN_HOST", "").strip()
    hosts = sorted({"localhost", "127.0.0.1", *([lan] if lan else [])})
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


async def main():
    from .main import app
    http_host = os.getenv("EDI_HTTP_HOST", "0.0.0.0")
    http_port = int(os.getenv("EDI_HTTP_PORT", "8000"))
    https_port = int(os.getenv("EDI_HTTPS_PORT", "8443"))
    servers = [uvicorn.Server(uvicorn.Config(app, host=http_host, port=http_port, log_level="warning"))]
    if ensure_cert():
        servers.append(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=https_port, log_level="warning",
                                                     ssl_certfile=str(CERT), ssl_keyfile=str(KEY))))
    sc_port = int(os.getenv("EDI_SHORTCUT_PORT", "0") or 0)
    if sc_port:  # atajo de Siri desde el iPhone (sólo /api/shortcut con llave)
        servers.append(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=sc_port, log_level="warning")))
    # Un solo manejador de señales para todos los servidores
    for s in servers[1:]:
        s.install_signal_handlers = lambda: None
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
