"""v0.9: CRUD de dispositivos satélite (Ajustes → Dispositivos) + prueba de conexión."""
import json

from fastapi import APIRouter, HTTPException

from .. import db, satellites as sat_mod

router = APIRouter(prefix="/api/satellites", tags=["satelites"])


def _public(s: dict) -> dict:
    cmds = json.loads(s.get("commands") or "[]")
    return {"id": s["id"], "name": s["name"], "url": s["url"], "folder_label": s["folder_label"],
            "commands": cmds, "enabled": bool(s["enabled"]), "has_secret": bool(s["secret"])}


@router.get("")
def list_all():
    return [_public(s) for s in db.list_satellites()]


@router.post("")
def create(body: dict):
    name = (body.get("name") or "").strip()
    url = (body.get("url") or "").strip()
    secret = (body.get("secret") or "").strip()
    if not name or not url or not secret:
        raise HTTPException(400, "Falta nombre, URL o clave secreta.")
    if db.get_satellite_by_name(name):
        raise HTTPException(409, f"Ya tienes un dispositivo llamado «{name}».")
    cmds = body.get("commands") or []
    if isinstance(cmds, str):
        cmds = [c.strip() for c in cmds.split(",") if c.strip()]
    sid = db.add_satellite(name, url, secret, body.get("folder_label", ""), json.dumps(cmds))
    return _public(db.get_satellite(sid))


@router.patch("/{sid}")
def update(sid: int, body: dict):
    s = db.get_satellite(sid)
    if not s:
        raise HTTPException(404, "Ese dispositivo ya no existe.")
    f = {}
    for k in ("name", "url", "folder_label"):
        if k in body and body[k] is not None:
            f[k] = str(body[k]).strip()
    if body.get("secret"):   # vacío = no cambiar, igual que las contraseñas de los proveedores
        f["secret"] = body["secret"].strip()
    if "commands" in body:
        cmds = body["commands"]
        if isinstance(cmds, str):
            cmds = [c.strip() for c in cmds.split(",") if c.strip()]
        f["commands"] = json.dumps(cmds)
    if "enabled" in body:
        f["enabled"] = 1 if body["enabled"] else 0
    db.update_satellite(sid, **f)
    return _public(db.get_satellite(sid))


@router.delete("/{sid}")
def delete(sid: int):
    return {"ok": db.delete_satellite(sid)}


@router.post("/test")
def test_unsaved(body: dict):
    """Prueba sin guardar: el formulario manda name/url/secret tal cual."""
    row = {"name": body.get("name") or "satélite", "url": (body.get("url") or "").strip(),
           "secret": (body.get("secret") or "").strip()}
    if not row["url"] or not row["secret"]:
        return {"ok": False, "message": "Falta la URL o la clave secreta."}
    ok, msg = sat_mod.ping(row)
    return {"ok": ok, "message": msg}


@router.post("/{sid}/test")
def test_saved(sid: int):
    s = db.get_satellite(sid)
    if not s:
        raise HTTPException(404, "Ese dispositivo ya no existe.")
    ok, msg = sat_mod.ping(s)
    return {"ok": ok, "message": msg}
