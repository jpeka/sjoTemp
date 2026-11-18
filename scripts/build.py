#!/usr/bin/env python3
"""Bygger webbplatsen i site/ från data/.

  site/index.html          sidan med diagram
  site/data.json           kompakt data för sidan
  site/sjotemp.sqlite.gz   hela databasen, gzip (tabeller: sources, stations, parameters, observations;
                           vyn observations_named ger läsbara tider och namn)
  site/observations.csv.gz alla mätvärden med stationsnamn, en fil, gzip
  site/stations.csv        stationslistan
"""
import csv
import glob
import gzip
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


def epoch(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def depth_key(d):
    return float(d) if d not in (None, "") else 0.0


def main():
    # Nedladdningsfilerna (sqlite, csv) byggs bara på begäran: python scripts/build.py --downloads
    downloads = "--downloads" in sys.argv
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

    # --- SQLite (kompakt: heltals-id för station, unix-tid) och CSV, i ett svep ---
    db_path = os.path.join(SITE, "sjotemp.sqlite")
    db = sqlite3.connect(db_path if downloads else ":memory:")
    db.executescript("""
        PRAGMA page_size = 8192;
        CREATE TABLE sources (source TEXT PRIMARY KEY, name TEXT, url TEXT, page TEXT);
        CREATE TABLE stations (
            sid INTEGER PRIMARY KEY, station_id TEXT UNIQUE, source TEXT REFERENCES sources(source), native_id TEXT,
            name TEXT, waterbody TEXT, lat REAL, lon REAL, first_seen TEXT, last_seen TEXT);
        CREATE TABLE parameters (pid INTEGER PRIMARY KEY, parameter TEXT UNIQUE, unit TEXT);
        CREATE TABLE observations (
            sid INTEGER REFERENCES stations(sid), t INTEGER, pid INTEGER REFERENCES parameters(pid),
            depth_m REAL, value REAL);
        CREATE VIEW observations_named AS
            SELECT strftime('%Y-%m-%dT%H:%M:%SZ', o.t, 'unixepoch') AS timestamp, s.name, s.waterbody,
                   p.parameter, o.depth_m, o.value, p.unit, s.station_id, s.source
            FROM observations o JOIN stations s USING (sid) JOIN parameters p USING (pid);
    """)
    db.executemany("INSERT INTO sources VALUES (?,?,?,?)",
                   [(m.SOURCE_ID, m.NAME, m.URL, getattr(m, "PAGE", "")) for m in SOURCES.values()])
    sid_of = {s["station_id"]: i for i, s in enumerate(stations, 1)}
    db.executemany("INSERT INTO stations VALUES (?,?,?,?,?,?,?,?,?,?)",
                   [(sid_of[s["station_id"]], s["station_id"], s["source"], s["native_id"], s["name"], s["waterbody"],
                     float(s["lat"]) if s["lat"] else None, float(s["lon"]) if s["lon"] else None,
                     s["first_seen"], s["last_seen"]) for s in stations])
    pid_of = {}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=DETAIL_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    detail, daily, n_obs = {}, {}, 0
    csv_out = (gzip.open(os.path.join(SITE, "observations.csv.gz"), "wt", newline="", encoding="utf-8", compresslevel=9)
               if downloads else open(os.devnull, "w", newline="", encoding="utf-8"))
    with csv_out as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["timestamp", "name", "waterbody", "parameter", "depth_m", "value", "unit", "station_id", "source"])
        batch = []
        for o in iter_obs():
            n_obs += 1
            s = st_by_id.get(o["station_id"], {})
            depth = o.get("depth_m") or ""
            w.writerow([o["timestamp"], s.get("name", ""), s.get("waterbody", ""), o["parameter"], depth,
                        o["value"], o["unit"], o["station_id"], s.get("source", "")])
            if o["parameter"] not in pid_of:
                pid_of[o["parameter"]] = len(pid_of) + 1
                db.execute("INSERT INTO parameters VALUES (?,?,?)", (pid_of[o["parameter"]], o["parameter"], o["unit"]))
            if downloads and o["station_id"] in sid_of:
                batch.append((sid_of[o["station_id"]], int(epoch(o["timestamp"])), pid_of[o["parameter"]],
                              float(depth) if depth else None, float(o["value"])))
            if len(batch) >= 50000:
                db.executemany("INSERT INTO observations VALUES (?,?,?,?,?)", batch)
                batch.clear()
            if o["parameter"] == "water_temp" and depth_key(depth) == page_depth.get(o["station_id"]):
                if o["timestamp"] >= cutoff:
                    detail.setdefault(o["station_id"], []).append([o["timestamp"], float(o["value"])])
                else:
                    acc = daily.setdefault(o["station_id"], {}).setdefault(o["timestamp"][:10], [0.0, 0])
                    acc[0] += float(o["value"])
                    acc[1] += 1
        db.executemany("INSERT INTO observations VALUES (?,?,?,?,?)", batch)
    if not downloads:
        db.close()
    else:
        db.execute("CREATE INDEX obs_sid_t ON observations(sid, t)")
        db.commit()
        db.execute("VACUUM")
        db.close()
        with open(db_path, "rb") as src, gzip.open(db_path + ".gz", "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
        os.remove(db_path)
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
