"""v0.8: el 'cerebro' de EDI (agent._brain) entiende frases coloquiales con IA en vez de reglas fijas,
la entrevista inicial de perfil, generar imágenes y editar archivos con confirmación."""
import json

from edi import agent, config, db, drafts, files, profile, providers


def _fresh(tmp_path, monkeypatch, name="data"):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / f"{name}.sqlite3")
    db.init()


def test_brain_entiende_tarea_coloquial(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: (json.dumps({"action": "add_task", "text": "pagar la luz", "when": ""}), "Stub"))
    r = agent._brain("ando saturado, no se me vaya a olvidar lo de la luz", 1, db.now())
    assert r["intent"] == "add_task"
    assert "pagar la luz" in r["reply"]
    assert db.list_tasks()


def test_brain_chat_normal_una_sola_llamada(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    calls = []
    def fake_chat(*a, **k):
        calls.append(1)
        return json.dumps({"action": "chat", "reply": "La capital de Francia es París."}), "Stub"
    monkeypatch.setattr(providers, "chat", fake_chat)
    r = agent._brain("cual es la capital de Francia", 1, db.now())
    assert r["reply"] == "La capital de Francia es París."
    assert len(calls) == 1  # una sola llamada a la IA, no dos


def test_brain_genera_imagen(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "generate_image", lambda prompt, **k: (b"\x89PNG-fake", None))
    r = agent._generate_image("un gato astronauta", 1)
    assert r["intent"] == "image"
    assert r["data"]["image_url"].startswith("/api/images/")
    saved = config.IMAGES_DIR / r["data"]["image_url"].split("/")[-1]
    assert saved.read_bytes() == b"\x89PNG-fake"


def test_brain_imagen_sin_llave_abre_ajustes(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(providers, "generate_image", lambda prompt, **k: (None, "sin_llave_gemini"))
    r = agent._generate_image("algo", 1)
    assert r["action"]["open"] == "settings"


def test_onboarding_pregunta_una_vez_y_aprende(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert profile.needs_onboarding()
    r1 = agent._onboard_followup("hola", 1)
    assert r1 and "?" in r1["reply"]
    r2 = agent._onboard_followup("me llamo Francisco", 1)
    assert r2 and db.get_profile().get("nombre") == "me llamo Francisco"
    r3 = agent._onboard_followup("programador freelance", 1)
    r4 = agent._onboard_followup("EDI y mi estadía", 1)
    assert not profile.needs_onboarding()
    # ya no vuelve a preguntar en esta sesión
    assert agent._onboard_followup("hola de nuevo", 1) is None


def test_onboarding_se_puede_saltar(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "data2")
    agent._onboard_followup("hola", 1)
    r = agent._onboard_followup("paso", 1)
    assert r is not None  # sigue con la siguiente pregunta, sin trabarse


def test_file_edit_confirmar_y_cancelar(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "data3")
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "nota.txt").write_text("hola")
    monkeypatch.setattr(config, "FILES_DIR", files_dir)
    monkeypatch.setattr(providers, "chat", lambda *a, **k: ("hola mundo", "Stub"))

    files.propose_edit("nota.txt", "agrega mundo", session_id=1)
    r = agent._file_edit_followup("sí", 1)
    assert r["intent"] == "file_edit"
    assert (files_dir / "nota_EDI.txt").read_text() == "hola mundo"

    files.propose_edit("nota.txt", "otra cosa", session_id=1)
    r2 = agent._file_edit_followup("cancela", 1)
    assert "no hago" in r2["reply"].lower()


def test_brain_wa_read_who_basura_pregunta_en_vez_de_buscar(tmp_path, monkeypatch):
    """v0.8.1: si el modelo gratis mete basura en 'who' (p. ej. repite pedazos del prompt como
    'leer mensajes' o la frase entera), EDI debe preguntar '¿de quién?' en vez de buscarlo entre
    tus contactos y contestar con nombres absurdos."""
    _fresh(tmp_path, monkeypatch, "data5")
    monkeypatch.setattr(drafts, "_wa_ready", lambda: True)
    called = {}
    monkeypatch.setattr(drafts.whatsapp, "find_contacts", lambda who: called.setdefault("who", who) or [])
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: (json.dumps({"action": "wa_read", "who": "leer mensajes"}), "Stub"))
    r = agent._brain("qué tal los mensajes", 1, db.now())
    assert r["intent"] == "ask_who"
    assert "quién" in r["reply"].lower()
    assert "who" not in called  # nunca llegó a buscar "leer mensajes" como si fuera un nombre


def test_brain_wa_read_who_valido_si_busca(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "data6")
    monkeypatch.setattr(drafts, "_wa_ready", lambda: True)
    monkeypatch.setattr(drafts.whatsapp, "find_contacts", lambda who: [{"jid": "1", "name": "Papá"}] if who == "papá" else [])
    monkeypatch.setattr(drafts.whatsapp, "messages", lambda jid, n: [{"text": "hola", "fromMe": False}])
    monkeypatch.setattr(drafts.whatsapp, "read", lambda jid: None)
    monkeypatch.setattr(providers, "chat",
                        lambda *a, **k: (json.dumps({"action": "wa_read", "who": "papá"}), "Stub"))
    r = agent._brain("qué tal los mensajes de papá", 1, db.now())
    assert r["intent"] == "wa_read"
    assert "Papá" in r["reply"]


def test_profile_learn_from_text_cero_tokens(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "data4")
    db.set_profile("nombre", "Francisco")  # ya onboardeado
    db.set_profile("ocupacion", "x")
    db.set_profile("proyectos", "y")
    assert profile.learn_from_text("ahora soy consultor independiente") == "ocupacion"
    assert db.get_profile()["ocupacion"] == "consultor independiente"
