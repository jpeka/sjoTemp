"""Datakällor för sjoTemp.

Varje källa är en modul med:
  SOURCE_ID   kort id, t.ex. "karlskrona"
  NAME        läsbart namn
  URL         var datat hämtas
  fetch_raw() -> rådata (det som laddades ner)
  parse(raw)  -> list[Observation]

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

    @property
    def station_id(self) -> str:
        return f"{self.source}:{self.native_id}"


def slugify(text: str) -> str:
    t = text.lower()
    for a, b in (("å", "a"), ("ä", "a"), ("ö", "o"), ("é", "e"), ("ü", "u")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


from . import bjarekraft, karlskrona, sodertalje  # noqa: E402

SOURCES = {m.SOURCE_ID: m for m in (karlskrona, bjarekraft, sodertalje)}
