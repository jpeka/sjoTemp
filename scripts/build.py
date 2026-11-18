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
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sources import SOURCES  # noqa: E402

DATA = os.path.join(ROOT, "data")
SITE = os.path.join(ROOT, "site")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


DETAIL_DAYS = 35  # i data.json: fulla serier senaste DETAIL_DAYS dygnen, dygnsmedel före det


def iter_obs():
    """Läser mätvärden fil för fil (källa, månad) för att hålla nere minnesåtgången."""
    for path in sorted(glob.glob(os.path.join(DATA, "observations", "*", "*.csv"))):
        yield from read_csv(path)


def depth_key(d):
    return float(d) if d not in (None, "") else 0.0


def main():
    st_path = os.path.join(DATA, "stations.csv")
    stations = read_csv(st_path) if os.path.exists(st_path) else []
    st_by_id = {s["station_id"]: s for s in stations}

    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE)
    shutil.copy(os.path.join(ROOT, "web", "index.html"), SITE)
    open(os.path.join(SITE, ".nojekyll"), "w").close()

    # Vilket djup sidan visar per station: det grundaste som finns.
    page_depth = {}
    for o in iter_obs():
        if o["parameter"] == "water_temp":
            d = depth_key(o.get("depth_m"))
            if o["station_id"] not in page_depth or d < page_depth[o["station_id"]]:
                page_depth[o["station_id"]] = d

    # --- SQLite ---
    db = sqlite3.connect(os.path.join(SITE, "sjotemp.sqlite"))
    db.executescript("""
        CREATE TABLE sources (source TEXT PRIMARY KEY, name TEXT, url TEXT, page TEXT);
        CREATE TABLE stations (
            station_id TEXT PRIMARY KEY, source TEXT REFERENCES sources(source), native_id TEXT,
            name TEXT, waterbody TEXT, lat REAL, lon REAL, first_seen TEXT, last_seen TEXT);
        CREATE TABLE observations (
            station_id TEXT REFERENCES stations(station_id), timestamp TEXT,
            parameter TEXT, depth_m REAL, value REAL, unit TEXT);
        CREATE VIEW observations_named AS
            SELECT o.timestamp, s.name, s.waterbody, o.parameter, o.depth_m, o.value, o.unit, o.station_id, s.source
            FROM observations o JOIN stations s USING (station_id);
    """)
    db.executemany("INSERT INTO sources VALUES (?,?,?,?)",
                   [(m.SOURCE_ID, m.NAME, m.URL, getattr(m, "PAGE", "")) for m in SOURCES.values()])
    db.executemany("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?,?)",
                   [(s["station_id"], s["source"], s["native_id"], s["name"], s["waterbody"],
                     float(s["lat"]) if s["lat"] else None, float(s["lon"]) if s["lon"] else None,
                     s["first_seen"], s["last_seen"]) for s in stations])

    # --- CSV, SQLite och sidans serier i ett svep ---
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DETAIL_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    detail, daily, n_obs = {}, {}, 0
    with open(os.path.join(SITE, "observations.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["timestamp", "name", "waterbody", "parameter", "depth_m", "value", "unit", "station_id", "source"])
        batch = []
        for o in iter_obs():
            n_obs += 1
            s = st_by_id.get(o["station_id"], {})
            depth = o.get("depth_m") or ""
            w.writerow([o["timestamp"], s.get("name", ""), s.get("waterbody", ""), o["parameter"], depth,
                        o["value"], o["unit"], o["station_id"], s.get("source", "")])
            batch.append((o["station_id"], o["timestamp"], o["parameter"],
                          float(depth) if depth else None, float(o["value"]), o["unit"]))
            if len(batch) >= 50000:
                db.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?)", batch)
                batch.clear()
            if o["parameter"] == "water_temp" and depth_key(depth) == page_depth.get(o["station_id"]):
                if o["timestamp"] >= cutoff:
                    detail.setdefault(o["station_id"], []).append([o["timestamp"], float(o["value"])])
                else:
                    acc = daily.setdefault(o["station_id"], {}).setdefault(o["timestamp"][:10], [0.0, 0])
                    acc[0] += float(o["value"])
                    acc[1] += 1
        db.executemany("INSERT INTO observations VALUES (?,?,?,?,?,?)", batch)
    db.execute("CREATE INDEX obs_station_time ON observations(station_id, timestamp)")
    db.execute("CREATE INDEX obs_time ON observations(timestamp)")
    db.commit()
    db.execute("VACUUM")
    db.close()
    if stations:
        shutil.copy(st_path, SITE)

    # --- JSON för sidan (vattentemperatur på grundaste djupet) ---
    series = {}
    for sid in set(detail) | set(daily):
        pts = [[d + "T12:00:00Z", round(v / n, 2)] for d, (v, n) in sorted(daily.get(sid, {}).items())]
        pts += sorted(detail.get(sid, []))
        series[sid] = pts
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detail_days": DETAIL_DAYS,
        "sources": {m.SOURCE_ID: {"name": m.NAME, "page": getattr(m, "PAGE", m.URL)} for m in SOURCES.values()},
        "stations": [{k: s[k] for k in ("station_id", "source", "name", "waterbody")} |
                     {"lat": float(s["lat"]) if s["lat"] else None, "lon": float(s["lon"]) if s["lon"] else None,
                      "depth": page_depth.get(s["station_id"]) or None}
                     for s in stations if s["station_id"] in series],
        "series": series,
        "counts": {"observations": n_obs, "stations": len(stations)},
    }
    with open(os.path.join(SITE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Byggde site/: {len(stations)} stationer, {n_obs} mätvärden, data.json {os.path.getsize(os.path.join(SITE, 'data.json')) // 1024} kB")


if __name__ == "__main__":
    main()
