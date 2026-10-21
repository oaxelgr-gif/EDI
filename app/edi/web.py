"""Herramientas en línea gratuitas y sin llaves:
  - Tipo de cambio: open.er-api.com
  - Clima: open-meteo.com (geocodificación + pronóstico)
  - Búsqueda web: DuckDuckGo (HTML) con respaldo en Wikipedia; lee las 2 primeras páginas
"""
import html as htmllib
import logging
import re
import unicodedata
from urllib.parse import parse_qs, unquote, urlparse

import httpx

log = logging.getLogger("edi.web")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/129.0 Safari/537.36", "Accept-Language": "es-MX,es;q=0.9"}

CURRENCIES = {
    "dolar canadiense": "CAD", "dolar": "USD", "dolares": "USD", "usd": "USD", "euro": "EUR", "euros": "EUR",
    "libra": "GBP", "yen": "JPY", "yuan": "CNY", "peso colombiano": "COP", "peso argentino": "ARS",
    "peso chileno": "CLP", "real": "BRL", "bitcoin": "BTC", "franco suizo": "CHF",
}
NAMES = {"USD": "el dólar", "EUR": "el euro", "GBP": "la libra esterlina", "JPY": "el yen", "CNY": "el yuan",
         "CAD": "el dólar canadiense", "COP": "el peso colombiano", "ARS": "el peso argentino",
         "CLP": "el peso chileno", "BRL": "el real", "CHF": "el franco suizo"}
WMO = {0: "despejado", 1: "mayormente despejado", 2: "parcialmente nublado", 3: "nublado", 45: "con niebla",
       48: "con niebla", 51: "con llovizna ligera", 53: "con llovizna", 55: "con llovizna intensa",
       61: "con lluvia ligera", 63: "con lluvia", 65: "con lluvia fuerte", 71: "con nieve ligera", 73: "con nieve",
       80: "con chubascos", 81: "con chubascos", 82: "con chubascos fuertes", 95: "con tormenta",
       96: "con tormenta y granizo", 99: "con tormenta y granizo"}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def _client():
    return httpx.Client(headers=UA, timeout=10, follow_redirects=True)


# ---------------- tipo de cambio ----------------
def find_currency(text: str) -> str | None:
    f = _fold(text)
    for k in sorted(CURRENCIES, key=len, reverse=True):
        if re.search(rf"\b{k}\b", f):
            return CURRENCIES[k]
    if re.search(r"tipo de cambio", f):
        return "USD"
    return None


def exchange(code: str) -> str:
    if code == "BTC":
        with _client() as c:
            j = c.get("https://api.coinbase.com/v2/prices/BTC-MXN/spot").json()
        return f"Un bitcoin vale alrededor de {float(j['data']['amount']):,.0f} pesos mexicanos."
    with _client() as c:
        j = c.get(f"https://open.er-api.com/v6/latest/{code}").json()
    mxn = j["rates"]["MXN"]
    when = (j.get("time_last_update_utc") or "")[:16]
    return (f"{NAMES.get(code, code).capitalize()} está en {mxn:.2f} pesos mexicanos"
            f"{f', según el tipo de cambio de referencia de hoy' if when else ''}.")


# ---------------- clima ----------------
def find_city(text: str) -> str | None:
    m = re.search(r"\b(?:en|de|para)\s+([A-ZÁÉÍÓÚÑ][\wáéíóúñ]+(?:\s+(?:de\s+)?[A-ZÁÉÍÓÚÑ][\wáéíóúñ]+)*)", text)
    if m:
        return m.group(1)
    m = re.search(r".*\b(?:en|para)\s+(.+?)[\s?.!¿¡]*$", text.strip(), re.I)   # última aparición de "en ..."
    if m:
        city = re.sub(r"\b(hoy|mañana|manana|ahorita|ahora|este momento|la tarde|la noche|esta semana)\b", "", m.group(1), flags=re.I).strip(" ,")
        if city and _fold(city) not in ("la", "el", "este momento"):
            return city
    return None


def weather(city: str, tomorrow: bool = False) -> str:
    with _client() as c:
        g = c.get("https://geocoding-api.open-meteo.com/v1/search",
                  params={"name": city, "count": 1, "language": "es"}).json()
        if not g.get("results"):
            return f"No encontré la ciudad {city}."
        r = g["results"][0]
        w = c.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": r["latitude"], "longitude": r["longitude"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,weather_code,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "forecast_days": 2}).json()
    name = r["name"]
    d = w["daily"]
    if tomorrow:
        return (f"Mañana en {name} se espera entre {d['temperature_2m_min'][1]:.0f} y {d['temperature_2m_max'][1]:.0f} grados, "
                f"{WMO.get(d['weather_code'][1], '')}, con {d['precipitation_probability_max'][1]}% de probabilidad de lluvia.")
    cur = w["current"]
    return (f"En {name} hay {cur['temperature_2m']:.0f} grados, se sienten como {cur['apparent_temperature']:.0f}, "
            f"{WMO.get(cur['weather_code'], '')}. Hoy la máxima será de {d['temperature_2m_max'][0]:.0f} y la mínima de "
            f"{d['temperature_2m_min'][0]:.0f}, con {d['precipitation_probability_max'][0]}% de probabilidad de lluvia.")


def weather_brief(city: str) -> str:
    """Una frase para el saludo del día: temperatura actual, rango y si conviene llevar paraguas."""
    with _client() as c:
        g = c.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1, "language": "es"}, timeout=5).json()
        if not g.get("results"):
            return ""
        r = g["results"][0]
        w = c.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": r["latitude"], "longitude": r["longitude"], "timezone": "auto",
            "current": "temperature_2m,weather_code",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max", "forecast_days": 1}, timeout=5).json()
    cur, d = w["current"], w["daily"]
    rain = d["precipitation_probability_max"][0] or 0
    txt = (f"En {r['name']} hay {cur['temperature_2m']:.0f} grados, {WMO.get(cur['weather_code'], '').strip()}; "
           f"hoy entre {d['temperature_2m_min'][0]:.0f} y {d['temperature_2m_max'][0]:.0f}.")
    if rain >= 40:
        txt += f" Lleve paraguas: {rain}% de probabilidad de lluvia."
    return txt.replace(", ;", ";")


# ---------------- búsqueda web ----------------
def _clean(s: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def search(query: str, n: int = 5) -> list[dict]:
    results = []
    try:
        with _client() as c:
            r = c.post("https://html.duckduckgo.com/html/", data={"q": query, "kl": "mx-es"})
        for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
                             r.text, re.S):
            url = m.group(1)
            if "duckduckgo.com/l/" in url:
                url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
            if "duckduckgo.com/y.js" in url:
                continue
            results.append({"title": _clean(m.group(2)), "url": url, "snippet": _clean(m.group(3))})
            if len(results) >= n:
                break
    except Exception as e:
        log.warning("DuckDuckGo: %s", e)
    if not results:  # respaldo: Wikipedia en español
        try:
            with _client() as c:
                j = c.get("https://es.wikipedia.org/w/api.php", params={
                    "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": n}).json()
            for it in j.get("query", {}).get("search", []):
                results.append({"title": it["title"], "snippet": _clean(it["snippet"]),
                                "url": "https://es.wikipedia.org/wiki/" + it["title"].replace(" ", "_")})
        except Exception as e:
            log.warning("Wikipedia: %s", e)
    return results


def page_text(url: str, limit: int = 1800) -> str:
    try:
        with _client() as c:
            r = c.get(url, timeout=7)
        if "html" not in r.headers.get("content-type", ""):
            return ""
        t = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", r.text)
        t = _clean(re.sub(r"\s+", " ", t))
        return t[:limit]
    except Exception:
        return ""


def research(query: str) -> tuple[str, list[dict]]:
    """Regresa (contexto para la IA, fuentes)."""
    results = search(query)
    if not results:
        return "", []
    ctx = []
    for i, r in enumerate(results[:5], 1):
        ctx.append(f"[{i}] {r['title']} — {r['snippet']} ({r['url']})")
    for r in results[:2]:
        txt = page_text(r["url"])
        if txt:
            ctx.append(f"Texto de {r['url']}: {txt}")
    return "\n".join(ctx), results[:5]
