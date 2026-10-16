// API van MP Kaartscan.
//  POST /api/login            {code}            zet de inlogcookie
//  GET  /api/docs?parent=&since=                documenten van een collectie die sinds `since` zijn veranderd
//  GET  /api/doc?path=                          een document
//  PUT  /api/doc              {path, data}      document opslaan
//  DELETE /api/doc?path=                        document verwijderen
//  POST /api/read             {prompt, images, tier}   foto's laten lezen door Claude (stream)
//  POST /api/sheet            {title, values}   tabblad in de Google Sheet via Apps Script
//  GET  /api/me                                 status voor de app
import { json, teamToken, ensureSchema, checkPath } from "../_lib.js";

export async function onRequest(ctx) {
  const { request, env } = ctx;
  const url = new URL(request.url);
  const route = url.pathname.replace(/^\/api\//, "");
  try {
    if (route === "login" && request.method === "POST") return login(request, env);
    if (!env.DB) return json({ error: "Database DB is niet gekoppeld in Cloudflare Pages" }, 500);
    await ensureSchema(env.DB);
    if (route === "me") return json({ ok: true, sheet: !!env.SHEET_HOOK_URL, read: !!env.ANTHROPIC_API_KEY, limit: Number(env.DAILY_LIMIT || 1500), used: await usedToday(env) });
    if (route === "docs" && request.method === "GET") return listDocs(url, env);
    if (route === "doc") return oneDoc(request, url, env);
    if (route === "read" && request.method === "POST") return read(request, env);
    if (route === "sheet" && request.method === "POST") return sheet(request, env);
    return json({ error: "onbekend" }, 404);
  } catch (e) {
    return json({ error: String(e && e.message || e).slice(0, 300) }, 500);
  }
}

async function login(request, env) {
  const { code } = await request.json().catch(() => ({}));
  if (!env.TEAM_CODE || String(code || "").trim() !== String(env.TEAM_CODE)) {
    await new Promise(r => setTimeout(r, 900));
    return json({ ok: false }, 403);
  }
  const tok = await teamToken(env);
  return json({ ok: true }, 200, { "set-cookie": `kp=${tok}; Path=/; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax` });
}

async function listDocs(url, env) {
  const parent = url.searchParams.get("parent") || "";
  if (!checkPath(parent, false)) return json({ error: "pad" }, 400);
  const since = Number(url.searchParams.get("since") || 0);
  const rows = await env.DB.prepare("SELECT path, id, data, u, deleted FROM docs WHERE parent = ?1 AND u > ?2 ORDER BY u LIMIT 2000")
    .bind(parent, since).all();
  return json({ now: Date.now(), docs: rows.results.map(r => ({ path: r.path, id: r.id, u: r.u, deleted: !!r.deleted, data: r.deleted ? null : JSON.parse(r.data) })) });
}

async function oneDoc(request, url, env) {
  if (request.method === "GET") {
    const path = url.searchParams.get("path"); if (!checkPath(path, true)) return json({ error: "pad" }, 400);
    const r = await env.DB.prepare("SELECT data, u, deleted FROM docs WHERE path = ?1").bind(path).first();
    return json(r && !r.deleted ? { exists: true, u: r.u, data: JSON.parse(r.data) } : { exists: false });
  }
  if (request.method === "PUT") {
    const { path, data } = await request.json();
    const seg = checkPath(path, true); if (!seg) return json({ error: "pad" }, 400);
    if (!data || typeof data !== "object" || Array.isArray(data)) return json({ error: "data" }, 400);
    const body = JSON.stringify(data); if (body.length > 900000) return json({ error: "te groot" }, 413);
    const u = Date.now();
    await env.DB.prepare("INSERT INTO docs (path, parent, id, data, u, deleted) VALUES (?1, ?2, ?3, ?4, ?5, 0) ON CONFLICT(path) DO UPDATE SET data = ?4, u = ?5, deleted = 0")
      .bind(path, seg.slice(0, -1).join("/"), seg[seg.length - 1], body, u).run();
    return json({ ok: true, u });
  }
  if (request.method === "DELETE") {
    const path = url.searchParams.get("path"); const seg = checkPath(path, true); if (!seg) return json({ error: "pad" }, 400);
    const u = Date.now();
    await env.DB.prepare("INSERT INTO docs (path, parent, id, data, u, deleted) VALUES (?1, ?2, ?3, NULL, ?4, 1) ON CONFLICT(path) DO UPDATE SET data = NULL, u = ?4, deleted = 1")
      .bind(path, seg.slice(0, -1).join("/"), seg[seg.length - 1], u).run();
    return json({ ok: true, u });
  }
  return json({ error: "methode" }, 405);
}

const today = () => new Date().toISOString().slice(0, 10);
async function usedToday(env) {
  const r = await env.DB.prepare("SELECT n FROM usage WHERE day = ?1").bind(today()).first();
  return r ? r.n : 0;
}

async function read(request, env) {
  if (!env.ANTHROPIC_API_KEY) return json({ error: "ANTHROPIC_API_KEY ontbreekt" }, 500);
  const limit = Number(env.DAILY_LIMIT || 1500);
  const used = await usedToday(env);
  if (used >= limit) return json({ error: "daglimiet", used, limit }, 429);
  const { prompt, images = [], tier = "quick" } = await request.json();
  if (typeof prompt !== "string" || !prompt || prompt.length > 20000) return json({ error: "prompt" }, 400);
  if (!Array.isArray(images) || images.length > 20) return json({ error: "afbeeldingen" }, 400);
  await env.DB.prepare("INSERT INTO usage (day, n) VALUES (?1, 1) ON CONFLICT(day) DO UPDATE SET n = n + 1").bind(today()).run();
  const model = tier === "quick" ? (env.MODEL_QUICK || "claude-haiku-5-5") : (env.MODEL_ACCURATE || "claude-sonnet-5-5");
  const content = images.filter(im => im && typeof im.data === "string")
    .map(im => ({ type: "image", source: { type: "base64", media_type: /^image\/(jpeg|png|webp|gif)$/.test(im.type) ? im.type : "image/jpeg", data: im.data } }));
  content.push({ type: "text", text: prompt });
  const r = await fetch(env.ANTHROPIC_URL || "https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": env.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model, max_tokens: 3000, stream: true, messages: [{ role: "user", content }] }),
  });
  if (!r.ok) {
    const t = await r.text();
    return json({ error: "claude", status: r.status, detail: t.slice(0, 400) }, r.status === 429 || r.status === 529 ? 429 : 502);
  }
  return new Response(r.body, { headers: { "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-store" } });
}

async function sheet(request, env) {
  if (!env.SHEET_HOOK_URL) return json({ error: "SHEET_HOOK_URL ontbreekt" }, 500);
  const { title, values } = await request.json();
  if (!Array.isArray(values) || !values.length || values.length > 5000) return json({ error: "waarden" }, 400);
  const r = await fetch(env.SHEET_HOOK_URL, {
    method: "POST", redirect: "follow", headers: { "content-type": "application/json" },
    body: JSON.stringify({ secret: env.SHEET_HOOK_SECRET || "", title: String(title || "Kaartscan").slice(0, 90), values }),
  });
  const text = await r.text(); let out = null; try { out = JSON.parse(text); } catch {}
  if (!r.ok || !out || !out.ok) return json({ error: "sheet", detail: (out && out.error) || text.slice(0, 300) }, 502);
  return json({ ok: true, title: out.title });
}
