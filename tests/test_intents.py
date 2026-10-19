from datetime import datetime

from edi.intents import detect

NOW = datetime(2026, 10, 19, 10, 0)  # lunes 10:00


def t(text):
    return detect(text, NOW)


def test_recordatorio_con_hora():
    i = t("EDI, recuérdame pagar la luz mañana a las 5")
    assert i.name == "add_task" and i.text == "pagar la luz"
    assert i.when == datetime(2026, 10, 20, 17, 0)


def test_recordatorio_relativo():
    i = t("recuérdame en media hora sacar la ropa")
    assert i.when == datetime(2026, 10, 19, 10, 30) and i.text == "sacar la ropa"


def test_dia_de_la_semana():
    i = t("agrega tarea entregar reporte el viernes a las 10 de la mañana")
    assert i.when == datetime(2026, 10, 23, 10, 0)


def test_tengo_que():
    i = t("tengo que ir al banco mañana")
    assert i.name == "add_task" and i.text == "ir al banco"


def test_nota_y_busqueda():
    assert t("recuerda que el wifi está en el cajón").name == "add_note"
    i = t("qué te dije sobre el wifi")
    assert i.name == "recall" and "wifi" in i.text


def test_correo_y_resumen():
    assert t("Oye EDI, ¿tengo correos nuevos?").name == "mail"
    assert t("dame mi resumen").name == "briefing"


def test_completar_por_numero():
    i = t("ya terminé la tarea 3")
    assert i.name == "complete" and i.ref == 3


def test_chat_libre():
    assert t("cuál es la capital de Francia").name == "chat"
