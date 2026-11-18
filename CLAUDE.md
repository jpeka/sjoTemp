# sjoTemp – instruktioner för Claude

Projektet samlar vattentemperaturer från svenska badplatser och sjöar, sparar allt som historik i git och publicerar en sida med diagram och nedladdningar på GitHub Pages (https://jpeka.github.io/sjoTemp/). Användaren skriver på svenska; svara på svenska.

## Struktur
- `sources/<id>.py` – en modul per källa: `SOURCE_ID`, `NAME`, `URL`, `PAGE`, `SCHEDULE` ("hourly"/"daily"), `fetch_raw()`, `parse(raw) -> list[Observation]`, valfritt `backfill(since)`. Registreras i `sources/__init__.py`.
- `scripts/collect.py` – hämtar och lägger till i `data/` (dedup: samma station, parameter och djup inom 90 s).
- `scripts/build.py` – bygger `site/` (index.html, data.json). Användaren vill inte erbjuda nedladdning på sidan; `--downloads` bygger sqlite/csv lokalt. `site/` committas inte.
- `web/index.html` – sidan (Chart.js från jsDelivr). Visar sjöar och grundaste djup; HaV är avvald som standard.
- `.github/workflows/collect.yml` – timvis insamling, historik via workflow_dispatch (`source`, `backfill`), deploy till Pages.

## Datamodell
- `data/stations.csv`: station_id (`<källa>:<native_id>`), source, native_id, name, waterbody (lake/sea/river/unknown), lat, lon, first_seen, last_seen.
- `data/observations/<källa>/<ÅÅÅÅ-MM>.csv`: station_id, timestamp (UTC, `...Z`), parameter (`water_temp`), depth_m (tomt = ytnära/okänt), value, unit (`degC`).

## Konventioner
- Testa nya källor mot sparad rådata i `tests/fixtures/` med `--raw-file` innan push. Sessionens skal kan sakna nät; live-test sker i Actions.
- Var snäll mot källorna: Södertälje svarar 429 vid täta anrop, Temperatur.nu tillåter 15 osignerade anrop/15 min och kräver signerade anrop för publika appar.
- Klassa vattentyp i källmodulen. Gissa inte; använd `unknown` hellre än fel.

## Utredda men ej inkopplade källor (nov 2026)
- Temperatur.nu: 106 vattenstationer, timvis historik. Väntar på klientnyckel (support@temperatur.nu). Dubblerar Karlskrona och Bjäre Kraft.
- SLU Miljödata MVM: kräver token (hemlighet `SLU_MVM_TOKEN`), historik från 1964.
- SITES: Erken 2017-06 – 2025-12 importerad med `scripts/import_sites.py` (lucka dec 2025 – sep 2026 innan livedatat börjar). Bolmen ej importerad. Nedladdning kräver licensgodkännande i webbläsaren.
- Linköping (ArcGIS saknar temperaturfält), Skellefteå (givare åter sommar 2027), Ulricehamn (avböjt datadelning), Uniper (ingen temperatur).
- HaV (`sources/hav.py`): kod klar men gw.havochvatten.se tar timeout från GitHub Actions. Körs från användarens Windows-dator med `scripts/hav_lokal.ps1` (Schemaläggaren, måndagar).
