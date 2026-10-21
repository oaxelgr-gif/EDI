"""Slack — menciones y mensajes directos, enviar mensajes por voz (con confirmación) y
mensajes marcados con ✅ como pendientes de trabajo.

Usa un token de USUARIO (xoxp-…) de una app propia en https://api.slack.com/apps con permisos:
  search:read, reactions:read, users:read, channels:read, groups:read, im:read, im:history,
  channels:history, groups:history, chat:write, im:write
Si tu Slack lo administra otra persona, pídele que apruebe la app (es gratis)."""
import time
import unicodedata

from .base import Connector, ConnectorError, tally, upsert_task

API = "https://slack.com/api/"


_USERS: dict[int, dict] = {}   # caché de personas por conexión (sólo en memoria)


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


class SlackConnector(Connector):
    kind = "slack"
    label = "Slack"
    help = ("Token de usuario (xoxp-) de una app propia. EDI te lee menciones y mensajes directos, envía mensajes cuando "
            "lo confirmas y convierte en pendiente cualquier mensaje al que reacciones con ✅.")
    help_url = "https://api.slack.com/apps"
    FIELDS = [
        {"key": "secret", "label": "Token de usuario", "type": "password", "required": True, "target": "secret", "placeholder": "xoxp-…"},
        {"key": "emoji", "label": "Reacción que crea un pendiente", "type": "text", "placeholder": "white_check_mark", "target": "config",
         "help": "Nombre del emoji sin dos puntos. Por defecto ✅ (white_check_mark)."},
    ]

    def call(self, method: str, http: str = "GET", **params) -> dict:
        tok = self.row.get("secret") or ""
        if not tok:
            raise ConnectorError("Falta el token de Slack.")
        hdr = {"Authorization": f"Bearer {tok}"}
        r = self.http(http, API + method, headers=hdr, **({"params": params} if http == "GET" else {"json": params}))
        j = r.json()
        if not j.get("ok"):
            err = j.get("error", "error")
            hints = {"missing_scope": f"falta el permiso {j.get('needed', '')} en la app de Slack",
                     "not_allowed_token_type": "este método necesita un token de usuario (xoxp-), no de bot",
                     "invalid_auth": "token inválido", "channel_not_found": "no encontré ese canal o persona",
                     "not_in_channel": "no eres miembro de ese canal"}
            raise ConnectorError(f"Slack: {hints.get(err, err)}.")
        return j

    def me(self) -> dict:
        if not self.cfg.get("me"):
            a = self.call("auth.test")
            self.save_cfg(me={"id": a["user_id"], "user": a.get("user"), "team": a.get("team")})
        return self.cfg["me"]

    def test(self) -> dict:
        self.cfg.pop("me", None)
        m = self.me()
        return {"ok": True, "message": f"Conectado a {m['team']} como {m['user']}."}

    # ---------- ✅ → pendientes ----------
    def sync(self) -> dict:
        emoji = (self.cfg.get("emoji") or "white_check_mark").strip(":")
        me = self.me()["id"]
        res = []
        try:
            j = self.call("reactions.list", user=me, count=50, full="true")
        except ConnectorError as e:
            raise ConnectorError(f"{e} (para ✅ → pendiente hace falta el permiso reactions:read)")
        for it in j.get("items", []):
            if it.get("type") != "message":
                continue
            msg = it.get("message", {})
            if not any(r.get("name") == emoji and me in r.get("users", []) for r in msg.get("reactions", [])):
                continue
            text = " ".join((msg.get("text") or "").split())
            key = f"{it.get('channel')}:{msg.get('ts')}"
            res.append(upsert_task(self, key, text=(text[:120] + ("…" if len(text) > 120 else "")) or "Mensaje de Slack",
                                   notes=text[:2000], link=msg.get("permalink", ""), ext_status="marcado con ✅", source="slack"))
        return tally(res)

    # ---------- lectura ----------
    def _users(self) -> dict:
        cache = _USERS.get(self.id)
        if cache and time.time() - cache.get("t", 0) < 3600:
            return cache["map"]
        users, cursor = {}, None
        for _ in range(10):
            j = self.call("users.list", limit=200, **({"cursor": cursor} if cursor else {}))
            for u in j.get("members", []):
                if u.get("deleted") or u.get("is_bot"):
                    continue
                p = u.get("profile", {})
                users[u["id"]] = p.get("display_name") or p.get("real_name") or u.get("name")
            cursor = j.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        _USERS[self.id] = {"t": time.time(), "map": users}
        return users

    def mentions(self, n: int = 8) -> list[dict]:
        me = self.me()["id"]
        j = self.call("search.messages", query=f"<@{me}>", sort="timestamp", count=n)
        users = self._users()
        out = []
        import re
        clean = lambda tx: re.sub(r"<@(\w+)>", lambda mm: "@" + users.get(mm.group(1), "alguien"), " ".join((tx or "").split()))
        for m in j.get("messages", {}).get("matches", []):
            out.append({"from": users.get(m.get("user"), m.get("username", "alguien")), "text": clean(m.get("text"))[:300],
                        "channel": (m.get("channel") or {}).get("name", ""), "ts": float(m.get("ts", 0)), "link": m.get("permalink", "")})
        return out

    def direct_messages(self, n_convs: int = 8) -> list[dict]:
        me = self.me()["id"]
        users = self._users()
        ims = self.call("users.conversations", types="im", limit=100).get("channels", [])
        out = []
        for im in ims[:40]:
            if len(out) >= n_convs:
                break
            h = self.call("conversations.history", channel=im["id"], limit=1).get("messages", [])
            if h and h[0].get("user") != me and time.time() - float(h[0].get("ts", 0)) < 3 * 86400:
                out.append({"from": users.get(im.get("user"), "alguien"), "text": " ".join((h[0].get("text") or "").split())[:300],
                            "ts": float(h[0]["ts"])})
        return sorted(out, key=lambda x: -x["ts"])

    # ---------- enviar ----------
    def find_target(self, name: str) -> dict:
        q = _fold(name).lstrip("#@ ").strip()
        if name.strip().startswith("#") or q.startswith("canal "):
            q = q.removeprefix("canal ").strip()
            chans = self.call("users.conversations", types="public_channel,private_channel", limit=200).get("channels", [])
            hit = next((c for c in chans if _fold(c["name"]) == q), None) or next((c for c in chans if q in _fold(c["name"])), None)
            if not hit:
                raise ConnectorError(f"No encontré el canal #{q} entre tus canales.")
            return {"channel": hit["id"], "name": f"#{hit['name']}"}
        users = self._users()
        scored = []
        for uid, nm in users.items():
            n = _fold(nm)
            sc = 3 if n == q else 2 if n.startswith(q) else 1 if q in n or all(w in n for w in q.split()) else 0
            if sc:
                scored.append((sc, uid, nm))
        if not scored:
            raise ConnectorError(f"No encontré a {name} en Slack.")
        scored.sort(key=lambda x: -x[0])
        if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][0] < 3:
            raise ConnectorError("Hay varias personas con ese nombre en Slack: " + ", ".join(s[2] for s in scored[:4]) + ". Dímelo completo.")
        uid, nm = scored[0][1], scored[0][2]
        ch = self.call("conversations.open", http="POST", users=uid)["channel"]["id"]
        return {"channel": ch, "name": nm}

    def send(self, channel: str, text: str) -> None:
        self.call("chat.postMessage", http="POST", channel=channel, text=text)

    def briefing(self) -> str:
        try:
            n = len([m for m in self.mentions(10) if time.time() - m["ts"] < 86400])
            return f"{n} mención{'es' if n != 1 else ''} en Slack" if n else ""
        except Exception:
            return ""
