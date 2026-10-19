"""OAuth2 para Outlook/Hotmail (Microsoft ya no acepta contraseña normal por IMAP).

Uso (una sola vez por cuenta):
    ./scripts/edi.sh outlook tu_correo@outlook.com
Te mostrará un código; ábrelo en https://microsoft.com/devicelogin y autoriza.
El token se guarda en data/ms_token_cache.json y se renueva solo.
"""
import sys

import msal

from . import config

SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All"]
AUTHORITY = "https://login.microsoftonline.com/consumers"  # cuentas personales


def _app():
    cache = msal.SerializableTokenCache()
    if config.MS_TOKEN_CACHE.exists():
        cache.deserialize(config.MS_TOKEN_CACHE.read_text())
    app = msal.PublicClientApplication(config.MS_CLIENT_ID, authority=AUTHORITY, token_cache=cache)
    return app, cache


def _save(cache):
    if cache.has_state_changed:
        config.MS_TOKEN_CACHE.write_text(cache.serialize())


def get_access_token(username: str):
    if not config.MS_CLIENT_ID:
        return None
    app, cache = _app()
    accounts = [a for a in app.get_accounts() if a.get("username", "").lower() == username.lower()]
    if not accounts:
        return None
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save(cache)
    return result.get("access_token") if result else None


def authorize(username: str):
    if not config.MS_CLIENT_ID:
        print("Primero pon MS_CLIENT_ID en .env (ver docs/CUENTAS_CORREO.md).")
        sys.exit(1)
    app, cache = _app()
    flow = app.initiate_device_flow(scopes=SCOPES, login_hint=username)
    if "user_code" not in flow:
        print("No se pudo iniciar el flujo:", flow)
        sys.exit(1)
    print("\n" + flow["message"] + "\n")
    result = app.acquire_token_by_device_flow(flow)
    _save(cache)
    if "access_token" in result:
        print(f"✅ Cuenta {username} autorizada. EDI ya puede leerla.")
    else:
        print("❌ Error:", result.get("error_description"))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m edi.oauth_ms correo@outlook.com")
        sys.exit(1)
    authorize(sys.argv[1])
