# kaartpricer-data

Gereedschap en data voor de kaartpricer skill van MP Collectibles.

* `kaartpricer.py`: herkent kaarten uit fotolezingen en maakt de rijen voor de Google Sheet.
* `build/`: bouwt de compacte kaartencatalogus uit de open TCGdex database.
* `.github/workflows/data.yml`: draait elke nacht rond 03:30 en zet op de branch `data`:
  * `catalog.json.gz`: alle Engelse en Aziatische kaarten met set, nummer, HP, aanvallen en Cardmarket product.
  * `prices.json.gz`: de publieke prijslijst van Cardmarket van die ochtend (trend, avg7, avg30, trend reverse holo, low).
  * `products.json.gz`: productnamen van Cardmarket, om koppelingen te controleren.
  * `meta.json`: datum en aantallen.

De branch `data` wordt elke dag overschreven zonder geschiedenis, zo blijft de repo klein.
* `app/index.html`: de scan app (claude.ai artifact "MP Kaartscan"). `build/app_data.py` maakt er `catalog.json` en `prices.json` bij;
  een geplande Claude taak zet die elke ochtend in de app.
  Opslag in de artifact database: `lijsten/<id>` (naam, pct, afgerond), `lijsten/<id>/scans` (werklijst) en `lijsten/<id>/inkopen` (opgeslagen inkopen met kaarten, betaald bedrag en inkoopprijs per kaart).

Handmatig verversen: tabblad Actions, workflow "data", Run workflow.

Houd deze repo privé: de prijslijst van Cardmarket is voor eigen gebruik.

## Losse app (Cloudflare Pages)

* `web/`: serverdeel (`functions/`), statische bestanden (`public/`), Apps Script voor de sheet en `SETUP.md` met de stappen.
* `build/web_build.py` maakt van `app/index.html` de losse versie; de workflow zet het resultaat elke nacht en bij elke wijziging op de branch `site`, waar Cloudflare Pages van publiceert.
* `web/seed.json` is een eenmalige export van de Claude versie, te importeren via het menu van de app.
