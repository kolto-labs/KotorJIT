const TERMINAL = new Set(["Succeeded", "Failed", "Cancelled"]);
const MAX_U64 = 18446744073709551615n;

function token() {
  return document.querySelector("#token")?.value || sessionStorage.getItem("kotor-token") || "";
}
function canonicalId(value, allowZero = false) {
  if (typeof value !== "string" || !/^(0|[1-9][0-9]{0,19})$/.test(value) ||
      BigInt(value) > MAX_U64 || (!allowZero && value === "0")) {
    throw new Error("expected canonical uint64 decimal string");
  }
  return value;
}
function wireBytes(value) {
  if (!value || value.encoding !== "base64" || typeof value.data !== "string") {
    throw new Error("invalid console byte object");
  }
  const raw = atob(value.data);
  if (String(raw.length) !== canonicalId(value.byte_length, true)) throw new Error("byte length mismatch");
  const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
  return { bytes, text: new TextDecoder().decode(bytes) };
}
async function request(body, signal, expectedIdentity) {
  const response = await fetch("/v1/console", {
    method: "POST",
    headers: { "Authorization": `Bearer ${token()}`, "Content-Type": "application/json" },
    body: JSON.stringify(body), signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `bridge HTTP ${response.status}`);
  if (result.protocol !== "kp.console.v1") throw new Error("unexpected console protocol");
  if (typeof result.runtime !== "string" || !result.runtime) throw new Error("missing runtime identity");
  if (expectedIdentity && result.runtime !== expectedIdentity.runtime) throw new Error("StaleRuntime: response identity mismatch");
  return result;
}
export async function status() { return request({ op: "status" }); }
async function baseline(signal) {
  const result = await request({ op: "status" }, signal);
  if (result.status !== "Found") throw new Error(`console status ${result.status || "missing"}`);
  return {
    runtime: result.runtime,
    session: canonicalId(result.session),
    last_line: canonicalId(result.last_line, true),
  };
}
export async function cancel(target) {
  // IDs are session-scoped. Requiring the full handle prevents a concurrent
  // baseline or a reset from silently retargeting a cancellation.
  if (!target || typeof target !== "object" || typeof target.runtime !== "string" || !target.runtime) {
    throw new Error("request handle requires runtime, session and request");
  }
  const id = {runtime: target.runtime, session: canonicalId(target.session), request: canonicalId(target.request)};
  return request({ op: "cancel", ...id }, undefined, id);
}
export async function complete(prefix = "") {
  const id = await baseline();
  return request({ op: "complete", runtime: id.runtime, session: id.session, prefix }, undefined, id);
}
export async function evaluate(code, { poll = 50, timeout = 10000 } = {}) {
  sessionStorage.setItem("kotor-token", token());
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const deadline = Date.now() + timeout;
  try {
    const id = await baseline(controller.signal);
    const submitted = await request({ op: "submit", runtime: id.runtime, session: id.session, code }, controller.signal, id);
    if (submitted.status !== "None" || submitted.session !== id.session) throw new Error(`submit ${submitted.status || "missing"}`);
    canonicalId(submitted.request);
    let outcome;
    while (Date.now() < deadline) {
      const reply = await request({ op: "outcome", runtime: id.runtime, session: id.session, request: submitted.request }, controller.signal, id);
      if (reply.status !== "Found") throw new Error(`outcome ${reply.status || "missing"}`);
      outcome = reply.outcome;
      if (!outcome || outcome.session !== id.session || outcome.request !== submitted.request) throw new Error("outcome request identity mismatch");
      if (TERMINAL.has(outcome.state)) break;
      await new Promise(resolve => setTimeout(resolve, Math.min(poll, Math.max(0, deadline - Date.now()))));
    }
    if (!outcome || !TERMINAL.has(outcome.state)) throw new Error("console request timed out; automatic replay is forbidden");
    const output = await request({ op: "output", runtime: id.runtime, session: id.session, after_sequence: id.last_line }, controller.signal, id);
    if (output.status !== "Found" || output.session !== id.session) throw new Error(`output ${output.status || "missing"}: session ${output.session || "missing"}`);
    const values = (outcome.values || []).map(value => value.type === "String" ? { ...value, ...wireBytes(value.bytes) } : value);
    return {
      runtime: id.runtime, session: id.session, request: submitted.request,
      state: outcome.state, values, error: outcome.error || null,
      return_count: outcome.return_count, returns_truncated: outcome.returns_truncated,
      output: (output.lines || []).filter(line => line.session === id.session && line.request === submitted.request),
      dropped_through: output.dropped_through,
    };
  } finally {
    clearTimeout(timer);
  }
}
export const kotor = { lua: { evaluate }, console: { status, cancel, complete } };
globalThis.kotor = kotor;
document.querySelector("#run")?.addEventListener("click", async () => {
  try { document.querySelector("#output").textContent = JSON.stringify(await evaluate(document.querySelector("#code").value), null, 2); }
  catch (error) { document.querySelector("#output").textContent = String(error); }
});
