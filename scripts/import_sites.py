#!/usr/bin/env python3
"""Lägger in Erkens temperaturprofil från SITES dataportal (CC BY 4.0).

Filen laddas ner manuellt (licensen godkänns i webbläsaren) från
https://meta.fieldsites.se/objects/gVQYm0aNPryFRtn2CpeuzzwF och läses sedan in:

  python scripts/import_sites.py SITES_TW-PROF_ERK_LRK_20170628-20251201_L2_60min.csv

Tider i filen är UTC+1. Precis som för livedatat sparas bara hela meter (1–15 m).
Raderna läggs i samma station som livedatat (erken:erken-profil).
"""
import csv
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from scripts.collect import store  # noqa: E402
from sources import to_float  # noqa: E402
from sources.erken import make_obs, to_utc  # noqa: E402

COL_RE = re.compile(r"^TW_-(\d+)\.0m$")


def main(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("TIMESTAMP,"))
    reader = csv.reader(lines[start:])
    header = next(reader)
    cols = [(i, float(m.group(1))) for i, h in enumerate(header) if (m := COL_RE.match(h.strip()))]
    print(f"Djup: {[d for _, d in cols]}")

    month, batch, total = None, [], 0
    for row in reader:
        if not row or not row[0].strip():
            continue
        ts = to_utc(row[0].strip().replace(" ", "T") + ":00")
        if month and ts[:7] != month and batch:
            total += store(batch)
            print(f"{month}: {len(batch)} värden", flush=True)
            batch = []
        month = ts[:7]
        for i, depth in cols:
            v = to_float(row[i]) if i < len(row) else None
            if v is not None and -1 <= v <= 35:
                batch.append(make_obs(ts, depth, v))
    if batch:
        total += store(batch)
    print(f"Klart: {total} nya värden")


if __name__ == "__main__":
    main(sys.argv[1])
