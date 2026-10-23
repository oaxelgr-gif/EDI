# EDI · satélite (frente 8)

Esto convierte este equipo (tu Mac, o cualquier otro) en un dispositivo donde EDI también puede leer,
resumir, proponer cambios de archivos y correr comandos aprobados — aunque el cerebro de EDI (la IA,
la memoria, los pendientes) corra centralizado en otra máquina (tu "server").

No instala nada: es un solo archivo de Python usando sólo su librería estándar.

## 1. Elige la carpeta y la clave

```bash
cd satellite
cp config.example.json config.json
```

Edita `config.json`:
- `"name"` — cómo le vas a decir a EDI ("en mi mac", "en la laptop"...). Debe ser único.
- `"secret"` — cualquier clave larga y al azar. Genera una fácil con:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(24))"
  ```
- `"folder"` — la ÚNICA carpeta que EDI podrá tocar aquí. Por defecto una carpeta nueva y vacía
  (`~/Documents/EDI-files-mac`); cámbiala por la carpeta real que quieras darle, por ejemplo la de un
  proyecto tuyo (`~/Documents/PharmaControl`). EDI nunca sale de ahí.
- `"commands"` — los únicos comandos que EDI podrá pedir que corras aquí, con el nombre que tú
  elijas a la izquierda y el comando real a la derecha. Si no quieres darle ninguno, deja `{}`.

## 2. Pruébalo a mano primero

```bash
python3 edi_satellite.py --config config.json
```

Debe decir `escuchando en :8790`. Déjalo corriendo y, desde otra terminal:

```bash
curl -H "X-EDI-Secret: TU_CLAVE" http://127.0.0.1:8790/health
```

Si contesta `{"ok": true, ...}`, ya funciona. Ctrl+C para pararlo.

## 3. Regístralo en EDI

En EDI, ve a **Ajustes → Satélites → Agregar dispositivo** y pon:
- Nombre: el mismo `"name"` de tu config.json.
- URL: `http://TU_IP_LOCAL:8790` (o tu IP/nombre de Tailscale si vas a hablarle desde otra red, p. ej.
  `http://100.x.x.x:8790`).
- Clave secreta: la misma que pusiste en `"secret"`.
- Comandos aprobados: los mismos nombres (no los comandos reales) que pusiste en `"commands"`.

Dale "Probar" — debe decir "Conectado".

## 4. Que se quede prendido solo

Desde la raíz del repo:

```bash
./scripts/05_instalar_satelite.sh
```

Esto instala un LaunchAgent (`com.edi.satellite`) para que el satélite arranque solo al iniciar
sesión y se reinicie si se cae. Para quitarlo: `./scripts/05_instalar_satelite.sh uninstall`.

## Ya con esto puedes decirle a EDI

- "resume el PDF de la actividad que tengo en mi mac"
- "en mi mac, corrígeme el bug de X en el archivo tal" (te propone el cambio, tú confirmas, y EDI
  guarda el resultado junto al original con el sufijo `_EDI`, nunca lo pisa)
- "corre las pruebas en mi mac" (si registraste un comando `pytest`)

Si el satélite está apagado o la clave no coincide, EDI te lo dice claro en vez de fingir que lo hizo.
