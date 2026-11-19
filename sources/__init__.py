"""Datakällor för sjoTemp.

Varje källa är en modul med:
  SOURCE_ID   kort id, t.ex. "karlskrona"
  NAME        läsbart namn
  URL         var datat hämtas
  PAGE        sida att länka till
  SCHEDULE    "hourly" (standard) eller "daily"
  fetch_raw() -> rådata (det som laddades ner)
  parse(raw)  -> list[Observation]
  backfill(since) (valfri) -> generator av list[Observation], för historik

Lägg till en ny källa genom att skapa en modul här och registrera den i SOURCES.
"""
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Observation:
    source: str            # källans id
    native_id: str         # stationens id hos källan
    name: str              # stationens namn
    waterbody: str         # "lake", "sea", "river" eller "unknown"
    lat: Optional[float]
    lon: Optional[float]
    timestamp: str         # UTC, ISO 8601 med Z, sekundupplösning
    parameter: str         # t.ex. "water_temp"
    value: float
    unit: str              # t.ex. "degC"
    depth_m: Optional[float] = None  # mätdjup i meter; None = ytnära/okänt

    @property
    def station_id(self) -> str:
        return f"{self.source}:{self.native_id}"


def slugify(text: str) -> str:
    t = text.lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def to_float(v) -> Optional[float]:
    """Tolkar tal som kan komma som sträng med komma. Returnerar None för tomt/NaN."""
    if isinstance(v, (int, float)):
        f = float(v)
    elif isinstance(v, str):
        try:
            f = float(v.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return None if f != f else f  # NaN


from . import bjarekraft, erken, karlskrona, sodertalje  # noqa: E402

SOURCES = {m.SOURCE_ID: m for m in (karlskrona, bjarekraft, sodertalje, erken)}
