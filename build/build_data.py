#!/usr/bin/env python3
"""Maakt de compacte databestanden voor de data branch.

  python3 build/build_data.py CATALOGUS.json PRIJZEN.json PRODUCTEN.json VORIGE_MAP UIT_MAP [TCGDEX_DATAS.json]

PRIJZEN en PRODUCTEN zijn de dagelijkse publieke bestanden van Cardmarket. Ontbreekt er een (download mislukt),
dan wordt de versie uit VORIGE_MAP (de vorige data branch) overgenomen, zodat de catalogus toch ververst.
"""
import collections, datetime, gzip, json, os, re, shutil, sys, unicodedata


def dump_gz(obj, path):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("niet bruikbaar:", path, str(e)[:120]); return None


def nkey(s):
    """Naam zonder [aanvallen], (toevoegingen), accenten en tekens: 'MCharizard EX [Crimson Dive]' en 'M Charizard EX' worden gelijk."""
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s or "").replace("♀", " f").replace("♂", " m").replace("δ", " delta")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def atkey(names):
    return frozenset(k for k in (nkey(a) for a in names or []) if k)


def card_pids(c):
    s = {v["cardmarket"] for v in c.get("variants") or [] if v.get("cardmarket")}
    if c.get("cardmarket_top"): s.add(c["cardmarket_top"])
    return s


def num_order(lid):
    m = re.search(r"\d+", str(lid)); return (int(m.group()) if m else 10**6, str(lid))


def fill_missing(cards, products):
    """TCGdex mist bij een deel van de oudere kaarten het Cardmarket nummer. Koppel die via de Cardmarket productlijst:
    zelfde expansie (afgeleid uit de kaarten van de set die wel een nummer hebben), zelfde naam, bij twijfel zelfde aanvallen.
    Meerdere gelijke kaarten in een set (gewone en full art) gaan op volgorde: laagste nummer bij laagste product id."""
    exp = {p["idProduct"]: p.get("idExpansion") for p in products}
    name = {p["idProduct"]: p.get("name") or "" for p in products}
    by_exp = collections.defaultdict(list)
    for pid, e in exp.items(): by_exp[e].append(pid)
    used = set()
    for c in cards: used |= card_pids(c)
    by_set = collections.defaultdict(list)
    for c in cards:
        if c["region"] == "data": by_set[c["set_id"]].append(c)
    stats = collections.Counter()
    for sid, cs in by_set.items():
        missing = [c for c in cs if not card_pids(c)]
        if not missing: continue
        stats["zonder"] += len(missing)
        seen = collections.Counter(exp[p] for c in cs for p in card_pids(c) if p in exp)
        if not seen: continue
        total = sum(seen.values()); exps = [e for e, n in seen.items() if n >= max(2, total * 0.1)] or [seen.most_common(1)[0][0]]
        pool = collections.defaultdict(list)
        for e in exps:
            for pid in by_exp.get(e, []):
                if pid not in used: pool[nkey(name[pid])].append(pid)
        groups = collections.defaultdict(list)
        for c in missing: groups[nkey(c["name"])].append(c)
        for key, mc in groups.items():
            cand = sorted(pool.get(key, []))
            if not cand: continue
            mc = sorted(mc, key=lambda c: num_order(c["local_id"]))
            pairs = []
            if len(cand) == len(mc): pairs = list(zip(mc, cand))
            elif len(mc) == 1:
                same = [p for p in cand if atkey((re.search(r"\[(.*)\]", name[p]) or [None, ""])[1].split("|")) == atkey(mc[0].get("attacks"))]
                if len(same) == 1: pairs = [(mc[0], same[0])]
            for c, pid in pairs:
                c["cardmarket_top"] = pid; c["cm_match"] = "naam"; used.add(pid); stats["gekoppeld"] += 1
                pool[key].remove(pid)
    return dict(stats)


def main(cat_path, price_path, prod_path, prev_dir, out, datas_path=None):
    os.makedirs(out, exist_ok=True); meta = {"gebouwd": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")}
    cards = []
    for c in load(cat_path):
        if c["region"] == "data":
            c["names"] = None                                   # Engelse kaarten: alleen de Engelse naam nodig
        c["variants"] = [v for v in (c.get("variants") or []) if v.get("cardmarket")] or None
        cards.append(c)
    assert len(cards) > 30000, f"catalogus te klein: {len(cards)}"
    pl = load(prod_path) if prod_path else None
    if pl and pl.get("products"):
        meta["cm_koppeling"] = fill_missing(cards, pl["products"]); print("cardmarket koppeling:", meta["cm_koppeling"])
    dump_gz(cards, os.path.join(out, "catalog.json.gz")); meta["kaarten"] = len(cards)

    pg = load(price_path) if price_path else None
    if pg and pg.get("priceGuides"):
        r2 = lambda x: round(x, 2) if isinstance(x, (int, float)) else None
        prices = {str(p["idProduct"]): [r2(p.get("trend")), r2(p.get("avg7")), r2(p.get("avg30")), r2(p.get("trend-holo")), r2(p.get("low"))]
                  for p in pg["priceGuides"]}
        dump_gz({"datum": pg.get("createdAt"), "velden": ["trend", "avg7", "avg30", "trend_reverse", "low"], "prijzen": prices},
                os.path.join(out, "prices.json.gz"))
        meta["prijzen_datum"] = pg.get("createdAt"); meta["prijzen"] = len(prices)
    elif os.path.exists(os.path.join(prev_dir, "prices.json.gz")):
        shutil.copy(os.path.join(prev_dir, "prices.json.gz"), out); meta["prijzen_datum"] = "OUD, download mislukt"
    if pl and pl.get("products"):
        dump_gz({"datum": pl.get("createdAt"), "producten": {str(p["idProduct"]): p.get("name") for p in pl["products"]},
                 "expansie": {str(p["idProduct"]): p.get("idExpansion") for p in pl["products"]}},
                os.path.join(out, "products.json.gz")); meta["producten"] = len(pl["products"])
    elif os.path.exists(os.path.join(prev_dir, "products.json.gz")):
        shutil.copy(os.path.join(prev_dir, "products.json.gz"), out)
    # welke kaarten een scan hebben op assets.tcgdex.net (alleen Engels): {serie: {set: [nummers]}}
    dt = load(datas_path) if datas_path else None
    if dt and isinstance(dt.get("en"), dict):
        img = {serie: {st: sorted(cards.keys()) for st, cards in sets.items() if isinstance(cards, dict)} for serie, sets in dt["en"].items() if isinstance(sets, dict)}
        dump_gz(img, os.path.join(out, "images.json.gz")); meta["plaatjes"] = sum(len(v) for s in img.values() for v in s.values())
    elif os.path.exists(os.path.join(prev_dir, "images.json.gz")):
        shutil.copy(os.path.join(prev_dir, "images.json.gz"), out)
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=1); print(meta)


if __name__ == "__main__":
    main(*sys.argv[1:7])
