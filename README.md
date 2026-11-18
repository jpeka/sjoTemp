# sjoTemp

Samlar in vattentemperaturer från badplatser i Sverige, sparar allt som historik och visar sjöarna i diagram.

**Webbsida:** https://jpeka.github.io/sjotemp/

## Källor

| Id | Källa | Badplatser | Hur datat hämtas | Schema |
|---|---|---|---|---|
| `karlskrona` | [Karlskrona kommun](https://service.karlskrona.se/FileStorageArea/Documents/badmedtemp.html) | 23 (varav 5 sjöar) | GeoJSON, senaste värdet per badplats | timvis |
| `bjarekraft` | [Bjäre Kraft](https://www.bjarekraft.se/privat/badtemperatur) | 8 (Västersjön är sjö) | HTML-sidan tolkas, senaste värdet | timvis |
| `sodertalje` | [Södertälje kommun](https://catalog.sodertalje.se) | 9, givare på ca 1 m | REST (`api.sodertalje.se/GETALLwatertemp`), historik från mars 2021 | timvis |
| `erken` | [Erkenlaboratoriet](https://erken-data.ebc.uu.se/ErkenPublic/index.html) | Erken, profil 1–15 m | Campbell-webbserver, timmedel, sparas per hel meter. Historik 2017-06 – 2025-12 från [SITES](https://meta.fieldsites.se/objects/gVQYm0aNPryFRtn2CpeuzzwF) (CC BY 4.0) via `scripts/import_sites.py` | timvis |
| `hav` | [HaV Badplatser och badvatten](https://www.havochvatten.se/data-kartor-och-rapporter/data-och-statistik/data-och-apier/api-badplatser-och-badvatten.html) | ca 2 600 (1 843 sjöar) | REST, badvattenprov med temperatur, 5 år bakåt | manuellt (servern svarar inte GitHub Actions) |

Allt som källorna publicerar sparas, även havsbaden. Sidan visar sjöarna som standard, och HaV väljs till med knappen eftersom proverna är glesa. HaV:s server tar inte emot anslutningar från GitHub Actions, så den källan körs lokalt: `python scripts/collect.py --source hav` och sedan commit + push.

Historik hämtas med *Run workflow* i Actions med fälten `source` och `backfill` (t.ex. `sodertalje` och `2021-03-01`), eller lokalt:

```
python scripts/collect.py --source sodertalje --backfill 2021-03-01
```

## Så fungerar det

- `.github/workflows/collect.yml` körs varje timme:
  1. `scripts/collect.py` hämtar alla källor och lägger till nya mätvärden i `data/`.
  2. Ändringar committas till repot.
  3. `scripts/build.py` bygger webbplatsen och databasen, som publiceras med GitHub Pages.
- En källa som inte svarar stoppar inte de andra.

## Data

I repot (textfiler, en sanning):

- `data/stations.csv` – en rad per badplats: `station_id, source, native_id, name, waterbody, lat, lon, first_seen, last_seen`
- `data/observations/<källa>/<ÅÅÅÅ-MM>.csv` – mätvärden: `station_id, timestamp, parameter, depth_m, value, unit` (`depth_m` tomt = ytnära eller okänt)

Tider är i UTC. På sidan visas grundaste djupet per station; nedladdningarna har alla djup. `waterbody` är `lake`, `sea`, `river` eller `unknown`.

För nedladdning på webbsidan:

- `sjotemp.sqlite.gz` – SQLite (gzip) med tabellerna `sources`, `stations`, `parameters`, `observations` och vyn `observations_named`
- `observations.csv.gz`, `stations.csv`, `data.json`

```sql
-- exempel
SELECT date(timestamp) AS dag, name, round(avg(value), 1) AS medel
FROM observations_named
WHERE waterbody = 'lake'
GROUP BY dag, name
ORDER BY dag;
```

## Lägga till en källa

1. Skapa `sources/<id>.py` med `SOURCE_ID`, `NAME`, `URL`, `PAGE`, `fetch_raw()` och `parse(raw)`, där `parse` returnerar en lista med `Observation`.
2. Registrera modulen i `SOURCES` i `sources/__init__.py`.
3. Spara ett exempel på rådata i `tests/fixtures/` och testa:
   ```
   python scripts/collect.py --source <id> --raw-file tests/fixtures/<fil>
   python scripts/build.py
   ```

Vattentypen sätts i respektive källmodul (`LAKES` eller `WATERBODY`).

## HaV på din dator (Windows)

HaV:s server svarar inte GitHub Actions, så den källan körs från din dator med `scripts/hav_lokal.ps1`. Skriptet hämtar proverna, committar och pushar, och pushen bygger om sidan.

Första gången (tar 15–20 minuter, hämtar fem års prov):

```powershell
git clone https://github.com/jpeka/sjoTemp.git "$env:USERPROFILE\sjoTemp"
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\sjoTemp\scripts\hav_lokal.ps1"
```

Schemalägg en gång i veckan (måndagar 07:30):

```powershell
schtasks /Create /TN "sjoTemp HaV" /SC WEEKLY /D MON /ST 07:30 /TR "powershell -NoProfile -ExecutionPolicy Bypass -File %USERPROFILE%\sjoTemp\scripts\hav_lokal.ps1"
```

Logg: `%USERPROFILE%\sjoTemp\hav_lokal.log`.
