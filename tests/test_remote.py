"""Acceso remoto: PIN con límite de intentos, dispositivos, Tailscale (simulado) y avisos "changed"."""
import asyncio
import hashlib
import hmac
import json
import os
import stat
import textwrap

import pytest
from fastapi.testclient import TestClient

from edi import db, live, security, tailnet
from edi.main import app

PHONE_UA = {"user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"}


@pytest.fixture(scope="module")
def mac():
    with TestClient(app) as c:   # http://testserver = la Mac
        yield c


def phone():
    return TestClient(app, base_url="https://testserver", headers=PHONE_UA)


@pytest.fixture(autouse=True)
def clean(mac):
    security.reset_attempts()
    security.logout_all()
    yield


def test_mac_sin_pin_y_celular_con_pin(mac):
    assert mac.get("/api/tasks").status_code == 200
    assert phone().get("/api/tasks").status_code == 401


def test_limite_de_intentos(mac):
    p, pin = phone(), security.get_pin()
    bad = "000000" if pin != "000000" else "111111"
    for left in (4, 3, 2, 1):
        r = p.post("/api/login", json={"pin": bad})
        assert r.status_code == 401 and r.json()["left"] == left
    r = p.post("/api/login", json={"pin": bad})
    assert r.status_code == 429 and r.json()["wait"] == 300
    assert p.post("/api/login", json={"pin": pin}).status_code == 429   # ni con el correcto durante la espera
    assert mac.get("/api/devices").json()["lock"] > 0


def test_dispositivos_y_cerrar_sesion_en_todos(mac):
    p = phone()
    assert p.post("/api/login", json={"pin": security.get_pin()}).status_code == 200
    assert p.get("/api/tasks").status_code == 200
    devs = mac.get("/api/devices/list").json()
    assert len(devs) == 1 and devs[0]["name"] == "iPhone · Safari" and devs[0]["via"] == "wifi"
    assert p.post("/api/devices/logout-all").status_code == 403          # sólo desde la Mac
    new = mac.post("/api/devices/logout-all").json()["pin"]
    assert len(new) == 6 and new == security.get_pin()
    assert p.get("/api/tasks").status_code == 401
    assert mac.get("/api/devices/list").json() == []


def test_quitar_un_dispositivo(mac):
    p = phone()
    p.post("/api/login", json={"pin": security.get_pin()})
    did = mac.get("/api/devices/list").json()[0]["id"]
    assert mac.delete(f"/api/devices/list/{did}").json()["ok"]
    assert p.get("/api/tasks").status_code == 401


def test_cookie_anterior_sigue_sirviendo(mac):
    secret = db.one("SELECT value FROM settings WHERE key='_secret'")["value"]
    legacy = hmac.new(secret.encode(), security.get_pin().encode(), hashlib.sha256).hexdigest()
    p = phone()
    p.cookies.set(security.COOKIE, legacy)
    r = p.get("/api/tasks")
    assert r.status_code == 200 and "." in r.cookies.get(security.COOKIE)
    assert len(mac.get("/api/devices/list").json()) == 1


def test_sin_tailscale_no_rompe(mac):
    d = mac.get("/api/devices?fresh=true").json()
    assert d["tailscale"]["installed"] is False and d["tailscale"]["url"] == ""
    assert mac.get("/api/devices/qr.svg?target=tailscale").status_code == 404
    assert tailnet.env_values() == {"EDI_TS_HOST": "", "EDI_TS_DNS": "", "EDI_TS_URL": "", "EDI_TS_ENABLE_URL": ""}


FAKE = textwrap.dedent("""\
    #!/bin/sh
    D="$(dirname "$0")"
    case "$1" in
      status) echo '{"BackendState":"Running","Self":{"DNSName":"mac.tail1.ts.net.","TailscaleIPs":["100.70.1.2"]},"CurrentTailnet":{"MagicDNSEnabled":true}}' ;;
      ip) echo 100.70.1.2 ;;
      serve)
        if [ "$2" = status ]; then
          if [ -f "$D/serve" ]; then echo "{\\"Web\\":{\\"mac.tail1.ts.net:443\\":{\\"Handlers\\":{\\"/\\":{\\"Proxy\\":\\"$(cat "$D/serve")\\"}}}}}"; else echo '{}'; fi
        elif [ "$2" = --bg ]; then echo "$3" > "$D/serve"; fi ;;
    esac
""")


def test_tailscale_simulado(tmp_path, monkeypatch):
    cli = tmp_path / "tailscale"
    cli.write_text(FAKE)
    cli.chmod(cli.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("TAILSCALE_CLI", str(cli))
    monkeypatch.delenv("EDI_TS_ENABLE_URL", raising=False)
    vals = tailnet.env_values()
    assert vals["EDI_TS_HOST"] == "100.70.1.2" and vals["EDI_TS_DNS"] == "mac.tail1.ts.net"
    assert vals["EDI_TS_URL"] == "https://mac.tail1.ts.net"
    assert (tmp_path / "serve").read_text().strip() == "http://127.0.0.1:8768"
    assert tailnet.disable_serve() is True


def test_cambios_avisan_changed():
    got = []

    async def run():
        live.bind(asyncio.get_running_loop(), got.append)
        tok = live.origin.set("tab-1")
        await asyncio.to_thread(db.add_task, "probar sincronización")
        await asyncio.to_thread(db.add_note, "una nota")
        live.origin.reset(tok)
        await asyncio.sleep(live.DEBOUNCE + 0.1)

    asyncio.run(run())
    assert got and got[-1]["type"] == "changed"
    assert set(got[-1]["kinds"]) >= {"tasks", "notes"} and got[-1]["origin"] == "tab-1"
    assert live.kinds_for_tables({"usage", "mail_seen", "notes_fts"}) == set()   # internas: sin aviso
