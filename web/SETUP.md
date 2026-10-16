# MP Kaartscan los van Claude: opzetten

Reken op ongeveer 20 minuten, achter je laptop. Alles hieronder doe je één keer.

## 1. Claude API sleutel

1. Maak een account op console.anthropic.com. Dit staat los van je gewone Claude abonnement.
2. Ga naar Billing en zet er tegoed op. Met €10 kun je duizenden binderpagina's scannen.
3. Ga naar API keys, kies Create Key en noem hem `kaartscan`. Kopieer de sleutel meteen, je ziet hem maar één keer.

## 2. Cloudflare

1. Maak een gratis account op dash.cloudflare.com.
2. Ga naar Workers & Pages, kies Create, het tabblad Pages en dan Connect to Git. Geef Cloudflare toegang tot GitHub en kies `mppulls/kaartpricer-data`.
3. Vul bij de instellingen in:
   * Production branch: `site`
   * Framework preset: None
   * Build command: leeg laten
   * Build output directory: `public`

   Klik op Save and Deploy. De eerste versie werkt nog niet helemaal, dat klopt.
4. Ga naar Storage & Databases, D1, Create database en noem hem `kaartscan`.
5. Open je Pages project, Settings, Bindings (in oudere schermen: Functions). Voeg een D1 database toe met variabelenaam `DB` en kies `kaartscan`.
6. Ga naar Settings, Variables and Secrets en voeg deze toe als Secret:
   * `TEAM_CODE`: de code waarmee jullie inloggen.
   * `ANTHROPIC_API_KEY`: de sleutel uit stap 1.
   * `SHEET_HOOK_SECRET`: een lange willekeurige tekst die je zelf verzint.

   `SHEET_HOOK_URL` komt in stap 3.
7. Ga naar Deployments en kies bij de bovenste versie Retry deployment. Dan worden de koppelingen actief.

## 3. Koppeling met je Google Sheet

1. Open de Kaartpricer sheet en kies Extensies, Apps Script.
2. Vervang alles in `Code.gs` door de inhoud van `web/apps-script/Code.gs`.
3. Open Projectinstellingen (tandwiel) en voeg bij Scripteigenschappen toe: `SECRET` met dezelfde tekst als `SHEET_HOOK_SECRET`.
4. Kies Implementeren, Nieuwe implementatie, type Web-app. Uitvoeren als: jijzelf. Toegang: iedereen. Geef toestemming en kopieer de URL van de web-app.
5. Zet die URL in Cloudflare als `SHEET_HOOK_URL` (gewone variabele is goed) en kies weer Retry deployment.

## 4. Op je telefoon

1. Open `https://<naam van je project>.pages.dev`.
2. Vul de teamcode in. Je blijft een jaar ingelogd.
3. Kies wie je bent (Mees of Plien). Iedereen heeft eigen lijsten, inkopen en dag afronden.
4. In Safari: Delen, Zet op beginscherm. Open de app vanaf het beginscherm en kies daar nog één keer je naam.
5. Alleen Mees, eenmalig: menu, Lijsten uit Claude importeren. Die lijsten worden van Mees.

Plien doet stap 1 tot en met 4 op haar eigen telefoon. Elkaars lijsten zie je onder Lijsten, bij "Van Mees" of "Van Plien".

## Goed om te weten

* Prijzen en kaartdata ververst GitHub elke nacht. Cloudflare zet de nieuwe versie daarna vanzelf online.
* Er is een daglimiet van 1500 leesrondes tegen misbruik. Aanpassen kan met de variabele `DAILY_LIMIT`.
* Snel lezen gebruikt Claude Haiku 5.5, Opnieuw lezen nauwkeurig gebruikt Claude Sonnet 5.5. Andere modellen kun je instellen met `MODEL_QUICK` en `MODEL_ACCURATE`.
* Kaartscans komen van TCGdex en worden bij Cloudflare en op je telefoon bewaard. Gebruik ze alleen in de app, niet in advertenties of op je website.
