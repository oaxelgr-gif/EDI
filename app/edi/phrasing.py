"""Variedad para las respuestas de 0 tokens (reglas, sin IA): así EDI no contesta siempre con la
misma frase exacta. No cambia QUÉ dice (los datos son los mismos), sólo CÓMO lo dice.
Elegido con random real (no una rotación fija) para que se sienta vivo; nunca se repite dos veces
seguidas en la misma conversación gracias a `pick_for`."""
import random

_last: dict[tuple[int, str], str] = {}   # (session_id, categoría) -> última frase usada, para no repetirla


def pick_for(session_id: int | None, category: str, options: list[str]) -> str:
    key = (session_id or 0, category)
    choices = [o for o in options if o != _last.get(key)] or options
    choice = random.choice(choices)
    _last[key] = choice
    return choice


TASK_SAVED = ["Listo, anotado en {where}: {text}{when}", "Hecho, ya quedó en {where}: {text}{when}",
              "Va, lo agrego a {where}: {text}{when}", "De acuerdo, ahí te lo dejo en {where}: {text}{when}",
              "Apuntado en {where}: {text}{when}"]
TASK_SAVED_REMINDER = [" Te aviso {when}.", " Ahí te aviso {when}.", " Te lo recuerdo {when}."]
TASK_DUP = ["Ya lo tenía en tus pendientes: {text}{when}", "Eso ya estaba anotado: {text}{when}",
            "Ese ya lo tengo: {text}{when}"]
TASK_COMPLETE = ["Hecho. Taché: {text}.", "Listo, lo marco como hecho: {text}.", "Va, tachado: {text}.",
                 "De una, ya quedó hecho: {text}."]
TASK_COMPLETE_FAIL = ["No encontré ese pendiente. Dime «mis tareas» para revisarlos.",
                      "No ubico cuál es. Pídeme «mis tareas» y lo vemos juntos.",
                      "Ese no lo tengo registrado. Revisa «mis tareas» y me dices cuál."]
TASK_DELETED = ["Pendiente eliminado.", "Listo, lo quité de tus pendientes.", "Va, ya lo borré."]
TASK_DELETE_FAIL = ["Dime el número del pendiente que quieres borrar.", "¿Cuál número es? Dime «mis tareas» si no te acuerdas."]
TASK_WHEN_Q = ["¿Para cuándo te recuerdo {text}? Por ejemplo «mañana a las 3», o di «sin fecha».",
               "¿Cuándo le aviso? Puedes decir «el viernes a las 10» o «sin fecha».",
               "¿A qué hora te lo recuerdo? Di «mañana a las 5» o «sin fecha» si sólo lo quieres anotado."]
TASK_WHEN_BAD = ["No entendí la fecha. Dime por ejemplo «mañana a las 3 de la tarde», «el viernes a las 10» o «sin fecha».",
                 "Esa fecha no la agarré bien. Prueba con «mañana a las 5» o «el lunes a las 10», o di «sin fecha»."]
TASK_WHEN_CANCEL = ["Va, no lo anoto.", "Entendido, lo dejo sin guardar.", "De acuerdo, no lo agendo."]

NOTE_SAVED = ["Guardado en mi memoria: {text}.", "Listo, ya lo tengo guardado: {text}.", "Anotado para no olvidarlo: {text}.",
              "Va, eso ya quedó en mi memoria: {text}."]
NOTE_DUP = ["Eso ya lo tenía guardado: {text}.", "Ese dato ya lo tengo: {text}."]
NOTE_FORGOT = ["Lo olvidé.", "Listo, ya lo borré de mi memoria.", "Va, lo olvido."]
NOTE_FORGOT_FAIL = ["Dime el número de la nota.", "¿Cuál número es? Revisa «mis notas» si no te acuerdas."]

NO_PROVIDERS = ["Mis proveedores de IA no respondieron. Revisa tu conexión o las llaves en Ajustes.",
                "No logré conectar con ningún proveedor de IA ahora mismo. Checa tu internet o las llaves en Ajustes."]
