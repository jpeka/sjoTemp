#!/usr/bin/env python3
"""Hämtar källor och lägger till nya mätvärden i data/.

Lagring (textfiler, lätta att diffa i git):
  data/stations.csv                          en rad per station
  data/observations/<källa>/<ÅÅÅÅ-MM>.csv    mätvärden, en fil per månad

Användning:
  python scripts/collect.py --schedule hourly          källor som körs varje timme
  python scripts/collect.py --source hav               en källa
  python scripts/collect.py --source sodertalje --backfill 2021-03-01
  python scripts/collect.py --source karlskrona --raw-file fil.geojson
"""
import argparse
import bisect
import csv
import os
import sys
from datetime import date, datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from sources import SOURCES  # noqa: E402

DATA = os.path.join(ROOT, "data")
STATIONS_CSV = os.path.join(DATA, "stations.csv")
STATION_FIELDS = ["station_id", "source", "native_id", "name", "waterbody", "lat", "lon", "first_seen", "last_seen"]
OBS_FIELDS = ["station_id", "timestamp", "parameter", "depth_m", "value", "unit"]
DEDUP_SECONDS = 90


def epoch(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def fmt_depth(d):
    return "" if d is None or d == "" else f"{float(d):g}"


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def store(observations):
    """Lägger till nya observationer och uppdaterar stationslistan. Returnerar antal nya rader."""
    stations = {r["station_id"]: r for r in read_csv(STATIONS_CSV)}
    by_file = {}
    for o in observations:
        path = os.path.join(DATA, "observations", o.source, o.timestamp[:7] + ".csv")
        by_file.setdefault(path, []).append(o)

        s = stations.get(o.station_id)
        if s is None:
            stations[o.station_id] = s = {
                "station_id": o.station_id, "source": o.source, "native_id": o.native_id,
                "first_seen": o.timestamp, "last_seen": o.timestamp, "lat": "", "lon": "",
            }
        s["name"] = o.name
        s["waterbody"] = o.waterbody
        if o.lat is not None and o.lon is not None:
            s["lat"], s["lon"] = round(o.lat, 6), round(o.lon, 6)
        s["first_seen"] = min(s["first_seen"], o.timestamp)
        s["last_seen"] = max(s["last_seen"], o.timestamp)

    added = 0
    for path, obs in by_file.items():
        rows = read_csv(path)
        # Samma mätning kan dyka upp med någon sekunds skillnad i tidsstämpel (t.ex. Södertälje).
        # Allt inom DEDUP_SECONDS för samma station, parameter och djup räknas som samma mätning.
        seen = {}
        for r in rows:
            r["depth_m"] = fmt_depth(r.get("depth_m"))
            seen.setdefault((r["station_id"], r["parameter"], r["depth_m"]), []).append(epoch(r["timestamp"]))
        for times in seen.values():
            times.sort()
        for o in obs:
            depth = fmt_depth(o.depth_m)
            times = seen.setdefault((o.station_id, o.parameter, depth), [])
            t = epoch(o.timestamp)
            i = bisect.bisect_left(times, t - DEDUP_SECONDS)
            if i < len(times) and times[i] <= t + DEDUP_SECONDS:
                continue
            times.insert(bisect.bisect_left(times, t), t)
            rows.append({"station_id": o.station_id, "timestamp": o.timestamp, "parameter": o.parameter,
                         "depth_m": depth, "value": o.value, "unit": o.unit})
            added += 1
        rows.sort(key=lambda r: (r["timestamp"], r["station_id"], r["parameter"],
                                 float(r["depth_m"]) if r["depth_m"] else -1))
        write_csv(path, OBS_FIELDS, rows)

    write_csv(STATIONS_CSV, STATION_FIELDS, sorted(stations.values(), key=lambda r: r["station_id"]))
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=sorted(SOURCES), help="kör bara en källa")
    ap.add_argument("--schedule", choices=["hourly", "daily"], help="kör källor med detta schema")
    ap.add_argument("--raw-file", help="läs rådata från fil i stället för att hämta (kräver --source)")
    ap.add_argument("--backfill", metavar="ÅÅÅÅ-MM-DD", help="hämta historik från datum (kräver --source)")
    args = ap.parse_args()

    if args.source:
        ids = [args.source]
    elif args.schedule:
        ids = sorted(s for s, m in SOURCES.items() if getattr(m, "SCHEDULE", "hourly") == args.schedule)
    else:
        ids = sorted(SOURCES)

    failed = 0
    for sid in ids:
        mod = SOURCES[sid]
        try:
            if args.backfill:
                if not hasattr(mod, "backfill"):
                    raise ValueError("källan saknar backfill()")
                total = 0
                batches = mod.backfill(date.fromisoformat(args.backfill))
                while True:
                    try:
                        batch = next(batches)
                    except StopIteration:
                        break
                    n = store(batch)  # spara efter varje omgång, så att ett senare fel inte kastar bort något
                    total += n
                    print(f"[{sid}] historik: {len(batch)} värden, {n} nya", flush=True)
                print(f"[{sid}] historik klar, {total} nya")
                continue
            if args.raw_file:
                with open(args.raw_file, "rb") as f:
                    raw = f.read()
            else:
                raw = mod.fetch_raw()
            obs = mod.parse(raw)
            added = store(obs)
            print(f"[{sid}] {len(obs)} värden i källan, {added} nya", flush=True)
        except Exception as e:  # en trasig källa ska inte stoppa de andra
            failed += 1
            print(f"[{sid}] FEL: {e}", file=sys.stderr, flush=True)

    print(datetime.now(timezone.utc).strftime("Klart %Y-%m-%dT%H:%M:%SZ"))
    return 1 if ids and failed == len(ids) else 0


if __name__ == "__main__":
    sys.exit(main())
