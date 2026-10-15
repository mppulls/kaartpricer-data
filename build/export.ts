// Zet de TCGdex kaartendatabase (TypeScript bestanden) om naar 1 JSON bestand.
// Gebruik: bun build/export.ts <pad naar cards-database> <uit.json>
import { Glob } from "bun";
import path from "node:path";
const root = path.resolve(process.argv[2]); const out = process.argv[3]; const rows: any[] = []; let failed = 0;
for (const region of ["data", "data-asia"]) {
  const base = path.join(root, region);
  for await (const rel of new Glob("*/*/*.ts").scan({ cwd: base })) {
    try {
      const c = (await import(path.join(base, rel))).default; const s = c.set ?? {};
      if (s.serie?.id === "tcgp") continue;
      rows.push({
        region, set_id: s.id ?? null, set_name: s.name?.en ?? s.name?.ja ?? s.name?.["zh-tw"] ?? null,
        set_abbr: s.abbreviations?.official ?? null, set_official: s.cardCount?.official ?? null,
        set_release: typeof s.releaseDate === "string" ? s.releaseDate : (s.releaseDate?.en ?? s.releaseDate?.ja ?? null),
        local_id: path.basename(rel, ".ts"), name: c.name?.en ?? null, names: c.name ?? null,
        rarity: c.rarity ?? null, hp: c.hp ?? null,
        attacks: (c.attacks ?? []).map((a: any) => a?.name?.en ?? null).filter(Boolean),
        variants: Array.isArray(c.variants) ? c.variants.map((v: any) => ({ type: v.type ?? null, size: v.size ?? null,
          stamp: v.stamp ?? null, foil: v.foil ?? null, cardmarket: v.thirdParty?.cardmarket ?? null })) : null,
        cardmarket_top: c.thirdParty?.cardmarket ?? null,
      });
    } catch (e) { failed++; }
  }
}
await Bun.write(out, JSON.stringify(rows)); console.log(`kaarten: ${rows.length}, mislukt: ${failed}`);
