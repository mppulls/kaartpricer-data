// Gedeelde hulpjes voor het serverdeel van MP Kaartscan (Cloudflare Pages Functions).
export const json = (obj, status = 200, headers = {}) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers } });

const enc = new TextEncoder();
export async function teamToken(env) {
  const key = await crypto.subtle.importKey("raw", enc.encode(String(env.TEAM_CODE || "")), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode("kaartscan-v1"));
  return [...new Uint8Array(sig)].map(b => b.toString(16).padStart(2, "0")).join("");
}
export function cookie(req, name) {
  const m = new RegExp("(?:^|;\\s*)" + name + "=([^;]+)").exec(req.headers.get("cookie") || "");
  return m ? decodeURIComponent(m[1]) : null;
}

let ready = false;
export async function ensureSchema(db) {
  if (ready) return;
  await db.batch([
    db.prepare("CREATE TABLE IF NOT EXISTS docs (path TEXT PRIMARY KEY, parent TEXT NOT NULL, id TEXT NOT NULL, data TEXT, u INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)"),
    db.prepare("CREATE INDEX IF NOT EXISTS docs_parent_u ON docs (parent, u)"),
    db.prepare("CREATE TABLE IF NOT EXISTS usage (day TEXT PRIMARY KEY, n INTEGER NOT NULL)"),
  ]);
  ready = true;
}

// paden zoals in de app: collectie/doc/collectie/doc, alleen veilige tekens
export function checkPath(p, wantDoc) {
  if (typeof p !== "string" || p.length > 500) return null;
  const seg = p.split("/");
  if (!seg.every(s => /^[A-Za-z0-9_\-.~:@+]{1,120}$/.test(s) && s !== "." && s !== "..")) return null;
  if (wantDoc !== undefined && (seg.length % 2 === 0) !== wantDoc) return null;
  return seg;
}
