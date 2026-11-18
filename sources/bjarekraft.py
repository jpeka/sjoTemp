"""Bjäre Kraft – badtemperaturer i Båstad och Ängelholm (LoRa-givare).

Sidan är serverrenderad HTML utan API. Varje badplats ligger i ett
<div class="one-place"> med uppdateringstid (MM/DD HH:MM, svensk tid, utan år),
temperatur ("5,2°C") och namn.
"""
import html
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import Observation, slugify

SOURCE_ID = "bjarekraft"
NAME = "Bjäre Kraft – badtemperaturer Båstad & Ängelholm"
URL = "https://www.bjarekraft.se/privat/badtemperatur"
PAGE = URL
RAW_EXT = "html"

TZ = ZoneInfo("Europe/Stockholm")
LAKES = {"Västersjön Hjärnarp"}

PLACE_RE = re.compile(
    r'class="one-place">\s*<div[^>]*>\s*(?P<when>\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2})\s*</div>\s*'
    r'<div\s+class="actual-temperature">\s*(?P<temp>-?\d+(?:[.,]\d+)?)\s*°C\s*</div>\s*'
    r'<div\s+class="location">(?P<name>.*?)</div>',
    re.S,
)


def fetch_raw() -> bytes:
    req = urllib.request.Request(URL, headers={"User-Agent": "sjoTemp (github.com/jpeka/sjotemp)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_when(when: str, now: datetime) -> str:
    """'11/18 16:01' i svensk tid -> UTC ISO. Året gissas: senaste tidpunkten som inte ligger i framtiden."""
    md, hm = when.split()
    month, day = map(int, md.split("/"))
    hour, minute = map(int, hm.split(":"))
    local_now = now.astimezone(TZ)
    for year in (local_now.year, local_now.year - 1):
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=TZ)
        except ValueError:
            continue
        if dt <= local_now + timedelta(hours=1):
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError(f"Kan inte tolka tid: {when}")


def parse(raw: bytes, now: datetime = None) -> list:
    now = now or datetime.now(timezone.utc)
    text = raw.decode("utf-8", errors="replace")
    out, seen = [], set()
    for m in PLACE_RE.finditer(text):
        name = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", m["name"])).split())
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(Observation(
            source=SOURCE_ID,
            native_id=slugify(name),
            name=name,
            waterbody="lake" if name in LAKES else "sea",
            lat=None, lon=None,
            timestamp=parse_when(m["when"], now),
            parameter="water_temp",
            value=round(float(m["temp"].replace(",", ".")), 2),
            unit="degC",
        ))
    if not out:
        raise ValueError("Hittade inga badplatser på sidan – har sidans HTML ändrats?")
    return out
