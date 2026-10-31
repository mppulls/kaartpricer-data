// Kaartscans van TCGdex, via Cloudflare gecachet zodat ze snel laden en op de telefoon bewaard blijven.
//  /img/<serie>/<set>/<nummer>.webp  ->  https://assets.tcgdex.net/en/<serie>/<set>/<nummer>/low.webp
export async function onRequest(ctx) {
  const url = new URL(ctx.request.url);
  const m = /^\/img\/([A-Za-z0-9.\-]{1,30})\/([A-Za-z0-9.\-]{1,30})\/([A-Za-z0-9.\-]{1,20})\.webp$/.exec(url.pathname);
  if (!m) return new Response("Niet gevonden", { status: 404 });
  const cache = caches.default;
  const key = new Request(url.origin + url.pathname);
  let res = await cache.match(key);
  if (res) return res;
  const up = await fetch(`https://assets.tcgdex.net/en/${m[1]}/${m[2]}/${m[3]}/low.webp`, { cf: { cacheTtl: 2592000, cacheEverything: true } });
  if (!up.ok) return new Response("Geen scan", { status: 404, headers: { "cache-control": "public, max-age=86400" } });
  res = new Response(up.body, { headers: { "content-type": "image/webp", "cache-control": "public, max-age=2592000, immutable" } });
  ctx.waitUntil(cache.put(key, res.clone()));
  return res;
}
