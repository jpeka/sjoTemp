"""Karlskrona kommuns badtemperaturer (senaste värde per badplats, GeoJSON)."""
import json
import urllib.request
from datetime import datetime, timezone

from . import Observation

SOURCE_ID = "karlskrona"
NAME = "Karlskrona kommun – badtemperaturer"
URL = "https://service.karlskrona.se/FileStorageArea/Documents/bad/1.1/swimAreas.geojson"
PAGE = "https://service.karlskrona.se/FileStorageArea/Documents/badmedtemp.html"
RAW_EXT = "geojson"

# Insjöbad. Övriga badplatser i källan ligger i havet.
LAKES = {"ALLSJÖN", "BREDASJÖN", "SKÄRSJÖN", "SKÄLAGÖLEN", "ALLJUNGEN"}


def to_utc(ts: str) -> str:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_raw() -> bytes:
    req = urllib.request.Request(URL, headers={"User-Agent": "sjoTemp (github.com/jpeka/sjotemp)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse(raw: bytes) -> list:
    data = json.loads(raw.decode("utf-8-sig"))
    out = []
    for feat in data.get("features", []):
        p = feat.get("properties") or {}
        name = (p.get("nameArea") or "").strip()
        temp = p.get("temperatureWater")
        ts = p.get("timeStamp") or ""
        if not name or not isinstance(temp, (int, float)):
            continue  # t.ex. "NaT" när givaren saknar värde
        try:
            ts_utc = to_utc(ts)
        except ValueError:
            continue
        coords = (feat.get("geometry") or {}).get("coordinates") or [None, None]
        out.append(Observation(
            source=SOURCE_ID,
            native_id=p.get("idArea") or name,
            name=name.upper().capitalize(),
            waterbody="lake" if name.upper() in LAKES else "sea",
            lat=coords[1], lon=coords[0],
            timestamp=ts_utc,
            parameter="water_temp",
            value=round(float(temp), 2),
            unit="degC",
        ))
    return out
