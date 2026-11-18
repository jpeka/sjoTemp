"""Havs- och vattenmyndigheten – Badplatser och badvatten (API v2).

Registret omfattar alla EU-bad och de övriga bad som kommunerna registrerar,
med vattentyp (Sjö, Hav, Vattendrag, Delta) och provpunktens koordinater.
Provresultaten innehåller vattentemperaturen vid provtagningen (hela grader som text)
och går fem år tillbaka. Proverna tas främst under badsäsongen, så källan körs dagligen
under sommaren och veckovis resten av året (se .github/workflows/hav.yml).

Dokumentation: https://www.havochvatten.se/data-kartor-och-rapporter/data-och-statistik/data-och-apier/api-badplatser-och-badvatten.html
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import Observation, to_float

SOURCE_ID = "hav"
NAME = "Havs- och vattenmyndigheten – badvattenprov"
BASE = "https://gw.havochvatten.se/external-public/bathing-waters/v2"
URL = BASE + "/bathing-waters"
PAGE = "https://www.havochvatten.se/badplatser-och-badvatten.html"
SCHEDULE = "daily"
PAUSE_S = 0.2

WATERTYPE = {1: "sea", 2: "river", 3: "lake", 4: "river"}  # 4 = Delta


def _get_json(url: str, retries: int = 3):
    req = urllib.request.Request(url, headers={"User-Agent": "sjoTemp (github.com/jpeka/sjotemp)",
                                               "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(5 * (attempt + 1))


def fetch_raw() -> bytes:
    listing = _get_json(URL)["watersAndAdvisories"]
    results = {}
    for item in listing:
        bw_id = item["bathingWater"]["id"]
        r = _get_json(f"{URL}/{bw_id}/results")
        results[bw_id] = (r or {}).get("results") or []
        time.sleep(PAUSE_S)
    return json.dumps({"waters": [i["bathingWater"] for i in listing], "results": results},
                      ensure_ascii=False).encode("utf-8")


def _iso(ts: str) -> str:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(raw: bytes) -> list:
    data = json.loads(raw.decode("utf-8"))
    out = []
    for bw in data.get("waters", []):
        pos = bw.get("samplingPointPosition") or {}
        for res in data.get("results", {}).get(bw["id"], []):
            temp = to_float(res.get("waterTemp"))
            if temp is None or not res.get("takenAt") or not (-2 <= temp <= 40):
                continue
            out.append(Observation(
                source=SOURCE_ID,
                native_id=bw["id"],
                name=(bw.get("name") or bw["id"]).strip(),
                waterbody=WATERTYPE.get(bw.get("waterTypeId"), "unknown"),
                lat=to_float(pos.get("latitude")), lon=to_float(pos.get("longitude")),
                timestamp=_iso(res["takenAt"]),
                parameter="water_temp",
                value=temp,
                unit="degC",
            ))
    return out
