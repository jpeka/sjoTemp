"""Södertälje kommun – badtemperaturer (IoT-givare på ca 1 m djup, Telge Nät).

Öppet REST-API, dokumenterat i kommunens datakatalog (catalog.sodertalje.se, store 15):
  https://api.sodertalje.se/getwatertemp                         senaste värde per aktiv givare
  https://api.sodertalje.se/GETALLwatertemp?start=ÅÅÅÅ-MM-DD&end=ÅÅÅÅ-MM-DD   alla mätningar i intervallet
Historik finns från mars 2021. API:et svarar "429: Too many requests" vid täta anrop,
så historiken hämtas en månad i taget med paus.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

from . import Observation, slugify, to_float

SOURCE_ID = "sodertalje"
NAME = "Södertälje kommun – badtemperaturer"
URL = "https://api.sodertalje.se/GETALLwatertemp"
PAGE = "https://www.sodertalje.se/kultur-och-fritid/natur-och-friluftsliv/badplatser/"
SCHEDULE = "hourly"
HISTORY_START = date(2021, 3, 1)
DEPTH_M = 1.0  # enligt kommunens databeskrivning

# Klassning av vattentyp. "unknown" visas bara när man väljer att visa alla badplatser.
WATERBODY = {
    "Nya Malmsjöbadet": "lake",
    "Mälarbadet": "lake",
    "Eklundsnäsbadet": "lake",
    "Bränningestrand": "sea",
    "Farstanäsbadet": "sea",
}


def _get(url: str, retries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "sjoTemp (github.com/jpeka/sjotemp)"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code not in (429, 500, 502, 503):
                raise
        if not body.lstrip().startswith(b"429"):
            return body
        time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"Södertälje: för många anrop ({url})")


def _range_url(start: date, end: date) -> str:
    return f"{URL}?start={start.isoformat()}&end={end.isoformat()}"


def fetch_raw() -> bytes:
    today = datetime.now(timezone.utc).date()
    return _get(_range_url(today - timedelta(days=2), today))


def parse(raw: bytes) -> list:
    rows = json.loads(raw.decode("utf-8"))
    out = []
    for r in rows if isinstance(rows, list) else []:
        name = (r.get("alias") or "").strip()
        temp = to_float(r.get("temp_water"))
        ts = r.get("ts")
        if not name or temp is None or not isinstance(ts, (int, float)):
            continue
        out.append(Observation(
            source=SOURCE_ID,
            native_id=slugify(name),
            name=name,
            waterbody=WATERBODY.get(name, "unknown"),
            lat=to_float(r.get("latitude")), lon=to_float(r.get("longitude")),
            timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            parameter="water_temp",
            value=round(temp, 2),
            unit="degC",
            depth_m=DEPTH_M,
        ))
    return out


def backfill(since: date = HISTORY_START):
    """Hämtar historik en månad i taget från `since` till idag."""
    start = date(since.year, since.month, 1)
    today = datetime.now(timezone.utc).date()
    while start <= today:
        nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        # API:et svarar 400 om slutdatum ligger för långt fram, så sista månaden slutar idag.
        yield parse(_get(_range_url(start, min(nxt, today))))
        start = nxt
        time.sleep(15)
