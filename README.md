# sjoTemp

Samlar in vattentemperaturer från badplatser i Sverige, sparar allt som historik och visar sjöarna i diagram.

**Webbsida:** https://jpeka.github.io/sjotemp/

## Källor

| Id | Källa | Badplatser | Hur datat hämtas |
|---|---|---|---|
| `karlskrona` | [Karlskrona kommun](https://service.karlskrona.se/FileStorageArea/Documents/badmedtemp.html) | 23 (varav 5 sjöar) | GeoJSON, senaste värdet per badplats |
| `bjarekraft` | [Bjäre Kraft](https://www.bjarekraft.se/privat/badtemperatur) | 8 (Västersjön är sjö) | HTML-sidan tolkas, senaste värdet |
| `sodertalje` | [Södertälje kommun](https://api.sodertalje.se/ui/#!/1) | 9 | Node-RED-dashboard via socket.io, ger 30 dagars historik |

Allt som källorna publicerar sparas, även havsbaden. Sidan visar sjöarna som standard.

## Så fungerar det

- `.github/workflows/collect.yml` körs varje timme:
  1. `scripts/collect.py` hämtar alla källor och lägger till nya mätvärden i `data/`.
  2. Ändringar committas till repot.
  3. `scripts/build.py` bygger webbplatsen och databasen, som publiceras med GitHub Pages.
- En källa som inte svarar stoppar inte de andra.

## Data

I repot (textfiler, en sanning):

- `data/stations.csv` – en rad per badplats: `station_id, source, native_id, name, waterbody, lat, lon, first_seen, last_seen`
- `data/observations/<källa>/<ÅÅÅÅ-MM>.csv` – mätvärden: `station_id, timestamp, parameter, value, unit`

Tider är i UTC. `waterbody` är `lake`, `sea`, `river` eller `unknown`.

För nedladdning på webbsidan:

- `sjotemp.sqlite` – SQLite med tabellerna `sources`, `stations`, `observations` och vyn `observations_named`
- `observations.csv`, `stations.csv`, `data.json`

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
