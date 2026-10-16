#!/usr/bin/env python3
"""Maakt de databestanden voor de scan app uit de data van setup (~/kaartpricer).

  python3 build/app_data.py UIT_MAP

catalog.json: Engelse kaarten, compact.  sets: [id, naam, code, totaal, release, serie, plaatjes set]
  kaarten: [set index, nummer, naam, hp, "aanval|aanval", zeldzaamheid index, [cardmarket ids], plaatje]
  plaatje: 0 geen scan, 1 scan onder de eigen set, 2 scan onder de hoofdset (trainer gallery, galarian gallery, shiny vault).
  Een scan staat op https://assets.tcgdex.net/en/<serie>/<set>/<nummer>/low.webp
prices.json: {"datum": ..., "p": {id: [trend, trend reverse holo]}} alleen voor ids in de catalogus.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import re
from kaartpricer import CATALOG, PRICES, IMAGES, products

out = sys.argv[1]; os.makedirs(out, exist_ok=True)
cards = [c for c in json.load(open(CATALOG, encoding="utf-8")) if c["region"] == "data" and c.get("name")]
imgs = json.load(open(IMAGES, encoding="utf-8")) if os.path.exists(IMAGES) else None
parent_of = lambda sid: re.sub(r"(tg|gg|sv|cc)$", "", sid or "")
def has_img(serie, sid, lid):
    return bool(imgs and lid in set(imgs.get(serie or "", {}).get(sid, [])))
sets, sidx, rar, ridx, rows, pids = [], {}, [], {}, [], set()
for c in sorted(cards, key=lambda c: (c.get("set_release") or "", c["set_id"] or "")):
    k = c["set_id"]
    if k not in sidx:
        sidx[k] = len(sets); sets.append([k, c.get("set_name") or k, c.get("set_abbr") or "", c.get("set_official") or 0, c.get("set_release") or "",
                                          c.get("serie_id") or "", parent_of(k)])
    r = c.get("rarity") or ""
    if r not in ridx:
        ridx[r] = len(rar); rar.append(r)
    ps = [p for p, label in products(c) if "jumbo" not in label]
    pids.update(ps)
    if imgs is None: img = 1 if c.get("serie_id") else 0
    else: img = 1 if has_img(c.get("serie_id"), k, c["local_id"]) else (2 if parent_of(k) != k and has_img(c.get("serie_id"), parent_of(k), c["local_id"]) else 0)
    rows.append([sidx[k], c["local_id"], c["name"], c.get("hp") or 0, "|".join(c.get("attacks") or []), ridx[r], ps, img])
json.dump({"sets": sets, "rarities": rar, "cards": rows}, open(os.path.join(out, "catalog.json"), "w", encoding="utf-8"),
          ensure_ascii=False, separators=(",", ":"))
p = json.load(open(PRICES, encoding="utf-8")) if os.path.exists(PRICES) else {"datum": None, "prijzen": {}}
small = {str(i): [p["prijzen"][str(i)][0], p["prijzen"][str(i)][3]] for i in pids if str(i) in p["prijzen"]}
json.dump({"datum": p.get("datum"), "p": small}, open(os.path.join(out, "prices.json"), "w"), separators=(",", ":"))
print(f"{len(rows)} kaarten, {len(sets)} sets, {len(small)} prijzen van {p.get('datum')}, met scan: {sum(1 for r in rows if r[7])}")
for f in ("catalog.json", "prices.json"):
    print(f, os.path.getsize(os.path.join(out, f)) // 1024, "KB")
