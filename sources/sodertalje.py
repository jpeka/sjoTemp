"""Södertälje kommun – badtemperaturer (Node-RED-dashboard på api.sodertalje.se).

Dashboarden har inget REST-API. Datat skickas över socket.io (Engine.IO v4,
long polling). Efter anslutning ber vi om "ui-replay-state" och får då:
  - tabellen med aktuella värden (inkl. givarens EUI och koordinater)
  - diagrammet "senaste 30 dagarna" med alla badplatsers tidsserier
Det betyder att varje körning också fyller i upp till 30 dagars historik.
"""
import http.cookiejar
import json
import time
import urllib.request
from datetime import datetime, timezone

from . import Observation, slugify

SOURCE_ID = "sodertalje"
NAME = "Södertälje kommun – badtemperaturer"
BASE = "https://api.sodertalje.se/ui/socket.io/?EIO=4&transport=polling"
URL = BASE
PAGE = "https://api.sodertalje.se/ui/#!/1"
RAW_EXT = "json"

CHART_30D = "3fa013c2.8540ac"
CHART_7D = "dbb8d7e7.ba72f8"
CURRENT_TABLE = "f5989e5d.bf3508"

# Klassning av vattentyp. "unknown" visas bara när man väljer att visa alla badplatser.
WATERBODY = {
    "Nya Malmsjöbadet": "lake",
    "Mälarbadet": "lake",
    "Eklundsnäsbadet": "lake",
    "Bränningestrand": "sea",
    "Farstanäsbadet": "sea",
}


def _poll(opener, sid=None, body=None, timeout=45):
    url = f"{BASE}&t={int(time.time() * 1000)}" + (f"&sid={sid}" if sid else "")
    data = body.encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "sjoTemp (github.com/jpeka/sjotemp)",
        "Content-Type": "text/plain;charset=UTF-8",
    })
    with opener.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def fetch_raw() -> bytes:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    hs = _poll(opener)
    if not hs.startswith("0"):
        raise ValueError(f"Oväntat svar vid anslutning: {hs[:80]}")
    sid = json.loads(hs[1:])["sid"]
    _poll(opener, sid, "40")

    found, replay_sent = {}, False
    deadline = time.time() + 90
    while time.time() < deadline and not (CHART_30D in found and CURRENT_TABLE in found):
        for pkt in _poll(opener, sid).split("\x1e"):
            if pkt == "2":  # ping
                _poll(opener, sid, "3")
            elif pkt.startswith("40") and not replay_sent:
                _poll(opener, sid, '42["ui-replay-state"]')
                replay_sent = True
            elif pkt.startswith("42"):
                try:
                    name, *args = json.loads(pkt[2:])
                except ValueError:
                    continue
                if name == "update-value" and args and isinstance(args[0], dict):
                    if args[0].get("id") in (CHART_30D, CHART_7D, CURRENT_TABLE):
                        found[args[0]["id"]] = args[0]
        if not replay_sent:
            _poll(opener, sid, '42["ui-replay-state"]')
            replay_sent = True
    try:
        _poll(opener, sid, "41", timeout=10)  # koppla ner
    except Exception:
        pass
    if not found:
        raise ValueError("Fick inga badtemperaturer från dashboarden")
    return json.dumps(found, ensure_ascii=False).encode("utf-8")


def _iso(ms) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(raw: bytes) -> list:
    found = json.loads(raw.decode("utf-8"))
    coords, out, current = {}, [], []

    for row in ((found.get(CURRENT_TABLE) or {}).get("msg") or {}).get("payload") or []:
        name = (row.get("alias") or "").strip()
        if not name:
            continue
        coords[name] = (row.get("latitude"), row.get("longitude"))
        if isinstance(row.get("temp_water"), (int, float)) and row.get("ts"):
            current.append((name, row["ts"], row["temp_water"]))

    # Samma mätning förekommer i flera diagram med tidsstämplar som skiljer sig några
    # hundra millisekunder. 30-dagarsdiagrammet går först, sedan 7 dagar, sist tabellen.
    for chart_id in (CHART_30D, CHART_7D):
        chart = found.get(chart_id)
        if not chart:
            continue
        for block in chart.get("value") or []:
            vals = block.get("values") or {}
            for name, points in zip(vals.get("series") or [], vals.get("data") or []):
                if not isinstance(points, list):
                    continue
                for p in points:
                    if isinstance(p, dict) and isinstance(p.get("y"), (int, float)) and isinstance(p.get("x"), (int, float)):
                        out.append((name.strip(), p["x"], p["y"]))

    kept, obs = {}, []
    for name, ms, temp in out + current:
        prev = kept.setdefault(name, [])
        if any(abs(ms - k) < 120_000 for k in prev):
            continue
        prev.append(ms)
        lat, lon = coords.get(name, (None, None))
        obs.append(Observation(
            source=SOURCE_ID,
            native_id=slugify(name),
            name=name,
            waterbody=WATERBODY.get(name, "unknown"),
            lat=lat, lon=lon,
            timestamp=_iso(ms),
            parameter="water_temp",
            value=round(float(temp), 2),
            unit="degC",
        ))
    return obs
