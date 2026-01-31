import express from "express";
import cors from "cors";
// --- add near top of server.mjs ---
const GH_TOKEN = os.getenv("GH_TOKEN")
const GH_BASE = "https://api.github.com";

const app = express();

// Allow your Vite dev origin; add more origins if needed
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || "http://localhost:5173").split(",");
app.use(cors({ origin: ALLOWED_ORIGINS }));

// Keep raw body so we can forward it unchanged (JSON, form-data, etc.)
app.use(express.raw({ type: "*/*", limit: "25mb" }));

// Helper: build headers from query params prefixed with header_*
function headersFromQuery(qs) {
  const headers = {};
  for (const [k, v] of Object.entries(qs)) {
    if (k.toLowerCase().startsWith("header_")) {
      const name = k.slice(7).replace(/_/g, "-"); // header_Accept_Language -> Accept-Language
      headers[name] = v;
    }
  }
  if (!headers.accept) headers.accept = "application/json";
  return headers;
}

app.all("/api/external", async (req, res) => {
  try {
    const target_url = req.query.target_url;
    if (!target_url) {
      return res.status(400).send("Missing required query param: target_url");
    }

    // Copy query params, remove control + header_* keys
    const incoming = { ...req.query };
    delete incoming.target_url;
    for (const key of Object.keys(incoming)) {
      if (key.toLowerCase().startsWith("header_")) delete incoming[key];
    }

    // Merge client query params into target_url
    const url = new URL(target_url);
    for (const [k, v] of Object.entries(incoming)) {
      // last write wins (client-provided qs takes precedence)
      url.searchParams.set(k, v);
    }

    // Build headers; preserve client content-type if sending a body
    const headers = headersFromQuery(req.query);
    const hasBody = !["GET", "HEAD"].includes(req.method);
    if (hasBody && req.headers["content-type"]) {
      headers["content-type"] = req.headers["content-type"];
    }

    const body = hasBody && req.body?.length ? req.body : undefined;

    console.log("Url:", url.toString());

    // Server-to-server fetch
    const r = await fetch(url, {
      method: req.method,
      headers,
      body,
    });

    // Mirror status and content-type (plus content-disposition if present)
    res.status(r.status);
    res.set("content-type", r.headers.get("content-type") || "application/json");
    const cd = r.headers.get("content-disposition");
    if (cd) res.set("content-disposition", cd);

    const buf = Buffer.from(await r.arrayBuffer());
    res.send(buf);
  } catch (err) {
    res.status(502).json({ error: "Upstream fetch failed", detail: String(err) });
  }
});

// tiny helper to forward a request to GitHub
async function ghFetch(path, { method = "GET", headers = {}, body } = {}) {
  if (!GH_TOKEN) throw new Error("GH_TOKEN not set");
  const r = await fetch(`${GH_BASE}${path}`, {
    method,
    headers: {
      "Authorization": `Token ${GH_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "my-components-app",
      ...headers,
    },
    body,
  });
  const buf = Buffer.from(await r.arrayBuffer());
  return { status: r.status, headers: r.headers, buf };
}

// List issues (bugs), create, get, update
app.get("/api/github/repos/:owner/:repo/issues", async (req, res) => {
  try {
    const url = new URL(`${GH_BASE}/repos/${req.params.owner}/${req.params.repo}/issues`);
    // pass through pagination & filters
    for (const [k, v] of Object.entries(req.query)) url.searchParams.set(k, v);
    const { status, headers, buf } = await ghFetch(url.pathname + "?" + url.searchParams.toString());
    res.status(status).type(headers.get("content-type") || "application/json").send(buf);
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
});

app.post("/api/github/repos/:owner/:repo/issues", async (req, res) => {
  try {
    const { status, headers, buf } = await ghFetch(
      `/repos/${req.params.owner}/${req.params.repo}/issues`,
      { method: "POST", headers: { "content-type": req.headers["content-type"] }, body: req.body }
    );
    res.status(status).type(headers.get("content-type") || "application/json").send(buf);
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
});

app.get("/api/github/repos/:owner/:repo/issues/:number", async (req, res) => {
  try {
    const { status, headers, buf } = await ghFetch(
      `/repos/${req.params.owner}/${req.params.repo}/issues/${req.params.number}`
    );
    res.status(status).type(headers.get("content-type") || "application/json").send(buf);
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
});

app.patch("/api/github/repos/:owner/:repo/issues/:number", async (req, res) => {
  try {
    const { status, headers, buf } = await ghFetch(
      `/repos/${req.params.owner}/${req.params.repo}/issues/${req.params.number}`,
      { method: "PATCH", headers: { "content-type": req.headers["content-type"] }, body: req.body }
    );
    res.status(status).type(headers.get("content-type") || "application/json").send(buf);
  } catch (e) {
    res.status(502).json({ error: String(e) });
  }
});

const PORT = process.env.PORT || 8020;
app.listen(PORT, () => {
  console.log(`External proxy running on http://localhost:${PORT}`);
});
