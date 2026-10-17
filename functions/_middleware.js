// Alles achter de teamcode, behalve het inlogscherm en wat een telefoon nodig heeft om het icoon te tonen.
import { cookie, teamToken, json } from "./_lib.js";
const OPEN = new Set(["/login", "/login.html", "/api/login", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png", "/favicon.ico"]);

export async function onRequest(ctx) {
  const { request, env, next } = ctx;
  const url = new URL(request.url);
  if (OPEN.has(url.pathname)) return next();
  if (!env.TEAM_CODE) return new Response("TEAM_CODE ontbreekt in de instellingen van Cloudflare Pages.", { status: 500 });
  const ok = cookie(request, "kp") === await teamToken(env);
  if (ok) return next();
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/img/")) return json({ error: "login" }, 401);
  return Response.redirect(new URL("/login", url).toString(), 302);
}
