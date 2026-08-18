/* AEGIS Investigator Workbench — protected fraud investigation portal.
   Auth: JWT (role=investigator) via POST /api/v1/investigator/login.
   Modules: dashboard, review queue, alerts, cases, live decisions, graph. */
const API = "/api/v1/investigator";
const TK = "aegis_inv_token";
const INV = "aegis_inv_profile";

const state = {
  token: localStorage.getItem(TK),
  profile: JSON.parse(localStorage.getItem(INV) || "null"),
  page: "dashboard",
  stats: null,
  queue: [],
  alerts: [],
  cases: [],
  decisions: [],
  insights: null,
  alertDetail: null,
  caseDetail: null,
  selectedTx: null,
  filters: { alertStatus: "", alertSeverity: "", caseStatus: "" },
  live: false,
  es: null,
};

const $ = s => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(n.style, v);
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v);
  }
  for (const c of kids.flat(Infinity)) {
    if (c == null || c === false || c === true) continue;
    n.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
};

const num = n => Number(n || 0).toLocaleString("ar-EG");
const dt = iso => {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("ar-SA", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
};
const pct = v => ((v || 0) * 100).toFixed(0) + "%";

function toast(msg, type = "info") {
  const t = el("div", { class: "toast " + type }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

async function api(path, opts = {}) {
  const h = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (state.token) h["Authorization"] = "Bearer " + state.token;
  const r = await fetch(API + path, { ...opts, headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined });
  if (r.status === 401) { logout(); throw new Error("انتهت الجلسة — سجّل الدخول مجددًا"); }
  const txt = await r.text();
  let d = {};
  try { d = txt ? JSON.parse(txt) : {}; } catch { d = { raw: txt }; }
  if (!r.ok) throw new Error(d.detail || d.message || ("خطأ " + r.status));
  return d;
}

function logout() {
  localStorage.removeItem(TK); localStorage.removeItem(INV);
  state.token = null; state.profile = null;
  if (state.es) { state.es.close(); state.es = null; }
  render();
}

/* ═══════════════ LOGIN ═══════════════ */
function renderLogin() {
  const email = el("input", { class: "form-control", type: "email", placeholder: "investigator@aegis.local", dir: "ltr" });
  const pass = el("input", { class: "form-control", type: "password", placeholder: "••••••••" });
  const err = el("div", { style: "color:#FCA5A5;font-size:13px;margin-top:8px;min-height:18px" });
  const btn = el("button", { class: "btn primary", style: "width:100%;padding:13px;margin-top:14px" }, "🔓 دخول المحقق");
  const form = el("form", {
    onsubmit: async e => {
      e.preventDefault();
      btn.disabled = true; btn.textContent = "جارٍ التحقق…"; err.textContent = "";
      try {
        const r = await fetch(API + "/login", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.value.trim(), password: pass.value }),
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail === "invalid_credentials" ? "بيانات دخول غير صحيحة" : (d.detail || "خطأ"));
        state.token = d.access_token;
        state.profile = d.investigator;
        localStorage.setItem(TK, state.token);
        localStorage.setItem(INV, JSON.stringify(d.investigator));
        toast("مرحبًا " + d.investigator.name, "success");
        render();
      } catch (ex) { err.textContent = ex.message; }
      btn.disabled = false; btn.textContent = "🔓 دخول المحقق";
    }
  },
    el("label", { style: "font-size:13px;color:var(--muted);margin-bottom:8px;display:block" }, "📧 البريد الإلكتروني"),
    email,
    el("label", { style: "font-size:13px;color:var(--muted);margin:12px 0 8px;display:block" }, "🔑 كلمة المرور"),
    pass, err, btn,
  );
  return el("div", { class: "login-wrap" },
    el("div", { class: "login-card" },
      el("div", { style: "font-size:4rem;text-align:center" }, "🛡️"),
      el("h1", { style: "text-align:center;font-size:1.7rem;font-weight:900" }, "AEGIS Investigator"),
      el("p", { style: "text-align:center;color:var(--muted);font-size:13px;margin:8px 0 24px" }, "منصة التحقيق في الاحتيال المالي — وصول مقيّد"),
      form,
      el("div", { style: "background:rgba(59,130,246,.08);padding:12px;border-radius:10px;margin-top:14px;font-size:11.5px;color:#93C5FD" },
        "💡 يُنشئ مالك النظام حسابات المحققين من بوابة المالك ← تبويب المحققون."),
    )
  );
}

/* ═══════════════ DATA LOADERS ═══════════════ */
async function loadStats() { try { state.stats = await api("/stats"); } catch { state.stats = null; } }
async function loadQueue() { try { state.queue = await api("/queue?limit=200"); } catch { state.queue = []; } }
async function loadAlerts() {
  const p = new URLSearchParams();
  if (state.filters.alertStatus) p.set("status", state.filters.alertStatus);
  if (state.filters.alertSeverity) p.set("severity", state.filters.alertSeverity);
  try { state.alerts = await api("/alerts?" + p.toString()); } catch { state.alerts = []; }
}
async function loadCases() {
  const p = new URLSearchParams();
  if (state.filters.caseStatus) p.set("status", state.filters.caseStatus);
  try { state.cases = await api("/cases?" + p.toString()); } catch { state.cases = []; }
}
async function loadDecisions() { try { state.decisions = await api("/decisions/recent?limit=100"); } catch { state.decisions = []; } }
async function loadInsights() { try { state.insights = await api("/graph/insights"); } catch { state.insights = null; } }
async function loadAlertDetail(id) { state.alertDetail = await api("/alerts/" + id); }
async function loadCaseDetail(id) { state.caseDetail = await api("/cases/" + id); }

/* ═══════════════ LIVE STREAM (SSE) ═══════════════ */
function toggleLive() {
  if (state.es) {
    state.es.close(); state.es = null; state.live = false;
    toast("تم إيقاف البث المباشر"); render(); return;
  }
  const es = new EventSource(API + "/stream?token=" + encodeURIComponent(state.token));
  es.addEventListener("decision.created", async () => {
    if (["dashboard", "queue", "decisions"].includes(state.page)) {
      await Promise.all([loadStats(), loadQueue(), loadDecisions()]);
      renderPage();
    }
  });
  es.onopen = () => { state.live = true; render(); };
  es.onerror = () => { state.live = false; };
  state.es = es;
  toast("البث المباشر مفعّل", "success"); render();
}

/* ═══════════════ UI HELPERS ═══════════════ */
function kpi(label, value, sub, tone = "brand") {
  const colors = { brand: "#3B82F6", success: "#10B981", warn: "#F59E0B", danger: "#EF4444", info: "#06B6D4", purple: "#A855F7" };
  return el("div", { class: "kpi", style: `border-top:3px solid ${colors[tone] || colors.brand}` },
    el("div", { class: "kpi-label" }, label),
    el("div", { class: "kpi-value" }, value),
    sub ? el("div", { style: "font-size:11.5px;color:var(--muted);margin-top:4px" }, sub) : null);
}
function badge(cls, text) { return el("span", { class: "badge " + (cls || "low") }, text || "-"); }
function detail(lbl, val) {
  return el("div", { class: "detail-item" },
    el("div", { class: "lbl" }, lbl),
    el("div", { class: "val" }, val ?? "-"));
}
function scoreBar(v, color) {
  return el("div", { class: "score-bar" },
    el("div", { style: `width:${Math.round((v || 0) * 100)}%;background:${color}` }));
}
const SEV_AR = { critical: "حرجة", high: "عالية", medium: "متوسطة", low: "منخفضة" };
const ST_AR = {
  open: "مفتوح", assigned: "مُسنَد", in_review: "قيد المراجعة", in_progress: "قيد المعالجة",
  escalated: "مُصعَّد", resolved_true_positive: "احتيال مؤكد", resolved_false_positive: "إنذار كاذب",
  closed: "مغلق", confirmed_fraud: "احتيال مؤكد", false_positive: "إنذار كاذب", inconclusive: "غير حاسم",
};
const DEC_AR = { allow: "سماح", challenge: "تحقق", review: "مراجعة", block: "حظر" };

/* ═══════════════ PAGE: DASHBOARD ═══════════════ */
function renderDashboard() {
  const s = state.stats || {};
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "📊 لوحة المحقق"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:18px" },
      "مرحبًا " + (state.profile?.name || "") + " — نظرة عامة على عبء العمل"),
    el("div", { class: "grid" },
      kpi("⏳ بانتظار المراجعة", num(s.review_pending), "قرارات review", "warn"),
      kpi("🚨 تنبيهات مفتوحة", num(s.open_alerts), "كل التنبيهات النشطة", "danger"),
      kpi("📌 تنبيهاتي", num(s.my_alerts), "المُسنَدة إليّ", "info"),
      kpi("📁 قضايا مفتوحة", num(s.open_cases), "كل القضايا", "purple"),
      kpi("🗂️ قضاياي", num(s.my_cases), "المُسنَدة إليّ", "brand"),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "⚡ إجراءات سريعة"),
      el("div", { style: "display:flex;gap:10px;flex-wrap:wrap" },
        el("button", { class: "btn primary", onclick: () => { state.page = "queue"; render(); } }, "⏳ فتح قائمة المراجعة"),
        el("button", { class: "btn", onclick: () => { state.page = "alerts"; render(); } }, "🚨 التنبيهات"),
        el("button", { class: "btn", onclick: () => { state.page = "cases"; render(); } }, "📁 القضايا"),
        el("button", { class: "btn", onclick: () => { state.page = "graph"; render(); } }, "🕸️ تحليل الشبكة"),
      )),
  );
}

/* ═══════════════ PAGE: REVIEW QUEUE ═══════════════ */
function renderQueue() {
  const rows = (state.queue || []).map(q => el("tr", { class: "clickable", onclick: () => openAlertFromQueue(q) },
    el("td", { style: "font-size:11px;white-space:nowrap" }, dt(q.ts)),
    el("td", {}, el("code", { style: "font-size:11px" }, (q.tx_id || "").slice(0, 14))),
    el("td", { style: "font-weight:700" }, num(q.amount) + " " + (q.currency || "")),
    el("td", { style: "font-size:12px" }, q.sender_account_id || "-"),
    el("td", { style: "font-size:12px" }, q.beneficiary_account_id || "-"),
    el("td", {}, scoreBar(q.risk_score, q.risk_score >= 0.8 ? "var(--danger)" : q.risk_score >= 0.6 ? "var(--warn)" : "var(--brand)")),
    el("td", { style: "font-weight:700" }, pct(q.risk_score)),
    el("td", {}, q.alert_status ? badge(q.alert_status, ST_AR[q.alert_status] || q.alert_status) : el("span", { style: "color:var(--muted);font-size:11px" }, "بدون تنبيه")),
    el("td", { style: "font-size:11px;color:var(--muted);max-width:220px" }, (q.reasoning_ar || "").slice(0, 90)),
  ));
  return el("div", {},
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px" },
      el("div", {},
        el("h1", { style: "font-size:1.7rem;font-weight:900" }, "⏳ قائمة المراجعة"),
        el("p", { style: "color:var(--muted);font-size:13px;margin-top:4px" }, "قرارات «مراجعة» بانتظار محقق — اضغط على صف لفتح التنبيه المرتبط"),
      ),
      el("button", { class: "btn primary", onclick: async () => { await loadQueue(); renderPage(); toast("تم التحديث", "success"); } }, "🔄 تحديث"),
    ),
    el("div", { class: "card" },
      rows.length === 0
        ? el("div", { style: "color:var(--muted);text-align:center;padding:40px" }, "✅ لا توجد قرارات بانتظار المراجعة — قائمة نظيفة.")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعاملة"), el("th", {}, "المبلغ"),
              el("th", {}, "المرسل"), el("th", {}, "المستفيد"), el("th", {}, ""),
              el("th", {}, "المخاطر"), el("th", {}, "التنبيه"), el("th", {}, "التفسير"))),
            el("tbody", {}, ...rows))),
  );
}
async function openAlertFromQueue(q) {
  try {
    if (q.alert_id) {
      await loadAlertDetail(q.alert_id);
      state.page = "alertDetail";
    } else {
      state.selectedTx = q.tx_id;
      state.alertDetail = null;
      state.page = "txDetail";
    }
    render();
  } catch (e) { toast(e.message, "error"); }
}

/* ═══════════════ PAGE: ALERTS ═══════════════ */
function renderAlerts() {
  const f = state.filters;
  const mk = (val, opts, onch) => el("select", { onchange: e => { onch(e.target.value); loadAlerts().then(renderPage); } },
    ...opts.map(o => el("option", { value: o[0], ...(val === o[0] ? { selected: "" } : {}) }, o[1])));
  const rows = (state.alerts || []).map(a => el("tr", { class: "clickable", onclick: async () => { await loadAlertDetail(a.alert_id); state.page = "alertDetail"; render(); } },
    el("td", { style: "font-size:11px;white-space:nowrap" }, dt(a.created_at)),
    el("td", {}, el("code", { style: "font-size:11px" }, a.alert_id.slice(0, 14))),
    el("td", {}, badge(a.severity, SEV_AR[a.severity] || a.severity)),
    el("td", { style: "font-size:12px;max-width:260px" }, a.title || "-"),
    el("td", {}, badge(a.status, ST_AR[a.status] || a.status)),
    el("td", { style: "font-size:12px" }, a.assignee || "—"),
  ));
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🚨 التنبيهات"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:14px" }, "دورة حياة كاملة: إسناد → مراجعة → تصعيد → حل"),
    el("div", { class: "filters" },
      mk(f.alertStatus, [["", "كل الحالات"], ["open", "مفتوح"], ["assigned", "مُسنَد"], ["in_review", "قيد المراجعة"], ["escalated", "مُصعَّد"], ["resolved_true_positive", "احتيال مؤكد"], ["resolved_false_positive", "إنذار كاذب"]], v => f.alertStatus = v),
      mk(f.alertSeverity, [["", "كل الخطورات"], ["critical", "حرجة"], ["high", "عالية"], ["medium", "متوسطة"], ["low", "منخفضة"]], v => f.alertSeverity = v),
      el("button", { class: "btn sm", onclick: async () => { state.filters.assignee = "me"; state.alerts = await api("/alerts?assignee=me"); renderPage(); } }, "📌 المُسنَدة إليّ"),
      el("button", { class: "btn sm", onclick: async () => { state.filters.alertStatus = ""; state.filters.alertSeverity = ""; await loadAlerts(); renderPage(); } }, "✕ مسح"),
    ),
    el("div", { class: "card" },
      rows.length === 0
        ? el("div", { style: "color:var(--muted);text-align:center;padding:30px" }, "لا توجد تنبيهات مطابقة.")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "الخطورة"),
              el("th", {}, "العنوان"), el("th", {}, "الحالة"), el("th", {}, "المُسنَد إليه"))),
            el("tbody", {}, ...rows))),
  );
}

/* ═══════════════ PAGE: ALERT DETAIL ═══════════════ */
function renderAlertDetail() {
  const d = state.alertDetail;
  if (!d || !d.alert) return el("div", { style: "color:var(--muted);padding:40px;text-align:center" }, "جارٍ التحميل…");
  const a = d.alert, tx = d.transaction, dec = d.decision;
  const resolved = (a.status || "").startsWith("resolved");
  const noteI = el("textarea", { class: "form-control", rows: "2", placeholder: "أضف ملاحظة تحقيق…" });
  const act = (label, cls, fn, confirmMsg) => el("button", {
    class: "btn " + cls,
    onclick: async () => {
      if (confirmMsg && !confirm(confirmMsg)) return;
      try { await fn(); await loadAlertDetail(a.alert_id); toast("تم", "success"); render(); }
      catch (e) { toast(e.message, "error"); }
    }
  }, label);

  return el("div", {},
    el("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:14px" },
      el("button", { class: "btn sm", onclick: () => { state.page = "alerts"; render(); } }, "→ رجوع"),
      el("h1", { style: "font-size:1.5rem;font-weight:900" }, "🚨 تنبيه " + a.alert_id.slice(0, 14)),
      badge(a.severity, SEV_AR[a.severity] || a.severity),
      badge(a.status, ST_AR[a.status] || a.status),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, a.title || "-"),
      el("p", { style: "color:var(--muted);font-size:13.5px;line-height:1.9" }, a.description || ""),
      el("div", { class: "detail-grid" },
        detail("المعرّف الكامل", a.alert_id),
        detail("المؤسسة (tenant)", a.tenant_id),
        detail("المعاملة", a.tx_id || "-"),
        detail("المُسنَد إليه", a.assignee || "غير مُسنَد"),
        detail("أُنشئ", dt(a.created_at)),
        detail("آخر تحديث", dt(a.updated_at)),
        a.resolution ? detail("الحل", ST_AR[a.resolution] || a.resolution) : null,
      ),
    ),
    dec ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "⚖️ القرار المرتبط"),
      el("div", { class: "detail-grid" },
        detail("القرار", DEC_AR[dec.decision] || dec.decision),
        detail("درجة المخاطر", pct(dec.risk_score)),
        detail("النطاق", dec.risk_band),
        detail("النمط", dec.typology || "-"),
      ),
      el("p", { style: "font-size:13px;color:var(--muted);margin-top:8px;line-height:1.9" }, dec.reasoning_ar || ""),
    ) : null,
    tx ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "💳 المعاملة"),
      el("div", { class: "detail-grid" },
        detail("المبلغ", num(tx.amount) + " " + (tx.currency || "")),
        detail("المرسل", tx.sender_account_id),
        detail("المستفيد", tx.beneficiary_account_id),
        detail("بلد المستفيد", tx.beneficiary_country || "-"),
        detail("الجهاز", tx.device_id || "-"),
        detail("IP", tx.ip || "-"),
      ),
      tx.sender_account_id ? el("button", { class: "btn sm", style: "margin-top:10px",
        onclick: async () => { try { state.insights = null; const c = await api("/graph/account/" + encodeURIComponent(tx.sender_account_id)); state.selectedTx = null; state.alertDetail = null; state.graphAccount = c; state.page = "graphAccount"; render(); } catch (e) { toast(e.message, "error"); } }
      }, "🕸️ تحليل حساب المرسل في الشبكة") : null,
    ) : null,
    !resolved ? el("div", { class: "card", style: "border-color:var(--brand)" },
      el("h3", { style: "margin-bottom:12px" }, "⚡ إجراءات المحقق"),
      el("div", { style: "display:flex;gap:8px;flex-wrap:wrap" },
        !a.assignee ? act("📌 إسناد إليّ", "primary", () => api(`/alerts/${a.alert_id}/assign`, { method: "POST" })) : null,
        a.status !== "in_review" ? act("🔍 بدء المراجعة", "", () => api(`/alerts/${a.alert_id}/status`, { method: "POST", body: { status: "in_review" } })) : null,
        act("📁 تصعيد إلى قضية", "warn", () => api(`/alerts/${a.alert_id}/escalate-to-case`, { method: "POST", body: { priority: "high" } }), "سيتم إنشاء قضية جديدة من هذا التنبيه. متابعة؟"),
        act("✅ حل: احتيال مؤكد", "danger", () => api(`/alerts/${a.alert_id}/resolve`, { method: "POST", body: { resolution: "resolved_true_positive", note: noteI.value } }), "تأكيد: هذا التنبيه احتيال حقيقي؟"),
        act("🆗 حل: إنذار كاذب", "success", () => api(`/alerts/${a.alert_id}/resolve`, { method: "POST", body: { resolution: "resolved_false_positive", note: noteI.value } }), "تأكيد: هذا التنبيه إنذار كاذب؟"),
      ),
    ) : el("div", { class: "card", style: "border-color:var(--success)" },
      el("strong", { style: "color:var(--success)" }, "✅ تم حل هذا التنبيه: " + (ST_AR[a.status] || a.status))),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "📝 ملاحظات التحقيق (" + (a.notes || []).length + ")"),
      ...(a.notes || []).map(n => el("div", { class: "note-item" },
        el("div", { class: "meta" }, (n.author || "-") + " · " + dt(n.at)),
        el("div", { style: "font-size:13.5px" }, n.text))),
      el("div", { style: "display:flex;gap:8px;margin-top:10px" },
        noteI,
        el("button", { class: "btn primary", style: "align-self:flex-end",
          onclick: async () => {
            if (!noteI.value.trim()) return;
            try { await api(`/alerts/${a.alert_id}/notes`, { method: "POST", body: { text: noteI.value.trim() } }); noteI.value = ""; await loadAlertDetail(a.alert_id); render(); }
            catch (e) { toast(e.message, "error"); }
          } }, "➕ إضافة"),
      ),
    ),
    d.history && d.history.length ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "🕓 سجل التدقيق"),
      ...d.history.map(h => el("div", { class: "timeline-item" },
        el("div", { style: "font-size:12.5px;font-weight:700" }, h.event_type),
        el("div", { style: "font-size:11px;color:var(--muted)" }, (h.actor || "-") + " · " + dt(h.ts)))),
    ) : null,
  );
}

/* ═══════════════ PAGE: CASES ═══════════════ */
function renderCases() {
  const f = state.filters;
  const mk = (val, opts, onch) => el("select", { onchange: e => { onch(e.target.value); loadCases().then(renderPage); } },
    ...opts.map(o => el("option", { value: o[0], ...(val === o[0] ? { selected: "" } : {}) }, o[1])));
  const rows = (state.cases || []).map(c => el("tr", { class: "clickable", onclick: async () => { await loadCaseDetail(c.case_id); state.page = "caseDetail"; render(); } },
    el("td", { style: "font-size:11px;white-space:nowrap" }, dt(c.created_at)),
    el("td", {}, el("code", { style: "font-size:11px" }, c.case_id.slice(0, 14))),
    el("td", { style: "font-size:12px;max-width:220px" }, c.title || "-"),
    el("td", {}, badge(c.priority, SEV_AR[c.priority] || c.priority)),
    el("td", {}, badge(c.status, ST_AR[c.status] || c.status)),
    el("td", { style: "font-size:12px" }, c.assignee || "—"),
    el("td", { style: "font-size:12px" }, (c.tx_ids || []).length + " معاملة"),
  ));
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "📁 القضايا"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:14px" }, "إدارة تحقيقات الاحتيال — من الفتح حتى الإغلاق الموثَّق"),
    el("div", { class: "filters" },
      mk(f.caseStatus, [["", "كل الحالات"], ["open", "مفتوح"], ["in_progress", "قيد المعالجة"], ["escalated", "مُصعَّد"], ["closed", "مغلق"]], v => f.caseStatus = v),
      el("button", { class: "btn sm", onclick: async () => { state.cases = await api("/cases?assignee=me"); renderPage(); } }, "📌 المُسنَدة إليّ"),
      el("button", { class: "btn sm", onclick: async () => { state.filters.caseStatus = ""; await loadCases(); renderPage(); } }, "✕ مسح"),
    ),
    el("div", { class: "card" },
      rows.length === 0
        ? el("div", { style: "color:var(--muted);text-align:center;padding:30px" }, "لا توجد قضايا مطابقة.")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "العنوان"),
              el("th", {}, "الأولوية"), el("th", {}, "الحالة"), el("th", {}, "المُسنَد إليه"), el("th", {}, "المعاملات"))),
            el("tbody", {}, ...rows))),
  );
}

/* ═══════════════ PAGE: CASE DETAIL ═══════════════ */
function renderCaseDetail() {
  const d = state.caseDetail;
  if (!d || !d.case) return el("div", { style: "color:var(--muted);padding:40px;text-align:center" }, "جارٍ التحميل…");
  const c = d.case;
  const closed = c.status === "closed";
  const noteI = el("textarea", { class: "form-control", rows: "2", placeholder: "أضف ملاحظة…" });
  const act = (label, cls, fn, confirmMsg) => el("button", {
    class: "btn " + cls,
    onclick: async () => {
      if (confirmMsg && !confirm(confirmMsg)) return;
      try { await fn(); await loadCaseDetail(c.case_id); toast("تم", "success"); render(); }
      catch (e) { toast(e.message, "error"); }
    }
  }, label);

  return el("div", {},
    el("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:14px" },
      el("button", { class: "btn sm", onclick: () => { state.page = "cases"; render(); } }, "→ رجوع"),
      el("h1", { style: "font-size:1.5rem;font-weight:900" }, "📁 قضية " + c.case_id.slice(0, 14)),
      badge(c.priority, SEV_AR[c.priority] || c.priority),
      badge(c.status, ST_AR[c.status] || c.status),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, c.title || "-"),
      el("p", { style: "color:var(--muted);font-size:13.5px;line-height:1.9" }, c.narrative || ""),
      el("div", { class: "detail-grid" },
        detail("المعرّف الكامل", c.case_id),
        detail("المؤسسة", c.tenant_id),
        detail("المُسنَد إليه", c.assignee || "غير مُسنَد"),
        detail("أُنشئت", dt(c.created_at)),
        detail("آخر تحديث", dt(c.updated_at)),
        c.resolution ? detail("الحل", ST_AR[c.resolution] || c.resolution) : null,
      ),
    ),
    (d.transactions || []).length ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "💳 المعاملات المرتبطة (" + d.transactions.length + ")"),
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "المعرّف"), el("th", {}, "المبلغ"), el("th", {}, "المرسل"), el("th", {}, "المستفيد"), el("th", {}, ""))),
        el("tbody", {}, ...d.transactions.map(t => el("tr", {},
          el("td", {}, el("code", { style: "font-size:11px" }, (t.tx_id || "").slice(0, 16))),
          el("td", { style: "font-weight:700" }, num(t.amount) + " " + (t.currency || "")),
          el("td", { style: "font-size:12px" }, t.sender_account_id),
          el("td", { style: "font-size:12px" }, t.beneficiary_account_id),
          el("td", {}, el("button", { class: "btn sm", onclick: async () => {
            try { state.graphAccount = await api("/graph/account/" + encodeURIComponent(t.sender_account_id)); state.page = "graphAccount"; render(); } catch (e) { toast(e.message, "error"); }
          } }, "🕸️ شبكة")),
        )))),
    ) : null,
    (d.alerts || []).length ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "🚨 التنبيهات المرتبطة (" + d.alerts.length + ")"),
      ...d.alerts.map(a => el("div", { class: "note-item", style: "cursor:pointer", onclick: async () => { await loadAlertDetail(a.alert_id); state.page = "alertDetail"; render(); } },
        el("div", { style: "display:flex;justify-content:space-between;align-items:center" },
          el("span", { style: "font-size:13px;font-weight:700" }, a.title || a.alert_id),
          badge(a.status, ST_AR[a.status] || a.status)))),
    ) : null,
    !closed ? el("div", { class: "card", style: "border-color:var(--brand)" },
      el("h3", { style: "margin-bottom:12px" }, "⚡ إجراءات القضية"),
      el("div", { style: "display:flex;gap:8px;flex-wrap:wrap" },
        !c.assignee ? act("📌 إسناد إليّ", "primary", () => api(`/cases/${c.case_id}/assign`, { method: "POST" })) : null,
        c.status !== "in_progress" ? act("🔍 بدء المعالجة", "", () => api(`/cases/${c.case_id}/status`, { method: "POST", body: { status: "in_progress" } })) : null,
        act("⬆️ تصعيد", "warn", () => api(`/cases/${c.case_id}/status`, { method: "POST", body: { status: "escalated" } })),
        act("🛑 إغلاق: احتيال مؤكد", "danger", () => api(`/cases/${c.case_id}/resolve`, { method: "POST", body: { resolution: "confirmed_fraud", note: noteI.value } }), "إغلاق القضية كاحتيال مؤكد؟ سيُعلَّم الحساب المرسل كحساب احتيالي في الشبكة."),
        act("🆗 إغلاق: إنذار كاذب", "success", () => api(`/cases/${c.case_id}/resolve`, { method: "POST", body: { resolution: "false_positive", note: noteI.value } }), "إغلاق القضية كإنذار كاذب؟"),
        act("❔ إغلاق: غير حاسم", "", () => api(`/cases/${c.case_id}/resolve`, { method: "POST", body: { resolution: "inconclusive", note: noteI.value } }), "إغلاق القضية كغير حاسمة؟"),
      ),
    ) : el("div", { class: "card", style: "border-color:var(--success)" },
      el("strong", { style: "color:var(--success)" }, "✅ قضية مغلقة: " + (ST_AR[c.resolution] || c.resolution || ""))),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "📝 الملاحظات (" + (c.notes || []).length + ")"),
      ...(c.notes || []).map(n => el("div", { class: "note-item" },
        el("div", { class: "meta" }, (n.author || "-") + " · " + dt(n.at)),
        el("div", { style: "font-size:13.5px" }, n.text))),
      el("div", { style: "display:flex;gap:8px;margin-top:10px" },
        noteI,
        el("button", { class: "btn primary", style: "align-self:flex-end",
          onclick: async () => {
            if (!noteI.value.trim()) return;
            try { await api(`/cases/${c.case_id}/notes`, { method: "POST", body: { text: noteI.value.trim() } }); noteI.value = ""; await loadCaseDetail(c.case_id); render(); }
            catch (e) { toast(e.message, "error"); }
          } }, "➕ إضافة"),
      ),
    ),
    d.history && d.history.length ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:10px" }, "🕓 سجل التدقيق"),
      ...d.history.map(h => el("div", { class: "timeline-item" },
        el("div", { style: "font-size:12.5px;font-weight:700" }, h.event_type),
        el("div", { style: "font-size:11px;color:var(--muted)" }, (h.actor || "-") + " · " + dt(h.ts)))),
    ) : null,
  );
}

/* ═══════════════ PAGE: LIVE DECISIONS ═══════════════ */
function renderDecisions() {
  const rows = (state.decisions || []).map(d => el("tr", {},
    el("td", { style: "font-size:11px;white-space:nowrap" }, dt(d.ts || d.timestamp || d.created_at)),
    el("td", {}, el("code", { style: "font-size:11px" }, (d.tx_id || "").slice(0, 14))),
    el("td", { style: "font-size:12px" }, d.tenant_id || "-"),
    el("td", {}, badge(d.decision, DEC_AR[d.decision] || d.decision)),
    el("td", { style: "font-weight:700" }, pct(d.risk_score)),
    el("td", { style: "font-size:12px" }, d.typology || "-"),
    el("td", { style: "font-size:11px;color:var(--muted);max-width:280px" }, (d.reasoning_ar || "").slice(0, 120)),
  ));
  return el("div", {},
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px" },
      el("div", {},
        el("h1", { style: "font-size:1.7rem;font-weight:900" }, "📡 القرارات الحيّة"),
        el("p", { style: "color:var(--muted);font-size:13px;margin-top:4px" }, "كل قرارات AEGIS عبر المؤسسات — تُحدَّث فوريًّا عند تفعيل البث"),
      ),
      el("div", { style: "display:flex;gap:8px;align-items:center" },
        el("span", { class: "live-dot" + (state.live ? "" : " off") }),
        el("span", { style: "font-size:12px;color:var(--muted)" }, state.live ? "بث مباشر" : "متوقف"),
        el("button", { class: "btn " + (state.live ? "danger" : "success"), onclick: toggleLive },
          state.live ? "⏸ إيقاف البث" : "▶ بث مباشر"),
        el("button", { class: "btn primary", onclick: async () => { await loadDecisions(); renderPage(); } }, "🔄"),
      ),
    ),
    el("div", { class: "card" },
      rows.length === 0
        ? el("div", { style: "color:var(--muted);text-align:center;padding:40px" }, "لا توجد قرارات بعد.")
        : el("table", {},
            el("thead", {}, el("tr", {},
              el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "المؤسسة"),
              el("th", {}, "القرار"), el("th", {}, "المخاطر"), el("th", {}, "النمط"), el("th", {}, "التفسير"))),
            el("tbody", {}, ...rows))),
  );
}

/* ═══════════════ PAGE: GRAPH INSIGHTS ═══════════════ */
function renderGraph() {
  const g = state.insights;
  const accI = el("input", { class: "form-control", placeholder: "أدخل معرّف حساب للتحليل (مثال: acct-a)", dir: "ltr", style: "max-width:320px" });
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🕸️ تحليل الشبكة"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "ذكاء العلاقات: أجهزة/عناوين مشتركة، حلقات، قرب من احتيال معروف"),
    !g ? el("div", { class: "card" }, el("div", { style: "color:var(--muted);text-align:center;padding:30px" }, "جارٍ التحميل…")) : el("div", {},
      el("div", { class: "grid" },
        kpi("العقد", num(g.nodes), "حسابات + معاملات + أجهزة + عناوين", "brand"),
        kpi("الأضلاع", num(g.edges), "العلاقات", "info"),
        kpi("حسابات احتيال معروفة", num((g.known_fraud_accounts || []).length), "من قضايا مؤكدة", "danger"),
      ),
      el("div", { class: "card" },
        el("h3", { style: "margin-bottom:10px" }, "🔎 تحليل حساب"),
        el("div", { style: "display:flex;gap:8px" },
          accI,
          el("button", { class: "btn primary", onclick: async () => {
            const v = accI.value.trim();
            if (!v) return;
            try { state.graphAccount = await api("/graph/account/" + encodeURIComponent(v)); state.page = "graphAccount"; render(); }
            catch (e) { toast(e.message, "error"); }
          } }, "تحليل"),
        ),
      ),
      el("div", { class: "split" },
        el("div", { class: "card" },
          el("h3", { style: "margin-bottom:10px" }, "💻 أجهزة مشتركة بين حسابات"),
          (g.shared_devices || []).length === 0 ? el("div", { style: "color:var(--muted);font-size:13px" }, "لا توجد أجهزة مشتركة.") :
          el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "الجهاز"), el("th", {}, "#حسابات"), el("th", {}, "الحسابات"))),
            el("tbody", {}, ...g.shared_devices.map(s => el("tr", {},
              el("td", {}, el("code", { style: "font-size:11px" }, s.device_id)),
              el("td", { style: "font-weight:700;color:var(--warn)" }, num(s.account_count)),
              el("td", { style: "font-size:11px" }, s.accounts.join(", ")),
            ))))),
        el("div", { class: "card" },
          el("h3", { style: "margin-bottom:10px" }, "🌐 عناوين IP مشتركة"),
          (g.shared_ips || []).length === 0 ? el("div", { style: "color:var(--muted);font-size:13px" }, "لا توجد عناوين مشتركة.") :
          el("table", {},
            el("thead", {}, el("tr", {}, el("th", {}, "IP"), el("th", {}, "#حسابات"))),
            el("tbody", {}, ...g.shared_ips.map(s => el("tr", {},
              el("td", {}, el("code", { style: "font-size:11px" }, s.ip)),
              el("td", { style: "font-weight:700;color:var(--warn)" }, num(s.account_count)),
            ))))),
      ),
      el("div", { class: "card" },
        el("h3", { style: "margin-bottom:10px" }, "🔗 أكثر الحسابات ارتباطًا بمستفيدين"),
        (g.top_linked_accounts || []).length === 0 ? el("div", { style: "color:var(--muted);font-size:13px" }, "لا توجد بيانات.") :
        el("table", {},
          el("thead", {}, el("tr", {}, el("th", {}, "الحساب"), el("th", {}, "عدد المستفيدين"))),
          el("tbody", {}, ...g.top_linked_accounts.map(t => el("tr", {},
            el("td", {}, el("code", { style: "font-size:11px" }, t.account_id)),
            el("td", { style: "font-weight:700" }, num(t.beneficiaries)),
          ))))),
    ),
  );
}

/* ═══════════════ PAGE: GRAPH ACCOUNT ═══════════════ */
function renderGraphAccount() {
  const c = state.graphAccount;
  if (!c) return el("div", { style: "color:var(--muted);padding:40px;text-align:center" }, "جارٍ التحميل…");
  if (!c.in_graph) return el("div", {},
    el("button", { class: "btn sm", onclick: () => { state.page = "graph"; render(); } }, "→ رجوع"),
    el("div", { class: "card", style: "margin-top:12px" }, "الحساب غير موجود في الشبكة بعد."));
  const list = (title, items) => el("div", { class: "card" },
    el("h3", { style: "margin-bottom:8px" }, title + " (" + (items || []).length + ")"),
    (items || []).length === 0 ? el("div", { style: "color:var(--muted);font-size:13px" }, "لا شيء.") :
    el("div", { style: "display:flex;gap:6px;flex-wrap:wrap" },
      ...items.map(i => el("code", { style: "font-size:11.5px;background:var(--bg);padding:4px 8px;border-radius:6px;border:1px solid var(--border)" }, i))));
  return el("div", {},
    el("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:14px" },
      el("button", { class: "btn sm", onclick: () => { state.page = "graph"; render(); } }, "→ رجوع"),
      el("h1", { style: "font-size:1.5rem;font-weight:900" }, "🕸️ تحليل: " + c.account_id),
      c.is_known_fraud ? badge("block", "⚠️ احتيال معروف") : null,
    ),
    el("div", { class: "detail-grid" },
      detail("حسابات تشاركه الجهاز", num((c.accounts_sharing_device || []).length)),
      detail("حسابات تشاركه IP", num((c.accounts_sharing_ip || []).length)),
      detail("مستفيدون مرتبطون", num((c.linked_beneficiaries || []).length)),
      detail("مسافة لأقرب احتيال معروف", c.hops_to_known_fraud == null ? "—" : c.hops_to_known_fraud + " خطوة"),
    ),
    list("💻 الأجهزة", c.devices),
    list("🌐 عناوين IP", c.ips),
    list("🔗 المستفيدون المرتبطون", c.linked_beneficiaries),
    list("⚠️ حسابات تشاركه الجهاز", c.accounts_sharing_device),
    list("⚠️ حسابات تشاركه IP", c.accounts_sharing_ip),
  );
}

/* ═══════════════ PAGE: TX DETAIL (from queue, no alert) ═══════════════ */
async function renderTxDetail() {
  const box = el("div", {},
    el("button", { class: "btn sm", onclick: () => { state.page = "queue"; render(); } }, "→ رجوع"),
    el("div", { style: "margin-top:12px;color:var(--muted)" }, "جارٍ التحميل…"));
  try {
    const d = await api("/transactions/" + encodeURIComponent(state.selectedTx));
    box.innerHTML = "";
    box.appendChild(el("button", { class: "btn sm", onclick: () => { state.page = "queue"; render(); } }, "→ رجوع"));
    const t = d.transaction, dec = d.decision;
    box.appendChild(el("div", { class: "card", style: "margin-top:12px" },
      el("h3", { style: "margin-bottom:10px" }, "💳 معاملة " + (t.tx_id || "").slice(0, 18)),
      el("div", { class: "detail-grid" },
        detail("المبلغ", num(t.amount) + " " + (t.currency || "")),
        detail("المرسل", t.sender_account_id),
        detail("المستفيد", t.beneficiary_account_id),
        detail("الوقت", dt(t.ts)),
      ),
      dec ? el("div", {},
        el("h4", { style: "margin:10px 0 6px;color:var(--accent)" }, "القرار: " + (DEC_AR[dec.decision] || dec.decision) + " · " + pct(dec.risk_score)),
        el("p", { style: "font-size:13px;color:var(--muted);line-height:1.9" }, dec.reasoning_ar || "")) : null,
      el("p", { style: "font-size:12px;color:var(--warn);margin-top:10px" },
        "ℹ️ لم يُنشأ تنبيه لهذه المعاملة. افتح صفحة التنبيهات أو أنشئ قضية يدويًّا عند الحاجة."),
    ));
  } catch (e) { box.appendChild(el("div", { style: "color:#FCA5A5" }, e.message)); }
  return box;
}

/* ═══════════════ ROUTER ═══════════════ */
async function renderPage() {
  const c = $("#content");
  if (!c) return;
  c.innerHTML = "<div style='color:#94A3B8;text-align:center;padding:40px'>جارٍ التحميل…</div>";
  try {
    if (state.page === "dashboard") { await loadStats(); c.replaceChildren(renderDashboard()); }
    else if (state.page === "queue") { await loadQueue(); c.replaceChildren(renderQueue()); }
    else if (state.page === "alerts") { await loadAlerts(); c.replaceChildren(renderAlerts()); }
    else if (state.page === "alertDetail") { c.replaceChildren(renderAlertDetail()); }
    else if (state.page === "cases") { await loadCases(); c.replaceChildren(renderCases()); }
    else if (state.page === "caseDetail") { c.replaceChildren(renderCaseDetail()); }
    else if (state.page === "decisions") { await loadDecisions(); c.replaceChildren(renderDecisions()); }
    else if (state.page === "graph") { await loadInsights(); c.replaceChildren(renderGraph()); }
    else if (state.page === "graphAccount") { c.replaceChildren(renderGraphAccount()); }
    else if (state.page === "txDetail") { c.replaceChildren(await renderTxDetail()); }
  } catch (e) {
    c.innerHTML = "";
    c.appendChild(el("div", { style: "color:#FCA5A5;text-align:center;padding:30px" }, "⚠️ خطأ: " + e.message));
  }
}

function render() {
  const root = $("#app");
  root.innerHTML = "";
  if (!state.token) { root.appendChild(renderLogin()); return; }
  const pages = [
    { id: "dashboard", icon: "📊", label: "لوحة المحقق" },
    { id: "queue", icon: "⏳", label: "قائمة المراجعة" },
    { id: "alerts", icon: "🚨", label: "التنبيهات" },
    { id: "cases", icon: "📁", label: "القضايا" },
    { id: "decisions", icon: "📡", label: "القرارات الحيّة" },
    { id: "graph", icon: "🕸️", label: "تحليل الشبكة" },
  ];
  root.appendChild(el("div", { class: "layout" },
    el("header", { class: "top" },
      el("div", { style: "display:flex;align-items:center;gap:10px" },
        el("span", { style: "font-size:1.7rem" }, "🛡️"),
        el("span", { class: "brand-title" }, "AEGIS Investigator"),
        el("span", { style: "font-size:12px;color:var(--muted)" }, "· منصة التحقيق في الاحتيال"),
      ),
      el("div", { style: "display:flex;gap:10px;align-items:center" },
        el("span", { style: "font-size:12.5px;color:var(--muted)" }, state.profile?.name || ""),
        el("span", { class: "badge assigned" }, "محقق"),
        el("button", { class: "btn danger", onclick: logout }, "🚪 خروج"),
      )),
    el("aside", {},
      ...pages.map(p => el("div", {
        class: "nav" + (state.page === p.id ? " active" : ""),
        onclick: () => { state.page = p.id; state.alertDetail = null; state.caseDetail = null; render(); }
      }, el("span", {}, p.icon), el("span", {}, p.label))),
    ),
    el("main", { id: "content" }),
  ));
  renderPage();
}

render();
