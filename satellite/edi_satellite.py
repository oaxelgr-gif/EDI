#!/usr/bin/env python3
"""EDI · satélite (frente 8, v0.9)

Programa chiquito que corre EN ESTE equipo (p. ej. tu Mac) para que el cerebro de EDI, aunque viva
centralizado en otra máquina (tu "server"), pueda leer, resumir, proponer cambios y correr comandos
aprobados también aquí. Sólo usa la librería estándar de Python — nada que instalar.

Reglas de seguridad, sin excepción:
  - Cada petición debe traer la clave secreta exacta (cabecera X-EDI-Secret) configurada abajo.
  - SÓLO puede leer/escribir dentro de UNA carpeta (`folder` en config.json). Nada de "../" ni rutas
    fuera de ahí.
  - SÓLO puede correr los comandos que tú listaste en `commands` (config.json), por su nombre exacto.
    Si el cerebro de EDI pide un comando que no está en esa lista, aquí se rechaza — así de simple.
  - Nunca escribe nada "de verdad": lo que EDI guarda aquí siempre es un archivo nuevo junto al
    original (sufijo "_EDI"), igual que ya hace con los archivos locales del server.

Uso:
    python3 edi_satellite.py --config config.json

Ver LEEME.md en esta misma carpeta para la guía paso a paso (incluye cómo dejarlo prendido solo).
"""
from __future__ import annotations

import argparse
import hmac
import json
import shlex
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

MAX_READ = 300_000      # ~300 KB: de sobra para código/texto, protege RAM en equipos chicos
MAX_WRITE = 500_000
RUN_TIMEOUT = 60

CFG: dict = {}
BASE: Path


def log(msg: str) -> None:
    print(f"[edi-satellite] {msg}", flush=True)


def _safe(rel: str) -> Path:
    """Igual que files._safe() del server: nunca deja salir de la carpeta autorizada."""
    rel = (rel or "").lstrip("/\\")
    p = (BASE / rel).resolve()
    if BASE not in p.parents and p != BASE:
        raise PermissionError(f"{rel} está fuera de la carpeta autorizada")
    return p


class Handler(BaseHTTPRequestHandler):
    server_version = "EDISatellite/0.9"

    def log_message(self, fmt, *args):  # silencia el log por defecto de http.server; usamos el nuestro
        pass

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self) -> bool:
        got = self.headers.get("X-EDI-Secret", "")
        return hmac.compare_digest(got, CFG.get("secret", ""))

    def do_GET(self):
        if not self._authed():
            return self._json(401, {"ok": False, "error": "clave secreta inválida"})
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/health":
            return self._json(200, {"ok": True, "name": CFG.get("name", "satélite"),
                                    "folder": str(BASE), "folder_label": CFG.get("folder_label", "")})
        if u.path == "/files":
            rel = (qs.get("path") or [""])[0]
            try:
                d = _safe(rel)
            except PermissionError as e:
                return self._json(400, {"ok": False, "error": str(e)})
            if not d.exists() or not d.is_dir():
                d = BASE
            out = []
            for p in sorted(d.rglob("*")):
                if p.name.startswith(".") or any(part.startswith(".") for part in p.relative_to(BASE).parts):
                    continue
                if p.is_file():
                    out.append({"name": p.name, "rel": str(p.relative_to(BASE)), "size": p.stat().st_size,
                               "is_dir": False})
            return self._json(200, {"ok": True, "entries": out[:500]})
        if u.path == "/read":
            rel = (qs.get("path") or [""])[0]
            try:
                p = _safe(rel)
            except PermissionError as e:
                return self._json(400, {"ok": False, "error": str(e)})
            if not p.exists() or not p.is_file():
                return self._json(404, {"ok": False, "error": "no existe"})
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")[:MAX_READ]
            except Exception as e:
                return self._json(400, {"ok": False, "error": f"no pude leerlo: {e}"})
            return self._json(200, {"ok": True, "content": text, "truncated": p.stat().st_size > MAX_READ})
        return self._json(404, {"ok": False, "error": "ruta desconocida"})

    def do_POST(self):
        if not self._authed():
            return self._json(401, {"ok": False, "error": "clave secreta inválida"})
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw or b"{}")
        except Exception:
            return self._json(400, {"ok": False, "error": "JSON inválido"})
        u = urlparse(self.path)

        if u.path == "/write":
            rel = body.get("path") or ""
            content = body.get("content") or ""
            if len(content) > MAX_WRITE:
                return self._json(400, {"ok": False, "error": "el archivo es demasiado grande"})
            try:
                p = _safe(rel)
            except PermissionError as e:
                return self._json(400, {"ok": False, "error": str(e)})
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
            except Exception as e:
                return self._json(400, {"ok": False, "error": f"no pude guardarlo: {e}"})
            log(f"escribí {rel}")
            return self._json(200, {"ok": True})

        if u.path == "/run":
            name = (body.get("cmd") or "").strip()
            cmds: dict = CFG.get("commands") or {}
            if name not in cmds:
                return self._json(403, {"ok": False, "error": "comando no aprobado", "allowed": list(cmds)})
            try:
                args = shlex.split(cmds[name])
                r = subprocess.run(args, cwd=str(BASE), capture_output=True, text=True, timeout=RUN_TIMEOUT)
                out = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
                log(f"corrí «{name}» (código {r.returncode})")
                return self._json(200, {"ok": r.returncode == 0, "code": r.returncode, "output": out[:6000]})
            except subprocess.TimeoutExpired:
                return self._json(200, {"ok": False, "code": -1, "output": f"tardó más de {RUN_TIMEOUT}s, lo corté"})
            except Exception as e:
                return self._json(200, {"ok": False, "code": -1, "output": str(e)})

        return self._json(404, {"ok": False, "error": "ruta desconocida"})


def main():
    global CFG, BASE
    ap = argparse.ArgumentParser(description="EDI · satélite")
    ap.add_argument("--config", default=str(Path(__file__).parent / "config.json"))
    args = ap.parse_args()
    cfg_path = Path(args.config)
    if not cfg_path.exists():
        log(f"No encuentro {cfg_path}. Copia config.example.json a config.json y edítalo primero.")
        sys.exit(1)
    CFG = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not CFG.get("secret") or CFG["secret"] == "CAMBIA_ESTO":
        log("Pon una clave secreta real en config.json antes de arrancar (no uses el valor de ejemplo).")
        sys.exit(1)
    BASE = Path(CFG.get("folder") or ".").expanduser().resolve()
    BASE.mkdir(parents=True, exist_ok=True)
    port = int(CFG.get("port", 8790))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    log(f"«{CFG.get('name', 'satélite')}» escuchando en :{port} · carpeta autorizada: {BASE}")
    log(f"Comandos aprobados: {', '.join(CFG.get('commands', {}).keys()) or '(ninguno)'}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
