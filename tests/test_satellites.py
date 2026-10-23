"""v0.9 (frente 8): EDI leyendo/programando también en otros dispositivos (satélites)."""
import importlib.util
import sys
from pathlib import Path

from edi import agent, config, db, files, satellites


def _fresh(tmp_path, monkeypatch, name="data"):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / f"{name}.sqlite3")
    db.init()


# ---------------- lado servidor: resolver qué dispositivo mencionó el usuario ----------------
def test_find_device_exacto_y_aproximado(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d1")
    db.add_satellite("mi mac", "http://127.0.0.1:8790", "sekret")
    assert satellites.find_device("mi mac")["name"] == "mi mac"
    assert satellites.find_device("en mi mac")["name"] == "mi mac"  # frase completa, no sólo el nombre


def test_find_device_sin_registrados_regresa_none(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d2")
    assert satellites.find_device("mi mac") is None
    assert satellites.device_names() == ""


def test_find_device_hint_vacio_o_generico_no_inventa(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d3")
    db.add_satellite("mi mac", "http://127.0.0.1:8790", "sekret")
    assert satellites.find_device("") is None
    assert satellites.find_device("el servidor") is None  # "servidor" está en la lista de genéricos


# ---------------- ping: nunca finge que conectó si no pudo ----------------
def test_ping_clave_mala_da_mensaje_claro(tmp_path, monkeypatch):
    class FakeResp:
        status_code = 401
        def json(self): return {}
    monkeypatch.setattr(satellites.httpx, "get", lambda *a, **k: FakeResp())
    ok, msg = satellites.ping({"url": "http://x:1", "secret": "mala", "name": "mi mac"})
    assert not ok and "clave" in msg.lower()


def test_ping_sin_conexion_da_mensaje_claro(tmp_path, monkeypatch):
    import httpx as httpx_mod
    def boom(*a, **k): raise httpx_mod.ConnectError("no")
    monkeypatch.setattr(satellites.httpx, "get", boom)
    ok, msg = satellites.ping({"url": "http://x:1", "secret": "s", "name": "mi mac"})
    assert not ok and "conectar" in msg.lower()


# ---------------- _device_action: nunca pretende haberlo hecho sin dispositivo vivo ----------------
def test_device_action_sin_dispositivos_abre_ajustes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d4")
    r = agent._device_action("device_summary", {"device": "mi mac"}, "", "resume el pdf en mi mac", 1)
    assert r["action"]["tab"] == "satellites"


def test_device_action_dispositivo_no_registrado_pregunta(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d5")
    db.add_satellite("mi mac", "http://127.0.0.1:8790", "sekret")
    r = agent._device_action("device_summary", {"device": "la laptop vieja de otro planeta"}, "", "x", 1)
    assert "¿en cuál" in r["reply"].lower() or "mi mac" in r["reply"]


def test_device_action_apagado_no_finge(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d6")
    db.add_satellite("mi mac", "http://127.0.0.1:1", "sekret")
    monkeypatch.setattr(satellites, "ping", lambda sat: (False, "No pude conectar."))
    r = agent._device_action("device_run", {"device": "mi mac", "text": "pytest"}, "pytest", "corre pytest en mi mac", 1)
    assert "no pude conectar" in r["reply"].lower()


def test_device_run_comando_no_aprobado(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d7")
    db.add_satellite("mi mac", "http://127.0.0.1:1", "sekret")
    monkeypatch.setattr(satellites, "ping", lambda sat: (True, "ok"))
    class FakeResp:
        status_code = 403
        def json(self): return {"allowed": ["pytest"]}
    monkeypatch.setattr(satellites.httpx, "post", lambda *a, **k: FakeResp())
    r = agent._device_action("device_run", {"device": "mi mac", "text": "rm -rf /"}, "rm -rf /", "borra todo en mi mac", 1)
    assert "no está en la lista" in r["reply"].lower()
    assert "pytest" in r["reply"]


# ---------------- edición remota: confirmar antes de escribir, nunca pisa el original ----------------
def test_propose_and_apply_edit_remoto_nunca_pisa_original(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d8")
    sid = db.add_satellite("mi mac", "http://127.0.0.1:1", "sekret")
    sat = db.get_satellite(sid)
    monkeypatch.setattr(satellites, "read_remote", lambda sat, rel, limit=20000: "contenido viejo")
    monkeypatch.setattr(satellites.providers, "chat", lambda *a, **k: ("contenido nuevo", "Stub"))
    r = satellites.propose_edit(sat, "notas/plan.txt", "mejora el plan", session_id=1)
    assert r["intent"] == "file_edit"
    eid = r["data"]["file_edit_id"]
    written = {}
    monkeypatch.setattr(satellites, "write_remote", lambda sat, rel, content: written.update(rel=rel, content=content))
    out = files.apply_edit(eid)  # el despacho files.apply_edit -> satellites.apply_edit debe activarse solo
    assert out["intent"] == "file_edit"
    assert written["rel"] == "notas/plan_EDI.txt"   # nunca el nombre original
    assert written["content"] == "contenido nuevo"


def test_discard_edit_remoto_no_escribe_nada(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "d9")
    sid = db.add_satellite("mi mac", "http://127.0.0.1:1", "sekret")
    eid = db.add_file_edit(1, "a.txt", "write", "x", "diff", "nuevo", satellite_id=sid)
    called = {}
    monkeypatch.setattr(satellites, "write_remote", lambda *a, **k: called.setdefault("hit", True))
    files.discard_edit(eid)
    assert "hit" not in called
    assert db.get_file_edit(eid)["status"] == "discarded"


# ---------------- lado satélite: aislamiento de carpeta y lista blanca de comandos ----------------
def _load_satellite_module():
    repo_root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("edi_satellite", repo_root / "satellite" / "edi_satellite.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["edi_satellite"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_satelite_safe_bloquea_salir_de_la_carpeta(tmp_path):
    mod = _load_satellite_module()
    mod.BASE = (tmp_path / "autorizada").resolve()
    mod.BASE.mkdir()
    (mod.BASE / "ok.txt").write_text("hola")
    assert mod._safe("ok.txt") == mod.BASE / "ok.txt"
    for bad in ("../fuera.txt", "../../etc/passwd"):
        try:
            mod._safe(bad)
            assert False, f"{bad} debió rechazarse"
        except PermissionError:
            pass
