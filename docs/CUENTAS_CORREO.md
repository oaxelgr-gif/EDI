# Conectar tus cuentas de correo a EDI

EDI lee por **IMAP en modo sólo lectura**: no borra, no envía y no marca como leído.
Nunca uses tu contraseña normal: cada proveedor te da una **contraseña de aplicación**.

Pasos generales:
1. Obtén la contraseña de aplicación (abajo).
2. Pégala en `.env` en la variable de esa cuenta (ej. `GMAIL_PERSONAL_PASS=abcdabcdabcdabcd`).
3. En `config/accounts.yaml` pon tu correo y `enabled: true`.
4. `./scripts/edi.sh restart` y di "revisa mis correos".

## Gmail / Google Workspace (escuela o trabajo)
1. Activa la verificación en 2 pasos: https://myaccount.google.com/security
2. Crea la contraseña: https://myaccount.google.com/apppasswords → nombre "EDI" → copia las 16 letras.
3. IMAP ya viene activado en Gmail. En cuentas de escuela/trabajo, el administrador puede tener bloqueadas las contraseñas de aplicación; si no aparece la opción, usa reenvío (ver abajo).

## Yahoo
Seguridad de la cuenta → "Generar contraseña de aplicación": https://login.yahoo.com/account/security

## iCloud
https://account.apple.com → Inicio de sesión y seguridad → Contraseñas específicas de apps → Generar.
Usuario: tu correo `@icloud.com` (o `@me.com`).

## Outlook / Hotmail / Live — dos opciones

Microsoft ya no permite contraseña normal por IMAP en cuentas personales.

### Opción A (más fácil, recomendada): reenviar a Gmail
Outlook.com → Configuración → Correo → Reenvío → activar y poner tu Gmail. EDI lo verá dentro de tu cuenta Gmail.

### Opción B: OAuth2 directo
1. Entra a https://entra.microsoft.com con tu cuenta → Aplicaciones → Registros de aplicaciones → **Nuevo registro**.
   - Nombre: EDI · Tipos de cuenta: **Sólo cuentas personales de Microsoft**.
2. En la app → Autenticación → **Permitir flujos de clientes públicos: Sí**.
3. Permisos de API → Agregar → Microsoft Graph → Delegados → `IMAP.AccessAsUser.All` y `offline_access`.
4. Copia el **Id. de aplicación (cliente)** a `.env` → `MS_CLIENT_ID=...`
5. Autoriza una vez:
   ```bash
   ./scripts/edi.sh outlook tu_correo@outlook.com
   ```
   Abre el enlace que aparece, escribe el código y acepta. El token se renueva solo (`data/ms_token_cache.json`).

## Otro servidor IMAP (trabajo, hosting)
```yaml
- name: Trabajo
  provider: imap
  host: mail.miempresa.com
  port: 993
  user: yo@miempresa.com
  password_env: TRABAJO_PASS
  folders: [INBOX]
```
Y en `.env`: `TRABAJO_PASS=...`

## Problemas comunes
| Mensaje | Solución |
|---|---|
| `Falta la variable X en .env` | El nombre en `password_env` debe existir en `.env`. |
| `AUTHENTICATIONFAILED` / `Invalid credentials` | Contraseña de aplicación mal copiada (quita espacios) o 2 pasos no activado. |
| `Falta autorizar ...` (Outlook) | Ejecuta `./scripts/edi.sh outlook correo`. |
| Una cuenta falla | Las demás siguen funcionando; EDI te dice cuál no pudo abrir. |
