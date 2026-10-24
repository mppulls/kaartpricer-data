/* MP Kaartscan los van Claude: levert dezelfde window.claude.use() als in Claude,
   maar dan via het eigen serverdeel. db = documenten met verversen elke paar seconden,
   sample = foto's lezen via /api/read, mcp = alleen "Google Sheets" via /api/sheet. */
(() => {
  if (window.claude) return;
  window.KP = { standalone: true, img: true };
  const api = async (method, url, body) => {
    const r = await fetch(url, { method, headers: body ? { "content-type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin" });
    if (r.status === 401) { location.href = "/login"; throw { code: "session_expired", message: "login" }; }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw { code: r.status === 429 ? "rate_limited" : r.status === 413 ? "invalid_argument" : "unavailable", message: j.error || String(r.status) };
    return j;
  };

  /* ---------------- db */
  const cols = new Map();   // collectiepad -> {docs: Map(id -> {data, u}), since, subs: Set, timer, loaded}
  const col = path => { if (!cols.has(path)) cols.set(path, { docs: new Map(), since: 0, subs: new Set(), timer: null, loaded: false, busy: false }); return cols.get(path); };
  const parentOf = p => p.split("/").slice(0, -1).join("/");
  const idOf = p => p.split("/").pop();
  const snapDoc = (id, data) => ({ id, exists: data != null, data: () => (data == null ? undefined : data), metadata: { fromCache: false, hasPendingWrites: false } });
  function notify(path) {
    const c = col(path);
    for (const s of c.subs) {
      let arr = [...c.docs.entries()].map(([id, v]) => ({ id, data: v.data }));
      if (s.filt) arr = arr.filter(d => s.filt.every(([f, op, v]) => OPS[op] && OPS[op](d.data[f], v)));
      if (s.order) { const [f, dir] = s.order; arr.sort((a, b) => { const x = a.data[f], y = b.data[f]; return (x > y ? 1 : x < y ? -1 : 0) * (dir === "desc" ? -1 : 1); }); }
      else arr.sort((a, b) => a.id < b.id ? -1 : 1);
      if (s.lim) arr = arr.slice(0, s.lim);
      const docs = arr.map(d => snapDoc(d.id, d.data));
      try { s.next({ docs, size: docs.length, empty: !docs.length, docChanges: () => docs.map((d, i) => ({ type: "added", doc: d, oldIndex: -1, newIndex: i })), metadata: { fromCache: false, hasPendingWrites: false } }); } catch (e) { console.error(e); }
    }
  }
  async function poll(path) {
    const c = col(path); if (c.busy) return; c.busy = true;
    try {
      const j = await api("GET", `/api/docs?parent=${encodeURIComponent(path)}&since=${Math.max(0, c.since - 3000)}`);
      let changed = !c.loaded;
      for (const d of j.docs) {
        const cur = c.docs.get(d.id);
        if (cur && cur.u >= d.u) continue;
        if (d.deleted) { if (cur) { c.docs.delete(d.id); changed = true; } c.deleted = c.deleted || new Map(); c.deleted.set(d.id, d.u); }
        else { const del = c.deleted && c.deleted.get(d.id); if (del && del > d.u) continue; c.docs.set(d.id, { data: d.data, u: d.u }); changed = true; }
        c.since = Math.max(c.since, d.u);
      }
      c.loaded = true; if (changed) notify(path);
    } catch (e) { for (const s of c.subs) if (s.err && e.code === "session_expired") s.err(e); }
    finally { c.busy = false; }
  }
  const tick = () => { if (document.visibilityState !== "visible") return; for (const [p, c] of cols) if (c.subs.size) poll(p); };
  setInterval(tick, 4000); document.addEventListener("visibilitychange", tick); window.addEventListener("online", tick);

  const OPS = { "==": (a, b) => a === b, "!=": (a, b) => a !== b, "<": (a, b) => a < b, "<=": (a, b) => a <= b, ">": (a, b) => a > b, ">=": (a, b) => a >= b };
  function query(path, order, lim, filt) {
    return {
      path,
      orderBy: (f, dir = "asc") => query(path, [f, dir], lim, filt),
      limit: n => query(path, order, n, filt),
      // filter op het eigen veld; 't > x' laat ook het ophalen pas bij x beginnen (met 6 uur marge voor klokverschil)
      where: (f, op, v) => { if (!OPS[op]) throw new TypeError("where: " + op + " wordt hier niet ondersteund"); return query(path, order, lim, [...(filt || []), [f, op, v]]); },
      async get() { await poll(path); const c = col(path); const docs = [...c.docs.entries()].map(([id, v]) => snapDoc(id, v.data)); return { docs, size: docs.length, empty: !docs.length, docChanges: () => [], metadata: {} }; },
      onSnapshot(next, err) {
        const c = col(path); const sub = { next, err, order, lim, filt }; c.subs.add(sub);
        const tf = (filt || []).find(([f, op]) => f === "t" && (op === ">" || op === ">="));
        if (tf && !c.loaded && Number.isFinite(tf[2])) c.since = Math.max(c.since, tf[2] - 6 * 3600e3);
        if (c.loaded) setTimeout(() => notify(path), 0); poll(path);
        return () => c.subs.delete(sub);
      },
      doc: id => docRef(`${path}/${id || Date.now().toString(36) + Math.random().toString(36).slice(2, 8)}`),
      async add(data) { const r = this.doc(); await r.set(data); return r; },
    };
  }
  function docRef(path) {
    const parent = parentOf(path), id = idOf(path);
    return {
      id, path,
      async get() { const j = await api("GET", `/api/doc?path=${encodeURIComponent(path)}`); return snapDoc(id, j.exists ? j.data : null); },
      async set(data) {
        const c = col(parent); const prev = c.docs.get(id);
        c.docs.set(id, { data: JSON.parse(JSON.stringify(data)), u: prev ? prev.u : 0 }); notify(parent);
        try { const j = await api("PUT", "/api/doc", { path, data }); const cur = c.docs.get(id); if (cur) cur.u = j.u; c.since = Math.max(c.since, 0); }
        catch (e) { if (prev) c.docs.set(id, prev); else c.docs.delete(id); notify(parent); throw e; }
      },
      async update(data) { const c = col(parent); const cur = c.docs.get(id); if (!cur) throw { code: "invalid_argument", message: "bestaat niet" }; return this.set({ ...cur.data, ...data }); },
      async delete() {
        const c = col(parent); const prev = c.docs.get(id); c.docs.delete(id); c.deleted = c.deleted || new Map(); c.deleted.set(id, Date.now() + 5000); notify(parent);
        try { await api("DELETE", `/api/doc?path=${encodeURIComponent(path)}`); } catch (e) { if (prev) c.docs.set(id, prev); notify(parent); throw e; }
      },
      collection: sub => query(`${path}/${sub}`),
      onSnapshot(next, err) { return query(parent).onSnapshot(s => next(s.docs.find(d => d.id === id) || snapDoc(id, null)), err); },
    };
  }
  const db = { doc: docRef, collection: p => query(p) };

  /* ---------------- sample */
  const toB64 = blob => new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(",")[1]); fr.onerror = rej; fr.readAsDataURL(blob); });
  async function sample(input, opts = {}) {
    const prompt = typeof input === "string" ? input : input.map(m => m.content).join("\n\n");
    const list = opts.images ? (opts.images instanceof Blob ? [opts.images] : [...opts.images]) : [];
    const images = await Promise.all(list.map(async b => ({ type: b.type || "image/jpeg", data: await toB64(b) })));
    let res;
    try { res = await fetch("/api/read", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ prompt, images, tier: opts.modelTier || "default" }), signal: opts.signal }); }
    catch (e) { throw { code: e && e.name === "AbortError" ? "cancelled" : "upstream_error", message: String(e) }; }
    if (res.status === 401) { location.href = "/login"; throw { code: "session_expired", message: "login" }; }
    if (!res.ok) { const j = await res.json().catch(() => ({})); throw { code: res.status === 429 ? "rate_limited" : "upstream_error", message: j.error || String(res.status) }; }
    const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "", text = "", stop = null;
    try {
      for (;;) {
        const { value, done } = await reader.read(); if (done) break;
        buf += dec.decode(value, { stream: true });
        let i; while ((i = buf.indexOf("\n\n")) >= 0) {
          const ev = buf.slice(0, i); buf = buf.slice(i + 2);
          const line = ev.split("\n").find(l => l.startsWith("data:")); if (!line) continue;
          let d; try { d = JSON.parse(line.slice(5)); } catch { continue; }
          if (d.type === "content_block_delta" && d.delta && d.delta.type === "text_delta") { text += d.delta.text; if (opts.onText) opts.onText({ text, delta: d.delta.text }); }
          else if (d.type === "message_delta" && d.delta) stop = d.delta.stop_reason || stop;
          else if (d.type === "error") throw { code: "upstream_error", message: (d.error && d.error.message) || "fout", text };
        }
      }
    } catch (e) { if (e && e.code) throw e; throw { code: e && e.name === "AbortError" ? "cancelled" : "upstream_error", message: String(e), text }; }
    if (!text.trim()) throw { code: "empty_completion", message: "leeg antwoord" };
    return { text, truncated: stop === "max_tokens", modelTierApplied: opts.modelTier || "default" };
  }
  sample.limits = async () => ({ maxPromptBytes: 262144, images: { maxCount: 20, maxInputBytes: 20e6, mediaTypes: ["image/jpeg", "image/png", "image/webp"] } });
  sample.json = async (input, opts) => { const { text } = await sample(input, opts); const m = /[\[{][\s\S]*[\]}]/.exec(text); return JSON.parse(m ? m[0] : text); };

  /* ---------------- mcp: alleen Google Sheets */
  let pendingTitle = null;
  const mcp = {
    async callTool(server, tool, input) {
      if (server !== "Google Sheets") throw { code: "server_not_connected", server, message: "niet beschikbaar" };
      if (tool === "update_spreadsheet") { pendingTitle = input && input.requests && input.requests[0] && input.requests[0].addSheet && input.requests[0].addSheet.properties.title; return { content: [], payload: {} }; }
      if (tool === "update_values") {
        const m = /^'(.*)'!/.exec(input.range || ""); const title = m ? m[1].replace(/''/g, "'") : pendingTitle;
        try { const j = await api("POST", "/api/sheet", { title, values: input.values }); return { content: [], payload: j }; }
        catch (e) { throw { code: "tool_error", server, message: e.message || "sheet" }; }
      }
      throw { code: "not_in_manifest", server, message: tool };
    },
    async listTools() { return { servers: [{ server: "Google Sheets", authStatus: "connected", tools: [{ name: "update_spreadsheet", description: "" }, { name: "update_values", description: "" }] }] }; },
  };

  const caps = { db, sample, mcp };
  window.claude = { use: async name => caps[name] || null };
})();
