const API = "/api/v1/admin/merchant";
const TK = "aegis_merchant_token";
const state = { token: localStorage.getItem(TK), tenant: null, page: "overview", stats: null, integration: null, conn: null, decisions: [], alerts: [], cases: [] };
const $ = s => document.querySelector(s);
const el = (t, a = {}, ...kids) => {
  const n = document.createElement(t);
  for (const [k, v] of Object.entries(a)) {
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const c of kids.flat()) if (c != null) n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return n;
};
const num = n => Number(n || 0).toLocaleString("ar-EG");
const dt = iso => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" }); };
function toast(m, t = "info") { const d = el("div", { class: "toast " + t }, m); document.body.appendChild(d); setTimeout(() => d.remove(), 3000); }

async function api(path, opts = {}) {
  const h = { "Content-Type": "application/json", "Authorization": "Bearer " + state.token, ...(opts.headers || {}) };
  const r = await fetch(API + path, { ...opts, headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || d.message || "خطأ");
  return d;
}
async function copy(txt, btn) {
  await navigator.clipboard.writeText(txt);
  if (btn) { const o = btn.textContent; btn.textContent = "✓"; setTimeout(() => btn.textContent = o, 1200); }
  toast("نُسخ", "success");
}

function renderLogin() {
  const key = el("input", { class: "form-control", type: "text", placeholder: "aeg_pk_...", dir: "ltr" });
  const sec = el("input", { class: "form-control", type: "password", placeholder: "aeg_sk_...", dir: "ltr" });
  const err = el("div", { style: "color:#FCA5A5;font-size:13px;margin-top:8px" });
  return el("div", { class: "login-wrap" },
    el("div", { class: "login-card" },
      el("div", { style: "font-size:4rem;text-align:center" }, "🏦"),
      el("h1", { style: "text-align:center;font-size:1.7rem;font-weight:900" }, "AEGIS Merchant"),
      el("p", { style: "text-align:center;color:var(--muted);font-size:13px;margin:8px 0 24px" }, "بوابة إدارة البنك / المحفظة / المؤسسة"),
      el("form", {
        onsubmit: async e => {
          e.preventDefault();
          try {
            const r = await fetch(API + "/login", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ api_key: key.value.trim(), api_secret: sec.value.trim() })
            });
            const j = await r.json();
            if (!r.ok) throw new Error(j.detail || "بيانات خاطئة");
            state.token = j.merchant_token; state.tenant = j.tenant;
            localStorage.setItem(TK, state.token);
            localStorage.setItem(TK + "_t", JSON.stringify(j.tenant));
            toast("مرحبا " + j.tenant.name, "success"); render();
          } catch (ex) { err.textContent = ex.message; }
        }
      },
        el("div", { style: "margin-bottom:12px" },
          el("label", { style: "font-size:13px;color:var(--muted);margin-bottom:6px;display:block" }, "🔑 API Key"), key),
        el("div", { style: "margin-bottom:12px" },
          el("label", { style: "font-size:13px;color:var(--muted);margin-bottom:6px;display:block" }, "🔐 API Secret (HMAC)"), sec),
        err,
        el("button", { class: "btn primary", style: "width:100%;padding:13px;margin-top:8px" }, "🔓 دخول")
      ),
      el("div", { style: "background:rgba(59,130,246,.08);padding:12px;border-radius:10px;margin-top:14px;font-size:11.5px;color:#93C5FD" },
        "احصل على مفاتيحك من مالك المنظومة عبر ",
        el("a", { href: "/admin/", target: "_blank", style: "color:#93C5FD;text-decoration:underline" }, "بوابة المالك"))
    )
  );
}

async function loadOverview() {
  [state.stats, state.conn] = await Promise.all([api("/stats"), api("/connection-status")]);
}
async function loadIntegration() {
  state.integration = await api("/integration");
  state.conn = await api("/connection-status");
}
async function loadDecisions() {
  state.decisions = await api("/decisions?limit=50");
}
async function loadAlerts() {
  state.alerts = await api("/alerts");
}
async function loadCases() {
  state.cases = await api("/cases");
}

function kpi(l, v, s) {
  return el("div", { class: "kpi" }, el("div", { class: "kpi-label" }, l), el("div", { class: "kpi-value" }, v),
    el("div", { style: "font-size:11.5px;color:var(--muted);margin-top:4px" }, s));
}
function row(l, v) {
  return el("div", { style: "display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border);font-size:13.5px" },
    el("span", { style: "color:var(--muted)" }, l), typeof v === "string" ? el("span", { style: "font-weight:700" }, v) : v);
}

function renderOverview() {
  if (!state.stats) return el("div", {}, "جارٍ التحميل…");
  const c = state.conn, s = state.stats, t = state.tenant;
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900" }, `مرحبا، ${t?.name || ""} 👋`),
    el("p", { style: "color:var(--muted);font-size:13.5px;margin-bottom:20px" }, "بوابة إدارة مؤسستك ضمن منظومة AEGIS"),
    el("div", { class: "card", style: "border-color:" + (c?.connected ? "rgba(16,185,129,.35)" : "rgba(239,68,68,.35)") },
      el("div", { style: "display:flex;gap:16px;align-items:center" },
        el("div", { style: "font-size:2.5rem" }, c?.connected ? "🟢" : "🔴"),
        el("div", { style: "flex:1" },
          el("h3", { style: "color:" + (c?.connected ? "var(--success)" : "var(--danger)") }, c?.connected ? "✅ متصل بنظام AEGIS" : "❌ منقطع"),
          el("p", { style: "color:var(--muted);font-size:13px;margin-top:4px" }, "AEGIS Core: " + (c?.aegis_core || "?") + " · AI Agent: " + (c?.ai_agent || "?")),
          el("p", { style: "color:var(--muted);font-size:11px;margin-top:4px" }, "آخر فحص: " + (c ? dt(c.checked_at) : "?"))
        ),
        el("button", { class: "btn primary", onclick: async () => { await loadOverview(); render(); toast("تم التحديث", "success"); } }, "🔄")
      )
    ),
    el("div", { class: "grid" },
      kpi("📊 إجمالي المعاملات", num(s.total_decisions), "على مؤسستك"),
      kpi("✅ مسموحة", num(s.by_decision.allow), "آمنة"),
      kpi("🔐 تحقق", num(s.by_decision.challenge), "OTP"),
      kpi("⏳ مراجعة", num(s.by_decision.review), "معلّقة"),
      kpi("🛑 محظورة", num(s.by_decision.block), "احتيال"),
      kpi("⚠️ متوسط المخاطر", (s.avg_risk * 100).toFixed(1) + "%", "على معاملاتك")
    ),
    el("div", { class: "card" },
      el("h3", {}, "🏢 معلومات المؤسسة"),
      el("div", { style: "margin-top:12px" },
        row("🆔 tenant_id", el("code", {}, t?.tenant_id || "?")),
        row("🏷️ النوع", t?.type === "wallet" ? "💳 محفظة" : t?.type === "bank" ? "🏦 بنك" : t?.type),
        row("🌍 الدولة", t?.country || "?"),
        row("📦 الخطة", t?.plan || "?")
      )
    )
  );
}

function credRow(label, value, masked = false) {
  const codeEl = el("code", { style: "flex:1;color:var(--accent);word-break:break-all;font-size:11.5px" }, masked ? "•".repeat(28) : value);
  const btn = el("button", { class: "btn", style: "padding:5px 10px;font-size:11px" }, "📋");
  btn.onclick = () => copy(value, btn);
  const inner = [el("div", { style: "font-weight:700;color:var(--muted);min-width:120px" }, label), codeEl, btn];
  if (masked) {
    let shown = false;
    const tog = el("button", { class: "btn", style: "padding:5px 10px;font-size:11px" }, "👁");
    tog.onclick = () => { shown = !shown; codeEl.textContent = shown ? value : "•".repeat(28); tog.textContent = shown ? "🙈" : "👁"; };
    inner.push(tog);
  }
  return el("div", { class: "creds-row" }, ...inner);
}
function renderCodeTabs(samples) {
  const tabs = el("div", { style: "display:flex;gap:6px;margin-bottom:8px;border-bottom:1px solid var(--border)" });
  const pre = el("pre", { style: "white-space:pre-wrap;color:#E2E8F0;font-family:monospace;font-size:12px;line-height:1.7" });
  const copyBtn = el("button", { class: "btn", style: "position:absolute;top:10px;left:10px;padding:5px 10px;font-size:11px" }, "📋");
  const box = el("div", { class: "code-block", style: "position:relative" }, copyBtn, pre);
  const langs = [["curl", "🌀 cURL"], ["nodejs", "🟩 Node.js"], ["python", "🐍 Python"]];
  langs.forEach(([id, label], i) => {
    const t = el("button", {
      class: "btn", style: "background:transparent;color:var(--muted);border-bottom:2px solid " + (i === 0 ? "var(--accent)" : "transparent"),
      onclick: () => {
        tabs.querySelectorAll("button").forEach(b => b.style.borderBottomColor = "transparent");
        t.style.borderBottomColor = "var(--accent)";
        pre.textContent = samples[id];
        copyBtn.onclick = () => copy(samples[id], copyBtn);
      }
    }, label);
    tabs.appendChild(t);
  });
  pre.textContent = samples.curl;
  copyBtn.onclick = () => copy(samples.curl, copyBtn);
  return el("div", {}, tabs, box);
}

function renderIntegration() {
  if (!state.integration) return el("div", {}, "جارٍ التحميل…");
  const g = state.integration;
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:8px" }, "🔌 إعدادات الأمان والربط"),
    el("p", { style: "color:var(--muted);margin-bottom:20px" }, "بيانات ربط مؤسستك — احفظها في مكان آمن"),
    el("div", { class: "card" },
      el("h3", {}, "🔑 مفاتيح الربط (API Credentials)"),
      el("div", { class: "creds-box" },
        credRow("🆔 tenant_id", g.tenant_id),
        credRow("🌐 endpoint", g.endpoint),
        credRow("🔑 api_key", g.api_key),
        credRow("🔐 hmac_secret", g.hmac_secret, true)
      ),
      el("div", { style: "background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);padding:12px;border-radius:10px;margin-top:14px;font-size:12px;color:#FCD34D" },
        "⚠️ لا تشارك HMAC Secret مع أي طرف. إذا تسرّب اطلب من مالك المنظومة تدويره.")
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "📖 كود التكامل الجاهز"),
      renderCodeTabs(g.code_samples)
    )
  );
}

function renderDecisions() {
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:8px" }, "⚖️ قرارات معاملاتي"),
    el("p", { style: "color:var(--muted);margin-bottom:16px" }, "قرارات AEGIS على معاملات مؤسستك فقط"),
    el("div", { class: "card" },
      state.decisions.length === 0
        ? el("div", { style: "text-align:center;color:var(--muted);padding:40px" }, "لا توجد قرارات بعد")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "القرار"),
              el("th", {}, "المخاطر"), el("th", {}, "النمط"), el("th", {}, "التفسير"))),
            el("tbody", {}, ...state.decisions.map(d =>
              el("tr", {},
                el("td", { style: "font-size:11px" }, dt(d.ts || d.timestamp || d.created_at)),
                el("td", {}, el("code", { style: "font-size:11px" }, (d.tx_id || "").slice(0, 12))),
                el("td", {}, el("span", { class: "badge " + d.decision }, d.decision)),
                el("td", {}, ((d.risk_score || 0) * 100).toFixed(0) + "%"),
                el("td", { style: "font-size:11px" }, d.typology || "-"),
                el("td", { style: "font-size:11px;color:var(--muted);max-width:280px" }, (d.reasoning_ar || "").slice(0, 120))
              )))
          )
    )
  );
}

function renderAlerts() {
  const SEV = { critical: "حرجة", high: "عالية", medium: "متوسطة", low: "منخفضة" };
  const ST = { open: "مفتوح", assigned: "مُسنَد", in_review: "قيد المراجعة", escalated: "مُصعَّد",
    resolved_true_positive: "احتيال مؤكد", resolved_false_positive: "إنذار كاذب" };
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:8px" }, "🚨 تنبيهات مؤسستي"),
    el("p", { style: "color:var(--muted);margin-bottom:16px" }, "التنبيهات التي أنشأها AEGIS على معاملاتك — تُدار من منصة المحقق"),
    el("div", { class: "card" },
      state.alerts.length === 0
        ? el("div", { style: "text-align:center;color:var(--muted);padding:40px" }, "✅ لا توجد تنبيهات على معاملاتك")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "الخطورة"),
              el("th", {}, "العنوان"), el("th", {}, "الحالة"))),
            el("tbody", {}, ...state.alerts.map(a =>
              el("tr", {},
                el("td", { style: "font-size:11px" }, dt(a.created_at)),
                el("td", {}, el("code", { style: "font-size:11px" }, (a.alert_id || "").slice(0, 14))),
                el("td", {}, el("span", { class: "badge " + a.severity }, SEV[a.severity] || a.severity)),
                el("td", { style: "font-size:12px;max-width:280px" }, a.title || "-"),
                el("td", {}, el("span", { class: "badge " + a.status }, ST[a.status] || a.status))
              )))
          )
    )
  );
}

function renderCases() {
  const ST = { open: "مفتوح", in_progress: "قيد المعالجة", escalated: "مُصعَّد", closed: "مغلق" };
  const RES = { confirmed_fraud: "احتيال مؤكد", false_positive: "إنذار كاذب", inconclusive: "غير حاسم" };
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:8px" }, "📁 قضايا التحقيق"),
    el("p", { style: "color:var(--muted);margin-bottom:16px" }, "القضايا المرتبطة بمؤسستك ونتائج التحقيق فيها"),
    el("div", { class: "card" },
      state.cases.length === 0
        ? el("div", { style: "text-align:center;color:var(--muted);padding:40px" }, "لا توجد قضايا مرتبطة بمؤسستك")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "العنوان"),
              el("th", {}, "الأولوية"), el("th", {}, "الحالة"), el("th", {}, "النتيجة"))),
            el("tbody", {}, ...state.cases.map(c =>
              el("tr", {},
                el("td", { style: "font-size:11px" }, dt(c.created_at)),
                el("td", {}, el("code", { style: "font-size:11px" }, (c.case_id || "").slice(0, 14))),
                el("td", { style: "font-size:12px;max-width:240px" }, c.title || "-"),
                el("td", {}, el("span", { class: "badge " + c.priority }, c.priority)),
                el("td", {}, el("span", { class: "badge " + c.status }, ST[c.status] || c.status)),
                el("td", { style: "font-size:12px" }, c.resolution ? (RES[c.resolution] || c.resolution) : "—")
              )))
          )
    )
  );
}

async function renderPage() {
  const c = $("#content"); if (!c) return;
  c.innerHTML = "جارٍ التحميل…";
  try {
    if (state.page === "overview") { await loadOverview(); c.replaceChildren(renderOverview()); }
    else if (state.page === "integration") { await loadIntegration(); c.replaceChildren(renderIntegration()); }
    else if (state.page === "decisions") { await loadDecisions(); c.replaceChildren(renderDecisions()); }
    else if (state.page === "alerts") { await loadAlerts(); c.replaceChildren(renderAlerts()); }
    else if (state.page === "cases") { await loadCases(); c.replaceChildren(renderCases()); }
  } catch (e) {
    if (String(e.message).includes("401") || String(e.message).includes("merchant_auth")) {
      localStorage.removeItem(TK); state.token = null; render(); return;
    }
    c.textContent = "خطأ: " + e.message;
  }
}

function render() {
  const root = $("#app"); root.innerHTML = "";
  if (!state.token) { root.appendChild(renderLogin()); return; }
  if (!state.tenant) { try { state.tenant = JSON.parse(localStorage.getItem(TK + "_t") || "null"); } catch {} }
  const pages = [
    { id: "overview", icon: "📊", label: "نظرة عامة" },
    { id: "decisions", icon: "⚖️", label: "قرارات معاملاتي" },
    { id: "alerts", icon: "🚨", label: "التنبيهات" },
    { id: "cases", icon: "📁", label: "القضايا" },
    { id: "integration", icon: "🔌", label: "إعدادات الربط" }
  ];
  root.appendChild(el("div", { class: "layout" },
    el("header", { class: "top" },
      el("div", {}, el("span", { style: "font-size:1.7rem" }, "🏦 "), el("span", { class: "brand-title" }, "AEGIS Merchant Portal")),
      el("div", { style: "display:flex;gap:12px;align-items:center" },
        el("span", { style: "color:var(--muted);font-size:13px" }, state.tenant?.name || "?"),
        el("button", { class: "btn danger", onclick: () => { localStorage.removeItem(TK); localStorage.removeItem(TK + "_t"); state.token = null; render(); } }, "🚪 خروج"))
    ),
    el("aside", {},
      ...pages.map(p => el("div", {
        class: "nav" + (state.page === p.id ? " active" : ""),
        onclick: () => { state.page = p.id; render(); }
      }, el("span", {}, p.icon), el("span", {}, p.label)))
    ),
    el("main", { id: "content" })
  ));
  renderPage();
}
render();
