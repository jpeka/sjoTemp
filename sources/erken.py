"""Erken – temperaturprofil från Erkenlaboratoriet (Uppsala universitet, SITES Water).

Givarkedjan är förankrad året runt och mäter var 0,25–0,5 m från 1 till 15,5 m djup.
Data hämtas från laboratoriets publika Campbell-webbserver (LoggerNet), tabellen
Output60min (timmedel). Servern har bara de senaste ca två månaderna; äldre data finns
i SITES dataportal (2017–2025) och läggs in med scripts/import_sites.py.

Vi sparar hela meter (1, 2, … 15 m) för att hålla nere datamängden.
Tiderna i loggern antas vara svensk normaltid (UTC+1) året runt, som i SITES-filerna.
"""
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from . import Observation, to_float

SOURCE_ID = "erken"
NAME = "Erkenlaboratoriet (Uppsala universitet) – temperaturprofil"
BASE = "https://erken-data.ebc.uu.se/ErkenPublic/"
TABLE = "Server:Erken_Underwater_Temp_Sys.Output60min"
URL = f"{BASE}?command=DataQuery&format=json&uri={TABLE}"
PAGE = "https://erken-data.ebc.uu.se/ErkenPublic/index.html"
SCHEDULE = "hourly"

STATION = dict(native_id="erken-profil", name="Erken", waterbody="lake", lat=59.84247, lon=18.630983)
LOGGER_TZ = timezone(timedelta(hours=1))
FIELD_RE = re.compile(r"^WTemp(\d+)_(\d+)_Avg$")


def _query(seconds: int) -> bytes:
    req = urllib.request.Request(f"{URL}&mode=backfill&p1={seconds}",
                                 headers={"User-Agent": "sjoTemp (github.com/jpeka/sjotemp)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def fetch_raw() -> bytes:
    return _query(3 * 86400)


def to_utc(local: str) -> str:
    dt = datetime.fromisoformat(local[:19]).replace(tzinfo=LOGGER_TZ)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_obs(ts_utc: str, depth: float, value: float) -> Observation:
    return Observation(source=SOURCE_ID, timestamp=ts_utc, parameter="water_temp",
                       value=round(value, 3), unit="degC", depth_m=depth, **STATION)


def parse(raw: bytes) -> list:
    d = json.loads(raw.decode("utf-8"))
    cols = []
    for i, f in enumerate(d.get("head", {}).get("fields", [])):
        m = FIELD_RE.match(f["name"])
        if m and m.group(2) == "00":
            cols.append((i, float(m.group(1))))
    out = []
    for row in d.get("data", []):
        ts = to_utc(row["time"])
        for i, depth in cols:
            v = to_float(row["vals"][i])
            if v is not None and -1 <= v <= 35:
                out.append(make_obs(ts, depth, v))
    return out


def backfill(since=None):
    yield parse(_query(70 * 86400))
