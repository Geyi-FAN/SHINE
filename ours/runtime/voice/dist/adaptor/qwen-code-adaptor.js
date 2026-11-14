// ../../../../voice_pi05_harness/vendor/Qwen-Live-Harness/node_modules/@qwen-code/sdk/dist/daemon/index.js
var x = class extends Error {
  status;
  body;
  constructor(n, t, o) {
    super(o), this.name = "DaemonHttpError", this.status = n, this.body = t;
  }
};
var St = 3e4;
var ms = /* @__PURE__ */ new Set(["authorized", "expired", "error", "cancelled"]);
var Ie = class {
  constructor(n) {
    this.client = n;
  }
  async start(n) {
    let t = await this.client.startDeviceFlow(n), o = this.client;
    return { deviceFlowId: t.deviceFlowId, providerId: t.providerId, userCode: t.userCode, verificationUri: t.verificationUri, verificationUriComplete: t.verificationUriComplete, expiresAt: t.expiresAt, intervalMs: t.intervalMs, attached: t.attached, cancel: () => o.cancelDeviceFlow(t.deviceFlowId, { clientId: n.clientId }), awaitCompletion: async (r = {}) => await ps(o, t, n.clientId, r) };
  }
  status(n, t) {
    return this.client.getDeviceFlow(n, t);
  }
  cancel(n, t) {
    return this.client.cancelDeviceFlow(n, t);
  }
};
async function ps(e, n, t, o) {
  return await gs(e, n, t, o);
}
async function ft(e, n, t, o) {
  try {
    return await e.getDeviceFlow(n.deviceFlowId, { clientId: t, signal: o });
  } catch (s) {
    if (s instanceof x && s.status === 404) return { deviceFlowId: n.deviceFlowId, providerId: n.providerId, status: "error", errorKind: "not_found_or_evicted", hint: "device-flow not found on daemon (evicted past terminal grace, daemon restart, or unknown deviceFlowId)", createdAt: Date.now() };
    throw s;
  }
}
function Dt(e, n = {}) {
  if (e !== void 0 && Number.isFinite(e) && !(n.allowZero ? e < 0 : e <= 0)) return e;
}
async function gs(e, n, t, o) {
  let s = o.signal, r = Dt(o.timeoutMs, { allowZero: true }), a = Dt(o.pollOverrideMs), i = r !== void 0 ? Date.now() + r : n.expiresAt + St, d = Math.max(1e3, a ?? n.intervalMs ?? 5e3), c = d;
  for (; ; ) {
    if (s?.aborted) throw On(s);
    if (Date.now() >= i) return await ft(e, n, t, s);
    let g = await ft(e, n, t, s);
    if (g.intervalMs && g.intervalMs !== c && (c = g.intervalMs, d = g.intervalMs, o.onThrottled?.(g.intervalMs)), ms.has(g.status)) return g;
    await hs(d, s);
  }
}
async function hs(e, n) {
  if (n?.aborted) throw On(n);
  await new Promise((t, o) => {
    let s = setTimeout(() => {
      a(), t();
    }, e), r = () => {
      a(), o(On(n));
    };
    function a() {
      clearTimeout(s), n?.removeEventListener("abort", r);
    }
    n && n.addEventListener("abort", r, { once: true });
  });
}
function On(e) {
  let n = e?.reason;
  return n instanceof Error ? n : typeof n == "string" ? new Error(n) : new Error("aborted");
}
function fs(e) {
  return Array.from(e).some((n) => {
    let t = n.charCodeAt(0);
    return t <= 31 || t === 127;
  });
}
function kt(e) {
  return typeof e == "string" && e.length <= 2048 && /^https?:\/\//i.test(e) && !fs(e);
}
function Ds(e) {
  if (typeof e != "object" || e === null) return false;
  let n = e;
  return typeof n.number == "number" && Number.isInteger(n.number) && n.number > 0 && kt(n.url) && (n.state === void 0 || n.state === "open" || n.state === "completed" || n.state === "not_planned");
}
function xe(e) {
  if (typeof e != "object" || e === null) return false;
  let n = e;
  return typeof n.number == "number" && Number.isInteger(n.number) && n.number > 0 && kt(n.url) && (n.state === void 0 || n.state === "open" || n.state === "merged" || n.state === "closed") && (n.issues === void 0 || Array.isArray(n.issues) && n.issues.length <= 10 && n.issues.every(Ds));
}
var pe = class extends Error {
  constructor(n) {
    super(n ?? "Transport connection closed"), this.name = "DaemonTransportClosedError";
  }
};
var nn = class extends Error {
  constructor(n) {
    super(n), this.name = "SseFramingError";
  }
};
var yt = 16 * 1024 * 1024;
async function* Pe(e, n) {
  let t = e.getReader(), o = new TextDecoder(), s = "", r;
  n && (r = () => {
    t.cancel().catch(() => {
    });
  }, n.aborted ? r() : n.addEventListener("abort", r, { once: true }));
  try {
    for (; ; ) {
      if (n?.aborted) return;
      let a, i;
      try {
        ({ value: a, done: i } = await t.read());
      } catch (c) {
        if (n?.aborted) return;
        throw c;
      }
      if (i) {
        if (s += o.decode(), s.length > 0) {
          let c = wt(s);
          for (let p of c.frames) {
            let g = Bn(p);
            g && (yield g);
          }
          if (c.tail.length > 0) {
            let p = Bn(c.tail);
            p && (yield p);
          }
        }
        return;
      }
      if (s += o.decode(a, { stream: true }), s.length > yt) throw new nn(`parseSseStream: unread buffer exceeded ${yt} UTF-16 code units without a frame separator \u2014 upstream likely not SSE`);
      let d = wt(s);
      if (d.frames.length > 0) for (let c of d.frames) {
        let p = Bn(c);
        p && (yield p);
      }
      s = d.tail;
    }
  } finally {
    n && r && n.removeEventListener("abort", r);
    try {
      await t.cancel();
    } catch {
    }
  }
}
function wt(e) {
  let n = [], t = 0;
  for (; t < e.length; ) {
    let o = e.indexOf(`

`, t);
    if (o === -1) {
      let a = e.indexOf(`\r
\r
`, t);
      if (a === -1) break;
      n.push(e.slice(t, a)), t = a + 4;
      continue;
    }
    let r = e.slice(t, o).indexOf(`\r
\r
`);
    if (r !== -1) {
      let a = t + r;
      n.push(e.slice(t, a)), t = a + 4;
    } else n.push(e.slice(t, o)), t = o + 2;
  }
  return { frames: n, tail: e.slice(t) };
}
function Bn(e) {
  if (!e) return;
  let n = [];
  for (let o of e.split(/\r?\n/)) {
    if (!o.startsWith("data:")) continue;
    let s = o.slice(5);
    n.push(s.startsWith(" ") ? s.slice(1) : s);
  }
  if (n.length === 0) return;
  let t = n.join(`
`);
  try {
    let o = JSON.parse(t);
    if (typeof o != "object" || o === null || Array.isArray(o) || o.v !== 1 || typeof o.type != "string") return;
    let s = o.id;
    return s !== void 0 && (!Number.isSafeInteger(s) || s < 1) ? void 0 : o;
  } catch {
    return;
  }
}
var Ss = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
var tn = class {
  baseUrl;
  token;
  _fetch;
  activeSseRequests = /* @__PURE__ */ new Set();
  _disposed = false;
  type = "rest";
  supportsReplay = true;
  restFetch;
  constructor(n, t, o) {
    this.baseUrl = n, this.token = t, this._fetch = o, this.restFetch = o;
  }
  get connected() {
    return !this._disposed;
  }
  async fetch(n, t, o) {
    if (this._disposed) throw new pe();
    return this._fetch(n, t);
  }
  async *subscribeEvents(n, t = {}) {
    if (this._disposed) throw new pe();
    let o = new AbortController();
    this.activeSseRequests.add(o);
    try {
      let s = { Accept: "text/event-stream" };
      this.token && (s.Authorization = `Bearer ${this.token}`), t.clientId && (s["X-Qwen-Client-Id"] = t.clientId), t.lastEventId !== void 0 && (s["Last-Event-ID"] = String(t.lastEventId), t.epoch !== void 0 && (s["X-Qwen-Event-Epoch"] = t.epoch));
      let r = t.signal ? ks([t.signal, o.signal]) : o.signal, a = `${this.baseUrl}/session/${encodeURIComponent(n)}/events`, i = new URLSearchParams();
      t.maxQueued !== void 0 && i.set("maxQueued", String(t.maxQueued)), t.sseConnectReason !== void 0 && i.set("connectReason", t.sseConnectReason), t.previousSseStreamId !== void 0 && i.set("previousStreamId", t.previousSseStreamId);
      let d = i.toString();
      d && (a += `?${d}`);
      let c, p = t.connectTimeoutMs;
      p && Number.isFinite(p) && (c = setTimeout(() => o.abort(new DOMException("Initial connect timed out", "TimeoutError")), p), typeof c == "object" && c && "unref" in c && c.unref());
      let g;
      try {
        g = await this._fetch(a, { headers: s, signal: r });
      } finally {
        c !== void 0 && clearTimeout(c);
      }
      if (!g.ok) {
        let b;
        try {
          let C = await g.text();
          try {
            b = JSON.parse(C);
          } catch {
            b = C;
          }
        } catch {
        }
        let P = b && typeof b == "object" && "error" in b ? String(b.error) : `HTTP ${g.status}`;
        throw new x(g.status, b, `GET /session/:id/events: ${P}`);
      }
      let f = g.headers.get("content-type") ?? "";
      if (!f.toLowerCase().includes("text/event-stream")) {
        try {
          await g.body?.cancel();
        } catch {
        }
        throw new x(g.status, f, `GET /session/:id/events: expected content-type text/event-stream, got "${f}"`);
      }
      if (!g.body) throw new Error("No SSE body");
      let S = g.headers.get("x-qwen-sse-stream-id");
      t.onSseStreamAccepted?.(S && Ss.test(S) ? S.toLowerCase() : void 0);
      let v = g.headers.get("x-qwen-event-epoch");
      v && t.onEpoch?.(v), yield* Pe(g.body, r);
    } finally {
      o.abort(), this.activeSseRequests.delete(o);
    }
  }
  dispose() {
    if (!this._disposed) {
      this._disposed = true;
      for (let n of this.activeSseRequests) n.abort();
      this.activeSseRequests.clear();
    }
  }
};
function ks(e) {
  let n = AbortSignal.any;
  if (typeof n == "function") return n.call(AbortSignal, e);
  let t = new AbortController(), o = [], s = () => {
    for (; o.length > 0; ) {
      let r = o.pop();
      try {
        r?.();
      } catch {
      }
    }
  };
  for (let r of e) {
    if (r.aborted) return t.abort(r.reason), s(), t.signal;
    let a = () => {
      t.abort(r.reason), s();
    };
    r.addEventListener("abort", a, { once: true }), o.push(() => r.removeEventListener("abort", a));
  }
  return t.signal.addEventListener("abort", s, { once: true }), t.signal;
}
var bt = ["plan", "default", "auto-edit", "auto", "yolo"];
var te = class extends Error {
  capability;
  constructor(n, t) {
    super(`DaemonCapabilities.${n} is missing \u2014 ${t}. The daemon you are connected to likely predates the feature that added this field; upgrade the daemon or fall back to a different code path that doesn't require it.`), this.name = "DaemonCapabilityMissingError", this.capability = n;
  }
};
var Ce = ["missing_binary", "blocked_egress", "auth_env_error", "init_timeout", "restore_timeout", "protocol_error", "missing_file", "parse_error", "budget_exhausted", "mcp_budget_would_exceed", "mcp_server_spawn_failed", "invalid_config", "prompt_deadline_exceeded", "writer_idle_timeout", "model_stream_interrupted", "loop_detected"];
var Un = bt;
var he = "standalone_sessions_v1";
var Wn = "standalone_session_options_v1";
var T = class extends Error {
  constructor(t, o) {
    super(`${t}: malformed standalone-session response (${o})`);
    this.route = t;
    this.name = "DaemonStandaloneProtocolError";
  }
};
var ge = class extends Error {
  constructor(t, o, s) {
    super(`Standalone session creation outcome is unknown for ${t}; inspect recovery before retrying.`);
    this.sessionId = t;
    this.recovery = o;
    this.originalError = s;
    this.name = "DaemonStandaloneCreationOutcomeUnknownError";
  }
};
function A(e, n, t = "response") {
  if (typeof e != "object" || e === null || Array.isArray(e)) throw new T(n, `expected ${t} object`);
  return e;
}
function N(e, n, t, o = false) {
  let s = e[n];
  if (typeof s != "string" || !o && s.length === 0) throw new T(t, `expected ${n} string`);
  return s;
}
function Rt(e, n, t) {
  let o = e[n];
  if (!Array.isArray(o) || !o.every((s) => typeof s == "string")) throw new T(t, `expected ${n}[]`);
}
function _e(e, n, t) {
  let o = N(e, "sessionId", n);
  if (t !== void 0 && o !== t) throw new T(n, `expected sessionId ${t}, received ${o}`);
  return o;
}
function vt(e, n) {
  if (A(e.context, n, "context").kind !== "standalone") throw new T(n, "expected standalone context");
}
function Et(e, n) {
  let t = A(e, n, "workingDirectory");
  if (t.state !== "ready" && t.state !== "recreated") throw new T(n, "invalid workingDirectory.state");
  t.warnings !== void 0 && Rt(t, "warnings", n);
}
function Rs(e, n) {
  if (e.sourceType !== "standalone") throw new T(n, "expected standalone sourceType");
  vt(e, n), N(e, "projectlessOutputDirectory", n), Et(e.workingDirectory, n);
}
function qn(e, n, t) {
  if (e[n] !== void 0 && typeof e[n] != "string") throw new T(t, `expected ${n} string`);
}
function Tt(e, n) {
  if (N(e, "kind", n), !["ok", "warning", "error", "disabled", "not_started", "unknown"].includes(String(e.status))) throw new T(n, "invalid status");
  for (let t of ["error", "hint"]) qn(e, t, n);
  if (e.errorKind !== void 0 && !Ce.includes(e.errorKind)) throw new T(n, "invalid errorKind");
}
function vs(e, n) {
  let t = A(e, n, "provider model");
  if (N(t, "modelId", n), N(t, "baseModelId", n), N(t, "name", n, true), t.description !== void 0 && t.description !== null && typeof t.description != "string") throw new T(n, "invalid description");
  if (t.contextLimit !== void 0 && (typeof t.contextLimit != "number" || !Number.isFinite(t.contextLimit) || t.contextLimit <= 0)) throw new T(n, "invalid contextLimit");
  for (let o of ["baseUrl", "envKey"]) qn(t, o, n);
  for (let o of ["isCurrent", "isRuntime"]) if (typeof t[o] != "boolean") throw new T(n, `expected ${o} boolean`);
  if (t.modalities !== void 0) {
    let o = A(t.modalities, n, "modalities");
    for (let s of ["image", "pdf", "audio", "video"]) if (o[s] !== void 0 && typeof o[s] != "boolean") throw new T(n, `expected modalities.${s} boolean`);
  }
  if (t.configOptions !== void 0 && !Array.isArray(t.configOptions)) throw new T(n, "expected configOptions[]");
}
function It(e, n) {
  let t = A(e, n);
  if (t.workspaceCwd !== void 0 || t.acpChannelLive !== void 0) throw new T(n, "standalone options exposed workspace internals");
  if (t.v !== 1) throw new T(n, "expected v=1");
  if (typeof t.initialized != "boolean") throw new T(n, "expected initialized boolean");
  if (t.current !== void 0) {
    let o = A(t.current, n, "current");
    for (let s of ["authType", "modelId", "baseUrl", "fastModelId", "visionModelId"]) qn(o, s, n);
  }
  if (t.approvalMode !== void 0 && !Un.includes(t.approvalMode)) throw new T(n, "invalid approvalMode");
  if (!Array.isArray(t.providers)) throw new T(n, "expected providers[]");
  for (let o of t.providers) {
    let s = A(o, n, "provider");
    if (Tt(s, n), s.kind !== "model_provider") throw new T(n, "expected model_provider kind");
    if (N(s, "authType", n), typeof s.current != "boolean") throw new T(n, "expected provider current boolean");
    if (!Array.isArray(s.models)) throw new T(n, "expected models[]");
    for (let r of s.models) vs(r, n);
  }
  if (t.errors !== void 0) {
    if (!Array.isArray(t.errors)) throw new T(n, "expected errors[]");
    for (let o of t.errors) Tt(A(o, n, "error"), n);
  }
  return t;
}
function $n(e, n, t) {
  let o = A(e, n);
  if (_e(o, n, t), N(o, "workspaceCwd", n), typeof o.attached != "boolean") throw new T(n, "expected attached boolean");
  if (o.modelApplied !== void 0 && typeof o.modelApplied != "boolean") throw new T(n, "expected modelApplied boolean");
  return Rs(o, n), o;
}
function xt(e, n, t) {
  let o = A(e, n);
  return $n(o, n, t), A(o.state, n, "state"), o;
}
function Pt(e, n, t) {
  let o = A(e, n);
  if (_e(o, n, t), N(o, "workspaceCwd", n), o.sourceType !== "standalone") throw new T(n, "expected standalone sourceType");
  return vt(o, n), o;
}
function Ct(e, n, t) {
  let o = A(e, n);
  return o.state === "creating" ? { sessionId: _e(o, n, t), state: "creating" } : Pt(o, n, t);
}
function _t(e, n) {
  let t = A(e, n);
  if (!Array.isArray(t.sessions)) throw new T(n, "expected sessions[]");
  if (t.nextCursor !== void 0 && typeof t.nextCursor != "string") throw new T(n, "expected nextCursor string");
  for (let o of ["liveMergeFailed", "truncated"]) if (t[o] !== void 0 && typeof t[o] != "boolean") throw new T(n, `expected ${o} boolean`);
  for (let o of t.sessions) Pt(o, n);
  return t;
}
function At(e, n, t) {
  let o = A(e, n);
  return _e(o, n, t), N(o, "projectlessOutputDirectory", n), Et(o.workingDirectory, n), o;
}
function Mt(e, n, t) {
  let o = A(e, n);
  return _e(o, n, t), N(o, "displayName", n, true), o;
}
function Nn(e, n, t) {
  let o = A(e, n);
  for (let s of t) Rt(o, s, n);
  if (!Array.isArray(o.errors)) throw new T(n, "expected errors[]");
  for (let s of o.errors) {
    let r = A(s, n, "batch error");
    for (let a of ["sessionId", "code", "message"]) N(r, a, n);
  }
  return o;
}
function Ot(e, n) {
  return Nn(e, n, ["archived", "alreadyArchived", "notFound"]);
}
function Bt(e, n) {
  return Nn(e, n, ["unarchived", "alreadyActive", "notFound"]);
}
function Ut(e, n) {
  return Nn(e, n, ["removed", "notFound", "fileCleanupPending"]);
}
function Fn(e) {
  return e instanceof x && e.status === 404 && Wt(e.body) === "standalone_session_not_found";
}
function Ln(e) {
  return e instanceof ge || e instanceof x && Wt(e.body) === "standalone_creation_outcome_unknown";
}
function Wt(e) {
  return typeof e == "object" && e !== null && !Array.isArray(e) ? e.code : void 0;
}
var on = "/workspace/memory/remember";
var sn = "/workspace/memory/forget";
var rn = "/workspace/memory/dream";
function qt(e) {
  if (typeof e != "object" || e === null || Array.isArray(e)) return;
  let n = e;
  if (n.v !== 1 || typeof n.type != "string") return;
  let t = n.requestId, o = n.modelSource, s = typeof t == "string" && t.length > 0, r = o === "fast" || o === "main", a = (i) => i === void 0 || typeof i == "number" && Number.isSafeInteger(i) && i >= 0;
  if (n.type === "started") {
    if (!s || typeof n.model != "string" || !r) return;
  } else if (n.type === "thinking") {
    if (!s) return;
  } else if (n.type === "delta") {
    if (!s || !Number.isSafeInteger(n.seq) || n.seq < 0 || typeof n.text != "string" || n.text.length === 0) return;
  } else if (n.type === "done") {
    if (!s || typeof n.model != "string" || !r || !a(n.inputTokens) || !a(n.outputTokens)) return;
  } else if (n.type === "error") {
    if (typeof n.code != "string" || typeof n.message != "string") return;
  } else return;
  return n;
}
var an = 20;
var xs = 3e4;
var $t = 0;
var Ps = 7e4;
var Cs = 1e4;
var _s = 65e3;
var As = 9e4;
var Ft = 35e3;
var Ms = 6e4;
var Os = 2e3;
var Lt = Ms + Os;
var fe = 2147483647;
var Bs = 5;
var J = 33e4;
var Us = "X-Qwen-Client-Id";
var l = encodeURIComponent;
function Gt(e) {
  let n = new URLSearchParams();
  e.cursor !== void 0 && n.set("cursor", e.cursor), e.direction !== void 0 && n.set("direction", e.direction), e.atRecordId !== void 0 && n.set("atRecordId", e.atRecordId), e.snapshot !== void 0 && n.set("snapshot", e.snapshot), e.beforeRecordId !== void 0 && n.set("beforeRecordId", e.beforeRecordId), e.limit !== void 0 && n.set("limit", String(e.limit));
  let t = n.toString();
  return t ? `?${t}` : "";
}
function jt(e) {
  let n = new URLSearchParams();
  e.snapshot !== void 0 && n.set("snapshot", e.snapshot), e.start !== void 0 && n.set("start", String(e.start)), e.limit !== void 0 && n.set("limit", String(e.limit));
  let t = n.toString();
  return t ? `?${t}` : "";
}
function Nt(e) {
  let n = e.trim();
  if (!n) throw new Error("rule must be a non-empty string");
  return n;
}
function zn(e) {
  if (e === void 0) return Bs;
  if (e === null || e === 0 || e === 1 / 0) return 1 / 0;
  if (!Number.isInteger(e) || e < 0) throw new TypeError("bad maxPendingPromptsPerSession");
  return e;
}
function Ws(e) {
  let n = e.length;
  for (; n > 0 && e.charCodeAt(n - 1) === 47; ) n--;
  return n === e.length ? e : e.slice(0, n);
}
function qs() {
  try {
    let n = globalThis.process?.env?.QWEN_SERVER_TOKEN;
    if (typeof n != "string") return;
    let t = n.trim();
    return t.length === 0 ? void 0 : t;
  } catch {
    return;
  }
}
var Ae = class extends Error {
  constructor(n, t, o) {
    super(`Pending prompts full: "${n}" (${o}/${t})`), this.name = "DaemonPendingPromptLimitError", this.sessionId = n, this.limit = t, this.pendingCount = o;
  }
};
var dn = class extends Error {
  constructor(t, o) {
    super(`Daemon returned session "${o}" instead of requested session "${t}".`);
    this.requestedSessionId = t;
    this.actualSessionId = o;
    this.name = "DaemonSessionIdProtocolError";
  }
};
var zt = 12e4;
var jn = class {
  baseUrl;
  token;
  _fetch;
  fetchTimeoutMs;
  hasExplicitFetchTimeout;
  cachedSessionRestoreTimeoutMs;
  promptLimit;
  promptCounts = /* @__PURE__ */ Object.create(null);
  transport;
  _authFlow;
  get auth() {
    return this._authFlow || (this._authFlow = new Ie(this)), this._authFlow;
  }
  constructor(n) {
    this.baseUrl = Ws(n.baseUrl), this.token = n.token ?? qs(), this._fetch = n.fetch ?? n.transport?.restFetch ?? globalThis.fetch.bind(globalThis), this.hasExplicitFetchTimeout = n.fetchTimeoutMs !== void 0;
    let t = n.fetchTimeoutMs ?? xs;
    this.fetchTimeoutMs = Number.isFinite(t) && t > 0 ? t : 0, this.promptLimit = zn(n.maxPendingPromptsPerSession), this.transport = n.transport ?? new tn(this.baseUrl, this.token, this._fetch);
  }
  get maxPendingPromptsPerSession() {
    return this.promptLimit;
  }
  reservePromptSlot(n, t = this.promptLimit) {
    if (t === 1 / 0) return () => {
    };
    let o = this.promptCounts, s = o[n] ?? 0;
    if (s >= t) throw new Ae(n, t, s);
    o[n] = s + 1;
    let r;
    return () => {
      r || (r = true, (o[n] ?? 0) <= 1 ? delete o[n] : --o[n]);
    };
  }
  async fetchWithTimeout(n, t = {}, o, s, r = "transport") {
    let a = this.fetchTimeoutMs;
    if (s !== void 0 && Number.isFinite(s) && s >= 0 && (a = s), !a || !Number.isFinite(a)) {
      let g = r === "rest" ? await this._fetch(n, t) : await this.transport.fetch(n, t);
      return o ? o(g) : g;
    }
    let i = new AbortController(), d = setTimeout(() => {
      i.abort(new DOMException("timeout", "TimeoutError"));
    }, a);
    typeof d == "object" && d && "unref" in d && d.unref();
    let c = t.signal ?? void 0, p = c ? Gn([c, i.signal]) : i.signal;
    try {
      let g = r === "rest" ? await this._fetch(n, { ...t, signal: p }) : await this.transport.fetch(n, { ...t, signal: p });
      return o ? await o(g) : g;
    } finally {
      clearTimeout(d);
    }
  }
  headers(n = {}, t) {
    let o = { ...n };
    return this.token && (o.Authorization = `Bearer ${this.token}`), t && (o[Us] = t), o;
  }
  async failOnError(n, t, o) {
    let s;
    try {
      let i = await n.text();
      if (i.length > 0) try {
        s = JSON.parse(i);
      } catch {
        s = i;
      }
    } catch {
    }
    let r = s && typeof s == "object" && !Array.isArray(s) ? s : void 0, a = r && "error" in r ? String(r.error) : `HTTP ${n.status}`;
    if (n.status >= 500 && r?.error === "Internal error" && typeof r.code == "number") {
      let i = r.data;
      if (typeof i == "string" && i.length > 0) a = i;
      else if (i && typeof i == "object" && !Array.isArray(i)) {
        let d = i, c = d.details, p = d.message;
        typeof c == "string" && c.length > 0 ? a = c : typeof p == "string" && p.length > 0 && (a = p);
      }
    }
    if (o && n.status === 503 && s && typeof s == "object") {
      let i = s;
      if (i.code === "prompt_queue_full") return new Ae(typeof i.sessionId == "string" ? i.sessionId : o, typeof i.limit == "number" ? i.limit : 0, typeof i.pendingCount == "number" ? i.pendingCount : 0);
    }
    return new x(n.status, s, `${t}: ${a}`);
  }
  async jsonRequest(n, t, o = {}) {
    let s = o.body !== void 0;
    return await this.fetchWithTimeout(`${this.baseUrl}${n}`, { ...o.method ? { method: o.method } : {}, headers: this.headers(s ? { "Content-Type": "application/json" } : {}, o.clientId), ...s ? { body: JSON.stringify(o.body) } : {}, ...o.signal ? { signal: o.signal } : {} }, async (r) => {
      if (!r.ok) throw await this.failOnError(r, t);
      return await r.json();
    }, o.timeoutMs, o.mode);
  }
  async workspaceJsonRequest(n, t, o, s = {}) {
    return await this.jsonRequest(`/workspaces/${n}${t}`, o, s);
  }
  async sessionExportRequest(n, t, o = {}) {
    let s = o.format ?? "html", r = o.format ? `?format=${l(o.format)}` : "";
    return await this.fetchWithTimeout(`${this.baseUrl}${n}${r}`, { headers: this.headers({}, o.clientId) }, async (a) => {
      if (!a.ok) throw await this.failOnError(a, t);
      let i = await a.text(), d = a.headers.get("content-type") ?? "", c = /filename="([^"]+)"/i.exec(a.headers.get("content-disposition") ?? "")?.[1] ?? `export.${s}`;
      return { content: i, filename: c, mimeType: d, format: s };
    }, void 0, "rest");
  }
  async workspaceNoContentRequest(n, t, o, s = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspaces/${n}${t}`, { ...s.method ? { method: s.method } : {}, headers: this.headers({}, s.clientId) }, async (r) => {
      if (r.status === 204) {
        try {
          await r.body?.cancel();
        } catch {
        }
        return;
      }
      if (r.status === 404 && s.okNotFoundCode) {
        let a = await this.failOnError(r, o);
        if (a.body?.code === s.okNotFoundCode) return;
        throw a;
      }
      throw await this.failOnError(r, o);
    }, s.timeoutMs);
  }
  workspaceById(n) {
    return new Me(this, l(n));
  }
  workspaceByCwd(n) {
    return new Me(this, l(n));
  }
  async health() {
    return await this.fetchWithTimeout(`${this.baseUrl}/health`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /health");
      return await n.json();
    });
  }
  async capabilities() {
    let n = await this.fetchWithTimeout(`${this.baseUrl}/capabilities`, { headers: this.headers() }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /capabilities");
      return await o.json();
    }), t = n.limits?.sessionRestoreTimeoutMs;
    return this.cachedSessionRestoreTimeoutMs = typeof t == "number" && Number.isInteger(t) && t > 0 && t <= fe ? t : void 0, n;
  }
  async brand() {
    return await this.fetchWithTimeout(`${this.baseUrl}/brand`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /brand");
      return await n.json();
    });
  }
  async notify(n, t) {
    return await this.jsonRequest("/workspace/notify", "POST /workspace/notify", { method: "POST", body: n, timeoutMs: t?.timeoutMs ?? Ft, mode: "rest" });
  }
  async requireCapability(n) {
    let t = await this.capabilities();
    if (!Array.isArray(t.features) || !t.features.includes(n)) throw new te(n, `daemon does not advertise the ${n} feature`);
  }
  async daemonStatus(n = "summary") {
    let t = n === "summary" ? "" : `?detail=${n}`;
    return await this.jsonRequest(`/daemon/status${t}`, "GET /daemon/status");
  }
  async usageDashboard(n = {}) {
    let t = new URLSearchParams();
    n.range !== void 0 && t.set("range", n.range), n.heatmapDays !== void 0 && t.set("heatmapDays", String(n.heatmapDays));
    let o = t.toString();
    return await this.jsonRequest(`/usage/dashboard${o ? `?${o}` : ""}`, "GET /usage/dashboard");
  }
  async workspaceMcp() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/mcp");
      return await n.json();
    });
  }
  async setUserMcpServer(n, t) {
    return await this.jsonRequest(`/workspace/config/mcp/servers/${l(n)}`, "PUT /workspace/config/mcp/servers/:name", { method: "PUT", body: { scope: "user", config: t }, mode: "rest" });
  }
  async removeUserMcpServer(n) {
    return await this.jsonRequest(`/workspace/config/mcp/servers/${l(n)}?scope=user`, "DELETE /workspace/config/mcp/servers/:name", { method: "DELETE", mode: "rest" });
  }
  async setUserMcpServerEnabled(n, t) {
    return await this.jsonRequest(`/workspace/config/mcp/${l(n)}/${t ? "enable" : "disable"}`, "POST /workspace/config/mcp/:server/:action", { method: "POST", body: {}, mode: "rest" });
  }
  async initializeWorkspaceMcp() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/initialize`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: "{}" }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "POST /workspace/mcp/initialize");
      return await n.json();
    });
  }
  async reloadWorkspaceMcp(n = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/reload`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: JSON.stringify(n) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "POST /workspace/mcp/reload");
      return await t.json();
    });
  }
  async workspaceGit(n) {
    return await this.jsonRequest(`/workspace/git${n?.wait ? "?wait=1" : ""}`, "GET /workspace/git", { mode: "rest" });
  }
  async workspaceGitDiff() {
    return await this.jsonRequest("/workspace/git/diff", "GET /workspace/git/diff", { mode: "rest" });
  }
  async workspaceGitDiffFile(n, t) {
    let o = `/workspace/git/diff/file?path=${l(n)}` + (t != null ? `&oldPath=${l(t)}` : "");
    return await this.jsonRequest(o, "GET /workspace/git/diff/file", { mode: "rest" });
  }
  async workspaceGitLog(n, t, o) {
    let s = new URLSearchParams();
    n != null && s.set("limit", String(n)), t != null && s.set("skip", String(t)), o && s.set("range", o);
    let r = s.toString();
    return await this.jsonRequest(`/workspace/git/log${r ? `?${r}` : ""}`, "GET /workspace/git/log", { mode: "rest" });
  }
  async workspaceGitCommitDetail(n) {
    return await this.jsonRequest(`/workspace/git/log/commit?sha=${l(n)}`, "GET /workspace/git/log/commit", { mode: "rest" });
  }
  async workspaceGitBranches() {
    return await this.jsonRequest("/workspace/git/branches", "GET /workspace/git/branches", { mode: "rest" });
  }
  async workspaceGitCheckout(n) {
    return await this.jsonRequest("/workspace/git/checkout", "POST /workspace/git/checkout", { method: "POST", body: { ref: n }, mode: "rest" });
  }
  async workspaceGitCreateBranch(n, t) {
    return await this.jsonRequest("/workspace/git/branch", "POST /workspace/git/branch", { method: "POST", body: { name: n, startPoint: t }, mode: "rest" });
  }
  async workspaceGitPush(n) {
    return await this.jsonRequest("/workspace/git/push", "POST /workspace/git/push", { method: "POST", body: n ?? {}, mode: "rest" });
  }
  async workspaceGitPull(n, t) {
    return await this.jsonRequest("/workspace/git/pull", "POST /workspace/git/pull", { method: "POST", body: n ?? {}, mode: "rest", timeoutMs: t });
  }
  async workspaceGitCommit(n, t) {
    return await this.jsonRequest("/workspace/git/commit", "POST /workspace/git/commit", { method: "POST", body: { message: n, ...t }, mode: "rest" });
  }
  async workspaceMcpTools(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/${l(n)}/tools`, { headers: this.headers() }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /workspace/mcp/:server/tools");
      return await t.json();
    });
  }
  async workspaceMcpResources(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/${l(n)}/resources`, { headers: this.headers() }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /workspace/mcp/:server/resources");
      return await t.json();
    });
  }
  async workspaceSkills() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/skills`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/skills");
      return await n.json();
    });
  }
  workspaceConfigSkills() {
    return this.jsonRequest("/workspace/config/skills", "Skills config", { mode: "rest" });
  }
  workspaceRuntimeSkills() {
    return this.jsonRequest("/workspace/runtime/skills", "Skills runtime", { mode: "rest" });
  }
  async workspaceAcpPreheat(n) {
    let t = n ?? 5e3, o = n !== void 0 ? `?timeoutMs=${encodeURIComponent(n)}` : "";
    return await this.jsonRequest(`/workspace/acp/preheat${o}`, "POST /workspace/acp/preheat", { method: "POST", timeoutMs: t + 2e3, mode: "rest" });
  }
  async workspaceAcpStatus() {
    return await this.jsonRequest("/workspace/acp/status", "GET /workspace/acp/status", { mode: "rest" });
  }
  async ensureWorkspaceRuntime() {
    return await this.jsonRequest("/workspace/runtime/ensure", "POST /workspace/runtime/ensure", { method: "POST", timeoutMs: Lt, mode: "rest" });
  }
  async workspaceRuntimeStatus() {
    return await this.jsonRequest("/workspace/runtime/status", "GET /workspace/runtime/status", { mode: "rest" });
  }
  async workspaceProviders() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/providers`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/providers");
      return await n.json();
    });
  }
  async workspaceHooks() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/hooks`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/hooks");
      return await n.json();
    });
  }
  async sessionHooks(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/hooks`, { headers: this.headers() }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /session/:id/hooks");
      return await t.json();
    });
  }
  async sessionResources(n, t) {
    return await this.jsonRequest(`/session/${l(n)}/resources`, "GET /session/:id/resources", { clientId: t, mode: "rest" });
  }
  async workspaceExtensions() {
    return await this.jsonRequest("/workspace/extensions", "GET /workspace/extensions", { mode: "rest" });
  }
  async installExtension(n, t) {
    return await this.jsonRequest("/workspace/extensions/install", "POST /workspace/extensions/install", { method: "POST", body: n, clientId: t, mode: "rest" });
  }
  async installExtensionArchive(n, t) {
    let o = new URLSearchParams({ filename: n.filename, consent: String(n.consent === true) });
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/extensions/install-archive?${o}`, { method: "POST", headers: this.headers({ "Content-Type": "application/octet-stream" }, t), body: n.archive }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /workspace/extensions/install-archive");
      return await s.json();
    }, zt, "rest");
  }
  async extensionOperationStatus(n) {
    return await this.jsonRequest(`/workspace/extensions/operations/${l(n)}`, "GET /workspace/extensions/operations/:operationId", { mode: "rest" });
  }
  async activeExtensionOperations() {
    return await this.jsonRequest("/workspace/extensions/operations", "GET /workspace/extensions/operations", { mode: "rest" });
  }
  async respondToExtensionInteraction(n, t, o, s) {
    return await this.jsonRequest(`/workspace/extensions/operations/${l(n)}/interactions/${l(t)}`, "POST /workspace/extensions/operations/:operationId/interactions/:interactionId", { method: "POST", body: o, clientId: s, mode: "rest" });
  }
  async checkExtensionUpdates(n) {
    return await this.jsonRequest("/workspace/extensions/check-updates", "POST /workspace/extensions/check-updates", { method: "POST", body: {}, clientId: n, mode: "rest" });
  }
  async refreshExtensions(n) {
    return await this.jsonRequest("/workspace/extensions/refresh", "POST /workspace/extensions/refresh", { method: "POST", body: {}, clientId: n, mode: "rest" });
  }
  async enableExtension(n, t, o) {
    return await this.jsonRequest(`/workspace/extensions/${l(n)}/enable`, "POST /workspace/extensions/:name/enable", { method: "POST", body: t, clientId: o, mode: "rest" });
  }
  async disableExtension(n, t, o) {
    return await this.jsonRequest(`/workspace/extensions/${l(n)}/disable`, "POST /workspace/extensions/:name/disable", { method: "POST", body: t, clientId: o, mode: "rest" });
  }
  async updateExtension(n, t) {
    return await this.jsonRequest(`/workspace/extensions/${l(n)}/update`, "POST /workspace/extensions/:name/update", { method: "POST", body: {}, clientId: t, mode: "rest" });
  }
  async uninstallExtension(n, t) {
    return await this.jsonRequest(`/workspace/extensions/${l(n)}`, "DELETE /workspace/extensions/:name", { method: "DELETE", clientId: t, mode: "rest" });
  }
  async extensionCatalog() {
    return await this.jsonRequest("/extensions", "GET /extensions", { mode: "rest" });
  }
  async installUserExtension(n, t) {
    return await this.jsonRequest("/extensions/install", "POST /extensions/install", { method: "POST", body: n, clientId: t, mode: "rest" });
  }
  async checkUserExtensionUpdates(n) {
    return await this.jsonRequest("/extensions/check-updates", "POST /extensions/check-updates", { method: "POST", body: {}, clientId: n, mode: "rest" });
  }
  async updateUserExtension(n, t) {
    return await this.jsonRequest(`/extensions/${l(n)}/update`, "POST /extensions/:extensionId/update", { method: "POST", body: {}, clientId: t, mode: "rest" });
  }
  async uninstallUserExtension(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/extensions/${l(n)}`, { method: "DELETE", headers: this.headers({}, t) }, async (o) => {
      if (o.status === 204) {
        await o.body?.cancel().catch(() => {
        });
        return;
      }
      if (!o.ok) throw await this.failOnError(o, "DELETE /extensions/:extensionId");
      return await o.json();
    }, void 0, "rest");
  }
  async setExtensionDefaultActivation(n, t, o) {
    return await this.jsonRequest(`/extensions/${l(n)}/activation`, "PUT /extensions/:extensionId/activation", { method: "PUT", body: { state: t }, clientId: o, mode: "rest" });
  }
  async setExtensionDefaultActivations(n, t, o) {
    return await this.jsonRequest("/extensions/activation", "PUT /extensions/activation", { method: "PUT", body: { extensionNames: [...n], state: t }, clientId: o, mode: "rest" });
  }
  async extensionOperation(n, t) {
    return await this.jsonRequest(`/extensions/operations/${l(n)}`, "GET /extensions/operations/:operationId", t ? { signal: t, mode: "rest" } : { mode: "rest" });
  }
  async waitForExtensionOperation(n, t = {}) {
    let o = t.pollIntervalMs ?? 1e3, s = t.timeoutMs ?? 10 * 6e4, r = s !== Number.POSITIVE_INFINITY, a = Date.now() + s, i = () => new Error(`Timed out waiting for extension operation ${n.operationId}. The server operation was not cancelled.`);
    for (; ; ) {
      t.signal?.throwIfAborted();
      let d = a - Date.now();
      if (d <= 0 || Number.isNaN(d)) throw i();
      let c;
      if (!r) c = await this.extensionOperation(n.operationId, t.signal);
      else {
        let g = new AbortController(), f = t.signal ? Gn([t.signal, g.signal]) : g.signal, S, v = new Promise((b, P) => {
          let C = () => {
            let B = i();
            P(B), g.abort(B);
          }, $ = () => {
            let B = a - Date.now();
            if (B <= 0) {
              C();
              return;
            }
            S = setTimeout(() => {
              Date.now() >= a ? C() : $();
            }, Math.min(B, fe));
          };
          $();
        });
        try {
          c = await Promise.race([this.extensionOperation(n.operationId, f), v]);
        } finally {
          S !== void 0 && clearTimeout(S), g.abort();
        }
      }
      if (c.status !== "queued" && c.status !== "running") return c;
      let p = a - Date.now();
      if (p <= 0) throw i();
      await new Promise((g, f) => {
        let v = setTimeout(() => {
          t.signal?.removeEventListener("abort", b), g();
        }, Math.min(o, p, fe)), b = () => {
          clearTimeout(v), t.signal?.removeEventListener("abort", b), f(t.signal?.reason ?? new DOMException("Aborted", "AbortError"));
        };
        t.signal?.addEventListener("abort", b, { once: true }), t.signal?.aborted && b();
      });
    }
  }
  async readWorkspaceFile(n, t = {}, o) {
    let s = new URLSearchParams({ path: n });
    return t.maxBytes !== void 0 && s.set("maxBytes", String(t.maxBytes)), t.line !== void 0 && s.set("line", String(t.line)), t.limit !== void 0 && s.set("limit", String(t.limit)), t.cursor !== void 0 && s.set("cursor", t.cursor), await this.fetchWithTimeout(`${this.baseUrl}/file?${s.toString()}`, { headers: this.headers({}, o) }, async (r) => {
      if (!r.ok) throw await this.failOnError(r, "GET /file");
      return await r.json();
    });
  }
  async readWorkspaceFileBytes(n, t = {}, o) {
    let s = new URLSearchParams({ path: n });
    return t.offset !== void 0 && s.set("offset", String(t.offset)), t.maxBytes !== void 0 && s.set("maxBytes", String(t.maxBytes)), await this.fetchWithTimeout(`${this.baseUrl}/file/bytes?${s.toString()}`, { headers: this.headers({}, o) }, async (r) => {
      if (!r.ok) throw await this.failOnError(r, "GET /file/bytes");
      return await r.json();
    });
  }
  async fileStat(n) {
    let t = new URLSearchParams({ path: n });
    return await this.fetchWithTimeout(`${this.baseUrl}/stat?${t.toString()}`, { headers: this.headers() }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /stat");
      return await o.json();
    });
  }
  async dirList(n) {
    let t = new URLSearchParams({ path: n });
    return await this.fetchWithTimeout(`${this.baseUrl}/list?${t.toString()}`, { headers: this.headers() }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /list");
      return await o.json();
    });
  }
  async workspacePathSuggestions(n) {
    let t = new URLSearchParams({ prefix: n });
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace-path-suggestions?${t.toString()}`, { headers: this.headers() }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /workspace-path-suggestions");
      return await o.json();
    });
  }
  async workspaceDirectoryPicker() {
    return await this.jsonRequest("/workspace-directory-picker", "POST /workspace-directory-picker", { method: "POST", body: {}, timeoutMs: 31e4, mode: "rest" });
  }
  async glob(n) {
    let t = new URLSearchParams({ pattern: n });
    return await this.fetchWithTimeout(`${this.baseUrl}/glob?${t.toString()}`, { headers: this.headers() }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /glob");
      return await o.json();
    });
  }
  async writeWorkspaceFile(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/file/write`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify(n) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /file/write");
      return await o.json();
    });
  }
  async editWorkspaceFile(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/file/edit`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify(n) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /file/edit");
      return await o.json();
    });
  }
  async uploadFileToPath(n, t, o, s) {
    let r = new URLSearchParams({ path: o.path }), a = `${this.baseUrl}${n}?${r.toString()}`, i = this.headers({ "Content-Type": "application/octet-stream" }, s);
    return o.onProgress ? await this.uploadWithProgress(a, t, o, i) : await this.fetchWithTimeout(a, { method: "POST", headers: i, body: o.data, ...o.signal ? { signal: o.signal } : {} }, async (d) => {
      if (!d.ok) throw await this.failOnError(d, t);
      let c = await d.text(), p;
      try {
        p = c ? JSON.parse(c) : void 0;
      } catch {
        p = c;
      }
      if (!p || typeof p != "object" || !("path" in p)) throw new Error(`${t}: invalid upload response body`);
      return p;
    }, o.timeoutMs, "rest");
  }
  async uploadWithProgress(n, t, o, s) {
    if (typeof XMLHttpRequest > "u") throw new Error(`${t}: upload progress requires XMLHttpRequest (browser only)`);
    let r = this.fetchTimeoutMs;
    o.timeoutMs !== void 0 && Number.isFinite(o.timeoutMs) && o.timeoutMs >= 0 && (r = o.timeoutMs);
    let a = o.onProgress;
    return await new Promise((i, d) => {
      if (o.signal?.aborted) {
        d(o.signal.reason ?? new DOMException("The operation was aborted.", "AbortError"));
        return;
      }
      let c = new XMLHttpRequest(), p, g = () => {
        p && o.signal && o.signal.removeEventListener("abort", p);
      };
      c.open("POST", n);
      for (let [f, S] of Object.entries(s)) c.setRequestHeader(f, S);
      r > 0 && (c.timeout = r), c.upload.onprogress = (f) => {
        f.lengthComputable && a && a({ loaded: f.loaded, total: f.total });
      }, c.onload = () => {
        g();
        let f;
        try {
          f = c.responseText ? JSON.parse(c.responseText) : void 0;
        } catch {
          f = c.responseText;
        }
        if (c.status >= 200 && c.status < 300) {
          if (!f || typeof f != "object" || !("path" in f)) {
            d(new Error(`${t}: invalid upload response body`));
            return;
          }
          i(f);
          return;
        }
        let S = f && typeof f == "object" && "error" in f ? String(f.error) : `HTTP ${c.status}`;
        d(new x(c.status, f, `${t}: ${S}`));
      }, c.onerror = () => {
        g(), d(new Error(`${t}: network request failed`));
      }, c.ontimeout = () => {
        g(), d(new DOMException("timeout", "TimeoutError"));
      }, c.onabort = () => {
        g(), d(o.signal?.reason ?? new DOMException("The operation was aborted.", "AbortError"));
      }, o.signal && (p = () => c.abort(), o.signal.addEventListener("abort", p, { once: true }));
      try {
        c.send(o.data);
      } catch (f) {
        g(), d(f);
      }
    });
  }
  async uploadWorkspaceFile(n, t) {
    return await this.uploadFileToPath("/file/upload", "POST /file/upload", n, t);
  }
  async workspaceMemory() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/memory`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/memory");
      return await n.json();
    });
  }
  async writeWorkspaceMemory(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/memory`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify(n) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /workspace/memory");
      return await o.json();
    });
  }
  async rememberWorkspaceMemory(n, t = {}) {
    return t.scope && await this.requireCapability(t.scope === "project" ? "workspace_memory_remember_project_scope" : "workspace_memory_remember_user_scope"), await this.jsonRequest(on, `POST ${on}`, { method: "POST", body: { content: n, contextMode: t.contextMode ?? "workspace", ...t.scope ? { scope: t.scope } : {} }, clientId: t.clientId });
  }
  async getWorkspaceMemoryRememberTask(n, t) {
    return await this.jsonRequest(`${on}/${l(n)}`, `GET ${on}/:taskId`, { clientId: t?.clientId });
  }
  async forgetWorkspaceMemory(n, t = {}) {
    return t.scope && await this.requireCapability("workspace_memory_forget_scope"), await this.jsonRequest(sn, `POST ${sn}`, { method: "POST", body: { query: n, ...t.scope ? { scope: t.scope } : {} }, clientId: t.clientId });
  }
  async getWorkspaceMemoryForgetTask(n, t) {
    return await this.jsonRequest(`${sn}/${l(n)}`, `GET ${sn}/:taskId`, { clientId: t?.clientId });
  }
  async dreamWorkspaceMemory(n = {}) {
    return await this.jsonRequest(rn, `POST ${rn}`, { method: "POST", body: {}, clientId: n.clientId });
  }
  async getWorkspaceMemoryDreamTask(n, t) {
    return await this.jsonRequest(`${rn}/${l(n)}`, `GET ${rn}/:taskId`, { clientId: t?.clientId });
  }
  async listWorkspaceAgents() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/agents`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/agents");
      return await n.json();
    });
  }
  async createWorkspaceAgent(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/agents`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify(n) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /workspace/agents");
      return await o.json();
    });
  }
  async generateWorkspaceAgent(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/agents/generate`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify({ description: n }) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /workspace/agents/generate");
      return await o.json();
    }, J);
  }
  async *generateContentEvents(n, t, o, s, r, a) {
    let i = await this.transport.fetch(`${this.baseUrl}${n}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json", Accept: "text/event-stream" }, s?.clientId), body: JSON.stringify(o), signal: s?.signal });
    if (!i.ok) throw await this.failOnError(i, t);
    if (!i.body) throw new Error("Generation response body is missing");
    let d = false;
    for await (let c of Pe(i.body, s?.signal)) {
      let p = r(c);
      if (p && (d = p.type === "done" || p.type === "error", yield p, a && d)) return;
    }
    if (a && !s?.signal?.aborted && !d) throw new Error("Stream ended without terminal event");
  }
  async *generateWorkspaceContent(n, t) {
    yield* this.generateContentEvents("/workspace/generate", "POST /workspace/generate", { prompt: n }, t, qt, true);
  }
  async getWorkspaceAgent(n, t = {}) {
    let o = t.scope ? `${this.baseUrl}/workspace/agents/${l(n)}?scope=${l(t.scope)}` : `${this.baseUrl}/workspace/agents/${l(n)}`;
    return await this.fetchWithTimeout(o, { headers: this.headers() }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "GET /workspace/agents/:agentType");
      return await s.json();
    });
  }
  async updateWorkspaceAgent(n, t, o = {}, s) {
    let r = o.scope ? `${this.baseUrl}/workspace/agents/${l(n)}?scope=${l(o.scope)}` : `${this.baseUrl}/workspace/agents/${l(n)}`;
    return await this.fetchWithTimeout(r, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, s), body: JSON.stringify(t) }, async (a) => {
      if (!a.ok) throw await this.failOnError(a, "POST /workspace/agents/:agentType");
      return await a.json();
    });
  }
  async deleteWorkspaceAgent(n, t = {}, o) {
    let s = t.scope ? `${this.baseUrl}/workspace/agents/${l(n)}?scope=${l(t.scope)}` : `${this.baseUrl}/workspace/agents/${l(n)}`;
    return await this.fetchWithTimeout(s, { method: "DELETE", headers: this.headers({}, o) }, async (r) => {
      if (r.status === 204) {
        try {
          await r.body?.cancel();
        } catch {
        }
        return;
      }
      if (r.status === 404) {
        let a = await this.failOnError(r, "DELETE /workspace/agents/:agentType"), i = a.body;
        if (i && i.code === "agent_not_found") return;
        throw a;
      }
      throw await this.failOnError(r, "DELETE /workspace/agents/:agentType");
    });
  }
  async workspaceEnv() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/env`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/env");
      return await n.json();
    });
  }
  async workspacePreflight() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/preflight`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/preflight");
      return await n.json();
    });
  }
  async workspaceTools() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/tools`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/tools");
      return await n.json();
    });
  }
  async getStandaloneSessionOptions() {
    await this.requireCapability(Wn);
    let n = "GET /standalone/session-options", t = await this.jsonRequest("/standalone/session-options", n, { mode: "rest" });
    return It(t, n);
  }
  async createStandaloneSession(n = {}) {
    await this.requireCapability(he);
    let { sessionId: t, ...o } = n, s = (t ?? globalThis.crypto.randomUUID()).toLowerCase();
    try {
      let r = await this.jsonRequest("/standalone/sessions", "POST /standalone/sessions", { method: "POST", body: { sessionId: s, ...o }, mode: "rest" });
      return $n(r, "POST /standalone/sessions", s);
    } catch (r) {
      if (r instanceof x && !Ln(r)) throw r;
      let a = await this.recoverStandaloneCreation(s);
      throw new ge(s, a, r);
    }
  }
  async listStandaloneSessions(n = {}) {
    return (await this.listStandaloneSessionsPage(n)).sessions;
  }
  async listStandaloneSessionsPage(n = {}) {
    let t = new URLSearchParams();
    n.cursor !== void 0 && t.set("cursor", n.cursor), n.pageSize !== void 0 && t.set("size", String(n.pageSize)), n.archiveState !== void 0 && t.set("archiveState", n.archiveState);
    let o = t.toString(), s = o ? `?${o}` : "";
    return await this.standaloneJsonRequest(`/standalone/sessions${s}`, "GET /standalone/sessions", _t);
  }
  async getStandaloneSession(n) {
    return await this.requireCapability(he), await this.getStandaloneSessionUnchecked(n.toLowerCase());
  }
  async loadStandaloneSession(n, t = {}, o) {
    return await this.restoreStandaloneSession("load", n, t, o);
  }
  async resumeStandaloneSession(n, t = {}, o) {
    return await this.restoreStandaloneSession("resume", n, t, o);
  }
  async repairStandaloneSessionDirectory(n) {
    let t = n.toLowerCase(), o = "POST /standalone/sessions/:id/repair-directory";
    return await this.standaloneJsonRequest(`/standalone/sessions/${l(t)}/repair-directory`, o, (s) => At(s, o, t), { method: "POST", body: {} });
  }
  async renameStandaloneSession(n, t, o) {
    let s = n.toLowerCase(), r = "PATCH /standalone/sessions/:id/metadata";
    return await this.standaloneJsonRequest(`/standalone/sessions/${l(s)}/metadata`, r, (a) => Mt(a, r, s), { method: "PATCH", body: { displayName: t }, clientId: o });
  }
  async exportStandaloneSession(n, t = {}) {
    return await this.requireCapability(he), await this.sessionExportRequest(`/standalone/sessions/${l(n.toLowerCase())}/export`, "GET /standalone/sessions/:id/export", t);
  }
  async archiveStandaloneSessions(n) {
    return await this.standaloneBatchRequest("archive", n, Ot);
  }
  async unarchiveStandaloneSessions(n) {
    return await this.standaloneBatchRequest("unarchive", n, Bt);
  }
  async deleteStandaloneSessions(n) {
    return await this.standaloneBatchRequest("delete", n, Ut);
  }
  async standaloneJsonRequest(n, t, o, s = {}) {
    await this.requireCapability(he);
    let r = await this.jsonRequest(n, t, { ...s, mode: "rest" });
    return o(r, t);
  }
  async standaloneBatchRequest(n, t, o) {
    let s = `POST /standalone/sessions/${n}`;
    return await this.standaloneJsonRequest(`/standalone/sessions/${n}`, s, o, { method: "POST", body: { sessionIds: t.map((r) => r.toLowerCase()) } });
  }
  async restoreStandaloneSession(n, t, o, s) {
    let r = t.toLowerCase(), a = `POST /standalone/sessions/:id/${n}`, { timeoutMs: i, ...d } = o;
    return await this.standaloneJsonRequest(`/standalone/sessions/${l(r)}/${n}`, a, (c) => xt(c, a, r), { method: "POST", body: d, clientId: s, timeoutMs: this.resolveRestoreTimeoutMs(i) });
  }
  async getStandaloneSessionUnchecked(n) {
    let t = "GET /standalone/sessions/:id", o = await this.jsonRequest(`/standalone/sessions/${l(n)}`, t, { mode: "rest" });
    return Ct(o, t, n);
  }
  async recoverStandaloneCreation(n) {
    try {
      let t = await this.getStandaloneSessionUnchecked(n);
      return "state" in t ? { state: "creating", sessionId: n } : { state: "existing", session: t };
    } catch (t) {
      return Fn(t) ? { state: "absent", sessionId: n } : { state: "unknown", sessionId: n, error: t };
    }
  }
  async createOrAttachSession(n, t) {
    return n.sessionId !== void 0 && n.sessionId !== null && await this.requireCapability("session_id_override"), (n.sourceType !== void 0 || n.sourceId !== void 0) && await this.requireCapability("session_source_metadata"), await this.fetchWithTimeout(`${this.baseUrl}/session`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify({ cwd: n.workspaceCwd, ...n.sessionId !== void 0 ? { sessionId: n.sessionId } : {}, ...n.modelServiceId ? { modelServiceId: n.modelServiceId } : {}, ...n.sessionScope !== void 0 ? { sessionScope: n.sessionScope } : {}, ...n.approvalMode !== void 0 ? { approvalMode: n.approvalMode } : {}, ...n.sourceType !== void 0 ? { sourceType: n.sourceType } : {}, ...n.sourceId !== void 0 ? { sourceId: n.sourceId } : {}, ...n.worktree !== void 0 ? { worktree: n.worktree } : {}, ...n.branch !== void 0 ? { branch: n.branch } : {} }) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /session");
      let s = await o.json();
      if (typeof n.sessionId == "string" && s.sessionId !== n.sessionId.toLowerCase()) throw new dn(n.sessionId.toLowerCase(), s.sessionId);
      return s;
    });
  }
  async listWorkspaceSessions(n, t) {
    return (await this.listWorkspaceSessionsPage(n, t)).sessions;
  }
  async listWorkspaceSessionsPage(n, t) {
    (t?.sourceType !== void 0 || t?.sourceId !== void 0) && await this.requireCapability("session_source_metadata");
    let o = t?.pageSize ?? an, s = Math.max(1, Math.min(1e3, Math.round(Number.isFinite(o) ? o : an))), r = new URLSearchParams({ size: String(s) });
    return t?.cursor !== void 0 && r.set("cursor", t.cursor), t?.archiveState !== void 0 && r.set("archiveState", t.archiveState), t?.view !== void 0 && r.set("view", t.view), t?.group !== void 0 && r.set("group", t.group), t?.parentSessionId !== void 0 && r.set("parentSessionId", t.parentSessionId), t?.sourceType !== void 0 && r.set("sourceType", t.sourceType), t?.sourceId !== void 0 && r.set("sourceId", t.sourceId), await this.jsonRequest(`/workspace/${l(n)}/sessions?${r.toString()}`, "GET /workspace/sessions");
  }
  async searchWorkspaceSessions(n, t, o = {}) {
    let s = new URLSearchParams({ q: t });
    return o.maxResults !== void 0 && s.set("maxResults", String(o.maxResults)), await this.jsonRequest(`/workspace/${l(n)}/sessions/search?${s.toString()}`, "GET /workspace/sessions/search", { ...o.signal ? { signal: o.signal } : {} });
  }
  getWorkspaceSessionLiveState(n, t = {}) {
    return this.workspaceByCwd(n).getSessionLiveState(t);
  }
  async listSessionGroups(n) {
    return await this.jsonRequest(`/workspace/${l(n)}/session-groups`, "GET /workspace/session-groups");
  }
  async createSessionGroup(n, t) {
    return (await this.jsonRequest(`/workspace/${l(n)}/session-groups`, "POST /workspace/session-groups", { method: "POST", body: t })).group;
  }
  async updateSessionGroup(n, t, o) {
    return (await this.jsonRequest(`/workspace/${l(n)}/session-groups/${l(t)}`, "PATCH /workspace/session-groups/:groupId", { method: "PATCH", body: o })).group;
  }
  async deleteSessionGroup(n, t) {
    return await this.jsonRequest(`/workspace/${l(n)}/session-groups/${l(t)}`, "DELETE /workspace/session-groups/:groupId", { method: "DELETE" });
  }
  async updateSessionOrganization(n, t, o) {
    return await this.jsonRequest(`/session/${l(n)}/organization`, "PATCH /session/:id/organization", { method: "PATCH", body: t, clientId: o });
  }
  async loadSession(n, t = {}, o) {
    return this.restoreSession("load", n, t, o);
  }
  async exportSession(n, t = {}) {
    return await this.sessionExportRequest(`/session/${l(n)}/export`, "GET /session/:id/export", t);
  }
  async getSessionTranscriptPage(n, t = {}) {
    return await this.jsonRequest(`/session/${l(n)}/transcript${Gt(t)}`, "GET /session/:id/transcript", { clientId: t.clientId, mode: "rest" });
  }
  async getSessionTurnIndexPage(n, t = {}) {
    return await this.jsonRequest(`/session/${l(n)}/turn-index${jt(t)}`, "GET /session/:id/turn-index", { clientId: t.clientId, mode: "rest" });
  }
  async resolveSubagentSession(n, t, o) {
    return await this.jsonRequest(`/session/${l(n)}/subagents/${l(t)}`, "GET /session/:id/subagents/:subagentRef", { clientId: o, mode: "rest" });
  }
  async cancelSubagentSession(n, t, o) {
    return await this.jsonRequest(`/session/${l(n)}/subagents/${l(t)}/cancel`, "POST /session/:id/subagents/:subagentRef/cancel", { clientId: o, mode: "rest", method: "POST" });
  }
  async resumeSession(n, t = {}, o) {
    return this.restoreSession("resume", n, t, o);
  }
  async resetWorktreeSession(n, t = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/worktree-reset`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: JSON.stringify({ ...t.workspaceCwd !== void 0 ? { cwd: t.workspaceCwd } : {}, ...t.modelServiceId !== void 0 ? { modelServiceId: t.modelServiceId } : {}, ...t.approvalMode !== void 0 ? { approvalMode: t.approvalMode } : {}, ...t.sourceType !== void 0 ? { sourceType: t.sourceType } : {}, ...t.sourceId !== void 0 ? { sourceId: t.sourceId } : {} }) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /session/:id/worktree-reset");
      return await o.json();
    });
  }
  async branchSession(n, t = {}, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/branch`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o), body: JSON.stringify({ name: t.name, ..."atRecordId" in t ? { atRecordId: t.atRecordId } : {} }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/branch");
      return await s.json();
    }, 12e4);
  }
  async createSideTaskSession(n, t = {}, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/side-task`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o), body: JSON.stringify({ ...t.name !== void 0 ? { name: t.name } : {} }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/side-task");
      return await s.json();
    });
  }
  async forkSession(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/fork`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o), body: JSON.stringify({ directive: t.directive }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/fork");
      return await s.json();
    });
  }
  async sessionContext(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/context`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/context");
      return await o.json();
    });
  }
  async sessionStatus(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/status`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/status");
      return await o.json();
    });
  }
  async sessionContextUsage(n, t = {}, o) {
    let s = new URLSearchParams();
    t.detail === true && s.set("detail", "true");
    let r = s.toString();
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/context-usage${r ? `?${r}` : ""}`, { headers: this.headers({}, o) }, async (a) => {
      if (!a.ok) throw await this.failOnError(a, "GET /session/:id/context-usage");
      return await a.json();
    });
  }
  async sessionSupportedCommands(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/supported-commands`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/supported-commands");
      return await o.json();
    });
  }
  async sessionTasks(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/tasks`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/tasks");
      return await o.json();
    });
  }
  async sessionAgents(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/agents`, { headers: this.headers({}, t), signal: o }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "GET /session/:id/agents");
      return await s.json();
    });
  }
  async sessionAgentTrace(n, t = {}) {
    let o = new URLSearchParams();
    t.rootAgentId && o.set("rootAgentId", t.rootAgentId);
    let s = o.size > 0 ? `?${o}` : "";
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/agent-trace${s}`, { headers: this.headers({}, t.clientId), signal: t.signal }, async (r) => {
      if (!r.ok) throw await this.failOnError(r, "GET /session/:id/agent-trace");
      return await r.json();
    });
  }
  async sessionWorkflowTasks(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/tasks?includeWorkflows=true`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/tasks");
      return await o.json();
    });
  }
  async sessionSavedWorkflow(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/saved-workflows/${l(t)}`, { headers: this.headers({}, o) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "GET /session/:id/saved-workflows/:name");
      return await s.json();
    });
  }
  async sessionLspStatus(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/lsp`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/lsp");
      return await o.json();
    });
  }
  async sessionTaskCancel(n, t, o, s) {
    return await this.sessionTaskMutation(n, t, "cancel", { kind: o }, s);
  }
  async sessionWorkflowTaskAction(n, t, o, s) {
    return await this.sessionTaskMutation(n, t, "workflow-action", { action: o }, s);
  }
  async sessionTaskMutation(n, t, o, s, r) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/tasks/${l(t)}/${o}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, r), body: JSON.stringify(s) }, async (a) => {
      if (!a.ok) throw await this.failOnError(a, `POST /session/:id/tasks/:taskId/${o}`);
      return await a.json();
    });
  }
  sessionGoalClear(n, t) {
    return this.jsonRequest(`/session/${l(n)}/goal/clear`, "POST /session/:id/goal/clear", { method: "POST", body: {}, clientId: t });
  }
  sessionGoal(n, t) {
    return this.jsonRequest(`/session/${l(n)}/goal`, "GET /session/:id/goal", { clientId: t });
  }
  sessionGoalControl(n, t, o) {
    return this.jsonRequest(`/session/${l(n)}/goal`, "POST /session/:id/goal", { method: "POST", body: t, clientId: o });
  }
  async sessionStats(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/stats`, { headers: this.headers({}, t) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/stats");
      return await o.json();
    });
  }
  async restoreSession(n, t, o, s) {
    let r = o.sourceType, a = o.sourceId;
    if (o.sourceType !== void 0 || o.sourceId !== void 0) try {
      await this.requireCapability("session_source_metadata");
    } catch (d) {
      if (!(d instanceof te)) throw d;
      r = void 0, a = void 0;
    }
    let i = this.resolveRestoreTimeoutMs(o.timeoutMs);
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(t)}/${n}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, s), body: JSON.stringify({ cwd: o.workspaceCwd, ...o.approvalMode !== void 0 ? { approvalMode: o.approvalMode } : {}, ...n === "load" && o.historyPageSize !== void 0 ? { historyPageSize: o.historyPageSize } : {}, ...n === "load" && o.liveReplayMode !== void 0 ? { liveReplayMode: o.liveReplayMode } : {}, ...r !== void 0 ? { sourceType: r } : {}, ...a !== void 0 ? { sourceId: a } : {} }) }, async (d) => {
      if (!d.ok) throw await this.failOnError(d, `POST /session/:id/${n}`);
      return await d.json();
    }, i);
  }
  resolveRestoreTimeoutMs(n) {
    if (n !== void 0) {
      if (!Number.isFinite(n) || !Number.isInteger(n) || n < 0) throw new TypeError("RestoreSessionRequest.timeoutMs must be a non-negative integer");
      return n > fe ? 0 : n;
    }
    if (this.hasExplicitFetchTimeout) return this.fetchTimeoutMs > fe ? 0 : this.fetchTimeoutMs;
    let t = this.cachedSessionRestoreTimeoutMs ? this.cachedSessionRestoreTimeoutMs + Cs : Ps;
    return t > fe ? 0 : t;
  }
  async setSessionApprovalMode(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/approval-mode`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ mode: t, ...o?.planMode !== void 0 ? { planMode: o.planMode } : {}, ...o?.persist === true ? { persist: true } : {} }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/approval-mode");
      return await s.json();
    });
  }
  async getRewindSnapshots(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/rewind/snapshots`, { method: "GET", headers: this.headers() }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /session/:id/rewind/snapshots");
      return await t.json();
    }, void 0, "rest");
  }
  async rewindSession(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/rewind`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ promptId: t, ...o?.rewindFiles !== void 0 ? { rewindFiles: o.rewindFiles } : {} }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/rewind");
      return await s.json();
    }, void 0, "rest");
  }
  async recapSession(n, t) {
    let o = await this.transport.fetch(`${this.baseUrl}/session/${l(n)}/recap`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t?.clientId), body: "{}", signal: t?.signal });
    if (!o.ok) throw await this.failOnError(o, "POST /session/:id/recap");
    return await o.json();
  }
  async *generateSessionContent(n, t, o) {
    yield* this.generateContentEvents(`/session/${l(n)}/generate`, "POST /session/:id/generate", { prompt: t }, o, qt, false);
  }
  async btwSession(n, t, o) {
    let s = await this.transport.fetch(`${this.baseUrl}/session/${l(n)}/btw`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ question: t }), signal: o?.signal });
    if (!s.ok) throw await this.failOnError(s, "POST /session/:id/btw");
    return await s.json();
  }
  async uploadSessionAttachment(n, t, o, s, r) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/attachments?name=${l(o)}`, { method: "POST", headers: this.headers({ "Content-Type": s }, r?.clientId), body: t, signal: r?.signal }, async (a) => {
      if (!a.ok) throw await this.failOnError(a, "POST /session/:id/attachments");
      return await a.json();
    });
  }
  async readSessionAttachment(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/attachments/${l(t)}`, { method: "GET", headers: this.headers({}, o?.clientId), signal: o?.signal }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "GET /session/:id/attachments/:attachmentId");
      let r = new Uint8Array(await s.arrayBuffer()), a = "";
      for (let i = 0; i < r.length; i += 32768) a += String.fromCharCode(...r.subarray(i, i + 32768));
      return { data: btoa(a), mimeType: s.headers.get("content-type") ?? "application/octet-stream" };
    });
  }
  async listSessionAttachments(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/attachments`, { method: "GET", headers: this.headers({}, t?.clientId), signal: t?.signal }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/attachments");
      let s = await o.json();
      return Array.isArray(s.attachments) ? s.attachments : [];
    });
  }
  async removeSessionAttachment(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/attachments/${l(t)}`, { method: "DELETE", headers: this.headers({}, o?.clientId), signal: o?.signal }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "DELETE /session/:id/attachments/:attachmentId");
      return (await s.json()).removed === true;
    });
  }
  async enqueueMidTurnMessage(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/mid-turn-message`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ message: t, messageId: o?.messageId, ...o?.content && o.content.length > 0 ? { content: o.content } : {} }), signal: o?.signal }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/mid-turn-message");
      return await s.json();
    });
  }
  async removeMidTurnMessage(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/mid-turn-messages/${l(t)}`, { method: "DELETE", headers: this.headers({}, o?.clientId) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "DELETE /session/:id/mid-turn-messages/:messageId");
      return await s.json();
    });
  }
  async getMidTurnMessages(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/mid-turn-messages`, { method: "GET", headers: this.headers({}, t?.clientId), signal: t?.signal }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/mid-turn-messages");
      return await o.json();
    });
  }
  async getPendingPrompts(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/pending-prompts`, { method: "GET", headers: this.headers({}, t?.clientId) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /session/:id/pending-prompts");
      return await o.json();
    });
  }
  async removePendingPrompt(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/pending-prompts/${l(t)}`, { method: "DELETE", headers: this.headers({}, o?.clientId) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "DELETE /session/:id/pending-prompts/:promptId");
      return await s.json();
    });
  }
  async shellCommand(n, t, o) {
    let s = await this.transport.fetch(`${this.baseUrl}/session/${l(n)}/shell`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ command: t }), signal: o?.signal });
    if (!s.ok) throw await this.failOnError(s, "POST /session/:id/shell");
    return await s.json();
  }
  async setWorkspaceToolEnabled(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/tools/${l(n)}/enable`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ enabled: t }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /workspace/tools/:name/enable");
      return await s.json();
    });
  }
  async setWorkspaceSkillEnabled(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/skills/${l(n)}/enable`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ enabled: t }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /workspace/skills/:name/enable");
      return await s.json();
    });
  }
  async setWorkspaceSkillsEnabled(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/skills/enable`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ skillNames: n, enabled: t }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /workspace/skills/enable");
      return await s.json();
    });
  }
  installWorkspaceSkill(n) {
    return this.jsonRequest("/workspace/skills/install", "Skill", { method: "POST", body: n });
  }
  deleteWorkspaceSkill(n, t) {
    return this.jsonRequest(`/workspace/skills/${l(n)}?scope=${t}`, "Skill", { method: "DELETE" });
  }
  installWorkspaceConfigSkill(n) {
    return this.jsonRequest("/workspace/config/skills/install", "Skill", { method: "POST", body: n, mode: "rest" });
  }
  deleteWorkspaceConfigSkill(n, t) {
    return this.jsonRequest(`/workspace/config/skills/${l(n)}?scope=${t}`, "Skill", { method: "DELETE", mode: "rest" });
  }
  async workspaceSettings(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/settings`, { method: "GET", headers: this.headers({}, n?.clientId) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /workspace/settings");
      return await t.json();
    });
  }
  async setWorkspaceSetting(n, t, o, s) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/settings`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, s?.clientId), body: JSON.stringify({ scope: n, key: t, value: o, ...s?.mcpServerMutation ? { mcpServerMutation: s.mcpServerMutation } : {} }) }, async (r) => {
      if (!r.ok) throw await this.failOnError(r, "POST /workspace/settings");
      return await r.json();
    });
  }
  async deleteModel(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/models`, { method: "DELETE", headers: this.headers({ "Content-Type": "application/json" }, t?.clientId), body: JSON.stringify(n) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "DELETE /workspace/models");
      return await o.json();
    }, this.hasExplicitFetchTimeout ? void 0 : $t);
  }
  async workspaceVoice(n) {
    return await this.jsonRequest("/workspace/voice", "GET /workspace/voice", { clientId: n });
  }
  async setWorkspaceVoice(n, t) {
    return await this.jsonRequest("/workspace/voice", "POST /workspace/voice", { method: "POST", body: n, clientId: t });
  }
  async transcribeWorkspaceVoice(n, t) {
    return await this.voiceTranscriptionRequest("/workspace/voice/transcribe", "POST /workspace/voice/transcribe", n, t);
  }
  async liveStatus(n) {
    return await this.jsonRequest("/live/status", "GET /live/status", { clientId: n });
  }
  async liveSetupStatus(n) {
    return await this.jsonRequest("/live/setup", "GET /live/setup", { clientId: n });
  }
  async updateLiveSetup(n, t) {
    return await this.jsonRequest("/live/setup", "POST /live/setup", { method: "POST", body: n, clientId: t });
  }
  async retryLiveHostInstall(n) {
    return await this.jsonRequest("/live/setup/install", "POST /live/setup/install", { method: "POST", body: {}, clientId: n });
  }
  async launchLiveHost(n) {
    return await this.jsonRequest("/live/setup/launch", "POST /live/setup/launch", { method: "POST", body: {}, clientId: n });
  }
  async startLive(n = "resume", t) {
    let o = n === "new" ? "/live/new" : "/live/start";
    return await this.jsonRequest(o, n === "new" ? "POST /live/new" : "POST /live/start", { method: "POST", body: {}, clientId: t });
  }
  async stopLive(n) {
    return await this.jsonRequest("/live/stop", "POST /live/stop", { method: "POST", body: {}, clientId: n });
  }
  async setLiveMute(n, t) {
    return await this.jsonRequest("/live/mute", "POST /live/mute", { method: "POST", body: n, clientId: t });
  }
  async setLiveShortcut(n, t) {
    return await this.jsonRequest("/live/shortcut", "POST /live/shortcut", { method: "POST", body: { shortcut: n }, clientId: t });
  }
  async workspaceVoiceTranscriptionRequest(n, t, o) {
    return await this.voiceTranscriptionRequest(`/workspaces/${n}/voice/transcribe`, "POST /workspaces/:workspace/voice/transcribe", t, o);
  }
  async voiceTranscriptionRequest(n, t, o, s) {
    let r = s.voiceModel ? `?${new URLSearchParams({ voiceModel: s.voiceModel }).toString()}` : "";
    return await this.fetchWithTimeout(`${this.baseUrl}${n}${r}`, { method: "POST", headers: this.headers({ "Content-Type": s.mimeType }, s.clientId), body: o }, async (a) => {
      if (!a.ok) throw await this.failOnError(a, t);
      return await a.json();
    }, s.timeoutMs ?? _s, "rest");
  }
  async workspaceTrust(n) {
    let t = n?.statusVersion === 2 ? "?statusVersion=2" : "";
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/trust${t}`, { method: "GET", headers: this.headers({}, n?.clientId) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /workspace/trust");
      return await o.json();
    });
  }
  async requestWorkspaceTrustChange(n, t) {
    return await this.jsonRequest("/workspace/trust/request", "POST /workspace/trust/request", { method: "POST", body: n, clientId: t });
  }
  async workspacePermissions(n) {
    return await this.jsonRequest("/workspace/permissions", "GET /workspace/permissions", { clientId: n?.clientId });
  }
  async setWorkspacePermissionRules(n, t, o, s) {
    return await this.jsonRequest("/workspace/permissions", "POST /workspace/permissions", { method: "POST", body: { scope: n, ruleType: t, rules: [...o] }, clientId: s?.clientId });
  }
  async addWorkspacePermissionRule(n, t, o, s) {
    let r = Nt(o), a = await this.workspacePermissions(s), i = a[n].rules[t];
    return i.includes(r) ? a : await this.setWorkspacePermissionRules(n, t, [...i, r], s);
  }
  async removeWorkspacePermissionRule(n, t, o, s) {
    let r = Nt(o), a = await this.workspacePermissions(s), i = a[n].rules[t];
    return i.includes(r) ? await this.setWorkspacePermissionRules(n, t, i.filter((d) => d !== r), s) : a;
  }
  async restartMcpServer(n, t) {
    let o = t?.entryIndex === void 0 ? "" : `?entryIndex=${l(String(t.entryIndex))}`;
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/${l(n)}/restart${o}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t?.clientId), body: "{}" }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /workspace/mcp/:server/restart");
      return await s.json();
    }, t?.timeoutMs ?? J);
  }
  async reload(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/reload`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, n?.clientId), body: "{}" }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "POST /workspace/reload");
      return await t.json();
    }, n?.timeoutMs);
  }
  async reloadChannelWorker(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/channel/reload`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, n?.clientId), body: "{}" }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "POST /workspace/channel/reload");
      return await t.json();
    }, n?.timeoutMs ?? 213e4);
  }
  async getChannelWorkerControl(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/channel`, { method: "GET", headers: this.headers({}, n?.clientId) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /workspace/channel");
      return await t.json();
    }, n?.timeoutMs);
  }
  async setChannelWorkerSelection(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/channel`, { method: "PUT", headers: this.headers({ "Content-Type": "application/json" }, t?.clientId), body: JSON.stringify({ selection: n }) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "PUT /workspace/channel");
      return await o.json();
    }, t?.timeoutMs ?? 213e4);
  }
  async stopChannelWorker(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/channel`, { method: "DELETE", headers: this.headers({}, n?.clientId) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "DELETE /workspace/channel");
      return await t.json();
    }, n?.timeoutMs ?? 213e4);
  }
  workspaceChannelTypes(n) {
    return this.jsonRequest("/workspace/channel-types", "GET /workspace/channel-types", { clientId: n?.clientId, timeoutMs: n?.timeoutMs, mode: "rest" });
  }
  workspaceChannels(n) {
    return this.jsonRequest("/workspace/channels", "GET /workspace/channels", { clientId: n?.clientId, timeoutMs: n?.timeoutMs, mode: "rest" });
  }
  upsertWorkspaceChannel(n, t, o) {
    return this.jsonRequest(`/workspace/channels/${l(n)}`, "PUT /workspace/channels/:name", { method: "PUT", body: t, clientId: o?.clientId, timeoutMs: o?.timeoutMs ?? 213e4, mode: "rest" });
  }
  deleteWorkspaceChannel(n, t, o) {
    return this.jsonRequest(`/workspace/channels/${l(n)}`, "DELETE /workspace/channels/:name", { method: "DELETE", body: t, clientId: o?.clientId, timeoutMs: o?.timeoutMs ?? 213e4, mode: "rest" });
  }
  setWorkspaceChannelStartup(n, t, o) {
    return this.jsonRequest(`/workspace/channels/${l(n)}/startup`, "PUT /workspace/channels/:name/startup", { method: "PUT", body: t, clientId: o?.clientId, timeoutMs: o?.timeoutMs ?? 213e4, mode: "rest" });
  }
  startWorkspaceChannel(n, t) {
    return this.workspaceChannelAction(n, "start", t);
  }
  stopWorkspaceChannel(n, t) {
    return this.workspaceChannelAction(n, "stop", t);
  }
  restartWorkspaceChannel(n, t) {
    return this.workspaceChannelAction(n, "restart", t);
  }
  workspaceChannelPairingRequests(n, t) {
    return this.jsonRequest(`/workspace/channels/${l(n)}/pairing-requests`, "GET /workspace/channels/:name/pairing-requests", { clientId: t?.clientId, timeoutMs: t?.timeoutMs, mode: "rest" });
  }
  approveWorkspaceChannelPairing(n, t, o) {
    return this.jsonRequest(`/workspace/channels/${l(n)}/pairing-requests/approve`, "POST /workspace/channels/:name/pairing-requests/approve", { method: "POST", body: t, clientId: o?.clientId, timeoutMs: o?.timeoutMs ?? 213e4, mode: "rest" });
  }
  workspaceChannelPairingApprovals(n, t) {
    return this.jsonRequest(`/workspace/channels/${l(n)}/pairing-approvals`, "GET /workspace/channels/:name/pairing-approvals", { clientId: t?.clientId, timeoutMs: t?.timeoutMs, mode: "rest" });
  }
  revokeWorkspaceChannelPairingApproval(n, t, o) {
    return this.jsonRequest(`/workspace/channels/${l(n)}/pairing-approvals`, "DELETE /workspace/channels/:name/pairing-approvals", { method: "DELETE", body: t, clientId: o?.clientId, timeoutMs: o?.timeoutMs ?? 213e4, mode: "rest" });
  }
  workspaceChannelAction(n, t, o) {
    return this.jsonRequest(`/workspace/channels/${l(n)}/${t}`, `POST /workspace/channels/:name/${t}`, { method: "POST", body: {}, clientId: o?.clientId, timeoutMs: o?.timeoutMs ?? 213e4, mode: "rest" });
  }
  async manageMcpServer(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/${l(n)}/${l(t)}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: "{}" }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /workspace/mcp/:server/:action");
      return await s.json();
    }, o?.timeoutMs ?? J);
  }
  async addRuntimeMcpServer(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/servers`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t?.clientId), body: JSON.stringify(n) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /workspace/mcp/servers");
      return await o.json();
    }, t?.timeoutMs ?? J);
  }
  async removeRuntimeMcpServer(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/mcp/servers/${l(n)}`, { method: "DELETE", headers: this.headers({}, t?.clientId) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "DELETE /workspace/mcp/servers/:name");
      return await o.json();
    }, t?.timeoutMs ?? J);
  }
  async initWorkspace(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/init`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, n?.clientId), body: JSON.stringify(n?.force === true ? { force: true } : {}) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "POST /workspace/init");
      return await t.json();
    });
  }
  async setupGithub(n, t) {
    return await this.jsonRequest("/workspace/setup-github", "POST /workspace/setup-github", { method: "POST", body: n, clientId: t, timeoutMs: As });
  }
  async setSessionModel(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/model`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o), body: JSON.stringify({ modelId: t }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/model");
      return await s.json();
    });
  }
  async setSessionConfigOption(n, t, o, s) {
    let r = typeof s == "string" ? { clientId: s } : s;
    return await this.jsonRequest(`/session/${l(n)}/config-option`, "POST /session/:id/config-option", { method: "POST", body: { configId: t, value: o, ...r?.persist !== void 0 ? { persist: r.persist } : {} }, clientId: r?.clientId });
  }
  async setSessionLanguage(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/language`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o?.clientId), body: JSON.stringify({ language: t, syncOutputLanguage: o?.syncOutputLanguage ?? false }) }, async (s) => {
      if (!s.ok) throw await this.failOnError(s, "POST /session/:id/language");
      return await s.json();
    });
  }
  async setUserLanguage(n, t) {
    return await this.jsonRequest("/language", "POST /language", { method: "POST", body: { language: n, syncOutputLanguage: t?.syncOutputLanguage ?? false }, clientId: t?.clientId });
  }
  async prompt(n, t, o, s) {
    o?.throwIfAborted();
    let r = this.reservePromptSlot(n), a = true;
    try {
      let i = await this.transport.fetch(`${this.baseUrl}/session/${l(n)}/prompt`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, s), body: JSON.stringify(t), signal: o });
      if (i.status === 202) {
        let d = await i.json();
        a = false;
        try {
          return await this._awaitTurnComplete(n, d.promptId, d.lastEventId, o, s, d.eventEpoch);
        } finally {
          r();
        }
      }
      if (!i.ok) throw await this.failOnError(i, "POST /session/:id/prompt", n);
      return await i.json();
    } finally {
      a && r();
    }
  }
  async promptNonBlocking(n, t, o, s) {
    let r = await this.transport.fetch(`${this.baseUrl}/session/${l(n)}/prompt`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, s), body: JSON.stringify(t), signal: o });
    if (r.status === 202) return await r.json();
    if (!r.ok) throw await this.failOnError(r, "POST /session/:id/prompt", n);
    return await r.json();
  }
  async _awaitTurnComplete(n, t, o, s, r, a) {
    let i = new AbortController(), d = s ? Gn([s, i.signal]) : i.signal;
    try {
      let c = this.subscribeEvents(n, { lastEventId: o, ...a !== void 0 ? { epoch: a } : {}, signal: d });
      for await (let p of c) {
        let g = cn(p, t);
        if (g !== void 0) return g;
      }
      throw new Error("SSE stream ended");
    } catch (c) {
      throw s?.aborted && c instanceof DOMException && c.name === "AbortError" && this.cancel(n, r).catch(() => {
      }), c;
    } finally {
      i.signal.aborted || i.abort();
    }
  }
  async heartbeat(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/heartbeat`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: "{}" }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /session/:id/heartbeat");
      return await o.json();
    });
  }
  async cancel(n, t) {
    await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/cancel`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: "{}" }, async (o) => {
      if (!o.ok && o.status !== 204) throw await this.failOnError(o, "POST /session/:id/cancel");
      try {
        await o.body?.cancel();
      } catch {
      }
    });
  }
  async *subscribeEvents(n, t = {}) {
    yield* this.transport.subscribeEvents(n, { lastEventId: t.lastEventId, epoch: t.epoch, onEpoch: t.onEpoch, maxQueued: t.maxQueued, clientId: t.clientId, sseConnectReason: t.sseConnectReason, previousSseStreamId: t.previousSseStreamId, onSseStreamAccepted: t.onSseStreamAccepted, signal: t.signal, connectTimeoutMs: this.fetchTimeoutMs || void 0 });
  }
  async respondToPermission(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/permission/${l(n)}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, o), body: JSON.stringify(t) }, async (s) => {
      if (s.status === 200) {
        try {
          await s.body?.cancel();
        } catch {
        }
        return true;
      }
      if (s.status === 404) {
        try {
          await s.body?.cancel();
        } catch {
        }
        return false;
      }
      throw await this.failOnError(s, "POST /permission/:requestId");
    });
  }
  async respondToSessionPermission(n, t, o, s) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/permission/${l(t)}`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, s), body: JSON.stringify(o) }, async (r) => {
      if (r.status === 200) {
        try {
          await r.body?.cancel();
        } catch {
        }
        return true;
      }
      if (r.status === 404) {
        try {
          await r.body?.cancel();
        } catch {
        }
        return false;
      }
      throw await this.failOnError(r, "POST /session/:id/permission/:requestId");
    });
  }
  async closeSession(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}`, { method: "DELETE", headers: this.headers({}, t) }, async (o) => {
      if (o.status === 204 || o.status === 404) {
        try {
          await o.body?.cancel();
        } catch {
        }
        return;
      }
      throw await this.failOnError(o, "DELETE /session/:id");
    });
  }
  async detachSession(n, t) {
    if (t) return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/detach`, { method: "POST", headers: this.headers({}, t) }, async (o) => {
      if (o.status === 204 || o.status === 404) {
        try {
          await o.body?.cancel();
        } catch {
        }
        return;
      }
      throw await this.failOnError(o, "POST /session/:id/detach");
    });
  }
  async deleteSessionsData(n, t) {
    return await this.fetchWithTimeout(`${this.baseUrl}/sessions/delete`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, t), body: JSON.stringify({ sessionIds: n }) }, async (o) => {
      if (o.ok) return await o.json();
      throw await this.failOnError(o, "POST /sessions/delete");
    });
  }
  async archiveSessionsData(n, t, o) {
    let s = typeof t == "object" ? t : void 0;
    return await this.fetchWithTimeout(`${this.baseUrl}/sessions/archive`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, typeof t == "string" ? t : o), body: JSON.stringify({ sessionIds: n, ...s?.resolveConflicts !== void 0 ? { resolveConflicts: s.resolveConflicts } : {} }) }, async (r) => {
      if (r.ok) return await r.json();
      throw await this.failOnError(r, "POST /sessions/archive");
    });
  }
  async unarchiveSessionsData(n, t, o) {
    let s = typeof t == "object" ? t : void 0;
    return await this.fetchWithTimeout(`${this.baseUrl}/sessions/unarchive`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, typeof t == "string" ? t : o), body: JSON.stringify({ sessionIds: n, ...s?.resolveConflicts !== void 0 ? { resolveConflicts: s.resolveConflicts } : {} }) }, async (r) => {
      if (r.ok) return await r.json();
      throw await this.failOnError(r, "POST /sessions/unarchive");
    });
  }
  async startDeviceFlow(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/auth/device-flow`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }, n.clientId), body: JSON.stringify({ providerId: n.providerId }) }, async (t) => {
      if (t.status !== 200 && t.status !== 201) throw await this.failOnError(t, "POST /workspace/auth/device-flow");
      return await t.json();
    });
  }
  async getDeviceFlow(n, t = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/auth/device-flow/${l(n)}`, { headers: this.headers({}, t.clientId), signal: t.signal }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "GET /workspace/auth/device-flow/:id");
      return await o.json();
    });
  }
  async cancelDeviceFlow(n, t = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/auth/device-flow/${l(n)}`, { method: "DELETE", headers: this.headers({}, t.clientId) }, async (o) => {
      if (o.status === 204 || o.status === 404) {
        try {
          await o.body?.cancel();
        } catch {
        }
        return;
      }
      throw await this.failOnError(o, "DELETE /workspace/auth/device-flow/:id");
    });
  }
  async getAuthStatus(n = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/auth/status`, { headers: this.headers({}, n.clientId) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "GET /workspace/auth/status");
      return await t.json();
    });
  }
  async getAuthProviders() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/auth/providers`, { headers: this.headers() }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "GET /workspace/auth/providers");
      return await n.json();
    });
  }
  async installAuthProvider(n) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspace/auth/provider`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: JSON.stringify(n) }, async (t) => {
      if (!t.ok) throw await this.failOnError(t, "POST /workspace/auth/provider");
      return await t.json();
    }, this.hasExplicitFetchTimeout ? void 0 : $t);
  }
  async addWorkspace(n, t = {}) {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspaces`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: JSON.stringify({ cwd: n, ...t.persist ? { persist: true } : {}, ...t.displayName !== void 0 ? { displayName: t.displayName } : {} }) }, async (o) => {
      if (!o.ok) throw await this.failOnError(o, "POST /workspaces");
      return await o.json();
    });
  }
  async updateWorkspace(n, t) {
    return await this.workspaceJsonRequest(l(n), "", "PATCH /workspaces/:workspace", { method: "PATCH", body: t, mode: "rest" });
  }
  async addScratchWorkspace() {
    return await this.fetchWithTimeout(`${this.baseUrl}/workspaces`, { method: "POST", headers: this.headers({ "Content-Type": "application/json" }), body: JSON.stringify({ kind: "scratch" }) }, async (n) => {
      if (!n.ok) throw await this.failOnError(n, "POST /workspaces");
      return await n.json();
    });
  }
  dispose() {
    this.transport.dispose();
  }
  listSessionSources(n, t) {
    return this.jsonRequest(`/session/${l(n)}/sources`, "GET /session/:id/sources", { clientId: t, mode: "rest" });
  }
  upsertSessionSource(n, t, o) {
    return this.jsonRequest(`/session/${l(n)}/sources`, "POST /session/:id/sources", { method: "POST", body: t, clientId: o, mode: "rest" });
  }
  removeSessionSource(n, t, o) {
    return this.jsonRequest(`/session/${l(n)}/sources/${l(t)}`, "DELETE /session/:id/sources/:sourceId", { method: "DELETE", clientId: o, mode: "rest" });
  }
  async listSessionArtifacts(n, t) {
    return await this.jsonRequest(`/session/${l(n)}/artifacts`, "GET /session/:id/artifacts", { clientId: t });
  }
  async addSessionArtifact(n, t, o) {
    return await this.jsonRequest(`/session/${l(n)}/artifacts`, "POST /session/:id/artifacts", { method: "POST", body: t, clientId: o });
  }
  async removeSessionArtifact(n, t, o) {
    return await this.jsonRequest(`/session/${l(n)}/artifacts/${l(t)}`, "DELETE /session/:id/artifacts/:artifactId", { method: "DELETE", clientId: o });
  }
  async updateSessionMetadata(n, t, o) {
    return await this.fetchWithTimeout(`${this.baseUrl}/session/${l(n)}/metadata`, { method: "PATCH", headers: this.headers({ "Content-Type": "application/json" }, o), body: JSON.stringify(t) }, async (s) => {
      if (s.status === 200) {
        let r = await s.json(), a = {};
        if (typeof r.displayName == "string" && (a.displayName = r.displayName), Array.isArray(r.prs)) {
          let i = r.prs.filter(xe);
          i.length > 0 && (a.prs = i);
        }
        return a;
      }
      throw await this.failOnError(s, "PATCH /session/:id/metadata");
    });
  }
};
var Me = class {
  constructor(n, t) {
    this.client = n;
    this.workspaceSelector = t;
  }
  workspaceMcp() {
    return this.get("/mcp", "GET /workspaces/:workspace/mcp");
  }
  mcpConfig() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/config/mcp/servers", "GET /workspaces/:workspace/config/mcp/servers", { mode: "rest" });
  }
  setMcpServer(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/config/mcp/servers/${l(n)}`, "PUT /workspaces/:workspace/config/mcp/servers/:name", { method: "PUT", body: { scope: "workspace", config: t }, mode: "rest" });
  }
  removeMcpServer(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/config/mcp/servers/${l(n)}?scope=workspace`, "DELETE /workspaces/:workspace/config/mcp/servers/:name", { method: "DELETE", mode: "rest" });
  }
  setMcpServerEnabled(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/config/mcp/${l(n)}/${t ? "enable" : "disable"}`, "POST /workspaces/:workspace/config/mcp/:server/:action", { method: "POST", body: {}, mode: "rest" });
  }
  runtimeMcp() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/runtime/mcp", "GET /workspaces/:workspace/runtime/mcp", { mode: "rest" });
  }
  runtimeMcpTools(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/runtime/mcp/${l(n)}/tools`, "GET /workspaces/:workspace/runtime/mcp/:server/tools", { mode: "rest" });
  }
  runtimeMcpResources(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/runtime/mcp/${l(n)}/resources`, "GET /workspaces/:workspace/runtime/mcp/:server/resources", { mode: "rest" });
  }
  reloadRuntimeMcp(n = {}) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/runtime/mcp/reload", "POST /workspaces/:workspace/runtime/mcp/reload", { method: "POST", body: n, mode: "rest", timeoutMs: J });
  }
  restartRuntimeMcpServer(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/runtime/mcp/${l(n)}/restart`, "POST /workspaces/:workspace/runtime/mcp/:server/restart", { method: "POST", body: {}, mode: "rest", timeoutMs: J });
  }
  manageRuntimeMcpServer(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/runtime/mcp/${l(n)}/${t}`, "POST /workspaces/:workspace/runtime/mcp/:server/:action", { method: "POST", body: {}, mode: "rest", timeoutMs: J });
  }
  ensureRuntime() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/runtime/ensure", "POST /workspaces/:workspace/runtime/ensure", { method: "POST", timeoutMs: Lt, mode: "rest" });
  }
  runtimeStatus() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/runtime/status", "GET /workspaces/:workspace/runtime/status", { mode: "rest" });
  }
  async openLocally() {
    await this.client.workspaceJsonRequest(this.workspaceSelector, "/open", "POST /workspaces/:workspace/open", { method: "POST", body: {}, mode: "rest" });
  }
  async openTerminalLocally() {
    await this.client.workspaceJsonRequest(this.workspaceSelector, "/open", "POST /workspaces/:workspace/open", { method: "POST", body: { target: "terminal" }, mode: "rest" });
  }
  notify(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/notify", "POST /workspaces/:workspace/notify", { method: "POST", body: n, timeoutMs: t?.timeoutMs ?? Ft, mode: "rest" });
  }
  workspaceChannelTypes(n) {
    return this.channelRequest("/channel-types", "GET /workspaces/:workspace/channel-types", void 0, n);
  }
  workspaceChannels(n) {
    return this.channelRequest("/channels", "GET /workspaces/:workspace/channels", void 0, n);
  }
  upsertWorkspaceChannel(n, t, o) {
    return this.channelRequest(`/channels/${l(n)}`, "PUT /workspaces/:workspace/channels/:name", { method: "PUT", body: t }, o);
  }
  deleteWorkspaceChannel(n, t, o) {
    return this.channelRequest(`/channels/${l(n)}`, "DELETE /workspaces/:workspace/channels/:name", { method: "DELETE", body: t }, o);
  }
  setWorkspaceChannelStartup(n, t, o) {
    return this.channelRequest(`/channels/${l(n)}/startup`, "PUT /workspaces/:workspace/channels/:name/startup", { method: "PUT", body: t }, o);
  }
  startWorkspaceChannel(n, t) {
    return this.channelAction(n, "start", t);
  }
  stopWorkspaceChannel(n, t) {
    return this.channelAction(n, "stop", t);
  }
  restartWorkspaceChannel(n, t) {
    return this.channelAction(n, "restart", t);
  }
  workspaceChannelPairingRequests(n, t) {
    return this.channelRequest(`/channels/${l(n)}/pairing-requests`, "GET /workspaces/:workspace/channels/:name/pairing-requests", void 0, t);
  }
  approveWorkspaceChannelPairing(n, t, o) {
    return this.channelRequest(`/channels/${l(n)}/pairing-requests/approve`, "POST /workspaces/:workspace/channels/:name/pairing-requests/approve", { method: "POST", body: t }, o);
  }
  workspaceChannelPairingApprovals(n, t) {
    return this.channelRequest(`/channels/${l(n)}/pairing-approvals`, "GET /workspaces/:workspace/channels/:name/pairing-approvals", void 0, t);
  }
  revokeWorkspaceChannelPairingApproval(n, t, o) {
    return this.channelRequest(`/channels/${l(n)}/pairing-approvals`, "DELETE /workspaces/:workspace/channels/:name/pairing-approvals", { method: "DELETE", body: t }, o);
  }
  channelAction(n, t, o) {
    return this.channelRequest(`/channels/${l(n)}/${t}`, `POST /workspaces/:workspace/channels/:name/${t}`, { method: "POST", body: {} }, o);
  }
  channelRequest(n, t, o, s) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, n, t, { ...o ?? {}, clientId: s?.clientId, timeoutMs: s?.timeoutMs ?? (o ? 213e4 : void 0), mode: "rest" });
  }
  initializeWorkspaceMcp() {
    return this.post("/mcp/initialize", "POST /workspaces/:workspace/mcp/initialize", {});
  }
  reloadWorkspaceMcp(n = {}) {
    return this.post("/mcp/reload", "POST /workspaces/:workspace/mcp/reload", n);
  }
  workspaceVoice(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/voice", "GET /workspaces/:workspace/voice", { clientId: n, mode: "rest" });
  }
  setWorkspaceVoice(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/voice", "POST /workspaces/:workspace/voice", { method: "POST", body: n, clientId: t, mode: "rest" });
  }
  transcribeWorkspaceVoice(n, t) {
    return this.client.workspaceVoiceTranscriptionRequest(this.workspaceSelector, n, t);
  }
  liveStatus(n) {
    return this.client.liveStatus(n);
  }
  liveSetupStatus(n) {
    return this.client.liveSetupStatus(n);
  }
  updateLiveSetup(n, t) {
    return this.client.updateLiveSetup(n, t);
  }
  retryLiveHostInstall(n) {
    return this.client.retryLiveHostInstall(n);
  }
  launchLiveHost(n) {
    return this.client.launchLiveHost(n);
  }
  startLive(n = "resume", t) {
    return this.client.startLive(n, t);
  }
  stopLive(n) {
    return this.client.stopLive(n);
  }
  setLiveMute(n, t) {
    return this.client.setLiveMute(n, t);
  }
  setLiveShortcut(n, t) {
    return this.client.setLiveShortcut(n, t);
  }
  workspaceGit(n) {
    let t = new URLSearchParams();
    n?.cwd && t.set("cwd", n.cwd), n?.wait && t.set("wait", "1");
    let o = t.toString(), s = o ? `/git?${o}` : "/git";
    return this.client.workspaceJsonRequest(this.workspaceSelector, s, "GET /workspaces/:workspace/git", { mode: "rest" });
  }
  workspaceGitDiff(n) {
    let t = n != null ? `/git/diff?cwd=${l(n)}` : "/git/diff";
    return this.client.workspaceJsonRequest(this.workspaceSelector, t, "GET /workspaces/:workspace/git/diff", { mode: "rest" });
  }
  workspaceGitDiffFile(n, t, o) {
    let s = `/git/diff/file?path=${l(n)}` + (t != null ? `&oldPath=${l(t)}` : "") + (o != null ? `&cwd=${l(o)}` : "");
    return this.client.workspaceJsonRequest(this.workspaceSelector, s, "GET /workspaces/:workspace/git/diff/file", { mode: "rest" });
  }
  workspaceGitLog(n, t, o, s) {
    let r = new URLSearchParams();
    n != null && r.set("limit", String(n)), t != null && r.set("skip", String(t)), o != null && r.set("cwd", o), s && r.set("range", s);
    let a = r.toString();
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/git/log${a ? `?${a}` : ""}`, "GET /workspaces/:workspace/git/log", { mode: "rest" });
  }
  workspaceGitCommitDetail(n, t) {
    let o = `/git/log/commit?sha=${l(n)}` + (t != null ? `&cwd=${l(t)}` : "");
    return this.client.workspaceJsonRequest(this.workspaceSelector, o, "GET /workspaces/:workspace/git/log/commit", { mode: "rest" });
  }
  workspaceGitBranches(n) {
    let t = n != null ? `/git/branches?cwd=${l(n)}` : "/git/branches";
    return this.client.workspaceJsonRequest(this.workspaceSelector, t, "GET /workspaces/:workspace/git/branches", { mode: "rest" });
  }
  workspaceGitCheckout(n, t) {
    let o = t != null ? `/git/checkout?cwd=${l(t)}` : "/git/checkout";
    return this.client.workspaceJsonRequest(this.workspaceSelector, o, "POST /workspaces/:workspace/git/checkout", { method: "POST", body: { ref: n }, mode: "rest" });
  }
  workspaceGitCreateBranch(n, t, o) {
    let s = o != null ? `/git/branch?cwd=${l(o)}` : "/git/branch";
    return this.client.workspaceJsonRequest(this.workspaceSelector, s, "POST /workspaces/:workspace/git/branch", { method: "POST", body: { name: n, startPoint: t }, mode: "rest" });
  }
  workspaceGitPush(n, t) {
    let o = t != null ? `/git/push?cwd=${l(t)}` : "/git/push";
    return this.client.workspaceJsonRequest(this.workspaceSelector, o, "POST /workspaces/:workspace/git/push", { method: "POST", body: n ?? {}, mode: "rest" });
  }
  workspaceGitPull(n, t, o) {
    let s = t != null ? `/git/pull?cwd=${l(t)}` : "/git/pull";
    return this.client.workspaceJsonRequest(this.workspaceSelector, s, "POST /workspaces/:workspace/git/pull", { method: "POST", body: n ?? {}, mode: "rest", timeoutMs: o });
  }
  workspaceGitCommit(n, t, o) {
    let s = o != null ? `/git/commit?cwd=${l(o)}` : "/git/commit";
    return this.client.workspaceJsonRequest(this.workspaceSelector, s, "POST /workspaces/:workspace/git/commit", { method: "POST", body: { message: n, ...t }, mode: "rest" });
  }
  workspaceGitHubPullRequests() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/github/prs", "GET /workspaces/:workspace/github/prs", { mode: "rest" });
  }
  workspaceGitHubCreatePullRequest(n, t) {
    let o = t != null ? `/github/prs/create?cwd=${l(t)}` : "/github/prs/create";
    return this.client.workspaceJsonRequest(this.workspaceSelector, o, "POST /workspaces/:workspace/github/prs/create", { method: "POST", body: n, mode: "rest" });
  }
  workspaceGitHubDefaultBranch() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/github/default-branch", "GET /workspaces/:workspace/github/default-branch", { mode: "rest" });
  }
  workspaceSkills() {
    return this.get("/skills", "GET /workspaces/:workspace/skills");
  }
  workspaceConfigSkills() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/config/skills", "GET /workspaces/:workspace/config/skills", { mode: "rest" });
  }
  workspaceRuntimeSkills() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/runtime/skills", "GET /workspaces/:workspace/runtime/skills", { mode: "rest" });
  }
  setWorkspaceConfigSkillEnabled(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/config/skills/${l(n)}/enable`, "POST /workspaces/:workspace/config/skills/:name/enable", { method: "POST", body: { enabled: t }, clientId: o?.clientId, mode: "rest" });
  }
  installWorkspaceConfigSkill(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/config/skills/install", "POST /workspaces/:workspace/config/skills/install", { method: "POST", body: n, mode: "rest" });
  }
  deleteWorkspaceConfigSkill(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/config/skills/${l(n)}?scope=${t}`, "DELETE /workspaces/:workspace/config/skills/:name", { method: "DELETE", mode: "rest" });
  }
  workspaceProviders() {
    return this.get("/providers", "GET /workspaces/:workspace/providers");
  }
  workspaceHooks() {
    return this.get("/hooks", "GET /workspaces/:workspace/hooks");
  }
  workspaceEnv() {
    return this.get("/env", "GET /workspaces/:workspace/env");
  }
  workspacePreflight() {
    return this.get("/preflight", "GET /workspaces/:workspace/preflight");
  }
  workspaceTools() {
    return this.get("/tools", "GET /workspaces/:workspace/tools");
  }
  workspaceMemory() {
    return this.get("/memory", "GET /workspaces/:workspace/memory");
  }
  remove(n) {
    let t = n?.force === void 0 ? void 0 : { force: n.force };
    return this.client.workspaceJsonRequest(this.workspaceSelector, "", "DELETE /workspaces/:workspace", { method: "DELETE", ...t ? { body: t } : {}, ...n?.timeoutMs !== void 0 ? { timeoutMs: n.timeoutMs } : {}, mode: "rest" });
  }
  writeWorkspaceMemory(n, t) {
    return this.post("/memory", "POST /workspaces/:workspace/memory", { ...n, scope: "workspace" }, t);
  }
  listWorkspaceAgents() {
    return this.get("/agents", "GET /workspaces/:workspace/agents");
  }
  createWorkspaceAgent(n, t) {
    return this.post("/agents", "POST /workspaces/:workspace/agents", { ...n, scope: n.scope ?? "workspace" }, t);
  }
  getWorkspaceAgent(n) {
    return this.get(`/agents/${l(n)}`, "GET /workspaces/:workspace/agents/:agentType");
  }
  updateWorkspaceAgent(n, t, o = {}) {
    let s = o.scope ? `?scope=${l(o.scope)}` : "";
    return this.post(`/agents/${l(n)}${s}`, "POST /workspaces/:workspace/agents/:agentType", t, o.clientId);
  }
  async deleteWorkspaceAgent(n, t = {}) {
    let o = t.scope ? `?scope=${l(t.scope)}` : "";
    return await this.client.workspaceNoContentRequest(this.workspaceSelector, `/agents/${l(n)}${o}`, "DELETE /workspaces/:workspace/agents/:agentType", { method: "DELETE", clientId: t.clientId, okNotFoundCode: "agent_not_found" });
  }
  async listWorkspaceSessionsPage(n) {
    (n?.sourceType !== void 0 || n?.sourceId !== void 0) && await this.client.requireCapability("session_source_metadata");
    let t = n?.pageSize ?? an, o = Math.max(1, Math.min(1e3, Math.round(Number.isFinite(t) ? t : an))), s = new URLSearchParams({ size: String(o) });
    return n?.cursor !== void 0 && s.set("cursor", n.cursor), n?.archiveState !== void 0 && s.set("archiveState", n.archiveState), n?.view !== void 0 && s.set("view", n.view), n?.group !== void 0 && s.set("group", n.group), n?.parentSessionId !== void 0 && s.set("parentSessionId", n.parentSessionId), n?.sourceType !== void 0 && s.set("sourceType", n.sourceType), n?.sourceId !== void 0 && s.set("sourceId", n.sourceId), await this.get(`/sessions?${s.toString()}`, "GET /workspaces/:workspace/sessions");
  }
  async listWorkspaceSessions(n) {
    return (await this.listWorkspaceSessionsPage(n)).sessions;
  }
  getWorkspaceSessionInfo() {
    return this.get("/session-info", "GET /workspaces/:workspace/session-info");
  }
  getSessionLiveState(n = {}) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/sessions/live-state", "GET /workspaces/:workspace/sessions/live-state", { clientId: n.clientId, timeoutMs: n.timeoutMs, mode: "rest" });
  }
  getSessionTranscriptPage(n, t = {}) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/session/${l(n)}/transcript${Gt(t)}`, "GET /workspaces/:workspace/session/:id/transcript", { clientId: t.clientId, mode: "rest" });
  }
  getSessionTurnIndexPage(n, t = {}) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/session/${l(n)}/turn-index${jt(t)}`, "GET /workspaces/:workspace/session/:id/turn-index", { clientId: t.clientId, mode: "rest" });
  }
  exportSession(n, t = {}) {
    return this.client.sessionExportRequest(`/workspaces/${this.workspaceSelector}/session/${l(n)}/export`, "GET /workspaces/:workspace/session/:id/export", t);
  }
  exportArchivedSession(n, t = {}) {
    return this.client.sessionExportRequest(`/workspaces/${this.workspaceSelector}/session/${l(n)}/archive/export`, "GET /workspaces/:workspace/session/:id/archive/export", t);
  }
  updateSessionMetadata(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/session/${l(n)}/metadata`, "PATCH /workspaces/:workspace/session/:id/metadata", { method: "PATCH", body: t, clientId: o, mode: "rest" });
  }
  listSessionGroups() {
    return this.get("/session-groups", "GET /workspaces/:workspace/session-groups");
  }
  async createSessionGroup(n) {
    return (await this.post("/session-groups", "POST /workspaces/:workspace/session-groups", n)).group;
  }
  async updateSessionGroup(n, t) {
    return (await this.client.workspaceJsonRequest(this.workspaceSelector, `/session-groups/${l(n)}`, "PATCH /workspaces/:workspace/session-groups/:groupId", { method: "PATCH", body: t })).group;
  }
  deleteSessionGroup(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/session-groups/${l(n)}`, "DELETE /workspaces/:workspace/session-groups/:groupId", { method: "DELETE" });
  }
  updateSessionOrganization(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/session/${l(n)}/organization`, "PATCH /workspaces/:workspace/session/:id/organization", { method: "PATCH", body: t, clientId: o });
  }
  deleteSessionsData(n, t) {
    return this.post("/sessions/delete", "POST /workspaces/:workspace/sessions/delete", { sessionIds: n }, t);
  }
  archiveSessionsData(n, t, o) {
    let s = typeof t == "object" ? t : void 0;
    return this.post("/sessions/archive", "POST /workspaces/:workspace/sessions/archive", { sessionIds: n, ...s?.resolveConflicts !== void 0 ? { resolveConflicts: s.resolveConflicts } : {} }, typeof t == "string" ? t : o);
  }
  unarchiveSessionsData(n, t, o) {
    let s = typeof t == "object" ? t : void 0;
    return this.post("/sessions/unarchive", "POST /workspaces/:workspace/sessions/unarchive", { sessionIds: n, ...s?.resolveConflicts !== void 0 ? { resolveConflicts: s.resolveConflicts } : {} }, typeof t == "string" ? t : o);
  }
  readWorkspaceFile(n, t = {}, o) {
    let s = new URLSearchParams({ path: n });
    return t.maxBytes !== void 0 && s.set("maxBytes", String(t.maxBytes)), t.line !== void 0 && s.set("line", String(t.line)), t.limit !== void 0 && s.set("limit", String(t.limit)), t.cursor !== void 0 && s.set("cursor", t.cursor), this.get(`/file?${s.toString()}`, "GET /workspaces/:workspace/file", o);
  }
  readWorkspaceFileBytes(n, t = {}, o) {
    let s = new URLSearchParams({ path: n });
    return t.offset !== void 0 && s.set("offset", String(t.offset)), t.maxBytes !== void 0 && s.set("maxBytes", String(t.maxBytes)), this.get(`/file/bytes?${s.toString()}`, "GET /workspaces/:workspace/file/bytes", o);
  }
  fileStat(n) {
    let t = new URLSearchParams({ path: n });
    return this.get(`/stat?${t.toString()}`, "GET /workspaces/:workspace/stat");
  }
  dirList(n) {
    let t = new URLSearchParams({ path: n });
    return this.get(`/list?${t.toString()}`, "GET /workspaces/:workspace/list");
  }
  glob(n, t = {}) {
    let o = new URLSearchParams({ pattern: n });
    return t.maxResults !== void 0 && o.set("maxResults", String(t.maxResults)), this.client.workspaceJsonRequest(this.workspaceSelector, `/glob?${o.toString()}`, "GET /workspaces/:workspace/glob", { signal: t.signal });
  }
  writeWorkspaceFile(n, t) {
    return this.post("/file/write", "POST /workspaces/:workspace/file/write", n, t);
  }
  editWorkspaceFile(n, t) {
    return this.post("/file/edit", "POST /workspaces/:workspace/file/edit", n, t);
  }
  uploadWorkspaceFile(n, t) {
    return this.client.uploadFileToPath(`/workspaces/${this.workspaceSelector}/file/upload`, "POST /workspaces/:workspace/file/upload", n, t);
  }
  workspaceSettings(n) {
    return this.get("/settings", "GET /workspaces/:workspace/settings", n?.clientId);
  }
  setWorkspaceSetting(n, t, o, s) {
    return this.post("/settings", "POST /workspaces/:workspace/settings", { scope: n, key: t, value: o, ...s?.mcpServerMutation ? { mcpServerMutation: s.mcpServerMutation } : {} }, s?.clientId);
  }
  workspaceTrust(n) {
    return this.get(n?.statusVersion === 2 ? "/trust?statusVersion=2" : "/trust", "GET /workspaces/:workspace/trust", n?.clientId);
  }
  requestWorkspaceTrustChange(n, t) {
    return this.post("/trust/request", "POST /workspaces/:workspace/trust/request", n, t);
  }
  workspacePermissions(n) {
    return this.get("/permissions", "GET /workspaces/:workspace/permissions", n?.clientId);
  }
  setWorkspacePermissionRules(n, t, o) {
    return this.post("/permissions", "POST /workspaces/:workspace/permissions", { scope: "workspace", ruleType: n, rules: [...t] }, o?.clientId);
  }
  setWorkspaceToolEnabled(n, t, o) {
    return this.post(`/tools/${l(n)}/enable`, "POST /workspaces/:workspace/tools/:name/enable", { enabled: t }, o?.clientId);
  }
  setWorkspaceSkillEnabled(n, t, o) {
    return this.post(`/skills/${l(n)}/enable`, "POST /workspaces/:workspace/skills/:name/enable", { enabled: t }, o?.clientId);
  }
  setWorkspaceSkillsEnabled(n, t, o) {
    return this.post("/skills/enable", "POST /workspaces/:workspace/skills/enable", { skillNames: n, enabled: t }, o?.clientId);
  }
  restartMcpServer(n, t) {
    let o = t?.entryIndex === void 0 ? "" : `?entryIndex=${l(String(t.entryIndex))}`;
    return this.post(`/mcp/${l(n)}/restart${o}`, "POST /workspaces/:workspace/mcp/:server/restart", {}, t?.clientId, t?.timeoutMs ?? J);
  }
  reload(n) {
    return this.post("/reload", "POST /workspaces/:workspace/reload", {}, n?.clientId, n?.timeoutMs);
  }
  initWorkspace(n) {
    return this.post("/init", "POST /workspaces/:workspace/init", n?.force === true ? { force: true } : {}, n?.clientId);
  }
  workspaceExtensions() {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/extensions", "GET /workspaces/:workspace/extensions", { mode: "rest" });
  }
  extensionState(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/extensions/${l(n)}/state`, "GET /workspaces/:workspace/extensions/:extensionId/state", { mode: "rest" });
  }
  setExtensionState(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/extensions/${l(n)}/state`, "PUT /workspaces/:workspace/extensions/:extensionId/state", { method: "PUT", body: t, clientId: o, mode: "rest" });
  }
  setExtensionActivation(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/extensions/${l(n)}/activation`, "PUT /workspaces/:workspace/extensions/:extensionId/activation", { method: "PUT", body: { state: t }, clientId: o, mode: "rest" });
  }
  setExtensionActivations(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/extensions/activation", "PUT /workspaces/:workspace/extensions/activation", { method: "PUT", body: { extensionNames: [...n], state: t }, clientId: o, mode: "rest" });
  }
  clearExtensionActivation(n, t) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, `/extensions/${l(n)}/activation`, "DELETE /workspaces/:workspace/extensions/:extensionId/activation", { method: "DELETE", clientId: t, mode: "rest" });
  }
  refreshExtensionRuntime(n) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, "/extensions/refresh", "POST /workspaces/:workspace/extensions/refresh", { method: "POST", body: {}, clientId: n, mode: "rest" });
  }
  get(n, t, o) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, n, t, { clientId: o });
  }
  post(n, t, o, s, r) {
    return this.client.workspaceJsonRequest(this.workspaceSelector, n, t, { method: "POST", body: o, clientId: s, timeoutMs: r });
  }
};
function Gn(e) {
  let n = AbortSignal.any;
  if (typeof n == "function") return n.call(AbortSignal, e);
  let t = new AbortController(), o = [], s = () => {
    for (; o.length > 0; ) {
      let r = o.pop();
      try {
        r?.();
      } catch {
      }
    }
  };
  for (let r of e) {
    if (r.aborted) return t.abort(r.reason), s(), t.signal;
    let a = () => {
      t.abort(r.reason), s();
    };
    r.addEventListener("abort", a, { once: true }), o.push(() => r.removeEventListener("abort", a));
  }
  return t.signal.addEventListener("abort", s, { once: true }), t.signal;
}
function cn(e, n) {
  if (e.type === "turn_complete") {
    let t = e.data;
    if (t.promptId === n) {
      let o = t.stopReason ?? "end_turn", s = t.branchPoint, r = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i, a = o === "end_turn" && typeof s?.assistantRecordUuid == "string" && r.test(s.assistantRecordUuid) && typeof s.checkpointUuid == "string" && r.test(s.checkpointUuid) ? { assistantRecordUuid: s.assistantRecordUuid, checkpointUuid: s.checkpointUuid } : void 0;
      return { stopReason: o, ...a ? { branchPoint: a } : {} };
    }
  }
  if (e.type === "turn_error") {
    let t = e.data;
    if (t.promptId === n) throw Object.assign(new x(500, t.code ?? "turn_error", t.message ?? "Prompt failed"), { _daemonTurnError: true });
  }
}
var Ls = 32 * 1024 * 1024;
var Oe = "mid_turn_message_injected";
var Be = "pending_prompt_added";
var Ue = "pending_prompt_started";
var We = "pending_prompt_completed";
var Vt = ["session_update", "permission_request", "permission_resolved", "permission_already_resolved", "model_switched", "model_switch_failed", "session_died", "session_closed", "session_metadata_updated", "session_recording_degraded", "artifact_changed", "source_changed", Oe, Be, Ue, We, "client_evicted", "slow_client_warning", "stream_error", "state_resync_required", "history_truncated", "mcp_budget_warning", "mcp_child_refused_batch", "memory_changed", "agent_changed", "auth_device_flow_started", "auth_device_flow_throttled", "auth_device_flow_authorized", "auth_device_flow_failed", "auth_device_flow_cancelled", "approval_mode_changed", "tool_toggled", "settings_changed", "trust_change_requested", "workspace_initialized", "github_setup_completed", "mcp_server_restarted", "mcp_server_restart_refused", "mcp_server_changed", "settings_reloaded", "mcp_server_added", "mcp_server_removed", "extensions_changed", "permission_partial_vote", "permission_forbidden", "prompt_cancelled", "replay_complete", "followup_suggestion", "channel_delivery_result", "user_shell_command", "user_shell_result", "turn_complete", "turn_error", "session_rewound", "session_branched", "session_snapshot", "git_branch_changed", "git_status_changed"];
var zs = new Set(Vt);
var da = "\0";
var ca = "\b";
var la = "\v";
var ua = "\f";
var ma = "\r";
var pa = "";
var ga = "";
var ha = "\x7F";
var fa = "\x9F";
var se = "\x1B";
var to = "\x07";
var Da = new RegExp(`[${da}-${ca}${la}${ua}${ma}${pa}-${ga}${ha}-${fa}]`, "g");
var so = new RegExp(`${se}\\][^${to}${se}]*(?:${to}|${se}\\\\)`, "g");
var Sa = new RegExp(`${se}P[^${se}]*${se}\\\\`, "g");
var ka = new RegExp(`${se}\\[[0-?]*[ -/]*[@-~]`, "g");
var qa = new Set(Ce);
var Ui = 128 * 1024 * 1024;
var md = Object.freeze([]);

// src/adaptor/managed-qwen-serve.ts
import { spawn, execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
var ManagedQwenServe = class {
  constructor(options) {
    this.options = options;
  }
  child;
  pending;
  stopping;
  closed = false;
  start() {
    if (this.closed)
      return Promise.reject(new Error("Managed Qwen Serve is closed."));
    if (this.child && (this.child.exitCode !== null || this.child.signalCode !== null)) {
      return Promise.reject(
        new Error(
          "Managed Qwen Serve has exited. Restart Live to launch it again."
        )
      );
    }
    return this.pending ??= this.launch().catch(async (error) => {
      await this.close();
      throw error;
    });
  }
  launch() {
    const token = randomBytes(32).toString("hex");
    const child = spawn(
      this.options.command,
      [
        "serve",
        "--hostname",
        "127.0.0.1",
        "--port",
        "0",
        ...this.options.cwd ? ["--workspace", this.options.cwd] : []
      ],
      {
        cwd: this.options.cwd,
        detached: process.platform !== "win32",
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          QWEN_SERVER_TOKEN: token,
          QWEN_CODE_NO_RELAUNCH: "true"
        }
      }
    );
    this.child = child;
    child.once("exit", () => {
      void this.close().catch(() => void 0);
    });
    child.stderr?.resume();
    return new Promise((resolve3, reject) => {
      let settled = false;
      let buffer = "";
      const finish = (error, baseUrl) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error);
        else resolve3({ baseUrl, token });
      };
      const timer = setTimeout(
        () => finish(
          new Error(
            "Managed Qwen Serve startup timed out. Check that the configured Qwen Code supports `qwen serve`."
          )
        ),
        this.options.startupTimeoutMs ?? 3e4
      );
      child.on(
        "error",
        () => finish(
          new Error(
            "Unable to start managed Qwen Serve. Check the configured executable and workspace."
          )
        )
      );
      child.on(
        "exit",
        (code, signal) => finish(
          new Error(
            `Managed Qwen Serve exited before becoming ready (${signal ?? code ?? "unknown"}). Check the installed Qwen Code version and configuration.`
          )
        )
      );
      child.stdout?.setEncoding("utf8");
      child.stdout?.on("data", (chunk) => {
        if (settled) return;
        buffer += chunk;
        let newline;
        while ((newline = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, newline);
          buffer = buffer.slice(newline + 1);
          const match = /^qwen serve listening on (http:\/\/127\.0\.0\.1:(\d+)) \(/.exec(
            line
          );
          if (match && Number(match[2]) > 0 && Number(match[2]) <= 65535) {
            finish(void 0, match[1]);
          }
        }
        if (buffer.length > 8192) buffer = "";
      });
    });
  }
  close() {
    this.closed = true;
    return this.stopping ??= this.stopChild().catch((error) => {
      this.stopping = void 0;
      throw error;
    });
  }
  async stopChild() {
    const child = this.child;
    if (!child?.pid) return;
    if (process.platform === "win32") {
      if (child.exitCode === null && child.signalCode === null) {
        await new Promise(
          (resolve3) => execFile(
            "taskkill",
            ["/pid", String(child.pid), "/T", "/F"],
            () => resolve3()
          )
        );
      }
      return;
    }
    const signalGroup = async (signal) => {
      try {
        process.kill(-child.pid, signal);
        return true;
      } catch (error) {
        const code = error.code;
        if (code === "ESRCH") return false;
        if (code === "EPERM" && !await processGroupExists(child.pid))
          return false;
        throw error;
      }
    };
    if (!await signalGroup("SIGTERM")) return;
    const deadline = Date.now() + 3e3;
    while (Date.now() < deadline) {
      if (!await signalGroup(0)) return;
      await new Promise((resolve3) => setTimeout(resolve3, 50));
    }
    await signalGroup("SIGKILL");
    if (child.exitCode === null && child.signalCode === null) {
      await new Promise((resolve3) => {
        const timer = setTimeout(resolve3, 500);
        child.once("exit", () => {
          clearTimeout(timer);
          resolve3();
        });
      });
    }
  }
};
async function processGroupExists(group) {
  const output = await new Promise((resolve3, reject) => {
    execFile(
      "/bin/ps",
      ["-A", "-o", "pgid="],
      {
        timeout: 2e3,
        maxBuffer: 1024 * 1024,
        encoding: "utf8"
      },
      (error, stdout) => {
        if (error)
          reject(
            new Error(
              "Could not verify managed Qwen Serve process cleanup. Retry Quit."
            )
          );
        else resolve3(stdout);
      }
    );
  });
  const groups = output.trim().split(/\s+/u);
  if (!groups.length || groups.some((value) => !/^\d+$/u.test(value)))
    throw new Error(
      "Could not verify managed Qwen Serve process cleanup. Retry Quit."
    );
  return groups.some((value) => Number(value) === group);
}

// src/adaptor/adaptor-utils.ts
import { realpathSync, statSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
var MAX_DETAIL_CHARS = 48e3;
var MAX_PERMISSION_INPUT_CHARS = 16384;
var SENSITIVE_PERMISSION_KEY = /api[_-]?key|private[_-]?key|access[_-]?key|token|password|passwd|secret|authorization|cookie|credential/i;
function isRecord(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function classifyOption(optionId, name, wireKind) {
  switch (wireKind) {
    case "allow_once":
      return { kind: "proceed", escalation: "once" };
    case "allow_always":
      return { kind: "proceed", escalation: "always" };
    case "reject_once":
      return { kind: "reject", escalation: "once" };
    case "reject_always":
      return { kind: "reject", escalation: "always" };
    default:
      break;
  }
  if (wireKind !== void 0) return { kind: "other" };
  return { kind: "other" };
}
function describePersistentScope(name, wireKind) {
  if (wireKind !== "allow_always" || !name || name.length > 1024) return;
  const label = sanitizeTitleLine(redactPermissionText(name));
  if (label.includes("[REDACTED]")) return;
  if (/\b(?:in (?:this |the )?(?:project|workspace)|for (?:this |the )?(?:command|tool|user|session)|all (?:edits|commands|tools|files)|(?:project|workspace|user)[ -]wide)\b/i.test(
    label
  ) || /(?:本|此|当前)(?:项目|工作区|命令|工具|会话)|所有(?:编辑|命令|工具|文件)/u.test(
    label
  ))
    return label;
  return;
}
function describeToolCall(toolCall) {
  if (!isRecord(toolCall)) return "a tool call";
  const details = describePermissionDetails(toolCall);
  const name = stripControlSequences(details.toolName ?? "");
  const command = details.command ?? "";
  const title = typeof toolCall["title"] === "string" ? toolCall["title"] : "";
  const detail = stripControlSequences(
    redactPermissionText((command || title).slice(0, 8192))
  );
  if (name && detail) return `${name}: ${detail}`;
  return name || detail || "a tool call";
}
function redactPermissionText(text) {
  return text.replace(/\b(Bearer|Basic)\s+[^\s'";]+/gi, "$1 [REDACTED]").replace(
    /((?:--)?\b[\w-]{0,64}(?:api[_-]?key|private[_-]?key|access[_-]?key|token|password|passwd|secret|authorization|cookie|credential)[\w-]{0,64}["']?\s*(?:=|:|\s)\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s;]+)/gi,
    "$1[REDACTED]"
  ).replace(
    /\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b/g,
    "[REDACTED]"
  ).replace(
    /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
    "[REDACTED]"
  ).replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, "$1[REDACTED]@");
}
function describePermissionDetails(toolCall, sessionCwd) {
  if (!isRecord(toolCall)) return {};
  let incomplete = false;
  let budget = MAX_PERMISSION_INPUT_CHARS;
  const string = (value, max = 8192) => {
    if (typeof value !== "string" || value.length === 0) return;
    if (value.length > max) {
      incomplete = true;
      return;
    }
    const redacted = redactPermissionText(value);
    if (redacted !== value) incomplete = true;
    return redacted;
  };
  const displayString = (value, max) => {
    const exact = string(value, max);
    if (exact === void 0) return;
    const display = sanitizeTitleLine(exact);
    if (display !== exact) incomplete = true;
    return display || void 0;
  };
  const followsSecretFlag = (value, index) => {
    const previous = value[index - 1];
    return typeof previous === "string" && /^--?[\w-]+$/.test(previous) && SENSITIVE_PERMISSION_KEY.test(previous);
  };
  const seen = /* @__PURE__ */ new Set();
  const snapshot = (value, depth = 0) => {
    if (budget <= 0 || depth > 6) {
      incomplete = true;
      return "[OMITTED]";
    }
    if (typeof value === "string") {
      budget -= value.length;
      if (budget < 0) {
        incomplete = true;
        return "[OMITTED]";
      }
      const redacted = redactPermissionText(value);
      if (redacted !== value) incomplete = true;
      return redacted;
    }
    if (value === null || typeof value === "boolean") return value;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value !== "object" || !value || seen.has(value)) {
      incomplete = true;
      return "[OMITTED]";
    }
    seen.add(value);
    const entries = Array.isArray(value) ? value.slice(0, 65).map((item, index) => [String(index), item]) : Object.entries(value);
    if (entries.length > 64) incomplete = true;
    const result = /* @__PURE__ */ Object.create(null);
    for (const [key, child] of entries.slice(0, 64)) {
      budget -= key.length + 4;
      if (budget <= 0) {
        incomplete = true;
        break;
      }
      if (SENSITIVE_PERMISSION_KEY.test(key) || Array.isArray(value) && followsSecretFlag(value, Number(key))) {
        result[key] = "[REDACTED]";
        incomplete = true;
      } else result[key] = snapshot(child, depth + 1);
    }
    seen.delete(value);
    return Array.isArray(value) ? Object.values(result) : result;
  };
  const raw = toolCall["rawInput"] ?? toolCall["input"] ?? toolCall["arguments"];
  let input = raw;
  if (typeof raw === "string" && raw.length <= MAX_PERMISSION_INPUT_CHARS) {
    try {
      input = JSON.parse(raw);
    } catch {
    }
  }
  const record = isRecord(input) ? input : {};
  const toolCallId = string(toolCall["toolCallId"] ?? toolCall["id"], 256);
  const toolName = displayString(toolCall["name"] ?? toolCall["toolName"], 256);
  const rawCommand = toolCall["command"] ?? record["command"] ?? record["cmd"];
  let command;
  if (Array.isArray(rawCommand)) {
    if (rawCommand.length <= 64 && rawCommand.every(
      (part) => typeof part === "string" && part.length <= 8192
    )) {
      const argv = rawCommand.map((part, index) => {
        if (followsSecretFlag(rawCommand, index)) {
          incomplete = true;
          return "[REDACTED]";
        }
        return part === "" ? "" : string(part);
      });
      command = string(JSON.stringify(argv));
    } else incomplete = true;
  } else command = string(rawCommand);
  const operation = displayString(
    toolCall["operation"] ?? record["operation"] ?? toolCall["kind"],
    256
  );
  const reportedCwd = string(
    toolCall["cwd"] ?? record["cwd"] ?? record["workdir"] ?? record["working_directory"],
    4096
  );
  let cwd = reportedCwd ?? string(sessionCwd, 4096);
  let cwdVerified = false;
  try {
    if (sessionCwd && isAbsolute(sessionCwd)) {
      const trusted = realpathSync(sessionCwd);
      const candidate = reportedCwd ? realpathSync(resolve(trusted, reportedCwd)) : trusted;
      if (statSync(trusted).isDirectory() && candidate === trusted) {
        cwd = trusted;
        cwdVerified = true;
      }
    }
  } catch {
  }
  const resources = [];
  let resourceBudget = 8192;
  const addResource = (value) => {
    const path4 = string(value, 4096);
    if (path4 && !resources.includes(path4)) {
      resourceBudget -= path4.length;
      if (resources.length >= 24 || resourceBudget < 0) incomplete = true;
      else resources.push(path4);
    }
  };
  for (const key of [
    "path",
    "file_path",
    "filePath",
    "directory",
    "source",
    "destination"
  ])
    addResource(record[key]);
  const locations = toolCall["locations"];
  if (Array.isArray(locations)) {
    if (locations.length > 24) incomplete = true;
    for (const location of locations.slice(0, 24))
      if (isRecord(location)) addResource(location["path"]);
  }
  let rawInput = raw === void 0 ? void 0 : snapshot(input);
  if (rawInput !== void 0 && JSON.stringify(rawInput).length > MAX_PERMISSION_INPUT_CHARS) {
    rawInput = void 0;
    incomplete = true;
  }
  if (raw === void 0 && (command || operation || resources.length))
    incomplete = true;
  const metadataKeys = /* @__PURE__ */ new Set([
    "toolCallId",
    "id",
    "name",
    "toolName",
    "title",
    "kind",
    "status",
    "content",
    "locations",
    "rawInput",
    "rawOutput",
    "command",
    "operation",
    "cwd",
    "input",
    "arguments",
    "sessionUpdate"
  ]);
  if (Object.keys(toolCall).some((key) => !metadataKeys.has(key)))
    incomplete = true;
  if (toolCall["command"] !== void 0 && record["command"] !== void 0 && toolCall["command"] !== record["command"])
    incomplete = true;
  const details = {
    ...toolCallId ? { toolCallId } : {},
    ...toolName ? { toolName } : {},
    ...command ? { command } : {},
    ...rawInput !== void 0 ? { rawInput } : {},
    ...cwd ? { cwd, cwdVerified } : {},
    ...operation ? { operation } : {},
    ...resources.length ? { resources } : {},
    ...incomplete ? { incomplete: true } : {}
  };
  return JSON.stringify(details).length > MAX_DETAIL_CHARS ? { ...toolCallId ? { toolCallId } : {}, incomplete: true } : details;
}
function stripControlSequences(text) {
  return text.replace(/\x1b\][\s\S]*?(?:\x07|\x1b\\)/g, "").replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b[NOP]/g, "").replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/g, " ");
}
function sanitizeTitleLine(title) {
  const firstLine = title.split(/\r?\n/, 1)[0] ?? "";
  return firstLine.replace(/\x1b\][\s\S]*?(?:\x07|\x1b\\)/g, "").replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b[NOP]/g, "").replace(/[\x00-\x1f\x7f-\x9f]/g, " ").trim();
}

// src/adaptor/public-activity.ts
function publicActivity(update, jobRef, sessionCwd) {
  const kind = update["sessionUpdate"];
  let activity;
  let text = "";
  let details;
  let toolStatus;
  if (kind === "agent_message_chunk") {
    const content = update["content"];
    if (!isRecord(content) || typeof content["text"] !== "string") return;
    activity = "message";
    text = content["text"];
  } else if (kind === "plan") {
    if (!Array.isArray(update["entries"])) return;
    activity = "plan";
    text = update["entries"].slice(0, 24).flatMap((entry) => {
      if (!isRecord(entry) || typeof entry["content"] !== "string") return [];
      const status = ["pending", "in_progress", "completed"].includes(
        String(entry["status"])
      ) ? String(entry["status"]) : "pending";
      return [`[${status}] ${entry["content"].slice(0, 1024)}`];
    }).join("\n");
  } else if (kind === "tool_call" || kind === "tool_call_update") {
    activity = "tool";
    details = describePermissionDetails(update, sessionCwd);
    const parts = [];
    if (details.command || details.toolName)
      parts.push(describeToolCall(update));
    else if (typeof update["title"] === "string") parts.push(update["title"]);
    if (["pending", "in_progress", "completed", "failed"].includes(
      String(update["status"])
    )) {
      toolStatus = update["status"];
      parts.push(`[${String(update["status"])}]`);
    }
    if (Array.isArray(update["content"])) {
      for (const part of update["content"].slice(0, 24)) {
        if (!isRecord(part) || part["type"] !== "content") continue;
        const content = part["content"];
        if (isRecord(content) && content["type"] === "text" && typeof content["text"] === "string")
          parts.push(content["text"]);
      }
    }
    text = parts.join("\n");
  } else return;
  text = stripControlSequences(redactPermissionText(text.slice(0, 8192))).slice(
    0,
    8192
  );
  if (!text && !details?.toolCallId && !toolStatus) return;
  return {
    type: "activity",
    kind: activity,
    text,
    ...jobRef ? { jobRef } : {},
    ...details?.toolCallId ? { toolCallId: details.toolCallId } : {},
    ...toolStatus ? { toolStatus } : {},
    ...details && Object.keys(details).length ? { details } : {}
  };
}

// src/vendor/qwen-code-peer/endpoint.ts
import { randomBytes as randomBytes4, randomUUID as randomUUID2 } from "node:crypto";

// src/vendor/qwen-code-peer/client.ts
import * as net from "node:net";
import * as path from "node:path";

// src/vendor/qwen-code-peer/frames.ts
import { randomUUID } from "node:crypto";
var PEER_FRAME_VERSION = 1;
var MAX_FRAME_CHARS = 1024 * 1024;
var MAX_DROPPED_MSG_IDS = 256;
var PEER_DELIVERY_STATUSES = [
  "held",
  "denied",
  "refused",
  "expired",
  "delivered",
  "misaddressed",
  "dropped"
];
var MSG_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/;
function canonicalizeMsgId(msgId) {
  return msgId.replace(/-/g, "").toLowerCase();
}
function isPeerMsgId(value) {
  return typeof value === "string" && MSG_ID_RE.test(value) && canonicalizeMsgId(value) !== "all";
}
function isRecord2(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function optionalString(value) {
  return typeof value === "string" ? value : void 0;
}
function isDeliveryStatus(value) {
  return typeof value === "string" && PEER_DELIVERY_STATUSES.includes(value);
}
function optionalDropReason(value) {
  return value === "rate-limited" || value === "duplicate" || value === "queue-full" ? value : void 0;
}
function parsePeerFrame(line) {
  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }
  if (!isRecord2(parsed)) return null;
  const msgV = parsed["msgV"];
  if (typeof msgV !== "number" || msgV > PEER_FRAME_VERSION) return null;
  const msgId = parsed["msgId"];
  if (!isPeerMsgId(msgId)) return null;
  if (parsed["type"] === "user") {
    const message = parsed["message"];
    if (!isRecord2(message) || message["role"] !== "user") return null;
    const content = message["content"];
    if (typeof content !== "string" || content.length === 0) return null;
    const fromMode = parsed["fromMode"];
    const replyToken = optionalString(parsed["replyToken"]);
    const toSessionId = optionalString(parsed["toSessionId"]);
    return {
      msgV,
      msgId,
      type: "user",
      from: optionalString(parsed["from"]),
      ...replyToken !== void 0 ? { replyToken } : {},
      fromName: optionalString(parsed["fromName"]),
      ...fromMode === "bypass" || fromMode === "prompting" ? { fromMode } : {},
      ...toSessionId !== void 0 ? { toSessionId } : {},
      priority: parsed["priority"] === "now" ? "now" : "next",
      message: { role: "user", content }
    };
  }
  if (parsed["type"] === "control") {
    if (parsed["action"] !== "delivery_status") return null;
    const status = parsed["status"];
    if (!isDeliveryStatus(status)) return null;
    const origMsgId = parsed["origMsgId"];
    if (typeof origMsgId !== "string" || origMsgId.length === 0) return null;
    const dropReason = status === "dropped" ? optionalDropReason(parsed["dropReason"]) : void 0;
    const rawIds = status === "dropped" ? parsed["droppedMsgIds"] : void 0;
    const droppedMsgIds = Array.isArray(rawIds) ? rawIds.filter(isPeerMsgId).slice(0, MAX_DROPPED_MSG_IDS) : [];
    return {
      msgV,
      msgId,
      type: "control",
      action: "delivery_status",
      status,
      origMsgId,
      from: optionalString(parsed["from"]),
      reason: optionalString(parsed["reason"]),
      ...dropReason !== void 0 ? { dropReason } : {},
      ...droppedMsgIds.length > 0 ? { droppedMsgIds } : {}
    };
  }
  return null;
}
function encodePeerFrame(frame) {
  return `${JSON.stringify(frame)}
`;
}
function buildAuthLine(token) {
  return `${JSON.stringify({ msgV: PEER_FRAME_VERSION, type: "auth", token })}
`;
}
function parsePeerAuthLine(line) {
  let parsed;
  try {
    parsed = JSON.parse(line);
  } catch {
    return null;
  }
  if (!isRecord2(parsed)) return null;
  const msgV = parsed["msgV"];
  if (typeof msgV !== "number" || msgV > PEER_FRAME_VERSION) return null;
  if (parsed["type"] !== "auth") return null;
  const token = parsed["token"];
  return typeof token === "string" && token.length > 0 ? token : null;
}
function buildUserFrame(fields) {
  return {
    msgV: PEER_FRAME_VERSION,
    msgId: randomUUID(),
    type: "user",
    ...fields.from !== void 0 ? { from: fields.from } : {},
    ...fields.replyToken !== void 0 ? { replyToken: fields.replyToken } : {},
    ...fields.fromName !== void 0 ? { fromName: fields.fromName } : {},
    ...fields.fromMode !== void 0 ? { fromMode: fields.fromMode } : {},
    ...fields.toSessionId !== void 0 ? { toSessionId: fields.toSessionId } : {},
    priority: fields.priority ?? "next",
    message: { role: "user", content: fields.content }
  };
}
function buildDeliveryStatusFrame(fields) {
  return {
    msgV: PEER_FRAME_VERSION,
    msgId: randomUUID(),
    type: "control",
    action: "delivery_status",
    status: fields.status,
    origMsgId: fields.origMsgId,
    ...fields.from !== void 0 ? { from: fields.from } : {},
    reason: fields.reason ?? describeDeliveryStatus(fields.status),
    ...fields.status === "dropped" && fields.dropReason !== void 0 ? { dropReason: fields.dropReason } : {},
    // Left off rather than sent empty: the field means "these ids too".
    ...fields.status === "dropped" && fields.droppedMsgIds !== void 0 && fields.droppedMsgIds.length > 0 ? { droppedMsgIds: fields.droppedMsgIds.slice(0, MAX_DROPPED_MSG_IDS) } : {}
  };
}
function describeDeliveryStatus(status) {
  switch (status) {
    case "held":
      return "Your message is waiting for the recipient to review it.";
    case "denied":
      return "The recipient reviewed your message and declined it.";
    case "refused":
      return "The recipient does not take messages like this one, so nobody saw it. Do not re-send it.";
    case "expired":
      return "Your message was not delivered: it waited too long, or the recipient closed first.";
    case "delivered":
      return "Your message was delivered.";
    case "misaddressed":
      return "That address belongs to a different session than the one you named. Look the recipient up again before re-sending.";
    case "dropped":
      return "Your message was turned away before anyone saw it. Treat it as unsent.";
    default: {
      const exhaustive = status;
      return exhaustive;
    }
  }
}

// src/vendor/qwen-code-peer/client.ts
var SEND_TIMEOUT_MS = 5e3;
var PROBE_TIMEOUT_MS = 250;
var MAX_CONCURRENT_SENDS = 64;
var inFlightSends = 0;
var PeerSendError = class extends Error {
  constructor(message, code, options = {}) {
    super(message);
    this.code = code;
    this.name = "PeerSendError";
    this.local = options.local ?? false;
  }
  /**
   * True when the failure is this process's own limit rather than anything
   * at the other end: nothing was dialed and nothing was written.
   */
  local;
};
function isLocalIpcPath(candidate) {
  if (typeof candidate !== "string" || candidate.length === 0) return false;
  if (candidate.includes("\0")) return false;
  if (process.platform === "win32") {
    const normalized = candidate.replace(/\//g, "\\").toLowerCase();
    return normalized.startsWith("\\\\.\\pipe\\") || normalized.startsWith("\\\\?\\pipe\\");
  }
  if (candidate.startsWith("//")) return false;
  return path.isAbsolute(candidate);
}
function sendPeerFrame(socketPath, frame, options = {}) {
  const timeoutMs = options.timeoutMs ?? SEND_TIMEOUT_MS;
  return new Promise((resolve3, reject) => {
    if (!isLocalIpcPath(socketPath)) {
      reject(
        new PeerSendError(
          `Refusing to dial a path that is not local: ${socketPath}`,
          void 0
        )
      );
      return;
    }
    const encoded = encodePeerFrame(frame);
    if (encoded.length - 1 > MAX_FRAME_CHARS) {
      reject(
        new PeerSendError(
          `The frame is ${encoded.length - 1} characters, over the ${MAX_FRAME_CHARS} a peer accepts`,
          "EMSGSIZE"
        )
      );
      return;
    }
    if (inFlightSends >= MAX_CONCURRENT_SENDS) {
      reject(
        new PeerSendError(
          `Already sending ${inFlightSends} frames; not opening another connection`,
          "EBUSY",
          { local: true }
        )
      );
      return;
    }
    const socket = net.connect({ path: socketPath });
    inFlightSends += 1;
    let settled = false;
    const settle = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      inFlightSends -= 1;
      if (error) {
        socket.destroy();
        reject(new PeerSendError(error.message, error.code));
      } else {
        resolve3();
      }
    };
    const deadline = setTimeout(() => {
      settle(
        Object.assign(new Error(`Timed out sending to ${socketPath}`), {
          code: "ETIMEDOUT"
        })
      );
    }, timeoutMs);
    socket.on("error", (error) => settle(error));
    socket.on("connect", () => {
      socket.end(
        options.authToken !== void 0 ? buildAuthLine(options.authToken) + encoded : encoded
      );
    });
    socket.on("close", () => settle());
  });
}
function probePeerSocketVerdict(socketPath) {
  return new Promise((resolve3) => {
    if (!isLocalIpcPath(socketPath)) {
      resolve3("unknown");
      return;
    }
    const socket = net.connect({ path: socketPath });
    let settled = false;
    const settle = (verdict) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      socket.destroy();
      resolve3(verdict);
    };
    const deadline = setTimeout(() => settle("unknown"), PROBE_TIMEOUT_MS);
    deadline.unref();
    socket.on("connect", () => settle("alive"));
    socket.on("error", (error) => {
      if (error.code === "EAGAIN" || error.code === "EBUSY") {
        settle("alive");
      } else if (error.code === "ENOENT" || error.code === "ECONNREFUSED") {
        settle("dead");
      } else {
        settle("unknown");
      }
    });
  });
}

// src/vendor/qwen-code-peer/label.ts
import { createHash } from "node:crypto";
var INVISIBLE_RUN = /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]+/gu;
var ELLIPSIS = "\u2026";
var MAX_LABEL_CHARS = 200;
var MAX_SESSION_NAME_CHARS = 40;
function flattenPeerLabel(value) {
  const oneLine = value.replace(INVISIBLE_RUN, " ").trim();
  const points = Array.from(oneLine);
  return points.length > MAX_LABEL_CHARS ? `${points.slice(0, MAX_LABEL_CHARS - 1).join("")}${ELLIPSIS}` : oneLine;
}
function boundSessionName(name) {
  const points = Array.from(flattenPeerLabel(name));
  return points.length > MAX_SESSION_NAME_CHARS ? `${points.slice(0, MAX_SESSION_NAME_CHARS - 1).join("")}${ELLIPSIS}` : points.join("");
}
function peerRef(sessionId) {
  return createHash("sha256").update(sessionId).digest("hex").slice(0, 6);
}

// src/vendor/qwen-code-peer/directory.ts
function toDirectoryEntry(record) {
  if (!record.ipcPath) return null;
  const name = flattenPeerLabel(record.name);
  if (name.length === 0) return null;
  return {
    sessionId: record.sessionId,
    name,
    ref: peerRef(record.sessionId),
    cwd: flattenPeerLabel(record.cwd),
    pid: record.pid,
    kind: record.kind ?? "tui",
    ipcPath: record.ipcPath,
    ...record.ipcToken !== void 0 ? { ipcToken: record.ipcToken } : {},
    startedAt: record.startedAt
  };
}
async function reachableEntries(records, probe = probePeerSocketVerdict, options = {}) {
  const candidates = records.map(toDirectoryEntry).filter((entry) => entry !== null);
  const verdicts = new Map(
    await Promise.all(
      [...new Set(candidates.map((entry) => entry.ipcPath))].map(
        async (ipcPath) => [ipcPath, await probe(ipcPath)]
      )
    )
  );
  const reachable = candidates.filter(
    (entry) => verdicts.get(entry.ipcPath) === "alive"
  );
  if (options.collapseTwins === false) return reachable;
  const newest = /* @__PURE__ */ new Map();
  for (const entry of reachable) {
    const key = `${entry.sessionId}\0${entry.name}`;
    const seen = newest.get(key);
    if (!seen || entry.startedAt > seen.startedAt) newest.set(key, entry);
  }
  return [...newest.values()];
}
function resolvePeerTarget(peers, target) {
  const trimmed = target.trim();
  if (trimmed.length === 0) return { kind: "none" };
  const decide = (matches) => {
    const unique = [...new Set(matches)];
    if (unique.length === 1) return { kind: "one", peer: unique[0] };
    if (unique.length > 1) return { kind: "ambiguous", matches: unique };
    return { kind: "none" };
  };
  const withRef = /^(.*?)\s*\[([0-9a-f]{4,12})\]$/i.exec(trimmed);
  if (withRef) {
    const namePart = withRef[1];
    const ref = withRef[2].toLowerCase();
    return decide([
      ...peers.filter((peer) => peer.name === trimmed),
      ...peers.filter(
        (peer) => peer.ref === ref && (namePart.length === 0 || peer.name === namePart)
      )
    ]);
  }
  return decide([
    ...peers.filter((peer) => peer.name === trimmed),
    ...peers.filter((peer) => peer.ref === trimmed.toLowerCase())
  ]);
}
function advertisablePeerAddress(peer, peers) {
  return [peer.name, `${peer.name} [${peer.ref}]`, `[${peer.ref}]`].find(
    (candidate) => {
      const resolved = resolvePeerTarget(peers, candidate);
      return resolved.kind === "one" && resolved.peer === peer;
    }
  );
}
function suggestPeerNames(peers, target, limit = 3) {
  const needle = target.trim().replace(/\s*\[[0-9a-f]{0,12}\]?$/i, "").trim().toLowerCase();
  if (needle.length === 0) return [];
  return peers.filter((peer) => peer.name.toLowerCase().includes(needle)).sort(
    (a, b) => Number(!a.name.toLowerCase().startsWith(needle)) - Number(!b.name.toLowerCase().startsWith(needle))
  ).slice(0, limit).map(
    (peer) => peers.filter((other) => other.name === peer.name).length > 1 ? `${peer.name} [${peer.ref}]` : peer.name
  );
}

// src/vendor/qwen-code-peer/errors.ts
var PeerEndpointError = class extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
    this.name = "PeerEndpointError";
  }
};
function describeError(error) {
  return error instanceof Error ? error.message : String(error);
}

// src/vendor/qwen-code-peer/identity.ts
import * as fs2 from "node:fs";
function isPidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return !isZombie(pid);
  } catch (error) {
    const code = error.code;
    return (code === "EPERM" || code === "EACCES") && !isZombie(pid);
  }
}
function statFieldsAfterComm(pid) {
  let raw;
  try {
    raw = fs2.readFileSync(`/proc/${pid}/stat`, "utf8");
  } catch {
    return null;
  }
  const commEnd = raw.lastIndexOf(")");
  if (commEnd === -1) return null;
  return raw.slice(commEnd + 1).trim().split(/\s+/);
}
function isZombie(pid) {
  if (process.platform !== "linux") return false;
  return statFieldsAfterComm(pid)?.[0] === "Z";
}
var cachedBootId;
function readLocalBootId() {
  if (cachedBootId !== void 0) return cachedBootId;
  if (process.platform !== "linux") return null;
  try {
    const value = fs2.readFileSync("/proc/sys/kernel/random/boot_id", "utf8").trim();
    if (/^[0-9a-f-]+$/i.test(value)) {
      cachedBootId = value;
      return value;
    }
  } catch {
  }
  return null;
}
function readProcStartToken(pid) {
  if (process.platform !== "linux") return null;
  if (!Number.isInteger(pid) || pid <= 0) return null;
  const bootId = readLocalBootId();
  if (bootId === null) return null;
  const startTime = statFieldsAfterComm(pid)?.[19];
  return startTime !== void 0 && /^\d+$/.test(startTime) ? `${bootId}:${startTime}` : null;
}
function readPidNamespaceId() {
  if (process.platform !== "linux") return null;
  try {
    return fs2.statSync("/proc/self/ns/pid").ino;
  } catch {
    return null;
  }
}
function bootIdOf(procStart) {
  const separator = procStart.indexOf(":");
  return separator === -1 ? null : procStart.slice(0, separator);
}
function isSameProcess(pid, procStart) {
  if (!isPidAlive(pid)) return false;
  if (procStart == null) return true;
  const current = readProcStartToken(pid);
  if (current === null) return true;
  return current === procStart;
}

// src/vendor/qwen-code-peer/inbox.ts
import { randomBytes as randomBytes2, timingSafeEqual } from "node:crypto";
import * as fsSync from "node:fs";
import * as fs3 from "node:fs/promises";
import * as net2 from "node:net";
import * as os from "node:os";
import * as path2 from "node:path";
var MAX_SOCKET_PATH_BYTES = 103;
var SOCKET_DIR_NAME = "qwen-socks";
var MAX_PEER_CONNECTIONS = 64;
var LINE_DEADLINE_MS = 3e4;
var SOCKET_DIR_MODE = 448;
var SOCKET_MODE = 384;
var NONCE_DIRNAME = new RegExp(`^${SOCKET_DIR_NAME}-[0-9a-f]{16}$`);
function resolveInboxCandidates(pid = process.pid) {
  if (process.platform === "win32") return [];
  const candidates = [];
  const runtimeDir = process.env["XDG_RUNTIME_DIR"];
  if (runtimeDir) {
    candidates.push(path2.join(runtimeDir, SOCKET_DIR_NAME, `${pid}.sock`));
  }
  const nonce = randomBytes2(8).toString("hex");
  candidates.push(
    path2.join(os.tmpdir(), `${SOCKET_DIR_NAME}-${nonce}`, `${pid}.sock`),
    path2.join("/tmp", `${SOCKET_DIR_NAME}-${nonce}`, `${pid}.sock`)
  );
  return candidates.filter(
    (candidate, index) => Buffer.byteLength(candidate) <= MAX_SOCKET_PATH_BYTES && candidates.indexOf(candidate) === index
  );
}
function siblingSocketPath(socketPath) {
  const base = path2.basename(socketPath, ".sock").split("-")[0];
  const sibling = path2.join(
    path2.dirname(socketPath),
    `${base}-${randomBytes2(4).toString("hex")}.sock`
  );
  return Buffer.byteLength(sibling) <= MAX_SOCKET_PATH_BYTES ? sibling : null;
}
function tokenMatches(expected, presented) {
  const a = Buffer.from(expected);
  const b = Buffer.from(presented);
  return a.length === b.length && timingSafeEqual(a, b);
}
function createLineReader(onLine, onOverflow) {
  let buffer = "";
  return (chunk) => {
    buffer += chunk;
    let newline = buffer.indexOf("\n");
    while (newline !== -1) {
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (line.trim().length > 0) onLine(line);
      newline = buffer.indexOf("\n");
    }
    if (buffer.length > MAX_FRAME_CHARS) {
      buffer = "";
      onOverflow();
    }
  };
}
function listen(server, target) {
  return new Promise((resolve3, reject) => {
    server.once("error", reject);
    server.listen(target, () => {
      server.removeListener("error", reject);
      resolve3();
    });
  });
}
async function bindAt(requested, options) {
  if (!isLocalIpcPath(requested)) {
    throw new Error(`not an absolute local path: ${requested}`);
  }
  if (Buffer.byteLength(requested) > MAX_SOCKET_PATH_BYTES) {
    throw new Error(`longer than ${MAX_SOCKET_PATH_BYTES} bytes: ${requested}`);
  }
  const dir = path2.dirname(requested);
  const ownsDir = NONCE_DIRNAME.test(path2.basename(dir));
  const dropDirIfOurs = () => ownsDir ? fs3.rmdir(dir).catch(() => {
  }) : Promise.resolve();
  const created = await fs3.mkdir(dir, {
    recursive: true,
    mode: SOCKET_DIR_MODE
  });
  try {
    const stats = await fs3.lstat(dir);
    if (!stats.isDirectory()) throw new Error(`${dir} is not a directory`);
    const uid = process.getuid?.();
    if (uid !== void 0 && stats.uid !== uid) {
      throw new Error(`${dir} belongs to uid ${stats.uid}, not ${uid}`);
    }
    if (created !== void 0 || ownsDir || path2.basename(dir) === SOCKET_DIR_NAME) {
      await fs3.chmod(dir, SOCKET_DIR_MODE);
    }
  } catch (error) {
    await dropDirIfOurs();
    throw error;
  }
  let target = requested;
  if (await probePeerSocketVerdict(target) !== "dead") {
    const sibling = siblingSocketPath(target);
    if (sibling === null) {
      await dropDirIfOurs();
      throw new Error(`${target} is in use and no sibling name fits`);
    }
    target = sibling;
  }
  await fs3.unlink(target).catch(() => {
  });
  const keepAlive = options.keepAlive ?? true;
  const lineDeadlineMs = options.lineDeadlineMs ?? LINE_DEADLINE_MS;
  const connections = /* @__PURE__ */ new Set();
  const server = net2.createServer({ allowHalfOpen: true }, (socket) => {
    connections.add(socket);
    socket.setEncoding("utf8");
    if (!keepAlive) socket.unref();
    let deadline;
    const arm = () => {
      clearTimeout(deadline);
      deadline = setTimeout(() => socket.destroy(), lineDeadlineMs);
      deadline.unref();
    };
    arm();
    let authed = false;
    let refused = false;
    const read = createLineReader(
      (line) => {
        if (refused) return;
        if (!authed) {
          const presented = parsePeerAuthLine(line);
          if (presented !== null && tokenMatches(options.requiredToken, presented)) {
            authed = true;
            arm();
            return;
          }
          refused = true;
          socket.destroy();
          return;
        }
        const frame = parsePeerFrame(line);
        if (frame === null) return;
        arm();
        try {
          options.onFrame(frame);
        } catch {
        }
      },
      () => {
        refused = true;
        socket.destroy();
      }
    );
    socket.on("data", read);
    socket.on("end", () => socket.end());
    socket.on("error", () => {
    });
    socket.on("close", () => {
      clearTimeout(deadline);
      connections.delete(socket);
    });
  });
  server.maxConnections = MAX_PEER_CONNECTIONS;
  try {
    await listen(server, target);
  } catch (error) {
    const sibling = error.code === "EADDRINUSE" ? siblingSocketPath(target) : null;
    if (sibling === null) {
      await dropDirIfOurs();
      throw error;
    }
    try {
      await listen(server, sibling);
      target = sibling;
    } catch (retryError) {
      await dropDirIfOurs();
      throw retryError;
    }
  }
  server.on("error", () => {
  });
  try {
    await fs3.chmod(target, SOCKET_MODE);
  } catch (error) {
    server.close();
    await fs3.unlink(target).catch(() => {
    });
    await dropDirIfOurs();
    throw error;
  }
  if (!keepAlive) server.unref();
  let closed = false;
  const destroyConnections = () => {
    for (const socket of connections) socket.destroy();
    connections.clear();
  };
  return {
    socketPath: target,
    async close() {
      if (closed) return;
      closed = true;
      destroyConnections();
      await new Promise((resolve3) => server.close(() => resolve3()));
      await fs3.unlink(target).catch(() => {
      });
      await dropDirIfOurs();
    },
    closeSync() {
      if (closed) return;
      closed = true;
      destroyConnections();
      server.close();
      try {
        fsSync.unlinkSync(target);
        if (ownsDir) fsSync.rmdirSync(dir);
      } catch {
      }
    }
  };
}
async function startPeerInbox(options) {
  const candidates = options.socketPath !== void 0 ? [options.socketPath] : resolveInboxCandidates();
  if (candidates.length === 0) {
    throw new PeerEndpointError(
      "unsupported-platform",
      "peer inboxes need UNIX domain sockets, which this platform does not offer here"
    );
  }
  let firstFailure;
  for (const candidate of candidates) {
    try {
      return await bindAt(candidate, options);
    } catch (error) {
      firstFailure ??= `${candidate}: ${describeError(error)}`;
    }
  }
  throw new PeerEndpointError(
    "bind-failed",
    `could not bind a peer inbox (tried ${candidates.length} path${candidates.length === 1 ? "" : "s"}; first: ${firstFailure})`
  );
}

// src/vendor/qwen-code-peer/registry.ts
import { randomBytes as randomBytes3 } from "node:crypto";
import * as fsSync2 from "node:fs";
import * as fs4 from "node:fs/promises";
import * as os2 from "node:os";
import * as path3 from "node:path";
var SESSION_REGISTRY_SCHEMA_VERSION = 1;
var REGISTRY_DIR_MODE = 448;
var RECORD_FILE_MODE = 384;
var MAX_RECORD_BYTES = 64 * 1024;
var RECORD_FILENAME = /^(\d+)(?:-[0-9a-f]{8})?\.json$/;
var KIND_RE = /^[a-z][a-z0-9-]{0,15}$/;
function isValidSessionKind(kind) {
  return KIND_RE.test(kind);
}
function resolveQwenHome(explicit) {
  const configured = explicit || process.env["QWEN_HOME"];
  if (configured) {
    let resolved = configured;
    if (resolved === "~" || resolved.startsWith("~/") || resolved.startsWith("~\\")) {
      resolved = path3.join(
        os2.homedir(),
        ...resolved.slice(2).split(/[/\\]+/).filter(Boolean)
      );
    }
    return path3.resolve(resolved);
  }
  const home = os2.homedir();
  return home ? path3.join(home, ".qwen") : path3.join(os2.tmpdir(), ".qwen");
}
function sessionRegistryDir(qwenHome) {
  return path3.join(qwenHome, "sessions");
}
function pidOfRecordFilename(name) {
  const match = RECORD_FILENAME.exec(name);
  if (!match) return null;
  const digits = match[1];
  const pid = Number.parseInt(digits, 10);
  return Number.isSafeInteger(pid) && pid > 0 && String(pid) === digits ? pid : null;
}
function parseRecordText(raw) {
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { status: "unusable" };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { status: "unusable" };
  }
  const value = parsed;
  const schemaVersion = value["schemaVersion"];
  if (typeof schemaVersion !== "number") return { status: "unusable" };
  if (schemaVersion > SESSION_REGISTRY_SCHEMA_VERSION) {
    return { status: "newer" };
  }
  const { pid, sessionId, cwd, name, startedAt } = value;
  if (typeof pid !== "number" || !Number.isInteger(pid) || pid <= 0 || typeof sessionId !== "string" || typeof cwd !== "string" || typeof name !== "string" || typeof startedAt !== "number" || !Number.isFinite(startedAt)) {
    return { status: "unusable" };
  }
  const { procStart, pidNs, qwenVersion, kind, ipcPath, ipcToken } = value;
  return {
    status: "ok",
    record: {
      schemaVersion,
      pid,
      procStart: typeof procStart === "string" ? procStart : null,
      pidNs: typeof pidNs === "number" && Number.isFinite(pidNs) ? pidNs : null,
      sessionId,
      cwd,
      name,
      startedAt,
      qwenVersion: typeof qwenVersion === "string" ? qwenVersion : null,
      // Absent means a writer older than the field, which reads differently
      // from a malformed one; a kind this build does not know is kept.
      ...typeof kind === "string" && KIND_RE.test(kind) ? { kind } : {},
      ...typeof ipcPath === "string" && ipcPath.length > 0 ? { ipcPath } : {},
      ...typeof ipcToken === "string" && ipcToken.length > 0 ? { ipcToken } : {}
    }
  };
}
function isMissing(error) {
  return error?.code === "ENOENT";
}
async function readRecordFile(filePath) {
  try {
    const stats = await fs4.stat(filePath);
    if (!stats.isFile() || stats.size > MAX_RECORD_BYTES) {
      return { status: "unusable" };
    }
    return parseRecordText(await fs4.readFile(filePath, "utf8"));
  } catch (error) {
    return isMissing(error) ? { status: "missing" } : { status: "read-error" };
  }
}
function readRecordFileSync(filePath) {
  try {
    const stats = fsSync2.statSync(filePath);
    if (!stats.isFile() || stats.size > MAX_RECORD_BYTES) {
      return { status: "unusable" };
    }
    return parseRecordText(fsSync2.readFileSync(filePath, "utf8"));
  } catch (error) {
    return isMissing(error) ? { status: "missing" } : { status: "read-error" };
  }
}
async function readLiveSessionRecords(dir) {
  let entries;
  try {
    entries = await fs4.readdir(dir);
  } catch {
    return [];
  }
  const ownNamespace = readPidNamespaceId();
  const ownBootId = readLocalBootId();
  const live = [];
  await Promise.all(
    entries.map(async (name) => {
      const pid = pidOfRecordFilename(name);
      if (pid === null) return;
      const read = await readRecordFile(path3.join(dir, name));
      if (read.status !== "ok") return;
      const record = read.record;
      if (record.pid !== pid) return;
      if (record.pidNs !== ownNamespace) return;
      const recordBootId = record.procStart === null ? null : bootIdOf(record.procStart);
      if (recordBootId !== null && recordBootId !== ownBootId) return;
      if (!isSameProcess(record.pid, record.procStart)) return;
      live.push(record);
    })
  );
  return live.sort((a, b) => b.startedAt - a.startedAt);
}
function isDeadPredecessor(record) {
  if (record.pid !== process.pid) return false;
  if (record.pidNs !== readPidNamespaceId()) return false;
  if (record.procStart === null) return false;
  const current = readProcStartToken(process.pid);
  if (current === null) return false;
  return bootIdOf(record.procStart) === bootIdOf(current) && record.procStart !== current;
}
async function isClaimable(filePath, shared) {
  let stats;
  try {
    stats = await fs4.lstat(filePath);
  } catch (error) {
    return isMissing(error);
  }
  if (!shared || !stats.isFile()) return false;
  const existing = await readRecordFile(filePath);
  switch (existing.status) {
    case "missing":
    case "unusable":
      return true;
    case "ok":
      return isDeadPredecessor(existing.record);
    default:
      return false;
  }
}
async function ensureRegistryDir(dir) {
  await fs4.mkdir(dir, { recursive: true, mode: REGISTRY_DIR_MODE });
  try {
    await fs4.chmod(dir, REGISTRY_DIR_MODE);
  } catch (error) {
    const code = error.code;
    if (code !== "ENOSYS" && code !== "ENOTSUP") throw error;
  }
}
async function writeAtomically(filePath, contents) {
  const temporary = `${filePath}.${randomBytes3(6).toString("hex")}.tmp`;
  let handle;
  try {
    handle = await fs4.open(temporary, "wx", RECORD_FILE_MODE);
    await handle.writeFile(contents, "utf8");
    await handle.sync();
    await handle.close();
    handle = void 0;
    await fs4.rename(temporary, filePath);
  } catch (error) {
    await handle?.close().catch(() => {
    });
    await fs4.unlink(temporary).catch(() => {
    });
    throw error;
  }
}
var registrations = Promise.resolve();
function writeOwnRecord(dir, record) {
  const run = () => claimAndWrite(dir, record);
  const written = registrations.then(run, run);
  registrations = written.catch(() => {
  });
  return written;
}
async function claimAndWrite(dir, record) {
  await ensureRegistryDir(dir);
  const contents = JSON.stringify(record, null, 2);
  const shared = path3.join(dir, `${record.pid}.json`);
  if (await isClaimable(shared, true)) {
    await writeAtomically(shared, contents);
    return shared;
  }
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const minted = path3.join(
      dir,
      `${record.pid}-${randomBytes3(4).toString("hex")}.json`
    );
    if (await isClaimable(minted, false)) {
      await writeAtomically(minted, contents);
      return minted;
    }
  }
  throw new Error(`no free record name for PID ${record.pid} in ${dir}`);
}
function isOwnRecord(read, sessionId) {
  return read.status === "ok" && read.record.pid === process.pid && read.record.sessionId === sessionId;
}
async function removeOwnRecord(filePath, sessionId) {
  if (!isOwnRecord(await readRecordFile(filePath), sessionId)) return;
  await fs4.unlink(filePath).catch(() => {
  });
}
function removeOwnRecordSync(filePath, sessionId) {
  if (!isOwnRecord(readRecordFileSync(filePath), sessionId)) return;
  try {
    fsSync2.unlinkSync(filePath);
  } catch {
  }
}

// src/vendor/qwen-code-peer/endpoint.ts
var MAX_TRACKED_SENDS = 200;
var MAX_REMEMBERED_MESSAGES = 200;
var CONTROLLER_TOKEN_PREFIX = "qpc_";
var MAX_CONTROLLER_TOKEN_CHARS = 256;
var RECEIPT_TRANSITIONS = {
  pending: /* @__PURE__ */ new Set([
    "held",
    "delivered",
    "denied",
    "refused",
    "expired",
    "misaddressed",
    "dropped"
  ]),
  held: /* @__PURE__ */ new Set(["delivered", "denied", "expired", "misaddressed"]),
  delivered: /* @__PURE__ */ new Set(["expired", "misaddressed"]),
  denied: /* @__PURE__ */ new Set(),
  refused: /* @__PURE__ */ new Set(),
  expired: /* @__PURE__ */ new Set(),
  misaddressed: /* @__PURE__ */ new Set(),
  dropped: /* @__PURE__ */ new Set()
};
var NEVER_WRITTEN_CODES = /* @__PURE__ */ new Set([
  void 0,
  "ENOENT",
  "ECONNREFUSED",
  "EMSGSIZE",
  "EAGAIN",
  "EBUSY"
]);
function describeSendFailure(error) {
  if (error instanceof PeerSendError) {
    if (error.local) {
      return "this program already has too many sends in flight, so nothing was written to that session; retry once some settle";
    }
    switch (error.code) {
      case "ENOENT":
      case "ECONNREFUSED":
        return "that session has exited and its address is stale; list the sessions again";
      case "EAGAIN":
      case "EBUSY":
        return "that session is alive but momentarily busy; retry shortly";
      case "ETIMEDOUT":
        return "that session accepted the connection but had not read the message after 5 seconds; it may still read it, so wait for a receipt rather than re-sending";
      default:
        return error.message;
    }
  }
  return describeError(error);
}
function isPresentableControllerToken(token) {
  return token.startsWith(CONTROLLER_TOKEN_PREFIX) && token.length > CONTROLLER_TOKEN_PREFIX.length && token.length <= MAX_CONTROLLER_TOKEN_CHARS && !/\s/.test(token);
}
var PeerEndpoint = class _PeerEndpoint {
  sessionId;
  name;
  ref;
  kind;
  cwd;
  /**
   * The token this endpoint's inbox requires. Anyone who can read the
   * registry can read it; never print it where a model or a log sees it.
   */
  ipcToken;
  /** Where this endpoint reads and writes session records. */
  registryDir;
  startedAt;
  options;
  inbox;
  recordFile;
  exitHook;
  closed = false;
  sends = /* @__PURE__ */ new Map();
  answered = /* @__PURE__ */ new Map();
  constructor(options, name, kind, sessionId) {
    this.options = options;
    this.name = name;
    this.kind = kind;
    this.sessionId = sessionId;
    this.ref = peerRef(sessionId);
    this.cwd = options.cwd ?? process.cwd();
    this.ipcToken = randomBytes4(32).toString("hex");
    this.registryDir = sessionRegistryDir(resolveQwenHome(options.qwenHome));
    this.startedAt = Date.now();
  }
  /**
   * Bind an inbox and publish this endpoint's record.
   *
   * The inbox is bound first: a record is listed the moment it lands, and
   * one that named no inbox yet would be a session nobody can reach. If the
   * record cannot be written, the inbox is closed again and nothing is left
   * behind.
   */
  static async start(options) {
    const name = boundSessionName(options.name ?? "");
    if (name.length === 0) {
      throw new PeerEndpointError(
        "invalid-name",
        "a peer endpoint needs a name that is not blank once flattened to one line"
      );
    }
    const kind = options.kind ?? "external";
    if (!isValidSessionKind(kind)) {
      throw new PeerEndpointError(
        "invalid-kind",
        `"${kind}" is not a kind: use lowercase letters, digits and dashes, starting with a letter, at most 16 characters`
      );
    }
    const sessionId = options.sessionId ?? randomUUID2();
    if (sessionId.trim().length === 0) {
      throw new PeerEndpointError(
        "invalid-session-id",
        "a peer endpoint needs a session id that is not blank"
      );
    }
    if (options.controllerToken !== void 0 && !isPresentableControllerToken(options.controllerToken)) {
      throw new PeerEndpointError(
        "invalid-controller-token",
        "controllerToken must be a token minted with `qwen sessions controllers add`, which starts with qpc_; an empty value usually means the variable holding it is unset"
      );
    }
    let procStart = readProcStartToken(process.pid);
    let pidNs = readPidNamespaceId();
    if (process.platform === "linux" && (procStart === null || pidNs === null)) {
      procStart = readProcStartToken(process.pid);
      pidNs = readPidNamespaceId();
      if (procStart === null || pidNs === null) {
        throw new PeerEndpointError(
          "registry-unwritable",
          "could not read this process start token or PID namespace, and a record without them could not be told apart from another process"
        );
      }
    }
    const endpoint = new _PeerEndpoint(options, name, kind, sessionId);
    endpoint.inbox = await startPeerInbox({
      ...options.socketPath !== void 0 ? { socketPath: options.socketPath } : {},
      requiredToken: endpoint.ipcToken,
      onFrame: (frame) => endpoint.handleFrame(frame),
      keepAlive: options.keepAlive ?? true
    });
    try {
      endpoint.recordFile = await writeOwnRecord(endpoint.registryDir, {
        schemaVersion: SESSION_REGISTRY_SCHEMA_VERSION,
        pid: process.pid,
        procStart,
        pidNs,
        sessionId,
        cwd: endpoint.cwd,
        name,
        startedAt: endpoint.startedAt,
        qwenVersion: options.version ?? null,
        kind,
        ipcPath: endpoint.inbox.socketPath,
        ipcToken: endpoint.ipcToken
      });
    } catch (error) {
      await endpoint.inbox.close();
      throw new PeerEndpointError(
        "registry-unwritable",
        `could not write the session record in ${endpoint.registryDir}: ${describeError(error)}`
      );
    }
    if (options.closeOnExit ?? true) {
      const hook = () => endpoint.closeSync();
      endpoint.exitHook = hook;
      process.once("exit", hook);
    }
    return endpoint;
  }
  /** The socket this endpoint listens on. */
  get ipcPath() {
    return this.inbox.socketPath;
  }
  /** The record file this endpoint published. */
  get recordPath() {
    return this.recordFile;
  }
  /**
   * The sessions this endpoint can send to right now: live, answering a
   * dial, and not this endpoint. A session whose `agents.crossSessionMessaging`
   * is off has no inbox and is not listed.
   */
  async list() {
    this.assertOpen();
    const peers = this.othersIn(await this.directory(true));
    return peers.flatMap((peer) => {
      const address = advertisablePeerAddress(peer, peers);
      return address === void 0 ? [] : [summarize(peer, address)];
    });
  }
  /**
   * Send `content` to the session `to` names.
   *
   * `sent` means the frame was written, not that anyone read it; the
   * receipts that follow say what became of it (see
   * {@link PeerEndpoint.awaitReceipt}).
   */
  async send(options) {
    this.assertOpen();
    const controller = options.controller === true;
    const controllerToken = this.options.controllerToken;
    if (controller && controllerToken === void 0) {
      throw new PeerEndpointError(
        "invalid-controller-token",
        "a controller send needs an endpoint started with a controllerToken"
      );
    }
    const directory = await this.directory(!controller);
    this.assertOpen();
    const peers = this.othersIn(directory);
    const resolved = resolvePeerTarget(peers, options.to);
    if (resolved.kind === "none") {
      const incarnations = [
        this.selfEntry(),
        ...directory.filter((peer2) => peer2.sessionId === this.sessionId)
      ];
      if (resolvePeerTarget(incarnations, options.to).kind !== "none") {
        return { kind: "self" };
      }
      return {
        kind: "not-found",
        suggestions: suggestPeerNames(peers, options.to)
      };
    }
    if (resolved.kind === "ambiguous") {
      return {
        kind: "ambiguous",
        matches: resolved.matches.flatMap((peer2) => {
          const address = advertisablePeerAddress(peer2, peers);
          return address === void 0 ? [] : [address];
        })
      };
    }
    const peer = resolved.peer;
    const summary = summarize(
      peer,
      advertisablePeerAddress(peer, peers) ?? options.to.trim()
    );
    if (options.content.length === 0) {
      return {
        kind: "failed",
        peer: summary,
        reason: "the message is empty; there is nothing to deliver"
      };
    }
    const frame = buildUserFrame({
      content: options.content,
      from: this.ipcPath,
      replyToken: this.ipcToken,
      fromName: this.name,
      // Pins the frame to the session the address resolved to. Addresses
      // are keyed by PID and PIDs are reused: a different session found at
      // that address later answers `misaddressed` instead of acting on a
      // message meant for its predecessor.
      toSessionId: peer.sessionId,
      ...options.priority !== void 0 ? { priority: options.priority } : {},
      ...options.fromMode !== void 0 ? { fromMode: options.fromMode } : {}
    });
    const authToken = controller ? controllerToken : peer.ipcToken;
    this.track(frame.msgId, summary.address);
    try {
      await sendPeerFrame(
        peer.ipcPath,
        frame,
        authToken !== void 0 ? { authToken } : {}
      );
      return { kind: "sent", msgId: frame.msgId, peer: summary };
    } catch (error) {
      const code = error instanceof PeerSendError ? error.code : void 0;
      const unwritten = NEVER_WRITTEN_CODES.has(code);
      if (unwritten) this.forget(frame.msgId);
      return {
        kind: "failed",
        peer: summary,
        ...code !== void 0 ? { code } : {},
        reason: describeSendFailure(error),
        ...unwritten ? {} : { msgId: frame.msgId }
      };
    }
  }
  /**
   * The receipt for a message this endpoint sent.
   *
   * Resolves at once when one has already arrived. With `final`, waits past
   * `held` for the decision. Resolves `undefined` on timeout, when the id is
   * not one this endpoint is tracking, and when the endpoint closes.
   */
  awaitReceipt(msgId, options = {}) {
    const entry = this.sends.get(canonicalizeMsgId(msgId));
    if (!entry) return Promise.resolve(void 0);
    const final = options.final ?? false;
    const satisfied = () => entry.last !== void 0 && (!final || entry.state !== "pending" && entry.state !== "held");
    if (satisfied()) return Promise.resolve(entry.last);
    if (this.closed) return Promise.resolve(void 0);
    return new Promise((resolve3) => {
      const finish = (receipt) => {
        clearTimeout(timer);
        entry.waiters.delete(wake);
        resolve3(receipt);
      };
      const wake = () => {
        if (satisfied()) finish(entry.last);
        else if (this.closed || entry.forgotten) finish(void 0);
      };
      const timer = setTimeout(
        () => finish(void 0),
        options.timeoutMs ?? 3e4
      );
      entry.waiters.add(wake);
    });
  }
  /**
   * Stop listening and remove this endpoint's record and socket. Pending
   * {@link PeerEndpoint.awaitReceipt} calls resolve `undefined`. Safe to
   * call more than once.
   */
  async close() {
    if (this.closed) return;
    this.beginClose();
    await this.inbox.close();
    await removeOwnRecord(this.recordFile, this.sessionId);
  }
  closeSync() {
    if (this.closed) return;
    this.beginClose();
    this.inbox.closeSync();
    removeOwnRecordSync(this.recordFile, this.sessionId);
  }
  beginClose() {
    this.closed = true;
    if (this.exitHook) {
      process.removeListener("exit", this.exitHook);
      this.exitHook = void 0;
    }
    for (const entry of this.sends.values()) wakeAll(entry);
  }
  assertOpen() {
    if (this.closed) {
      throw new PeerEndpointError("closed", "this peer endpoint is closed");
    }
  }
  async directory(collapseTwins) {
    return reachableEntries(
      await readLiveSessionRecords(this.registryDir),
      void 0,
      { collapseTwins }
    );
  }
  /**
   * Everyone but this endpoint. Excluded by session id, so another process
   * running with the same id — which an endpoint given a stable
   * `sessionId` can be — is excluded too, rather than messaged as a peer.
   */
  othersIn(directory) {
    return directory.filter((peer) => peer.sessionId !== this.sessionId);
  }
  selfEntry() {
    return {
      sessionId: this.sessionId,
      name: this.name,
      ref: this.ref,
      cwd: flattenPeerLabel(this.cwd),
      pid: process.pid,
      kind: this.kind,
      ipcPath: this.ipcPath,
      ipcToken: this.ipcToken,
      startedAt: this.startedAt
    };
  }
  track(msgId, address) {
    this.sends.set(canonicalizeMsgId(msgId), {
      msgId,
      address,
      state: "pending",
      waiters: /* @__PURE__ */ new Set()
    });
    while (this.sends.size > MAX_TRACKED_SENDS) {
      const oldest = this.sends.keys().next().value;
      if (oldest === void 0) break;
      this.forget(oldest);
    }
  }
  forget(msgId) {
    const key = canonicalizeMsgId(msgId);
    const entry = this.sends.get(key);
    if (!entry) return;
    this.sends.delete(key);
    entry.forgotten = true;
    wakeAll(entry);
  }
  handleFrame(frame) {
    if (this.closed) return;
    if (frame.type === "control") {
      this.applyReceipt(frame);
    } else {
      this.receive(frame);
    }
  }
  applyReceipt(frame) {
    this.settle(frame.origMsgId, frame);
    if (frame.status !== "dropped") return;
    for (const msgId of frame.droppedMsgIds ?? []) this.settle(msgId, frame);
  }
  settle(msgId, frame) {
    const entry = this.sends.get(canonicalizeMsgId(msgId));
    if (!entry || !RECEIPT_TRANSITIONS[entry.state].has(frame.status)) return;
    const receipt = {
      msgId: entry.msgId,
      address: entry.address,
      status: frame.status,
      previous: entry.state,
      // Written by whatever answered, and bound for a person: flattened
      // like every other label that crosses in, so it cannot carry escape
      // sequences or a megabyte of text into a terminal or a prompt.
      ...frame.reason !== void 0 ? { reason: flattenPeerLabel(frame.reason) } : {},
      ...frame.dropReason !== void 0 ? { dropReason: frame.dropReason } : {}
    };
    entry.state = frame.status;
    entry.last = receipt;
    wakeAll(entry);
    const onReceipt = this.options.onReceipt;
    if (onReceipt) this.invoke(() => onReceipt(receipt));
  }
  receive(frame) {
    const key = canonicalizeMsgId(frame.msgId);
    const answered = this.answered.get(key);
    if (answered !== void 0) {
      this.reply(frame, answered);
      return;
    }
    if (frame.toSessionId !== void 0 && frame.toSessionId !== this.sessionId) {
      this.reply(frame, "misaddressed");
      return;
    }
    const onMessage = this.options.onMessage;
    const status = onMessage ? "delivered" : "refused";
    this.answered.set(key, status);
    while (this.answered.size > MAX_REMEMBERED_MESSAGES) {
      const oldest = this.answered.keys().next().value;
      if (oldest === void 0) break;
      this.answered.delete(oldest);
    }
    this.reply(frame, status);
    if (!onMessage) return;
    const message = {
      msgId: frame.msgId,
      content: frame.message.content,
      priority: frame.priority,
      ...frame.from !== void 0 ? { from: frame.from } : {},
      ...frame.fromName !== void 0 ? { fromName: flattenPeerLabel(frame.fromName) } : {},
      ...frame.fromMode !== void 0 ? { fromMode: frame.fromMode } : {}
    };
    this.invoke(() => onMessage(message));
  }
  /**
   * Best-effort: a sender that has exited, or that gave no address, simply
   * never hears back.
   */
  reply(frame, status) {
    if (!frame.from) return;
    sendPeerFrame(
      frame.from,
      buildDeliveryStatusFrame({
        status,
        origMsgId: frame.msgId,
        from: this.ipcPath
      }),
      frame.replyToken !== void 0 ? { authToken: frame.replyToken } : {}
    ).catch(() => {
    });
  }
  invoke(callback) {
    try {
      const result = callback();
      if (result instanceof Promise) {
        result.catch((error) => this.reportError(error));
      }
    } catch (error) {
      this.reportError(error);
    }
  }
  reportError(error) {
    const onError = this.options.onError;
    if (!onError) return;
    try {
      onError(error instanceof Error ? error : new Error(String(error)));
    } catch {
    }
  }
};
function wakeAll(entry) {
  for (const wake of [...entry.waiters]) wake();
}
function summarize(peer, address) {
  return {
    sessionId: peer.sessionId,
    name: peer.name,
    ref: peer.ref,
    address,
    cwd: peer.cwd,
    pid: peer.pid,
    kind: peer.kind,
    startedAt: peer.startedAt
  };
}

// src/adaptor/qwen-peer-controller.ts
import { createHash as createHash2, randomBytes as randomBytes5 } from "node:crypto";
var MAX_DELIVERIES = 100;
var RECEIPT_TIMEOUT_MS = 3e4;
var TRANSITIONS = {
  pending: /* @__PURE__ */ new Set([
    "held",
    "delivered",
    "denied",
    "refused",
    "expired",
    "misaddressed",
    "dropped"
  ]),
  held: /* @__PURE__ */ new Set(["delivered", "denied", "expired", "misaddressed"]),
  delivered: /* @__PURE__ */ new Set(["expired", "misaddressed"]),
  denied: /* @__PURE__ */ new Set(),
  refused: /* @__PURE__ */ new Set(),
  expired: /* @__PURE__ */ new Set(),
  misaddressed: /* @__PURE__ */ new Set(),
  dropped: /* @__PURE__ */ new Set()
};
var NEVER_WRITTEN = /* @__PURE__ */ new Set([
  void 0,
  "ENOENT",
  "ECONNREFUSED",
  "EMSGSIZE",
  "EAGAIN",
  "EBUSY"
]);
function qwenPeerHandleId(qwenHome, peer) {
  return `qwen-peer:${createHash2("sha256").update(
    JSON.stringify([qwenHome, peer.sessionId, peer.pid, peer.startedAt])
  ).digest("hex")}`;
}
var QwenPeerController = class {
  constructor(options, dependencies = {}) {
    this.options = options;
    this.readRecords = dependencies.readRecords ?? readLiveSessionRecords;
    this.openInbox = dependencies.startInbox ?? startPeerInbox;
    this.sendFrame = dependencies.sendFrame ?? sendPeerFrame;
    this.receiptTimeoutMs = dependencies.receiptTimeoutMs ?? RECEIPT_TIMEOUT_MS;
  }
  records = /* @__PURE__ */ new Map();
  replyToken = randomBytes5(32).toString("hex");
  inbox;
  closed = false;
  exitHook;
  readRecords;
  openInbox;
  sendFrame;
  receiptTimeoutMs;
  async start() {
    const token = this.options.controllerToken;
    if (!token.startsWith("qpc_") || token.length <= 4 || token.length > 256 || /\s/u.test(token)) {
      throw new Error("The peer controller token is invalid.");
    }
    this.inbox = await this.openInbox({
      requiredToken: this.replyToken,
      onFrame: (frame) => this.receive(frame),
      keepAlive: false
    });
    if (!this.options.isActive() || this.closed) {
      await this.close();
      return;
    }
    this.exitHook = () => this.inbox?.closeSync();
    process.once("exit", this.exitHook);
  }
  deliveries() {
    return [...this.records.values()].map((entry) => this.snapshot(entry));
  }
  async send(handle, content) {
    const rejected = (note) => ({
      status: "rejected",
      note
    });
    if (!this.active())
      return rejected("Terminal instructions require an active voice call.");
    if (handle.adaptor !== this.options.adaptor || !handle.id.startsWith("qwen-peer:")) {
      return rejected("This is not a discovered terminal session.");
    }
    if (!content.trim()) return rejected("The instruction is empty.");
    let records;
    try {
      records = await this.readRecords(
        sessionRegistryDir(this.options.qwenHome)
      );
    } catch {
      return rejected(
        "The terminal directory could not be read. Refresh the session list."
      );
    }
    const matches = records.filter(
      (record2) => qwenPeerHandleId(this.options.qwenHome, record2) === handle.id
    );
    if (matches.length !== 1) {
      return rejected(
        "This terminal session has changed or exited. Refresh the session list."
      );
    }
    const record = matches[0];
    if (records.filter((candidate) => candidate.sessionId === record.sessionId).length !== 1) {
      return rejected(
        "This session is registered more than once. Close the duplicate terminal before sending."
      );
    }
    const peer = toDirectoryEntry(record);
    if (!peer || peer.kind !== "tui" || !isLocalIpcPath(peer.ipcPath)) {
      return rejected(
        "This terminal is no longer available for instructions. Refresh the session list."
      );
    }
    if (!this.active())
      return rejected("The voice call ended before the instruction was sent.");
    if (!this.makeRoom()) {
      return rejected(
        "This call already has 100 instructions still being tracked. Start a new call before sending more."
      );
    }
    const inbox = this.inbox;
    const frame = buildUserFrame({
      content,
      from: inbox.socketPath,
      replyToken: this.replyToken,
      fromName: this.options.name,
      toSessionId: record.sessionId,
      priority: "next"
    });
    const now = Date.now();
    const entry = {
      delivery: {
        id: frame.msgId,
        target: {
          id: handle.id,
          adaptor: this.options.adaptor,
          instructionOnly: true
        },
        status: "pending",
        tracking: true,
        createdAt: now,
        updatedAt: now
      },
      wireState: "pending"
    };
    this.records.set(canonicalizeMsgId(frame.msgId), entry);
    entry.timeout = setTimeout(() => {
      if (!entry.delivery.tracking || entry.wireState !== "pending") return;
      this.update(entry, {
        status: "unknown",
        note: "No receipt arrived in time. The instruction may still be received; do not resend automatically."
      });
    }, this.receiptTimeoutMs);
    entry.timeout.unref?.();
    this.notify();
    if (!this.active()) {
      this.finish(
        entry,
        "failed",
        "The voice call ended before the instruction was sent."
      );
      return rejected(entry.delivery.note);
    }
    try {
      await this.sendFrame(peer.ipcPath, frame, {
        authToken: this.options.controllerToken
      });
    } catch (error) {
      if (entry.delivery.tracking && entry.wireState === "pending") {
        if (error instanceof PeerSendError && NEVER_WRITTEN.has(error.code)) {
          this.finish(
            entry,
            "failed",
            "The instruction could not be sent. Refresh the session list before trying again."
          );
          return rejected(entry.delivery.note);
        }
        this.update(entry, {
          status: "unknown",
          note: "The send result is uncertain. The instruction may still be received; do not resend automatically."
        });
      }
    }
    return {
      status: entry.delivery.status === "unknown" ? "unknown" : "sent",
      delivery: this.snapshot(entry)
    };
  }
  async close() {
    this.closed = true;
    if (this.exitHook) process.removeListener("exit", this.exitHook);
    this.exitHook = void 0;
    for (const entry of this.records.values()) {
      clearTimeout(entry.timeout);
      if (!entry.delivery.tracking) continue;
      this.update(entry, {
        ...entry.wireState === "pending" || entry.wireState === "held" ? { status: "unknown" } : {},
        tracking: false,
        note: "The call ended and receipt tracking stopped. Sent instructions were not cancelled."
      });
    }
    await this.inbox?.close();
  }
  active() {
    return !this.closed && this.inbox !== void 0 && this.options.isActive();
  }
  receive(frame) {
    if (!this.active()) return;
    if (frame.type === "user") {
      if (frame.from) {
        void this.sendFrame(
          frame.from,
          buildDeliveryStatusFrame({
            status: "refused",
            origMsgId: frame.msgId,
            from: this.inbox.socketPath
          }),
          frame.replyToken ? { authToken: frame.replyToken } : {}
        ).catch(() => {
        });
      }
      return;
    }
    this.settle(frame.origMsgId, frame);
    if (frame.status === "dropped") {
      for (const id of frame.droppedMsgIds ?? []) this.settle(id, frame);
    }
  }
  settle(msgId, frame) {
    const entry = this.records.get(canonicalizeMsgId(msgId));
    if (!entry?.delivery.tracking || !TRANSITIONS[entry.wireState].has(frame.status))
      return;
    clearTimeout(entry.timeout);
    entry.wireState = frame.status;
    this.update(entry, {
      status: frame.status,
      tracking: frame.status === "held" || frame.status === "delivered",
      // Receipt reason is untrusted free text, never a diagnostic or authority.
      note: void 0
    });
  }
  finish(entry, status, note) {
    clearTimeout(entry.timeout);
    this.update(entry, { status, tracking: false, note });
  }
  update(entry, fields) {
    Object.assign(entry.delivery, fields, {
      updatedAt: Math.max(entry.delivery.updatedAt, Date.now())
    });
    this.notify();
  }
  makeRoom() {
    if (this.records.size < MAX_DELIVERIES) return true;
    for (const [id, entry] of this.records) {
      if (!entry.delivery.tracking) {
        this.records.delete(id);
        return true;
      }
    }
    return false;
  }
  snapshot(entry) {
    return { ...entry.delivery, target: { ...entry.delivery.target } };
  }
  notify() {
    try {
      this.options.onChange();
    } catch {
    }
  }
};

// src/adaptor/qwen-peer-reports.ts
import { createHash as createHash3, randomBytes as randomBytes6, randomUUID as randomUUID3 } from "node:crypto";
var MAX_TEXT_CHARS = 2e3;
var MAX_REPORT_WIRE_CHARS = 16384;
var MAX_PENDING_REPORTS = 32;
var MAX_RECENT_REPORTS = 100;
var MAX_CONTEXTS = 100;
var MAX_RECEIPT_WRITES = 16;
var RATE_WINDOW_MS = 6e4;
var GLOBAL_RATE = 20;
var SOURCE_RATE = 6;
var UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/iu;
function peerReportLabel(value, limit = 240) {
  return value.replace(/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]+/gu, " ").trim().slice(0, limit).replace(/[\uD800-\uDBFF]$/u, "");
}
function parseReport(content) {
  if (content.length > MAX_REPORT_WIRE_CHARS) return void 0;
  let parsed;
  try {
    parsed = JSON.parse(content);
  } catch {
  }
  if (parsed !== null && typeof parsed === "object" && !Array.isArray(parsed) && "qwen_live_harness_report" in parsed) {
    const envelope = parsed;
    const text = envelope["text"];
    const category = envelope["kind"];
    const correlation = envelope["correlation"];
    if (envelope["qwen_live_harness_report"] !== 1 || typeof text !== "string" || !text.trim() || text.length > MAX_TEXT_CHARS || typeof category !== "string" || !["progress", "blocked", "result", "info"].includes(category) || correlation !== void 0 && (typeof correlation !== "string" || !UUID.test(correlation))) {
      return void 0;
    }
    return {
      text,
      category,
      ...typeof correlation === "string" ? { correlation: correlation.toLowerCase() } : {}
    };
  }
  if (!content.trim() || content.length > MAX_TEXT_CHARS) return void 0;
  return { text: content, category: "info" };
}
var QwenPeerReports = class _QwenPeerReports {
  constructor(options, dependencies) {
    this.options = options;
    this.qwenHome = resolveQwenHome(options.qwenHome);
    this.registryDir = sessionRegistryDir(this.qwenHome);
    this.readRecords = dependencies.readRecords ?? readLiveSessionRecords;
    this.openInbox = dependencies.startInbox ?? startPeerInbox;
    this.sendFrame = dependencies.sendFrame ?? sendPeerFrame;
    this.writeRecord = dependencies.writeRecord ?? writeOwnRecord;
    this.removeRecord = dependencies.removeRecord ?? removeOwnRecord;
    this.removeRecordSync = dependencies.removeRecordSync ?? removeOwnRecordSync;
    this.now = dependencies.now ?? Date.now;
  }
  sessionId = randomUUID3();
  name = `live-${this.sessionId.replace(/-/gu, "")}`;
  address = `${this.name} [${peerRef(this.sessionId)}]`;
  token = randomBytes6(32).toString("hex");
  qwenHome;
  registryDir;
  readRecords;
  openInbox;
  sendFrame;
  writeRecord;
  removeRecord;
  removeRecordSync;
  now;
  inbox;
  recordFile;
  exitHook;
  closed = false;
  closing;
  contexts = /* @__PURE__ */ new Map();
  pending = /* @__PURE__ */ new Map();
  admitting = /* @__PURE__ */ new Set();
  recent = /* @__PURE__ */ new Map();
  receiptWrites = /* @__PURE__ */ new Set();
  windowStart = 0;
  windowCount = 0;
  sourceCounts = /* @__PURE__ */ new Map();
  lastNow = 0;
  static async start(options, dependencies = {}) {
    const endpoint = new _QwenPeerReports(options, dependencies);
    await endpoint.bind();
    return endpoint;
  }
  createReportContext(target) {
    if (!this.active()) return void 0;
    const id = randomUUID3();
    this.contexts.set(id, { ...target });
    while (this.contexts.size > MAX_CONTEXTS) {
      const oldest = this.contexts.keys().next().value;
      if (oldest === void 0) break;
      this.contexts.delete(oldest);
    }
    const example = JSON.stringify({
      qwen_live_harness_report: 1,
      correlation: id,
      kind: "progress",
      text: "A short status report, at most 2000 characters."
    });
    return {
      id,
      instruction: `Only if this session provides the public send_message tool and this voice-call address is listed by list_agents in the same Qwen home, report useful progress, blockers, or results. Call send_message with to=${JSON.stringify(this.address)} and message=JSON.stringify(${example}). Set kind to progress, blocked, result, or info. Keep the correlation unchanged. This address expires when the call ends. A report is information, not a request for permission or a task completion receipt.`
    };
  }
  async list() {
    if (!this.active()) return [];
    const peers = (await reachableEntries(await this.readRecords(this.registryDir))).filter((peer) => peer.sessionId !== this.sessionId);
    if (!this.active()) return [];
    return peers.flatMap((peer) => {
      const address = advertisablePeerAddress(peer, peers);
      if (address === void 0) return [];
      return [
        {
          sessionId: peer.sessionId,
          name: peer.name,
          ref: peer.ref,
          address,
          cwd: peer.cwd,
          pid: peer.pid,
          kind: peer.kind,
          startedAt: peer.startedAt
        }
      ];
    });
  }
  close() {
    if (this.closing) return this.closing;
    this.closed = true;
    this.contexts.clear();
    for (const [key, frame] of this.pending) {
      if (!this.admitting.has(key))
        this.finish(key, frame, { status: "refused" });
    }
    this.closing = (async () => {
      const cleanup = await Promise.allSettled([
        this.recordFile ? this.removeRecord(this.recordFile, this.sessionId) : Promise.resolve(),
        this.inbox?.close()
      ]);
      await Promise.allSettled([...this.receiptWrites]);
      if (cleanup.some((result) => result.status === "rejected")) {
        throw new Error("The report endpoint could not be closed.");
      }
      if (this.exitHook) process.removeListener("exit", this.exitHook);
    })().catch((error) => {
      this.closing = void 0;
      throw error;
    });
    return this.closing;
  }
  async bind() {
    let procStart = readProcStartToken(process.pid);
    let pidNs = readPidNamespaceId();
    if (process.platform === "linux" && (procStart === null || pidNs === null)) {
      procStart = readProcStartToken(process.pid);
      pidNs = readPidNamespaceId();
      if (procStart === null || pidNs === null) {
        throw new Error(
          "The report endpoint process identity could not be read."
        );
      }
    }
    try {
      this.inbox = await this.openInbox({
        requiredToken: this.token,
        onFrame: (frame) => this.receive(frame),
        keepAlive: false
      });
      this.recordFile = await this.writeRecord(this.registryDir, {
        schemaVersion: 1,
        pid: process.pid,
        procStart,
        pidNs,
        sessionId: this.sessionId,
        cwd: process.cwd(),
        name: this.name,
        startedAt: this.timestamp(),
        qwenVersion: null,
        kind: "external",
        ipcPath: this.inbox.socketPath,
        ipcToken: this.token
      });
    } catch {
      await this.inbox?.close().catch(() => {
      });
      throw new Error("The report endpoint could not be registered.");
    }
    this.exitHook = () => {
      this.closed = true;
      if (this.recordFile)
        this.removeRecordSync(this.recordFile, this.sessionId);
      this.inbox?.closeSync();
    };
    process.once("exit", this.exitHook);
  }
  active() {
    return !this.closed && this.options.isActive();
  }
  timestamp() {
    this.lastNow = Math.max(this.lastNow, this.now());
    return this.lastNow;
  }
  receive(frame) {
    if (frame.type !== "user") return;
    if (frame.toSessionId !== void 0 && frame.toSessionId !== this.sessionId) {
      this.reply(frame, { status: "misaddressed" });
      return;
    }
    const key = canonicalizeMsgId(frame.msgId);
    const previous = this.recent.get(key);
    if (previous) {
      this.reply(frame, previous);
      return;
    }
    if (this.pending.has(key)) return;
    if (!this.active() || !this.options.hasSink()) {
      this.finish(key, frame, { status: "refused" });
      return;
    }
    const payload = parseReport(frame.message.content);
    if (!payload) {
      this.finish(key, frame, { status: "refused" });
      return;
    }
    if (this.pending.size >= MAX_PENDING_REPORTS) {
      this.finish(key, frame, { status: "dropped", dropReason: "queue-full" });
      return;
    }
    if (!this.reserveRate(frame)) {
      this.finish(key, frame, {
        status: "dropped",
        dropReason: "rate-limited"
      });
      return;
    }
    this.pending.set(key, frame);
    void this.admit(key, frame, payload);
  }
  reserveRate(frame) {
    const now = this.timestamp();
    if (now - this.windowStart >= RATE_WINDOW_MS) {
      this.windowStart = now;
      this.windowCount = 0;
      this.sourceCounts.clear();
    }
    const source = createHash3("sha256").update(frame.from ?? "").digest("hex");
    const count = this.sourceCounts.get(source) ?? 0;
    if (this.windowCount >= GLOBAL_RATE || count >= SOURCE_RATE) return false;
    this.windowCount += 1;
    this.sourceCounts.set(source, count + 1);
    return true;
  }
  async admit(key, frame, payload) {
    let records = [];
    try {
      records = await this.readRecords(this.registryDir);
    } catch {
    }
    if (!this.pending.has(key)) return;
    if (!this.active() || !this.options.hasSink()) {
      this.finish(key, frame, { status: "refused" });
      return;
    }
    const matches = frame.from && frame.replyToken ? records.filter(
      (record) => record.ipcPath === frame.from && record.ipcToken === frame.replyToken
    ) : [];
    const candidate = matches.length === 1 ? matches[0] : void 0;
    const source = candidate?.sessionId && candidate.sessionId.length <= 256 ? candidate : void 0;
    const sourceSession = source && (source.kind ?? "tui") === "tui" ? {
      id: qwenPeerHandleId(this.qwenHome, source),
      adaptor: this.options.adaptor,
      instructionOnly: true
    } : void 0;
    const context = payload.correlation ? this.contexts.get(payload.correlation) : void 0;
    const knownDifferentTerminal = context?.adaptor === this.options.adaptor && context.id.startsWith("qwen-peer:") && source !== void 0 && context.id !== sourceSession?.id;
    const sourceLabel = peerReportLabel(source?.name ?? frame.fromName ?? "");
    const report = {
      id: key,
      callId: this.options.callId,
      source: sourceLabel || "Unknown peer",
      ...!sourceLabel ? { sourceIsFallback: true } : {},
      sourceStatus: source ? "matched" : "unconfirmed",
      ...sourceSession ? { sourceSession } : {},
      ...source ? { sourceSessionId: source.sessionId } : {},
      ...context && !knownDifferentTerminal ? { correlationId: payload.correlation } : {},
      category: payload.category,
      text: payload.text,
      receivedAt: this.timestamp()
    };
    let decision;
    this.admitting.add(key);
    try {
      decision = this.options.onReport(report) === true ? { status: "delivered" } : { status: "dropped", dropReason: "queue-full" };
    } catch {
      decision = { status: "refused" };
    }
    this.finish(key, frame, decision);
  }
  finish(key, frame, decision) {
    this.pending.delete(key);
    this.admitting.delete(key);
    this.recent.set(key, decision);
    while (this.recent.size > MAX_RECENT_REPORTS) {
      const oldest = this.recent.keys().next().value;
      if (oldest === void 0) break;
      this.recent.delete(oldest);
    }
    this.reply(frame, decision);
  }
  reply(frame, decision) {
    if (!frame.from || !isLocalIpcPath(frame.from) || this.receiptWrites.size >= MAX_RECEIPT_WRITES)
      return;
    const write = Promise.resolve().then(
      () => this.sendFrame(
        frame.from,
        buildDeliveryStatusFrame({
          origMsgId: frame.msgId,
          from: this.inbox?.socketPath,
          ...decision
        }),
        frame.replyToken !== void 0 ? { authToken: frame.replyToken } : {}
      )
    ).catch(() => {
    }).finally(() => this.receiptWrites.delete(write));
    this.receiptWrites.add(write);
  }
};

// src/adaptor/qwen-peer-discovery.ts
var QwenPeerDiscovery = class {
  constructor(options, adaptor, open2 = (options2) => PeerEndpoint.start(options2), controllerDependencies = {}) {
    this.adaptor = adaptor;
    this.open = open2;
    this.controllerDependencies = controllerDependencies;
    this.qwenHome = resolveQwenHome(options.qwenHome);
    this.controllerToken = options.controllerToken;
    this.reportsEnabled = options.reports ?? false;
  }
  qwenHome;
  controllerToken;
  reportsEnabled;
  requestedCall;
  current;
  controller;
  listeners = /* @__PURE__ */ new Set();
  reportListeners = /* @__PURE__ */ new Set();
  tail = Promise.resolve();
  start(callId) {
    this.requestedCall = callId;
    return this.serialize(async () => {
      if (this.current?.callId === callId) return;
      await this.closeCurrent();
      if (this.requestedCall !== callId) return;
      this.controller = void 0;
      this.notify();
      const owner = { ready: false };
      const endpoint = this.reportsEnabled ? await QwenPeerReports.start({
        qwenHome: this.qwenHome,
        adaptor: this.adaptor,
        callId,
        isActive: () => owner.ready && this.current?.owner === owner && this.requestedCall === callId,
        hasSink: () => this.reportListeners.size > 0,
        onReport: (report) => {
          const projected = report.sourceSession && this.controllerToken === void 0 ? {
            ...report,
            sourceSession: {
              ...report.sourceSession,
              readOnly: true
            }
          } : report;
          for (const listener of this.reportListeners) {
            if (listener(projected) === true) return true;
          }
          return false;
        }
      }) : (
        // Omitting onMessage makes the SDK refuse reports unless opted in.
        await this.open({
          name: `live-${this.adaptor}`,
          qwenHome: this.qwenHome
        })
      );
      this.current = { callId, endpoint, owner };
      if (this.requestedCall !== callId) {
        await this.closeCurrent();
        return;
      }
      if (this.controllerToken !== void 0) {
        const current = this.current;
        this.controller = new QwenPeerController(
          {
            qwenHome: this.qwenHome,
            adaptor: this.adaptor,
            name: endpoint.name ?? `live-${this.adaptor}`,
            controllerToken: this.controllerToken,
            isActive: () => this.current === current && this.requestedCall === callId,
            onChange: () => this.notify()
          },
          this.controllerDependencies
        );
        try {
          await this.controller.start();
        } catch {
          await this.closeCurrent();
          throw new Error(
            "Terminal instruction delivery could not be started. Check the controller configuration."
          );
        }
        if (this.requestedCall !== callId) await this.closeCurrent();
      }
      owner.ready = this.current?.owner === owner && this.requestedCall === callId;
    });
  }
  stop(callId) {
    if (this.requestedCall === callId) this.requestedCall = void 0;
    return this.serialize(async () => {
      if (this.current?.callId === callId) await this.closeCurrent();
    });
  }
  close() {
    this.requestedCall = void 0;
    return this.serialize(() => this.closeCurrent());
  }
  send(handle, text) {
    if (!this.controller) {
      return Promise.resolve({
        status: "rejected",
        note: "Terminal instructions require a configured controller token and an active voice call."
      });
    }
    return this.controller.send(handle, text);
  }
  deliveries() {
    return this.controller?.deliveries() ?? [];
  }
  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  subscribeReports(listener) {
    this.reportListeners.add(listener);
    return () => this.reportListeners.delete(listener);
  }
  createReportContext(target) {
    const current = this.current;
    if (!current || current.callId !== this.requestedCall) return void 0;
    return current.endpoint.createReportContext?.(target);
  }
  async list() {
    const current = this.current;
    if (!current || this.requestedCall !== current.callId) return [];
    const peers = await current.endpoint.list();
    if (this.current !== current || this.requestedCall !== current.callId)
      return [];
    const sessions = /* @__PURE__ */ new Map();
    for (const peer of peers) {
      if (peer.kind !== "tui" || !peer.sessionId || peer.sessionId.length > 256)
        continue;
      const id = qwenPeerHandleId(this.qwenHome, peer);
      sessions.set(id, {
        handle: {
          id,
          adaptor: this.adaptor,
          instructionOnly: true,
          ...this.controllerToken === void 0 ? { readOnly: true } : {}
        },
        label: peerReportLabel(peer.address),
        cwd: peerReportLabel(peer.cwd, 4096),
        state: "unknown",
        discovery: {
          source: "terminal",
          sessionId: peer.sessionId,
          address: peerReportLabel(peer.address)
        }
      });
    }
    return [...sessions.values()];
  }
  serialize(action) {
    const operation = this.tail.then(action);
    this.tail = operation.catch(() => {
    });
    return operation;
  }
  async closeCurrent() {
    const current = this.current;
    if (!current) return;
    await this.controller?.close();
    await current.endpoint.close();
    if (this.current === current) this.current = void 0;
  }
  notify() {
    for (const listener of this.listeners) {
      try {
        listener();
      } catch {
      }
    }
  }
};

// src/adaptor/qwen-code-adaptor.ts
var ADAPTOR_NAME = "qwen-code";
var REQUIRED_FEATURES = [
  "session_create",
  "session_prompt",
  "session_events",
  "session_cancel",
  "session_permission_vote",
  "session_mid_turn_message_mutation"
];
var MAX_SUMMARY_CHARS = 4e3;
var MAX_DETAIL_CHARS2 = 48e3;
function isRecord3(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function classifyOption2(optionId, name, wireKind) {
  if (wireKind !== void 0)
    return classifyOption(optionId, name, wireKind);
  const haystack = `${optionId} ${name ?? ""}`.toLowerCase().replace(/[_-]/g, " ");
  if (/\b(always|all|project|workspace|session|user|never|not)\b/.test(haystack))
    return { kind: "other" };
  if (["proceed_once", "allow_once"].includes(optionId))
    return { kind: "proceed", escalation: "once" };
  if (["reject_once", "deny_once", "cancel", "deny", "reject"].includes(optionId))
    return { kind: "reject", escalation: "once" };
  return { kind: "other" };
}
function pickLeastEscalating(options, wanted) {
  const rank = (option) => option.escalation === "once" ? 0 : option.escalation === void 0 ? 1 : 2;
  let best;
  for (const candidate of options) {
    if (candidate.kind !== wanted) continue;
    if (wanted === "proceed" && candidate.escalation === "always") continue;
    if (best === void 0 || rank(candidate) < rank(best)) best = candidate;
  }
  return best;
}
function pickPersistentGrant(options, wanted) {
  return options.find(
    (option) => option.kind === wanted && option.escalation === "always"
  );
}
function tailSlice(text, max) {
  let start = text.length - max;
  const unit = text.charCodeAt(start);
  if (unit >= 56320 && unit <= 57343) start += 1;
  return text.slice(start);
}
function clampTail(text, max) {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `\u2026${tailSlice(trimmed, max)}`;
}
function sanitizeTitleLine2(title) {
  const firstLine = title.split(/\r?\n/, 1)[0] ?? "";
  return firstLine.replace(/\x1b\][\s\S]*?(?:\x07|\x1b\\)/g, "").replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, "").replace(/\x1b[NOP]/g, "").replace(/[\x00-\x1f\x7f-\x9f]/g, " ").trim();
}
var QwenCodeAdaptor = class {
  name;
  client;
  managedServe;
  endpoint;
  closed = false;
  options;
  sessions = /* @__PURE__ */ new Map();
  /** Every cwd sessions were created in; listSessions unions across them. */
  sessionCwds = /* @__PURE__ */ new Set();
  workspaceCwd;
  peers;
  listDiscoveredSessions;
  sendInstruction;
  listInstructionDeliveries;
  subscribeInstructionDeliveries;
  createReportContext;
  subscribeReports;
  constructor(options) {
    this.options = options;
    this.endpoint = options.baseUrl;
    if (options.managedServe) {
      this.managedServe = new ManagedQwenServe({
        command: options.managedServe.command,
        cwd: options.defaultCwd
      });
    }
    this.name = options.name ?? ADAPTOR_NAME;
    if (options.peerDiscovery) {
      this.peers = new QwenPeerDiscovery(
        options.peerDiscovery,
        this.name,
        options.peerEndpointFactory
      );
      const peers = this.peers;
      this.listDiscoveredSessions = () => peers.list();
      this.sendInstruction = (handle, text) => peers.send(handle, text);
      this.listInstructionDeliveries = () => peers.deliveries();
      this.subscribeInstructionDeliveries = (listener) => peers.subscribe(listener);
      if (options.peerDiscovery.reports) {
        this.createReportContext = (target) => peers.createReportContext(target);
        this.subscribeReports = (listener) => peers.subscribeReports(listener);
      }
    }
    this.client = options.client ?? new jn({
      baseUrl: options.baseUrl,
      ...options.token ? { token: options.token } : {}
    });
  }
  capabilities() {
    return {
      steering: "native",
      imageInput: true,
      permissionForwarding: true,
      // Session-to-session messaging (proactive speak) is milestone M3.
      proactiveSpeak: false,
      sessionList: true,
      eventDelivery: "stream"
    };
  }
  async preflight() {
    try {
      if (this.closed) throw new Error("Qwen Code adaptor is closed.");
      if (this.managedServe) {
        const endpoint = await this.managedServe.start();
        this.endpoint = endpoint.baseUrl;
        this.client = new jn(endpoint);
      }
      if (this.closed) throw new Error("Qwen Code adaptor is closed.");
      await this.checkCapabilities();
      if (this.closed) throw new Error("Qwen Code adaptor is closed.");
    } catch (error) {
      await this.managedServe?.close();
      throw error;
    }
  }
  async checkCapabilities() {
    let caps;
    try {
      caps = await this.client.capabilities();
    } catch (error) {
      const detail = this.managedServe ? "The managed service did not complete its capability check" : error instanceof Error ? error.message : String(error);
      const status = isRecord3(error) && typeof error["status"] === "number" ? error["status"] : void 0;
      if (status !== void 0) {
        throw new Error(
          `qwen serve at ${this.endpoint} responded with HTTP ${status} and refused the request: ${detail}. Check the auth token and base URL.`
        );
      }
      throw new Error(
        `qwen serve is not reachable at ${this.endpoint}: ${detail}. ` + (this.managedServe ? "Check the installed Qwen Code version and configuration." : "Start it with `qwen serve` before launching qwen-live-harness.")
      );
    }
    const features = new Set(caps.features ?? []);
    const missing = REQUIRED_FEATURES.filter((f) => !features.has(f));
    if (missing.length > 0) {
      throw new Error(
        `qwen serve at ${this.endpoint} is missing required capabilities: ${missing.join(", ")}. Upgrade qwen-code.`
      );
    }
    this.workspaceCwd = caps.workspaceCwd;
  }
  async createSession(opts) {
    const cwd = opts?.cwd ?? this.options.defaultCwd ?? this.workspaceCwd;
    const session = await this.client.createOrAttachSession(
      {
        ...cwd !== void 0 ? { workspaceCwd: cwd } : {},
        sessionScope: "thread",
        sourceType: "qwen-live-harness"
      },
      this.options.clientId
    );
    if (cwd !== void 0) this.sessionCwds.add(cwd);
    const state = this.trackSession(session.sessionId, {
      busy: session.hasActivePrompt === true,
      ...cwd ? { cwd } : {},
      // The daemon issues the authoritative per-client id on create/attach;
      // every later call for this session must echo it (a self-made id is
      // rejected by the daemon's client registration guard). Older daemons
      // omit it — those calls stay anonymous.
      ...typeof session.clientId === "string" ? { clientId: session.clientId } : {}
    });
    if (opts?.label !== void 0) {
      await this.client.updateSessionMetadata(
        session.sessionId,
        { displayName: opts.label },
        state.clientId
      );
    }
    return { id: session.sessionId, adaptor: this.name };
  }
  async startDiscovery(callId) {
    await this.peers?.start(callId);
  }
  async stopDiscovery(callId) {
    await this.peers?.stop(callId);
  }
  async listSessions() {
    if (!this.listDiscoveredSessions) return this.listManagedSessions();
    const [managed, peers] = await Promise.allSettled([
      this.listManagedSessions(),
      this.listDiscoveredSessions()
    ]);
    if (managed.status === "rejected" && peers.status === "rejected") {
      throw new AggregateError(
        [managed.reason, peers.reason],
        "Could not list Qwen managed or terminal sessions"
      );
    }
    return [
      ...managed.status === "fulfilled" ? managed.value : [],
      ...peers.status === "fulfilled" ? peers.value : []
    ];
  }
  async listManagedSessions() {
    const defaultCwd = this.options.defaultCwd ?? this.workspaceCwd;
    const cwds = /* @__PURE__ */ new Set();
    if (defaultCwd !== void 0) cwds.add(defaultCwd);
    for (const cwd of this.sessionCwds) cwds.add(cwd);
    const summaries = /* @__PURE__ */ new Map();
    for (const cwd of cwds) {
      const sessions = await this.client.listWorkspaceSessions(cwd, {
        pageSize: 1e3
      });
      for (const raw of sessions) {
        const sessionId = raw["sessionId"];
        if (typeof sessionId !== "string" || summaries.has(sessionId)) {
          continue;
        }
        const tracked = this.sessions.get(sessionId);
        const label = raw["displayName"];
        const hasActivePrompt = raw["hasActivePrompt"];
        summaries.set(sessionId, {
          handle: { id: sessionId, adaptor: this.name },
          ...typeof label === "string" ? { label } : {},
          cwd,
          state: tracked ? tracked.closed ? "closed" : tracked.busy ? "busy" : "idle" : (
            // Untracked (e.g. after a qwen-live-harness restart): the wire record
            // itself says whether a prompt is running.
            typeof hasActivePrompt === "boolean" ? hasActivePrompt ? "busy" : "idle" : "unknown"
          )
        });
      }
    }
    return [...summaries.values()];
  }
  async prompt(handle, blocks, opts) {
    if (this.isDiscoveryHandle(handle)) {
      return {
        status: "rejected",
        note: "Terminal instructions use the text delivery channel; managed prompts are unavailable."
      };
    }
    const state = this.trackSession(handle.id);
    if (opts?.steer && state.busy) {
      const hasImages = blocks.some((block) => block.type === "image");
      if (!hasImages) {
        const message = blocks.filter(
          (block) => block.type === "text"
        ).map((block) => block.text).join("\n\n");
        let steered;
        try {
          steered = await this.client.enqueueMidTurnMessage(
            handle.id,
            message,
            state.clientId !== void 0 ? { clientId: state.clientId } : {}
          );
        } catch (error) {
          if (!(isRecord3(error) && error["status"] === 400)) throw error;
        }
        if (steered?.accepted) {
          return {
            status: "accepted",
            joinedActiveTurn: true,
            ...steered.messageId ? { joinedMessageId: steered.messageId } : {},
            ...!steered.messageId && state.activeJobRef !== void 0 ? { jobRef: state.activeJobRef } : {},
            note: "joined the currently running task"
          };
        }
      }
    }
    const prompt = await this.buildPromptBlocks(handle.id, blocks);
    let accepted;
    try {
      accepted = await this.client.promptNonBlocking(
        handle.id,
        { prompt },
        void 0,
        state.clientId
      );
    } catch (error) {
      if (isRecord3(error) && (error["status"] === 503 || error["name"] === "DaemonPendingPromptLimitError")) {
        return {
          status: "rejected",
          note: "the session is busy and its queue is full; wait or stop the current task first"
        };
      }
      throw error;
    }
    const promptId = accepted["promptId"];
    const jobRef = typeof promptId === "string" ? promptId : void 0;
    const wasBusy = state.busy;
    state.busy = true;
    if (!wasBusy && jobRef !== void 0) state.activeJobRef = jobRef;
    return {
      status: opts?.steer ? "queued" : "accepted",
      ...jobRef !== void 0 ? { jobRef } : {},
      ...opts?.steer ? { note: "queued as the next task in that session" } : {}
    };
  }
  async *events(handle, opts) {
    if (this.isDiscoveryHandle(handle)) return;
    const state = this.trackSession(handle.id);
    const stream = this.client.subscribeEvents(handle.id, {
      ...opts?.signal ? { signal: opts.signal } : {},
      ...state.clientId !== void 0 ? { clientId: state.clientId } : {}
    });
    for await (const envelope of stream) {
      const events = this.normalize(state, envelope);
      for (const event of events) {
        yield event;
        if (event.type === "session_closed") return;
      }
    }
  }
  isBusy(handle) {
    if (this.isDiscoveryHandle(handle)) return false;
    return this.sessions.get(handle.id)?.busy === true;
  }
  async cancel(handle) {
    if (this.isDiscoveryHandle(handle))
      throw new Error(
        "This terminal session is read-only; stopping is not supported."
      );
    await this.client.cancel(handle.id, this.sessions.get(handle.id)?.clientId);
  }
  async cancelJob(handle, jobRef) {
    if (this.isDiscoveryHandle(handle)) return "not_found";
    const state = this.sessions.get(handle.id);
    if (handle.adaptor !== this.name || !state || state.closed)
      return "not_found";
    const result = await this.client.removePendingPrompt(handle.id, jobRef, {
      ...state.clientId ? { clientId: state.clientId } : {}
    });
    return result.removed ? "stopping" : "not_found";
  }
  async respondPermission(handle, requestId, decision) {
    if (this.isDiscoveryHandle(handle))
      throw new Error(
        "This terminal session is read-only; permission forwarding is not supported."
      );
    const state = this.trackSession(handle.id);
    const options = state.permissionOptions.get(requestId) ?? [];
    let response;
    if (decision === "cancel") {
      response = { outcome: { outcome: "cancelled" } };
    } else {
      const wanted = decision === "deny" ? "reject" : "proceed";
      const option = (decision === "allow_always" ? pickPersistentGrant(options, wanted) : void 0) ?? pickLeastEscalating(options, wanted);
      response = option ? { outcome: { outcome: "selected", optionId: option.optionId } } : { outcome: { outcome: "cancelled" } };
    }
    state.ownVotes.add(requestId);
    let delivered;
    try {
      delivered = await this.client.respondToSessionPermission(
        handle.id,
        requestId,
        response,
        state.clientId
      );
    } catch (error) {
      state.ownVotes.delete(requestId);
      throw error;
    }
    if (delivered) {
      state.permissionOptions.delete(requestId);
    } else {
      state.ownVotes.delete(requestId);
    }
    return delivered ? "delivered" : "already_resolved";
  }
  async close() {
    this.closed = true;
    try {
      await this.peers?.close();
    } finally {
      await this.managedServe?.close();
      this.sessions.clear();
    }
  }
  // -- internals -----------------------------------------------------------
  localSessionCwd(state) {
    try {
      const host = new URL(this.options.baseUrl).hostname;
      return ["localhost", "127.0.0.1", "[::1]"].includes(host) ? state.cwd : void 0;
    } catch {
      return;
    }
  }
  isDiscoveryHandle(handle) {
    return handle.readOnly === true || handle.instructionOnly === true || handle.id.startsWith("qwen-peer:");
  }
  trackSession(sessionId, seed) {
    let state = this.sessions.get(sessionId);
    if (!state) {
      state = {
        busy: seed?.busy ?? false,
        turnBuffer: "",
        permissionOptions: /* @__PURE__ */ new Map(),
        ownVotes: /* @__PURE__ */ new Set(),
        closed: false
      };
      this.sessions.set(sessionId, state);
    } else if (seed?.busy !== void 0) {
      state.busy = seed.busy;
    }
    if (seed?.clientId !== void 0) state.clientId = seed.clientId;
    if (seed?.cwd !== void 0) state.cwd = seed.cwd;
    return state;
  }
  async buildPromptBlocks(sessionId, blocks) {
    const prompt = [];
    for (const block of blocks) {
      if (block.type === "text") {
        prompt.push({ type: "text", text: block.text });
        continue;
      }
      const reference = await this.client.uploadSessionAttachment(
        sessionId,
        new Blob([new Uint8Array(block.data)], { type: block.mimeType }),
        block.name ?? "attachment",
        block.mimeType
      );
      prompt.push(reference);
    }
    return prompt;
  }
  normalize(state, envelope) {
    const data = isRecord3(envelope.data) ? envelope.data : {};
    switch (envelope.type) {
      case "mid_turn_message_injected": {
        const jobRef = envelope.promptId;
        if (!jobRef || !Array.isArray(data["messageIds"])) return [];
        if (state.activeJobRef === void 0) {
          state.activeJobRef = jobRef;
          state.busy = true;
          state.turnBuffer = "";
        }
        return data["messageIds"].flatMap(
          (messageId) => typeof messageId === "string" && messageId ? [
            {
              type: "turn_joined",
              messageId,
              jobRef
            }
          ] : []
        );
      }
      case "pending_prompt_started": {
        state.busy = true;
        state.turnBuffer = "";
        const jobRef = envelope.promptId ?? state.activeJobRef;
        if (jobRef !== void 0) state.activeJobRef = jobRef;
        return [
          { type: "turn_started", ...jobRef !== void 0 ? { jobRef } : {} }
        ];
      }
      case "session_update": {
        const update = isRecord3(data["update"]) ? data["update"] : void 0;
        if (!update) return [];
        if (state.activeJobRef === void 0 && envelope.promptId !== void 0) {
          state.activeJobRef = envelope.promptId;
          state.busy = true;
          state.turnBuffer = "";
        }
        const kind = update["sessionUpdate"];
        const activity = publicActivity(
          update,
          envelope.promptId ?? state.activeJobRef,
          this.localSessionCwd(state)
        );
        if (kind === "agent_message_chunk") {
          const content = isRecord3(update["content"]) ? update["content"] : void 0;
          const text = content?.["text"];
          if (typeof text === "string" && (envelope.promptId === void 0 || envelope.promptId === state.activeJobRef)) {
            state.turnBuffer = `${state.turnBuffer}${text}`;
            if (state.turnBuffer.length > MAX_DETAIL_CHARS2) {
              state.turnBuffer = tailSlice(state.turnBuffer, MAX_DETAIL_CHARS2);
            }
          }
          return activity ? [activity] : [];
        }
        if (kind === "tool_call") {
          const title = update["title"];
          const summary = typeof title === "string" ? sanitizeTitleLine2(title) : "";
          return [
            ...activity ? [activity] : [],
            {
              type: "progress",
              ...envelope.promptId !== void 0 ? { jobRef: envelope.promptId } : {},
              summary: summary || "running a tool"
            }
          ];
        }
        return activity ? [activity] : [];
      }
      case "turn_complete": {
        const jobRef = envelope.promptId ?? state.activeJobRef;
        const active = envelope.promptId === void 0 || jobRef === state.activeJobRef;
        const detail = active ? state.turnBuffer.trim() : "";
        if (active) {
          state.busy = false;
          state.activeJobRef = void 0;
          state.turnBuffer = "";
        }
        if (data["stopReason"] === "cancelled") {
          return [{ type: "turn_error", jobRef, error: "cancelled" }];
        }
        return [
          {
            type: "turn_complete",
            ...jobRef !== void 0 ? { jobRef } : {},
            summary: clampTail(detail, MAX_SUMMARY_CHARS),
            ...detail ? { detail } : {}
          }
        ];
      }
      case "turn_error":
      case "prompt_cancelled": {
        const jobRef = envelope.promptId ?? state.activeJobRef;
        if (envelope.promptId === void 0 || jobRef === state.activeJobRef) {
          state.busy = false;
          state.activeJobRef = void 0;
          state.turnBuffer = "";
        }
        const message = data["message"] ?? data["error"];
        return [
          {
            type: "turn_error",
            ...jobRef !== void 0 ? { jobRef } : {},
            error: envelope.type === "prompt_cancelled" ? "cancelled" : typeof message === "string" ? message : "the task failed"
          }
        ];
      }
      case "permission_request": {
        const requestId = data["requestId"];
        if (typeof requestId !== "string") return [];
        const jobRef = envelope.promptId ?? state.activeJobRef;
        const rawOptions = Array.isArray(data["options"]) ? data["options"] : [];
        const options = rawOptions.flatMap((raw) => {
          if (!isRecord3(raw) || typeof raw["optionId"] !== "string") return [];
          const name = typeof raw["name"] === "string" ? raw["name"] : void 0;
          const wireKind = typeof raw["kind"] === "string" ? raw["kind"] : void 0;
          const classified = classifyOption2(raw["optionId"], name, wireKind);
          const persistentScope = describePersistentScope(name, wireKind);
          return [
            {
              optionId: raw["optionId"],
              ...name !== void 0 ? { label: name } : {},
              kind: classified.kind,
              ...classified.escalation !== void 0 ? { escalation: classified.escalation } : {},
              ...persistentScope ? { persistentScope } : {}
            }
          ];
        });
        state.permissionOptions.set(requestId, options);
        return [
          {
            type: "permission_request",
            ...jobRef !== void 0 ? { jobRef } : {},
            requestId,
            title: describeToolCall(data["toolCall"]),
            details: describePermissionDetails(
              data["toolCall"],
              this.localSessionCwd(state)
            ),
            options,
            payload: data
          }
        ];
      }
      case "permission_resolved":
      case "permission_already_resolved": {
        const requestId = data["requestId"];
        if (typeof requestId !== "string") return [];
        state.permissionOptions.delete(requestId);
        const votedByUs = state.ownVotes.delete(requestId);
        return [
          {
            type: "permission_resolved",
            requestId,
            byUs: envelope.originatorClientId !== void 0 ? state.clientId !== void 0 && envelope.originatorClientId === state.clientId : votedByUs
          }
        ];
      }
      case "session_died":
      case "session_closed": {
        state.closed = true;
        state.busy = false;
        return [{ type: "session_closed" }];
      }
      default:
        return [];
    }
  }
};
export {
  QwenCodeAdaptor
};
/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
/**
 * @license
 * Copyright 2026 Qwen Team
 * SPDX-License-Identifier: Apache-2.0
 */
