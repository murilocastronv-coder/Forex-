// OpenAI Responses API bridge for the MT5 scalping EA.
// Keep secrets in Render environment variables, never in source control.
const http = require("node:http");

const PORT = Number(process.env.PORT || 10000);
const HOST = "0.0.0.0";
const API_KEY = process.env.OPENAI_API_KEY;
const BRIDGE_TOKEN = process.env.BRIDGE_TOKEN;
const MODEL = process.env.OPENAI_MODEL || "gpt-6";
const MAX_BODY = 16 * 1024;

function send(res, status, obj) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  res.end(JSON.stringify(obj));
}
function extractOutputText(response) {
  for (const item of (response.output || [])) {
    if (item.type !== "message") continue;
    for (const content of (item.content || [])) {
      if (content.type === "output_text" && typeof content.text === "string") return content.text;
    }
  }
  return "";
}
function authorized(req) {
  if (!BRIDGE_TOKEN) return false;
  const auth = req.headers.authorization || "";
  return auth === `Bearer ${BRIDGE_TOKEN}`;
}
const server = http.createServer((req, res) => {
  let pathname = new URL(req.url || "/", "http://localhost").pathname;
  while (pathname.length > 1 && pathname.endsWith("/")) pathname = pathname.slice(0, -1);
  if (req.method === "GET" && (pathname === "/" || pathname === "/health"))
    return send(res, 200, { ok: true, service: "forex-scalper-ai", configured: Boolean(API_KEY && BRIDGE_TOKEN), endpoint: "/analyze" });

  if (req.method !== "POST" || pathname !== "/analyze")
    return send(res, 404, { error: "Not found" });
  if (!authorized(req)) return send(res, 401, { error: "Unauthorized" });
  if (!API_KEY) return send(res, 503, { error: "AI provider is not configured" });

  let raw = "";
  let tooLarge = false;
  req.on("data", chunk => {
    raw += chunk;
    if (Buffer.byteLength(raw) > MAX_BODY) {
      tooLarge = true;
      send(res, 413, { error: "Payload too large" });
      req.destroy();
    }
  });
  req.on("end", async () => {
    if (tooLarge) return;
    try {
      const m = JSON.parse(raw || "{}");
      const required = ["symbol", "candidate", "ema_fast", "ema_slow", "rsi", "atr_points", "spread_points", "last_close", "previous_close"];
      if (!required.every(k => Object.hasOwn(m, k)) || !["BUY", "SELL"].includes(m.candidate))
        return send(res, 400, { error: "Invalid market context" });

      const context = {};
      for (const k of required) context[k] = m[k];
      context.trend_tf = String(m.trend_tf || "M5");
      context.entry_tf = String(m.entry_tf || "M1");
      if (Object.values(context).some(v => typeof v === "number" && !Number.isFinite(v)))
        return send(res, 400, { error: "Invalid numeric input" });

      const instructions = [
        "You are a conservative technical-context reviewer for a demo-first MT5 scalping EA.",
        "Assess only the supplied snapshot; you do not have live news, order book, or future prices.",
        "Prefer WAIT when context is weak or spread is large relative to ATR. Never claim certainty or profitability.",
        "You are advisory only. The EA separately enforces risk limits and a human must approve each trade.",
        "Return exactly one JSON object: decision (BUY, SELL, WAIT), confidence (integer 0-100), reason (max 160 characters).",
        "Never recommend increasing lot size, removing stop loss, or recovering losses."
      ].join(" ");

      const apiResponse = await fetch("https://api.openai.com/v1/responses", {
        method: "POST",
        headers: { "Authorization": `Bearer ${API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model: MODEL,
          instructions,
          input: JSON.stringify(context),
          text: { format: { type: "json_schema", name: "scalper_signal", strict: true, schema: { type: "object", properties: { decision: { type: "string", enum: ["BUY", "SELL", "WAIT"] }, confidence: { type: "integer", minimum: 0, maximum: 100 }, reason: { type: "string" } }, required: ["decision", "confidence", "reason"], additionalProperties: false } } },
          max_output_tokens: 250
        }),
        signal: AbortSignal.timeout(4500)
      });
      const body = await apiResponse.json().catch(() => ({}));
      if (!apiResponse.ok) {
        const apiError = body && body.error ? body.error : {};
        console.error("OpenAI API request failed:", JSON.stringify({ status: apiResponse.status, code: apiError.code || null, type: apiError.type || null, message: apiError.message || "No error message returned" }));
        return send(res, 502, { error: "AI provider request failed" });
      }
      let parsed;
      try { parsed = JSON.parse(extractOutputText(body)); }
      catch { return send(res, 502, { error: "AI returned invalid JSON" }); }

      const decision = ["BUY", "SELL", "WAIT"].includes(parsed.decision) ? parsed.decision : "WAIT";
      const confidence = Number.isFinite(Number(parsed.confidence))
        ? Math.max(0, Math.min(100, Math.round(Number(parsed.confidence)))) : 0;
      const reason = String(parsed.reason || "No reason supplied").replace(/[<>]/g, "").slice(0, 160);
      return send(res, 200, { decision, confidence, reason });
    } catch (err) {
      console.error("Analysis failed:", err.message);
      return send(res, 502, { error: "Analysis unavailable" });
    }
  });
});
server.listen(PORT, HOST, () => console.log(`Scalper AI bridge listening on ${HOST}:${PORT}`));
