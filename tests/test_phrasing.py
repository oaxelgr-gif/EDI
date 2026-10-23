"""v0.7: variedad de frases (0 tokens) para que EDI no repita siempre lo mismo."""
from datetime import datetime, timedelta

from edi import agent, db, phrasing


def test_no_repite_dos_veces_seguidas():
    opciones = ["a", "b", "c"]
    vistos = [phrasing.pick_for(99, "cat_x", opciones) for _ in range(20)]
    for anterior, siguiente in zip(vistos, vistos[1:]):
        assert anterior != siguiente


def test_sesiones_distintas_no_se_pisan():
    phrasing._last.clear()
    a = phrasing.pick_for(1, "cat_y", ["x", "y"])
    # fuerzo la misma elección en otra sesión: no debe fallar ni heredar el estado de la sesión 1
    phrasing._last[(2, "cat_y")] = None
    b = phrasing.pick_for(2, "cat_y", ["x", "y"])
    assert a in ("x", "y") and b in ("x", "y")


def test_guardar_tarea_usa_banco_de_frases(tmp_path, monkeypatch):
    monkeypatch.setenv("EDI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("EDI_CONFIG_DIR", str(tmp_path / "config"))
    import importlib
    import edi.config as config
    importlib.reload(config)
    importlib.reload(db)
    db.init()
    r1 = agent._save_task("comprar leche", None)
    assert "comprar leche" in r1
    assert any(r1.startswith(tpl.split("{")[0]) for tpl in phrasing.TASK_SAVED)
    r2 = agent._save_task("comprar leche", None)  # duplicado
    assert any(r2.startswith(tpl.split("{")[0]) for tpl in phrasing.TASK_DUP)


def test_guardar_tarea_con_fecha_no_duplica_espacios():
    when = datetime.now() + timedelta(days=1)
    out = agent._save_task("llamar al doctor", when)
    assert "  " not in out  # sin doble espacio entre el texto y el recordatorio
