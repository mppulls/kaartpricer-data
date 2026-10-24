#!/usr/bin/env python3
"""Kaartpricer: foto's van Pokemonkaarten -> regels voor de sheet (naam, set, nummer, trend, Cardmarket link).

  python3 kaartpricer.py setup REPO                      haalt catalogus en prijzen van de branch "data" (seconden)
  python3 kaartpricer.py strips FOTO UIT.jpg [BOXES]     leesblad met naamstrook en nummerstrook per kaart
  python3 kaartpricer.py match LEZINGEN.json RIJEN.json [--trend]   lezingen -> rijen voor de sheet
  python3 kaartpricer.py trend IN.json UIT.json          trendkolom voor rijen die al in de sheet staan
"""
import collections, difflib, gzip, json, os, re, shutil, subprocess, sys, time, unicodedata, urllib.parse

HOME = os.path.expanduser("~/kaartpricer")
CATALOG = os.path.join(HOME, "catalog.json")
PRICES = os.path.join(HOME, "prices.json")
PRODUCTS = os.path.join(HOME, "products.json")
META = os.path.join(HOME, "meta.json")
IMAGES = os.path.join(HOME, "images.json")
LINK = "https://www.cardmarket.com/en/Pokemon/Products?idProduct={pid}&sellerCountry=23&minCondition={cond}"
SEARCH = "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString={q}&sellerCountry=23&minCondition={cond}"


def cond(card):
    """Cardmarket conditie: sets uit 2016 en eerder vanaf Good (4), 2017 en nieuwer vanaf Near Mint (2)."""
    rel = (card or {}).get("set_release") or ""
    return 4 if rel and rel < "2017" else 2
HEADER = ["Naam", "Set", "Nummer", "Trend", "Opmerking", "Cardmarket (NL, NM)"]


# ---------------------------------------------------------------- setup
def setup(repo):
    """Pakt catalog, prijzen en productnamen uit origin/data van de gekloonde repo. Lukt dat niet,
    dan bouwt hij de catalogus zelf uit TCGdex (2 a 3 minuten, zonder prijzen)."""
    os.makedirs(HOME, exist_ok=True); repo = os.path.abspath(os.path.expanduser(repo))
    git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True)
    if git("fetch", "-q", "--depth", "1", "origin", "data").returncode == 0:
        for name, dest in [("catalog.json.gz", CATALOG), ("prices.json.gz", PRICES), ("products.json.gz", PRODUCTS), ("images.json.gz", IMAGES), ("meta.json", META)]:
            r = git("show", f"FETCH_HEAD:{name}")
            if r.returncode != 0:
                print("ontbreekt op data branch:", name); continue
            open(dest, "wb").write(gzip.decompress(r.stdout) if name.endswith(".gz") else r.stdout)
        meta = json.load(open(META)) if os.path.exists(META) else {}
        print("klaar | kaarten:", meta.get("kaarten"), "| prijzen van:", meta.get("prijzen_datum"), "| gebouwd:", meta.get("gebouwd"))
        return
    print("data branch niet bereikbaar, catalogus zelf bouwen (zonder prijzen)")
    db = os.path.join(HOME, "tcgdex-db")
    if not os.path.isdir(db):
        subprocess.run(["git", "clone", "--depth", "1", "-q", "https://github.com/tcgdex/cards-database.git", db], check=True)
    if not shutil.which("bun"):
        subprocess.run(["npm", "i", "-g", "bun"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["bun", os.path.join(repo, "build", "export.ts"), db, CATALOG], check=True)


# ---------------------------------------------------------------- leesblad
def strips(photo, out, boxes_path=None):
    """Maakt 1 afbeelding met per kaart de naamstrook (boven) en de nummerstrook (onder), vergroot.
    BOXES is een JSON lijst [{"pos":"r1c1","box":[x0,y0,x1,y1]}] in fracties van de foto (0..1).
    Zonder BOXES: 3 x 3 raster, goed voor een rechte foto van 1 binderpagina."""
    from PIL import Image, ImageDraw, ImageOps
    try:
        import pillow_heif; pillow_heif.register_heif_opener()
    except ImportError:
        if photo.lower().endswith((".heic", ".heif")):
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "pillow-heif"], check=True)
            import pillow_heif; pillow_heif.register_heif_opener()
    im = ImageOps.exif_transpose(Image.open(photo)).convert("RGB"); W, H = im.size
    if boxes_path:
        boxes = json.load(open(boxes_path))
    else:
        m = 0.02  # kleine overlap, kaarten zitten zelden precies in het raster
        boxes = [{"pos": f"r{r+1}c{c+1}", "box": [max(0, c / 3 - m), max(0, r / 3 - m), min(1, (c + 1) / 3 + m), min(1, (r + 1) / 3 + m)]}
                 for r in range(3) for c in range(3)]
    CW = 700; tiles = []
    for b in boxes:
        x0, y0, x1, y1 = b["box"]; card = im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        s = CW / card.width; card = card.resize((CW, int(card.height * s)), Image.LANCZOS); h = card.height
        top = card.crop((0, 0, CW, int(h * 0.21))); bot = card.crop((0, int(h * 0.72), CW, h))
        t = Image.new("RGB", (CW, top.height + bot.height + 22), "white")
        ImageDraw.Draw(t).text((4, 4), b["pos"], fill="black"); t.paste(top, (0, 20)); t.paste(bot, (0, 20 + top.height)); tiles.append(t)
    rows = (len(tiles) + 1) // 2; th = max(t.height for t in tiles)
    sheet = Image.new("RGB", (CW * 2 + 10, rows * (th + 6)), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % 2) * (CW + 10), (i // 2) * (th + 6)))
    sheet.save(out, quality=88); print(out, sheet.size, f"foto {W}x{H}, kaartbreedte ca. {int((boxes[0]['box'][2]-boxes[0]['box'][0])*W)} px")


# ---------------------------------------------------------------- koppelen
LABELS = {"ultra", "rare", "mega", "attack", "full", "art", "alt", "sir", "ir", "hyper", "gold", "secret",
          "illustration", "special", "holo", "reverse", "promo"}
SUFFIXES = {"ex", "gx", "v", "vmax", "vstar", "break", "lv", "x", "star"}
PLAIN = {"common", "uncommon", "rare", "holo rare", "double rare", "holo rare v", "holo rare vmax", "holo rare vstar",
         "none", "rare holo", "amazing rare"}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().replace("'s", "")
    return re.sub(r"[^a-z0-9 ]+", " ", s).split()


def sim(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def name_score(query, cand):
    q, c = norm(query), norm(cand)
    qs = [t for t in q if t not in SUFFIXES and t not in LABELS] or [t for t in q if t not in SUFFIXES]
    cs = [t for t in c if t not in SUFFIXES]
    if not qs or not cs:
        return 0.0
    rc = sum(1 for t in cs if max(sim(t, u) for u in qs) >= 0.72) / len(cs)
    rq = sum(1 for u in qs if max(sim(u, t) for t in cs) >= 0.72) / len(qs)
    return round(max(sim("".join(qs), "".join(cs)), 0.6 * max(rc, rq) + 0.4 * min(rc, rq)), 3)


def parse_number(num):
    num = (num or "").strip().upper().replace(" ", ""); left, _, right = num.partition("/")
    m = re.fullmatch(r"([A-Z]*)0*(\d+)([A-Z]?)", left)
    return (m.group(1) + m.group(2) + m.group(3)) if m else left, (int(right) if right.isdigit() else None)


class Catalog:
    def __init__(self, path=CATALOG):
        self.cards = json.load(open(path, encoding="utf-8")); self.by_local = collections.defaultdict(list)
        for c in self.cards:
            self.by_local[parse_number(c["local_id"])[0]].append(c)

    def decide(self, name, number, set_code=None, region="data"):
        lid, total = parse_number(number); out = []
        for c in self.by_local.get(lid, []):
            if c["region"] != region:
                continue
            ns = name_score(name, c["name"] or "") if name else 0.5; score = ns; anchored = False
            if total is not None:
                if c["set_official"] == total: score += 0.5; anchored = True
                else: score -= 0.35
            if set_code and c["set_abbr"] and set_code.upper() == c["set_abbr"].upper(): score += 0.6; anchored = True
            if ns >= 0.4 or (set_code and anchored):
                out.append((score, ns, anchored, c))
        out.sort(key=lambda x: -x[0])
        if not out:
            return "geen", None
        best = out[0]
        if len(out) > 1 and best[0] - out[1][0] < 0.15:
            return "twijfel", best[3]
        if (best[2] and best[1] >= 0.55) or (not best[2] and best[1] >= 0.85):
            return "zeker", best[3]
        return "twijfel", best[3]

    def by_name(self, name, hp=None, attacks=None, lang="en"):
        out = []
        for c in self.cards:
            if (lang == "en") != (c["region"] == "data"):
                continue
            nm = c["name"] if lang == "en" else (c.get("names") or {}).get(lang)
            if not nm:
                continue
            if lang == "en":
                if norm(nm) != norm(name) and name_score(name, nm) < 0.8: continue
                if [t for t in norm(nm) if t in SUFFIXES] != [t for t in norm(name) if t in SUFFIXES]: continue
            elif nm.replace(" ", "") != name.replace(" ", ""):
                continue
            if hp and c.get("hp") and int(c["hp"]) != int(hp): continue
            if attacks and lang == "en":
                have = {" ".join(norm(a)) for a in c.get("attacks") or []}
                if not any(" ".join(norm(a)) in have for a in attacks): continue
            out.append(c)
        return out


def products(card):
    seen, out = set(), []
    for v in card.get("variants") or []:
        pid = v.get("cardmarket")
        if not pid or pid in seen:
            continue
        seen.add(pid); label, special = v.get("type") or "?", 0
        if v.get("stamp"): label += " met stempel " + "/".join(v["stamp"]); special += 2
        if v.get("size") and v["size"] != "standard": label += " " + str(v["size"]); special += 4
        if v.get("foil"): label += " " + str(v["foil"]) + " foil"; special += 1
        out.append((special, pid, label))
    if card.get("cardmarket_top") and card["cardmarket_top"] not in seen:
        out.append((0, card["cardmarket_top"], "standaard"))
    return [(p, l) for _, p, l in sorted(out, key=lambda x: x[0])]


def tag(c):
    return f"{c['set_abbr'] or c['set_id']} {c['local_id']}"


def printed_number(card, read):
    """Alleen het eigen nummer van de kaart, zonder het totaal van de set. Moderne kaarten met 3 cijfers (043)."""
    lid = card["local_id"]; left = (read or "").upper().replace(" ", "").partition("/")[0]
    if left and parse_number(left)[0] == parse_number(lid)[0]:
        return left
    return lid.zfill(3) if lid.isdigit() and (card.get("set_release") or "") >= "2020" else lid


def set_label(card):
    """Setnaam met de officiele setcode erachter, bv. 'Destined Rivals (DRI)'. Aziatische sets krijgen hun set id."""
    name = card.get("set_name") or ""; code = card.get("set_abbr") or (card.get("set_id") if card.get("region") != "data" else None)
    return f"{name} ({code})" if code else name


def identify(cat, r):
    lang = r.get("lang") or "en"
    if r.get("pick"):                                   # keuze van Claude uit eerder getoonde kandidaten
        ps, pn = r["pick"]
        hit = [c for c in cat.cards if (c["set_abbr"] or c["set_id"] or "").upper() == ps.upper() and parse_number(c["local_id"])[0] == parse_number(pn)[0]]
        if hit:
            return "gekozen", hit[0], []
    if r.get("number") and lang == "en":
        st, card = cat.decide(r.get("name"), r["number"], r.get("set_code"))
        if st == "zeker":
            return "zeker", card, []
    cands = cat.by_name(r.get("name") or "", r.get("hp"), r.get("attacks"), lang)
    if not cands:
        return "geen", None, []
    total = parse_number(r.get("number") or "")[1]
    if total:
        cands = [c for c in cands if c["set_official"] == total] or cands
    if r.get("art") and len(cands) > 1:
        full = [c for c in cands if (c.get("rarity") or "none").lower() not in PLAIN]
        cands = (full if r["art"] == "full" else [c for c in cands if c not in full]) or cands
    if len(cands) == 1:
        return "terugval", cands[0], []
    return "twijfel", cands[0], cands


def load_prices():
    if not os.path.exists(PRICES):
        return None, {}
    p = json.load(open(PRICES, encoding="utf-8")); return p.get("datum"), p.get("prijzen", {})


def load_products():
    return json.load(open(PRODUCTS, encoding="utf-8")).get("producten", {}) if os.path.exists(PRODUCTS) else {}


def trend_value(prices, pid, reverse=False):
    """Trend van Cardmarket (alle Engelse en anderstalige verkopen samen, alle condities). Reverse holo: trend_reverse."""
    p = prices.get(str(pid)) if pid else None
    if not p:
        return ""
    v = p[3] if reverse else p[0]
    return v if v is not None else ""


def pid_from_link(link):
    m = re.search(r"idProduct=(\d+)", link or ""); return m.group(1) if m else None


def match(readings_path, rows_path, with_trend=False):
    cat = Catalog(); R = json.load(open(readings_path, encoding="utf-8")); rows = []; stat = collections.Counter()
    pdate, prices = load_prices() if with_trend else (None, {}); pnames = load_products()
    for r in R:
        st, card, cands = identify(cat, r); stat[st] += 1; lang = r.get("lang") or "en"; notes = []; pid = None
        rev = bool(r.get("reverse"))
        if card:
            prods = products(card); name = card["name"] or r.get("name_en") or r.get("name"); setn = set_label(card)
            if lang != "en": name = f"{name} ({lang.upper()})"
            num = printed_number(card, r.get("number"))
            if prods:
                pid = prods[0][0]; link = LINK.format(pid=pid, cond=cond(card)) + ("&language=1" if lang == "en" else "") + ("&isReverseHolo=Y" if rev else "")
                cm = pnames.get(str(pid))
                if cm and lang == "en" and name_score(card["name"] or "", cm) < 0.6:
                    notes.append(f"Controleer link: Cardmarket product heet '{cm}'")
            else:
                link = SEARCH.format(q=urllib.parse.quote(f"{name} {card['local_id']}"), cond=cond(card)); notes.append("Geen directe Cardmarket koppeling, dit is een zoeklink")
            if st == "terugval": notes.append("Nummer niet goed leesbaar, gevonden op naam, HP en aanval")
            if st == "gekozen": notes.append("Nummer niet leesbaar, gekozen op artwork. Controleer")
            if st == "twijfel": notes.append("CONTROLEER, kan ook zijn: " + ", ".join(tag(c) for c in cands[1:6]))
            for vpid, label in [x for x in prods[1:] if "jumbo" not in x[1]][:2]:   # jumbo herken je zelf wel
                notes.append(f"Variant {label}: " + LINK.format(pid=vpid, cond=cond(card)))
        else:
            name, setn, num = r.get("name_en") or r.get("name") or "?", "", r.get("number") or ""
            link = SEARCH.format(q=urllib.parse.quote(name), cond=2); notes.append("NIET IN CATALOGUS, zoeklink")
            if lang != "en": name = f"{name} ({lang.upper()})"
        if rev: notes.insert(0, "Reverse holo")
        if r.get("note"): notes.append(r["note"])
        tr = trend_value(prices, pid, rev) if with_trend else ""
        row = [name, setn, ("'" + num) if num else "", tr, " | ".join(notes), link]
        rows += [row] * int(r.get("qty") or 1)
        if st != "zeker":
            print(f"{st:8} {r.get('photo','')} {r.get('pos','')} {r.get('name')!s:.26} -> {(tag(card) + ' ' + str(card['rarity'])) if card else 'niets'}"
                  + (" | kandidaten: " + "; ".join(f"{tag(c)} {c['rarity']}" for c in cands[:8]) if cands else ""))
    json.dump([HEADER] + rows, open(rows_path, "w", encoding="utf-8"), ensure_ascii=False)
    extra = f" | trend van {pdate}, {sum(1 for x in rows if x[3] != '')} van {len(rows)} gevonden" if with_trend else ""
    print(f"{len(rows)} rijen in {rows_path} |", dict(stat), extra)


def trend(in_path, out_path):
    """IN: rijen zoals ze in de sheet staan (A tot F, met of zonder kop). UIT: de kolom Trend, 1 waarde per rij."""
    pdate, prices = load_prices(); rows = json.load(open(in_path, encoding="utf-8")); col = []; found = 0
    if not prices:
        sys.exit("geen prijsbestand, draai eerst setup")
    for row in rows:
        row = list(row) + [""] * 6
        if row[0] == "Naam":
            col.append(["Trend"]); continue
        pid = pid_from_link(row[5]); v = trend_value(prices, pid, "reverse holo" in str(row[4]).lower())
        found += v != ""; col.append([v])
    json.dump(col, open(out_path, "w"), ensure_ascii=False)
    print(f"trend van {pdate}: {found} van {sum(1 for c in col if c != ['Trend'])} rijen | som {round(sum(c[0] for c in col if isinstance(c[0], (int, float))), 2)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup": setup(sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(__file__)))
    elif cmd == "strips": strips(*sys.argv[2:5])
    elif cmd == "match": match(sys.argv[2], sys.argv[3], "--trend" in sys.argv)
    elif cmd == "trend": trend(sys.argv[2], sys.argv[3])
    else: print(__doc__)
