#!/usr/bin/env python3
"""Maakt de compacte databestanden voor de data branch.

  python3 build/build_data.py CATALOGUS.json PRIJZEN.json PRODUCTEN.json VORIGE_MAP UIT_MAP [TCGDEX_DATAS.json]

PRIJZEN en PRODUCTEN zijn de dagelijkse publieke bestanden van Cardmarket. Ontbreekt er een (download mislukt),
dan wordt de versie uit VORIGE_MAP (de vorige data branch) overgenomen, zodat de catalogus toch ververst.
"""
import collections, datetime, gzip, json, os, re, shutil, sys, unicodedata
from difflib import SequenceMatcher


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
    """Naam zonder [aanvallen], (toevoegingen), Lv.nn, accenten en tekens: 'MCharizard EX [Crimson Dive]' en 'M Charizard EX' worden gelijk."""
    s = re.sub(r"^(Unown) \[(.)\]", r"\1 \2", s or "")                       # Cardmarket: 'Unown [J] Lv.12 [...]'
    s = re.sub(r"\[(G|C|GL|FB|E4|4|M)\](?=\s*(LV|Lv|lv))", r" \1 ", s)      # Cardmarket: 'Charizard [G] LV.X', TCGdex: 'Charizard G LV.X'
    s = re.sub(r"\bLV\.?\s*X\b", " ", s, flags=re.I)                         # LV.X staat bij TCGdex vaak niet in de naam
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)
    s = re.sub(r"\bLv\.?\s*\d+\b", " ", s, flags=re.I)                         # DP tijdperk: 'Gliscor Lv.47'
    s = s.replace("♀", " f").replace("♂", " m").replace("δ", " delta")
    s = re.sub(r"\s*[☆★]|\s+Gold Star\b", " star", s)                       # Gold Star: TCGdex 'Rayquaza ☆' of 'Mewtwo Star', Cardmarket 'Rayquaza Gold Star'
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


def pkey(s):
    s = re.sub(r"\s+-\s+[^\[]*", " ", s or "").replace("Delta Species", " ")
    k = nkey(s); return k[5:] if k.startswith("basic") and k.endswith("energy") else k


LVX = re.compile(r"\bLV\.?\s*X\b", re.I)


def atkey(names):
    return frozenset(k for k in (nkey(a) for a in names or []) if k)


def atk_close(a, b):
    """Kloppen de aanvallen? None als een van beide onbekend is. Kleine spellingsverschillen ('Splintered Shard(s) GX') tellen als gelijk."""
    if not a or not b: return None
    return bool(a & b) or any(SequenceMatcher(None, x, y).ratio() >= 0.8 for x in a for y in b)


SFX = re.compile(r"\b(ex|gx|v|vmax|vstar|break|star)\b", re.I)


def sfx(n):
    """Achtervoegsels die een andere kaart maken: Pikachu en Pikachu EX, Lapras en Lapras VMAX, Rayquaza en Rayquaza ☆ (Gold Star)."""
    n = re.sub(r"\[.*?\]|\(.*?\)", " ", re.sub(r"[☆★]", " star ", n or ""))
    return frozenset(t.lower() for t in SFX.findall(n))


def clean_cm_name(n):
    """Cardmarket productnaam als kaartnaam: zonder aanvallen, Lv.nn en ' - Ghetsis' toevoegingen, [G] wordt G."""
    n = re.sub(r"\s*\[[^\]]*(\|[^\]]*)+\]\s*$|\s*\[[^\]]{3,}\]\s*$", "", n or "")
    n = re.sub(r"\[(G|C|GL|FB|M)\]", r"\1", n).replace("[4]", "E4")
    n = re.sub(r"\s+Lv\.?\s*\d+\b", "", n, flags=re.I)
    return re.sub(r"\s+", " ", n).strip()


def main_pids(c):
    """Nummers van de kaart zelf, zonder speciale uitgaven (stempel, jumbo) die vaak in een andere expansie staan."""
    s = {v["cardmarket"] for v in c.get("variants") or [] if v.get("cardmarket") and not v.get("stamp") and v.get("size") in (None, "standard")}
    if c.get("cardmarket_top"): s.add(c["cardmarket_top"])
    return s or card_pids(c)


def card_pids(c):
    s = {v["cardmarket"] for v in c.get("variants") or [] if v.get("cardmarket")}
    if c.get("cardmarket_top"): s.add(c["cardmarket_top"])
    return s


def num_order(lid):
    m = re.search(r"\d+", str(lid)); return (int(m.group()) if m else 10**6, str(lid))


def fill_missing(cards, products):
    """TCGdex mist bij een deel van de oudere kaarten het Cardmarket nummer. Koppel die via de Cardmarket productlijst:
    zelfde expansie (afgeleid uit de kaarten van de set die wel een nummer hebben, anders uit de namen), zelfde naam, bij twijfel
    zelfde aanvallen. Meerdere gelijke kaarten (gewone en full art) gaan op volgorde: laagste nummer bij laagste product id.
    Alleen koppelen als de aantallen precies kloppen, anders liever geen link dan een verkeerde."""
    exp = {p["idProduct"]: p.get("idExpansion") for p in products}
    name = {p["idProduct"]: p.get("name") or "" for p in products}
    patk = {pid: atkey([a for a in (re.search(r"\[([^\]]*\|[^\]]*|[^\]]{3,})\]\s*$", n) or [None, ""])[1].split("|")
                        if a.strip().lower() not in ("top", "bottom")]) for pid, n in name.items()}            # LEGEND [Top] is geen aanval
    by_exp = collections.defaultdict(list)
    for pid, e in exp.items(): by_exp[e].append(pid)
    by_set = collections.defaultdict(list)
    for c in cards:
        if c["region"] == "data": by_set[c["set_id"]].append(c)
    stats = collections.Counter()
    for c in cards:                                                     # TCGdex zonder naam (Arceus AR1 tot AR9): naam van Cardmarket
        if c["region"] == "data" and not c.get("name") and not any(o.get("name") and o["local_id"] == c["local_id"] for o in by_set[c["set_id"]]):
            ps = sorted(p for p in main_pids(c) if p in name)
            if ps: c["name"] = clean_cm_name(name[ps[0]]); stats["naam_aangevuld"] += 1
    # welke Cardmarket expansie(s) horen bij een set: tel alleen koppelingen waarvan naam en aanvallen kloppen.
    # (TCGdex koppelt bijvoorbeeld 62 Engelse XY promo's aan een andere expansie met heel andere kaarten)
    set_exps, primary = {}, {}
    for sid, cs in by_set.items():
        raw_cnt, agree = collections.Counter(), collections.Counter()
        for c in cs:
            ck, ca = nkey(c["name"]), atkey(c.get("attacks"))
            for p in main_pids(c):
                e = exp.get(p)
                if e is None: continue
                raw_cnt[e] += 1
                if p in name and pkey(name[p]) == ck and atk_close(ca, patk[p]) is not False: agree[e] += 1
        base = agree or raw_cnt
        if base:
            total = sum(base.values()); primary[sid] = base.most_common(1)[0][0]
            set_exps[sid] = [e for e, n in base.items() if n >= max(2, total * 0.1)] or [primary[sid]]
    # verdachte TCGdex nummers: twee kaarten in een set met hetzelfde nummer, of een product met een andere naam of andere aanvallen.
    # Die gaan mee in de koppeling; vindt die een zeker beter product, dan vervangt dat het oude nummer, anders blijft het oude staan.
    suspects = []
    for sid, cs in by_set.items():
        share = collections.defaultdict(set)
        for c in cs:
            for p in card_pids(c): share[p].add(c["local_id"])
        for c in cs:
            ps = card_pids(c)
            if not ps: continue
            ck, ca = nkey(c["name"]), atkey(c.get("attacks"))
            mp = main_pids(c)
            bad = any(len(share[p]) > 1 for p in ps) or any(p in name and pkey(name[p]) != ck for p in mp) or \
                  any(p in name and atk_close(ca, patk[p]) is False for p in mp) or \
                  (sid in set_exps and any(exp.get(p) not in set_exps[sid] for p in mp if p in exp))
            if bad:
                c["_oud"] = (c.get("variants"), c.get("cardmarket_top")); c["variants"] = None; c["cardmarket_top"] = None; suspects.append(c)
    used = set()
    for c in cards: used |= card_pids(c)

    def fits(c, pid):                                                   # aanvallen mogen elkaar niet tegenspreken
        a, b = atkey(c.get("attacks")), patk[pid]
        return not a or not b or bool(a & b)

    def assign(mc, cand):
        mc = sorted(mc, key=lambda c: num_order(c["local_id"])); cand = sorted(cand)
        pairs = list(zip(mc, cand))
        if not all(fits(c, p) for c, p in pairs): return False
        for c, pid in pairs:
            c["cardmarket_top"] = pid; c["cm_match"] = "naam"; used.add(pid); stats["gekoppeld"] += 1
        return True

    def ordered(mc, ps, known):
        """Kaarten op nummer, producten op id: alleen koppelen als de kaarten die al een nummer hebben precies op hun plek vallen."""
        cards_all = sorted(mc + [c for c, _ in known], key=lambda c: num_order(c["local_id"]))
        prods_all = sorted(set(ps) | {p for _, p in known})
        if len(cards_all) != len(prods_all): return False
        pos = {id(c): i for i, c in enumerate(cards_all)}
        if any(prods_all[pos[id(c)]] != p for c, p in known): return False
        pairs = [(c, prods_all[pos[id(c)]]) for c in mc]
        if not all(fits(c, p) for c, p in pairs): return False
        for c, pid in pairs:
            c["cardmarket_top"] = pid; c["cm_match"] = "naam"; used.add(pid); stats["gekoppeld"] += 1
        return True

    def match_group(mc, cand, lo, hi, strict, known, prim):
        cand = [p for p in cand if p not in used]
        if not cand: return
        if not strict and ordered(mc, cand, known): return
        if not strict and prim is not None and ordered(mc, [p for p in cand if exp.get(p) == prim], known): return
        # per kaart de producten met overlappende aanvallen; kaarten met dezelfde kandidaten (gewone en full art) samen op volgorde
        clusters = collections.defaultdict(list)
        for c in mc:
            a = atkey(c.get("attacks"))
            if not a: continue
            f = tuple(sorted(p for p in cand if patk[p] & a))
            if f: clusters[f].append(c)
        for f, cs in clusters.items():
            a = atkey(cs[0].get("attacks"))
            kn = [(c, p) for c, p in known if patk.get(p, frozenset()) & a or atkey(c.get("attacks")) & a]
            ps = [p for p in f if p not in used]
            if not ordered(cs, ps, kn) and not (prim is not None and ordered(cs, [p for p in ps if exp.get(p) == prim], kn)):
                ordered(cs, [p for p in ps if lo <= p <= hi], kn)       # later toegevoegde losse producten (jumbo, varianten) eruit

    for sid, cs in by_set.items():
        missing = [c for c in cs if not card_pids(c)]
        if not missing: continue
        stats["zonder"] += sum(1 for c in missing if "_oud" not in c)
        seen = sid in set_exps
        if seen:
            exps = set_exps[sid]
        else:                                                           # set zonder enkel nummer: expansie raden uit de namen
            want = collections.Counter(nkey(c["name"]) for c in missing)
            score = collections.Counter()
            for e, pids in by_exp.items():
                free = [p for p in pids if p not in used]
                if not free or len(free) > 3 * len(missing) + 10: continue
                have = collections.Counter(nkey(name[p]) for p in free)
                score[e] = sum(min(n, have[k]) for k, n in want.items())
            if not score: continue
            e, hit = score.most_common(1)[0]
            if hit < max(3, 0.6 * len(missing)): continue
            exps = [e]; stats["expansie_geraden"] += 1
        strict = not seen                                               # geraden expansie: alleen bij exact dezelfde aanvallen
        known = sorted(p for c in cs for p in card_pids(c) if exp.get(p) in exps)
        span = (known[-1] - known[0]) if known else 0
        lo, hi = (known[0] - max(60, span // 5), known[-1] + max(60, span // 5)) if known else (0, 10**12)
        # eerst met LV.X als apart kenmerk (Arceus LV.X naast twaalf gewone Arceus), daarna zonder (TCGdex laat LV.X vaak weg)
        for aware in (True, False):
            lv = (lambda t: "lvx" if LVX.search(t or "") else "") if aware else (lambda t: "")
            pool = collections.defaultdict(list)
            for e in exps:
                for pid in by_exp.get(e, []):
                    if pid not in used: pool[pkey(name[pid]) + lv(name[pid])].append(pid)
            groups, have = collections.defaultdict(list), collections.defaultdict(list)
            for c in cs:
                if not card_pids(c): groups[nkey(c["name"]) + lv(c["name"])].append(c)
                ps = sorted(p for p in card_pids(c) if exp.get(p) in exps)
                if ps: have[nkey(c["name"]) + lv(c["name"])].append((c, ps[0]))
            for key, mc in groups.items():
                if pool.get(key): match_group(mc, pool[key], lo, hi, strict, have.get(key, []), primary.get(sid))
    # Lv.X: TCGdex laat 'LV.X' vaak weg (DP18 heet daar 'Palkia'). Neem het over van het gekoppelde Cardmarket product.
    for c in cards:
        if c["region"] != "data" or LVX.search(c.get("name") or ""): continue
        if any(LVX.search(name.get(p, "")) for p in card_pids(c)):
            c["name"] = (c["name"] or "").strip() + " LV.X"; stats["lvx_naam"] += 1
            if (c.get("rarity") or "Common") in ("Common", "None"): c["rarity"] = "Rare Holo LV.X"
    for c in suspects:
        oud = c.pop("_oud")
        if c.get("cm_match"):
            c["cm_match"] = "gecorrigeerd"; stats["gekoppeld"] -= 1; stats["gecorrigeerd"] += 1
            continue
        c["variants"], c["cardmarket_top"] = oud
        # geen betere gevonden: haal alleen de nummers weg die aantoonbaar een andere kaart zijn (ander achtervoegsel zoals EX of VMAX,
        # of andere aanvallen in combinatie met een andere naam of een vreemde expansie). Bij twijfel blijft het oude nummer staan.
        ca, cs_, exps_ = atkey(c.get("attacks")), sfx(c["name"]), set_exps.get(c["set_id"])
        def wrong(p):
            if p not in name: return False
            if sfx(name[p]) != cs_: return True
            return atk_close(ca, patk[p]) is False and (pkey(name[p]) != nkey(c["name"]) or (exps_ and exp.get(p) not in exps_))
        bad = {p for p in card_pids(c) if wrong(p)}
        if bad:
            c["variants"] = [v for v in c.get("variants") or [] if v.get("cardmarket") not in bad] or None
            if c.get("cardmarket_top") in bad: c["cardmarket_top"] = None
            stats["nummer_weg"] += len(bad)
            if not card_pids(c): c["cm_match"] = "verwijderd"; stats["link_weg"] += 1
    # level (DP en Platinum: 'Dialga Lv.69') uit de Cardmarket naam, helpt bij herkennen en zoeken
    for c in cards:
        if c["region"] != "data": continue
        for p in sorted(main_pids(c)):
            m = re.search(r"\bLv\.?\s*(\d{1,3})\b", name.get(p, ""), re.I)
            if m: c["lv"] = int(m.group(1)); stats["level"] += 1; break
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
