#!/usr/bin/env python3
"""Bygger webbplatsen i site/ från data/.

  site/index.html          sidan med diagram
  site/data.json           kompakt data för sidan
  site/sjotemp.sqlite      hela databasen (tabeller: sources, stations, observations)
  site/observations.csv    alla mätvärden med stationsnamn, en fil
  site/stations.csv        stationslistan
"""
import csv
import glob
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sources import SOURCES  # noqa: E402

DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    stations = read_csv(os.path.join(DATA, "stations.csv")) if os.path.exists(os.path.join(DATA, "stations.csv")) else []
    obs = []
    for path in sorted(glob.glob(os.path.join(DATA, "observations", "*", "*.csv"))):
        obs.extend(read_csv(path))
    obs.sort(key=lambda r: (r["timestamp"], r["station_id"], r["parameter"]))
    st_by_id = {s["station_id"]: s for s in stations}

    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    shutil.copy(os.path.join(ROOT, "web", "index.html"), SITE)
    open(os.path.join(SITE, ".nojekyll"), "w").close()

    # --- SQLite ---
    db = sqlite3.connect(os.path.join(SITE, "sjotemp.sqlite"))
    db.executescript("""
        CREATE TABLE sources (source TEXT PRIMARY KEY, name TEXT, url TEXT, page TEXT);
        CREATE TABLE stations (
            station_id TEXT PRIMARY KEY, source TEXT REFERENCES sources(source), native_id TEXT,
            name TEXT, waterbody TEXT, lat REAL, lon REAL, first_seen TEXT, last_seen TEXT);
        CREATE TABLE observations (
            station_id TEXT REFERENCES stations(station_id), timestamp TEXT,
            parameter TEXT, value REAL, unit TEXT,
            PRIMARY KEY (station_id, timestamp, parameter)) WITHOUT ROWID;
        CREATE INDEX obs_time ON observations(timestamp);
        CREATE VIEW observations_named AS
            SELECT o.timestamp, s.name, s.waterbody, o.parameter, o.value, o.unit, o.station_id, s.source
            FROM observations o JOIN stations s USING (station_id);
    """)
    db.executemany("INSERT INTO sources VALUES (?,?,?,?)",
                   [(m.SOURCE_ID, m.NAME, m.URL, getattr(m, "PAGE", "")) for m in SOURCES.values()])
    db.executemany("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?,?)",
                   [(s["station_id"], s["source"], s["native_id"], s["name"], s["waterbody"],
                     float(s["lat"]) if s["lat"] else None, float(s["lon"]) if s["lon"] else None,
                     s["first_seen"], s["last_seen"]) for s in stations])
    db.executemany("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?)",
                   [(o["station_id"], o["timestamp"], o["parameter"], float(o["value"]), o["unit"]) for o in obs])
    db.commit()
    db.execute("VACUUM")
    db.close()

    # --- CSV ---
    shutil.copy(os.path.join(DATA, "stations.csv"), SITE) if stations else None
    with open(os.path.join(SITE, "observations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["timestamp", "name", "waterbody", "parameter", "value", "unit", "station_id", "source"])
        for o in obs:
            s = st_by_id.get(o["station_id"], {})
            w.writerow([o["timestamp"], s.get("name", ""), s.get("waterbody", ""), o["parameter"],
                        o["value"], o["unit"], o["station_id"], s.get("source", "")])

    # --- JSON för sidan (bara vattentemperatur) ---
    series = {}
    for o in obs:
        if o["parameter"] == "water_temp":
            series.setdefault(o["station_id"], []).append([o["timestamp"], float(o["value"])])
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {m.SOURCE_ID: {"name": m.NAME, "page": getattr(m, "PAGE", m.URL)} for m in SOURCES.values()},
        "stations": [{k: s[k] for k in ("station_id", "source", "name", "waterbody")} |
                     {"lat": float(s["lat"]) if s["lat"] else None, "lon": float(s["lon"]) if s["lon"] else None}
                     for s in stations],
        "series": series,
        "counts": {"observations": len(obs), "stations": len(stations)},
    }
    with open(os.path.join(SITE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Byggde site/: {len(stations)} stationer, {len(obs)} mätvärden")


if __name__ == "__main__":
    main()
