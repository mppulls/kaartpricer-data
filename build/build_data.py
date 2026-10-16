#!/usr/bin/env python3
"""Maakt de compacte databestanden voor de data branch.

  python3 build/build_data.py CATALOGUS.json PRIJZEN.json PRODUCTEN.json VORIGE_MAP UIT_MAP [TCGDEX_DATAS.json]

PRIJZEN en PRODUCTEN zijn de dagelijkse publieke bestanden van Cardmarket. Ontbreekt er een (download mislukt),
dan wordt de versie uit VORIGE_MAP (de vorige data branch) overgenomen, zodat de catalogus toch ververst.
"""
import datetime, gzip, json, os, shutil, sys


def dump_gz(obj, path):
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("niet bruikbaar:", path, str(e)[:120]); return None


def main(cat_path, price_path, prod_path, prev_dir, out, datas_path=None):
    os.makedirs(out, exist_ok=True); meta = {"gebouwd": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")}
    cards = []
    for c in load(cat_path):
        if c["region"] == "data":
            c["names"] = None                                   # Engelse kaarten: alleen de Engelse naam nodig
        c["variants"] = [v for v in (c.get("variants") or []) if v.get("cardmarket")] or None
        cards.append(c)
    assert len(cards) > 30000, f"catalogus te klein: {len(cards)}"
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
    pl = load(prod_path) if prod_path else None
    if pl and pl.get("products"):
        dump_gz({"datum": pl.get("createdAt"), "producten": {str(p["idProduct"]): p.get("name") for p in pl["products"]}},
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
