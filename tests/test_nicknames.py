"""v0.7: EDI aprende solo los apodos de WhatsApp ('apa' -> 'Papá') al confirmar a quién te referías,
sin que tengas que decirle 'recuerda que...'."""
from edi import db, drafts, whatsapp


def _fresh_pool(monkeypatch):
    whatsapp._pool_cache["t"] = 1e18
    whatsapp._pool_cache["v"] = [
        {"jid": "a@s", "name": "Papá", "saved": True, "last": {"text": "hola", "ts": 1}},
        {"jid": "c@s", "name": "Alan", "saved": True, "last": None},
        {"jid": "d@s", "name": "Ana", "saved": True, "last": None},
    ]


def _fresh_db(tmp_path, monkeypatch, name="data"):
    from edi import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / f"{name}.sqlite3")
    db.init()


def test_aprende_y_resuelve_apodo_ruidoso(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    _fresh_pool(monkeypatch)

    # alias que no se parece a ningún contacto: no hay nada que ofrecer todavía
    assert whatsapp.find_contacts("compadre") == []

    # el usuario confirma a quién se refería (como al elegir en la desambiguación)
    drafts._learn_nickname("compadre", "Papá")
    assert db.get_nickname(whatsapp.alias_key("compadre")) == "Papá"

    # la próxima vez que diga lo mismo (igual o con mayúsculas/puntuación distinta), resuelve directo
    assert [c["name"] for c in whatsapp.find_contacts("compadre")] == ["Papá"]
    assert [c["name"] for c in whatsapp.find_contacts("¿Compadre?")] == ["Papá"]
    assert [c["name"] for c in whatsapp.find_contacts("de mi compadre")] == ["Papá"]


def test_no_aprende_si_el_alias_ya_es_el_nombre_real(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch, "data2")
    drafts._learn_nickname("Papá", "Papá")
    assert db.get_nickname("papa") is None


def test_forget_nickname(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch, "data3")
    db.remember_nickname("apa", "Papá")
    assert db.get_nickname("apa") == "Papá"
    assert db.forget_nickname("apa") is True
    assert db.get_nickname("apa") is None
