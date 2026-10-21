"""GitHub — PRs que esperan tu revisión e issues asignados se vuelven pendientes de trabajo.
También: estado de tus PRs y del último build (GitHub Actions) de los repos que elijas.
Token: https://github.com/settings/tokens (clásico con 'repo' o fine-grained con lectura de PRs/Issues/Actions).
Sirve también para Lovable: Lovable sincroniza cada proyecto con un repositorio de GitHub."""
from .base import Connector, ConnectorError, tally, upsert_task

API = "https://api.github.com"


class GitHubConnector(Connector):
    kind = "github"
    label = "GitHub"
    help = ("Un token personal. EDI trae los PRs que te piden revisar y los issues asignados como pendientes de trabajo, "
            "y te dice cómo van tus PRs y builds. Tus proyectos de Lovable aparecen aquí si están enlazados a GitHub.")
    help_url = "https://github.com/settings/tokens"
    FIELDS = [
        {"key": "secret", "label": "Token personal", "type": "password", "required": True, "target": "secret",
         "placeholder": "ghp_… o github_pat_…"},
        {"key": "base_url", "label": "Servidor (sólo GitHub Enterprise)", "type": "url", "placeholder": "https://api.github.com",
         "target": "base_url", "help": "Déjalo vacío para github.com."},
        {"key": "repos", "label": "Repos para vigilar builds", "type": "text", "placeholder": "usuario/edi, empresa/app-web",
         "target": "config", "help": "Separados por coma. Para «¿pasó el build de …?» y el resumen del día."},
        {"key": "track", "label": "Traer como pendientes", "type": "select", "target": "config",
         "options": [["both", "Revisiones de PR e issues asignados"], ["reviews", "Sólo revisiones de PR"], ["issues", "Sólo issues asignados"]]},
    ]

    @property
    def api(self) -> str:
        return self.base or API

    def req(self, method: str, path: str, **kw):
        tok = self.row.get("secret") or ""
        if not tok:
            raise ConnectorError("Falta el token de GitHub.")
        r = self.http(method, self.api + path, headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                                                         "X-GitHub-Api-Version": "2022-11-28"}, **kw)
        return r.json() if r.content else {}

    def search(self, q: str, n: int = 50) -> list[dict]:
        return self.req("GET", "/search/issues", params={"q": q, "per_page": n, "sort": "updated"}).get("items", [])

    def test(self) -> dict:
        u = self.req("GET", "/user")
        self.save_cfg(login=u.get("login"))
        reviews = len(self.search("is:open is:pr review-requested:@me archived:false", 30))
        mine = len(self.search("is:open is:pr author:@me archived:false", 30))
        return {"ok": True, "message": f"Conectado como {u.get('login')}. {reviews} PR por revisar y {mine} PR tuyos abiertos."}

    @staticmethod
    def _key(it: dict) -> str:
        repo = it["repository_url"].split("/repos/")[-1]
        return f"{repo}#{it['number']}"

    def sync(self) -> dict:
        track = self.cfg.get("track") or "both"
        res, seen = [], set()
        if track in ("both", "reviews"):
            for it in self.search("is:open is:pr review-requested:@me archived:false"):
                k = self._key(it); seen.add(k)
                res.append(upsert_task(self, k, text=f"Revisar PR {k}: {it['title']}", link=it["html_url"],
                                       notes=(it.get("body") or "")[:1500], ext_status="revisión pendiente", source="github"))
        if track in ("both", "issues"):
            for it in self.search("is:open is:issue assignee:@me archived:false"):
                k = self._key(it); seen.add(k)
                labels = ", ".join(l["name"] for l in it.get("labels", []))
                res.append(upsert_task(self, k, text=f"{k}: {it['title']}", link=it["html_url"], notes=(it.get("body") or "")[:1500],
                                       priority="alta" if any(w in labels.lower() for w in ("urgent", "urgente", "critical", "bug")) else "normal",
                                       ext_status=labels or "abierto", source="github"))
        # Lo que ya no aparece (revisado, cerrado o reasignado) se marca hecho
        from .. import db
        for t in db.rows("SELECT * FROM tasks WHERE conn_id=? AND done=0", (self.id,)):
            if t["ext_key"] and t["ext_key"] not in seen:
                db.update_task(t["id"], done=1, ext_status="cerrado o revisado")
                res.append("done")
        return tally(res)

    # ---------- consultas por voz ----------
    def my_prs(self) -> list[dict]:
        out = []
        for it in self.search("is:open is:pr author:@me archived:false", 20):
            out.append({"key": self._key(it), "title": it["title"], "url": it["html_url"], "draft": it.get("draft", False)})
        return out

    def reviews(self) -> list[dict]:
        return [{"key": self._key(it), "title": it["title"], "url": it["html_url"]}
                for it in self.search("is:open is:pr review-requested:@me archived:false", 20)]

    def repos(self) -> list[str]:
        return [r.strip() for r in (self.cfg.get("repos") or "").split(",") if "/" in r]

    def last_build(self, repo: str) -> dict | None:
        runs = self.req("GET", f"/repos/{repo}/actions/runs", params={"per_page": 1}).get("workflow_runs", [])
        if not runs:
            return None
        r = runs[0]
        return {"repo": repo, "name": r.get("name"), "status": r.get("status"), "conclusion": r.get("conclusion"),
                "branch": r.get("head_branch"), "url": r.get("html_url")}

    def briefing(self) -> str:
        parts = []
        try:
            n = len(self.reviews())
            if n:
                parts.append(f"{n} PR esperando tu revisión")
            failed = [b["repo"].split("/")[-1] for b in (self.last_build(r) for r in self.repos()[:4]) if b and b["conclusion"] == "failure"]
            if failed:
                parts.append("falló el build de " + ", ".join(failed))
        except Exception:
            pass
        return " y ".join(parts)
