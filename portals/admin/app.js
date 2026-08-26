/* AEGIS Owner Portal — Super Admin (Multi-Tenant Control) */
const API = "/api/v1/admin";
const AEGIS_ROOT = "/api/v1";
const TK = "aegis_owner_token";


/* =============== I18N (AR/EN) =============== */
const EN_LABELS = {
  "لوحة المحقق": "Dashboard", "قائمة المراجعة": "Review Queue", "التنبيهات": "Alerts",
  "القضايا": "Cases", "القرارات الحيّة": "Live Decisions", "أثر القرار": "Decision Trace",
  "العملاء": "Customers", "المستفيدون": "Beneficiaries", "تحليل الشبكة": "Network Graph",
  "نظرة عامة": "Overview", "العملاء (بنوك ومحافظ)": "Tenants (Banks & Wallets)",
  "القرارات": "Decisions", "المحققون": "Investigators", "قواعد السياسة": "Policy Rules",
  "النماذج": "Models", "الرسم البياني": "Graph", "الإعدادات": "Settings", "التوثيق": "Docs",
  "أسعار الصرف": "FX Rates", "قوائم المراقبة": "Watchlists", "استوديو السياسات": "Policy Studio",
  "سجل التدقيق": "Audit Log", "العمليات": "Transactions",
  "🚨 التنبيهات": "🚨 Alerts", "📁 القضايا": "📁 Cases", "🕸️ تحليل الشبكة": "🕸️ Network Graph",
  "⏳ فتح قائمة المراجعة": "⏳ Open Review Queue", "⚡ إجراءات سريعة": "⚡ Quick Actions",
  "🚪 خروج": "🚪 Logout", "محقق": "Investigator"
};
function L(ar, en) { return state.lang === "ar" ? ar : en; }
function tl(txt) { return state.lang === "ar" ? txt : (EN_LABELS[txt] || txt); }
function applyDir() {
  document.documentElement.setAttribute("dir", state.lang === "ar" ? "rtl" : "ltr");
  document.documentElement.setAttribute("lang", state.lang);
}
function toggleLang() {
  state.lang = state.lang === "ar" ? "en" : "ar";
  try { localStorage.setItem("aegis_lang", state.lang); } catch (e) {}
  applyDir();
  render();
}
(function () {
  try {
    var _l = localStorage.getItem("aegis_lang") || "ar";
    document.documentElement.setAttribute("dir", _l === "ar" ? "rtl" : "ltr");
    document.documentElement.setAttribute("lang", _l);
  } catch (e) {}
})();

const state = {
  lang: (function(){ try { return localStorage.getItem("aegis_lang") || "ar"; } catch (e) { return "ar"; } })(),
  token: localStorage.getItem(TK),
  page: "overview",
  fxCurrencies: [],
  fxRates: [],
  watchlistEntries: [],
  auditLog: [],
  auditVerifyResult: null,
  policyTenants: [],
  policySelected: null,
  overview: null,
  tenants: [],
  decisions: [],
  selectedTenantId: null,
  selectedTenant: null,
  showAddForm: false,
  lastCreated: null,
  settings: null,
  investigators: [],
  rules: [],
  ruleDetail: null,
  modelsStatus: null,
  graphStats: null,
  graphInsights: null,
  tenantInvs: null,
  tenantInvsFor: null,
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
const dt = iso => { try { return new Date(iso).toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" }); } catch { return iso || "-"; } };

function toast(msg, type = "info") {
  const t = el("div", { class: "toast " + type }, msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}

async function api(path, opts = {}) {
  const h = { "Content-Type": "application/json", "X-Owner-Token": state.token, ...(opts.headers || {}) };
  const r = await fetch(API + path, { ...opts, headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const txt = await r.text();
  let d = {};
  try { d = txt ? JSON.parse(txt) : {}; } catch { d = { raw: txt }; }
  if (r.status === 401) { state.token = null; localStorage.removeItem(TK); try { render(); } catch {} throw new Error("انتهت الجلسة — سجّل الدخول مجددًا (401)"); }
  if (!r.ok) throw new Error(d.detail || d.message || ("خطأ " + r.status));
  return d;
}

async function apiRoot(path, opts = {}) {
  const h = { "Content-Type": "application/json", "X-Owner-Token": state.token, ...(opts.headers || {}) };
  const r = await fetch(AEGIS_ROOT + path, { ...opts, headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const txt = await r.text();
  let d = {};
  try { d = txt ? JSON.parse(txt) : {}; } catch { d = { raw: txt }; }
  if (r.status === 401) { state.token = null; localStorage.removeItem(TK); try { render(); } catch {} throw new Error("انتهت الجلسة — سجّل الدخول مجددًا (401)"); }
  if (!r.ok) throw new Error(d.detail || d.message || ("خطأ " + r.status));
  return d;
}

async function copy(txt, btn) {
  try {
    await navigator.clipboard.writeText(txt);
    if (btn) { const o = btn.textContent; btn.textContent = "✓"; setTimeout(() => btn.textContent = o, 1200); }
    toast("تم النسخ", "success");
  } catch { toast("فشل النسخ", "error"); }
}

/* ─────────────────────────────────────────── LOGIN ─── */
function renderLogin() {
  const inp = el("input", { class: "form-control", type: "password", placeholder: "Owner Token", value: "" });
  const err = el("div", { style: "color:#FCA5A5;font-size:13px;margin-top:8px" });
  const form = el("form", {
    onsubmit: async e => {
      e.preventDefault();
      try {
        const r = await fetch(API + "/overview", { headers: { "X-Owner-Token": inp.value.trim() } });
        if (!r.ok) throw new Error("رمز غير صالح");
        state.token = inp.value.trim();
        localStorage.setItem(TK, state.token);
        toast("مرحباً بك في بوابة المالك", "success");
        render();
      } catch (ex) { err.textContent = ex.message; }
    }
  },
    el("label", { style: "font-size:13px;color:var(--muted);margin-bottom:8px;display:block" }, "🔐 Owner Token"),
    inp, err,
    el("button", { class: "btn primary", style: "width:100%;padding:13px;margin-top:14px" }, "🔓 دخول"),
  );
  return el("div", { class: "login-wrap" },
    el("div", { class: "login-card" },
      el("div", { style: "font-size:4rem;text-align:center" }, "👑"),
      el("h1", { style: "text-align:center;font-size:1.7rem;font-weight:900" }, "AEGIS Owner Portal"),
      el("p", { style: "text-align:center;color:var(--muted);font-size:13px;margin:8px 0 24px" }, "بوابة مالك المنظومة — التحكم الكامل"),
      form,
      el("div", { style: "background:rgba(59,130,246,.08);padding:12px;border-radius:10px;margin-top:14px;font-size:11.5px;color:#93C5FD" },
        "💡 أدخل رمز المالك من ملف .env"),
    )
  );
}

/* ─────────────────────────────────────────── DATA LOADERS ─── */
async function loadOverview() {
  try {
    state.overview = await api("/overview");
  } catch (e) {
    state.overview = { tenants: { total: 0, active: 0 }, decisions: { total: 0, by_decision: {allow:0,challenge:0,review:0,block:0}, by_tenant: {}, avg_risk: 0 } };
  }
}

async function loadTenants() {
  try {
    const r = await api("/tenants");
    state.tenants = (r && r.tenants) || [];
  } catch { state.tenants = []; }
}

async function loadTenantDetail(tid) {
  state.selectedTenant = await api("/tenants/" + tid);
  state.selectedTenantId = tid;
}

async function loadSettings() {
  state.settings = await api("/settings");
}

async function loadInvestigators() {
  try { const r = await api("/investigators"); state.investigators = r.investigators || []; }
  catch { state.investigators = []; }
}

async function loadTenantInvestigators(tid) {
  const r = await api("/tenants/" + tid + "/investigators");
  state.tenantInvs = r;
  state.tenantInvsFor = tid;
}

async function loadRules() {
  try { state.rules = await apiRoot("/rules/"); } catch { state.rules = []; }
}

async function loadRuleDetail(id) {
  state.ruleDetail = await apiRoot("/rules/" + encodeURIComponent(id));
}

async function loadModels() {
  try { state.modelsStatus = await apiRoot("/models/status"); } catch { state.modelsStatus = null; }
}

async function loadGraph() {
  try {
    state.graphStats = await apiRoot("/graph/stats");
    state.graphInsights = await apiRoot("/graph/insights");
  } catch { state.graphStats = null; state.graphInsights = null; }
}

async function loadDecisions() {
  try {
    state.decisions = await apiRoot("/decisions/recent?limit=50") || [];
    if (!Array.isArray(state.decisions)) state.decisions = [];
  } catch { state.decisions = []; }
}

/* ─────────────────────────────────────────── UI HELPERS ─── */
function kpi(label, value, sub, tone = "brand") {
  const colors = { brand:"#3B82F6", success:"#10B981", warn:"#F59E0B", danger:"#EF4444", info:"#06B6D4", purple:"#A855F7" };
  return el("div", { class: "kpi", style: `border-top:3px solid ${colors[tone]||colors.brand}` },
    el("div", { class: "kpi-label" }, label),
    el("div", { class: "kpi-value" }, value),
    sub ? el("div", { style: "font-size:11.5px;color:var(--muted);margin-top:4px" }, sub) : null,
  );
}

function credRow(label, value, opts = {}) {
  const codeText = el("code", { style: "flex:1;color:var(--accent);word-break:break-all;font-size:11.5px;padding:0 8px" },
    opts.masked ? "•".repeat(28) + " (مخفي)" : value);
  const copyBtn = el("button", { class: "btn", style: "padding:5px 10px;font-size:11px" }, "📋");
  copyBtn.onclick = () => copy(value, copyBtn);
  const kids = [
    el("div", { style: "font-weight:700;color:var(--muted);min-width:130px;font-size:12px" }, label),
    codeText, copyBtn,
  ];
  if (opts.masked) {
    let shown = false;
    const btnEye = el("button", { class: "btn", style: "padding:5px 10px;font-size:11px" }, "👁");
    btnEye.onclick = () => {
      shown = !shown;
      codeText.textContent = shown ? value : "•".repeat(28) + " (مخفي)";
      btnEye.textContent = shown ? "🙈" : "👁";
    };
    kids.push(btnEye);
  }
  return el("div", { class: "creds-row" }, ...kids);
}

/* ─────────────────────────────────────────── PAGE: OVERVIEW ─── */
function renderOverview() {
  const o = state.overview;
  if (!o) return el("div", { style: "color:var(--muted);text-align:center;padding:40px" }, "جارٍ التحميل…");
  const d = o.decisions || { by_decision: {}, by_tenant: {} };
  const by = d.by_decision || {};
  const byT = d.by_tenant || {};
  const t = o.tenants || { total: 0, active: 0 };

  const box = el("div", {});
  box.appendChild(el("h1", { style: "font-size:1.8rem;font-weight:900;margin-bottom:6px" }, "📊 نظرة عامة على المنظومة"));
  box.appendChild(el("p", { style: "color:var(--muted);margin-bottom:18px" }, "إحصائيات شاملة لكل المؤسسات المرتبطة بـ AEGIS"));

  box.appendChild(el("div", { class: "grid" },
    kpi("🏢 المؤسسات", num(t.total), "نشطة: " + num(t.active), "brand"),
    kpi("📋 القرارات الكلية", num(d.total || 0), "منذ التشغيل", "info"),
    kpi("⚠️ متوسط المخاطر", ((d.avg_risk || 0) * 100).toFixed(1) + "%", "على كل المعاملات", "purple"),
    kpi("✅ مسموح", num(by.allow || 0), "معاملات آمنة", "success"),
    kpi("🔐 تحقق", num(by.challenge || 0), "طلبت OTP", "info"),
    kpi("⏳ مراجعة", num(by.review || 0), "قيد المراجعة", "warn"),
    kpi("🛑 محظور", num(by.block || 0), "احتيال مؤكد", "danger"),
  ));

  const rows = [];
  const namesById = {};
  (state.tenants || []).forEach(x => { namesById[x.tenant_id] = x.name; });
  Object.entries(byT).forEach(([tid, cnt]) => {
    rows.push(el("tr", {},
      el("td", {}, el("strong", {}, namesById[tid] || "غير معروف")),
      el("td", {}, el("code", {}, tid)),
      el("td", { style: "font-weight:800;color:var(--accent)" }, num(cnt)),
    ));
  });

  box.appendChild(el("div", { class: "card" },
    el("h3", { style: "margin-bottom:12px" }, "📈 توزيع القرارات على المؤسسات"),
    rows.length === 0
      ? el("div", { style: "color:var(--muted);text-align:center;padding:20px" }, "لا توجد قرارات بعد. أضف مؤسسة ثم أرسل معاملة عبر webhook.")
      : el("table", {},
          el("thead", {}, el("tr", {}, el("th", {}, "المؤسسة"), el("th", {}, "tenant_id"), el("th", {}, "عدد القرارات"))),
          el("tbody", {}, ...rows)
        )
  ));

  return box;
}

/* ─────────────────────────────────────────── PAGE: TENANTS ─── */
function renderTenants() {
  const box = el("div", {});
  const header = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px" },
    el("div", {},
      el("h1", { style: "font-size:1.7rem;font-weight:900" }, "🏢 العملاء (البنوك والمحافظ)"),
      el("p", { style: "color:var(--muted);font-size:13px;margin-top:4px" }, "أضف عميلاً جديداً → استلم مفاتيح API فوراً → سلّمها له")
    ),
    el("button", { class: "btn primary", style: "padding:11px 20px;font-size:14px",
      onclick: () => { state.showAddForm = !state.showAddForm; state.lastCreated = null; render(); }
    }, state.showAddForm ? "✕ إغلاق" : "➕ إضافة عميل جديد"),
  );
  box.appendChild(header);

  // Add-tenant form
  if (state.showAddForm) box.appendChild(renderAddTenantForm());

  // Newly created card (shows generated keys clearly)
  if (state.lastCreated) box.appendChild(renderNewCredsCard(state.lastCreated));

  // Tenants table
  const rows = [];
  (state.tenants || []).filter(t => t.status !== "deleted").forEach(t => {
    rows.push(el("tr", {},
      el("td", {}, el("strong", {}, t.name)),
      el("td", {}, el("code", { style: "font-size:11px" }, t.tenant_id)),
      el("td", {}, t.type === "wallet" ? "💳 محفظة" : t.type === "bank" ? "🏦 بنك" : t.type === "payment" ? "💰 دفع" : t.type),
      el("td", {}, t.country || "-"),
      el("td", {}, t.plan === "production" ? "🚀 Production" : "🧪 Sandbox"),
      el("td", {}, el("span", { class: "badge " + (t.status === "active" ? "allow" : "block") }, t.status || "active"),
        el("div", { style: "font-size:10.5px;color:var(--muted);margin-top:2px" }, "محققون: " + (t.investigators_used ?? 0) + "/" + (t.investigator_limit ?? 5))),
      el("td", {},
        el("div", { style: "display:flex;gap:4px;flex-wrap:wrap" },
          el("button", { class: "btn", style: "padding:5px 8px;font-size:11px",
            onclick: async () => { try { await loadTenantDetail(t.tenant_id); render(); } catch (e) { toast(e.message, "error"); } }
          }, "🔌 مفاتيح"),
          t.status === "active"
            ? el("button", { class: "btn sm danger", style: "padding:5px 8px;font-size:11px",
                onclick: async () => { try { await api("/tenants/" + t.tenant_id + "/suspend", { method: "POST", body: {} }); toast("أُوقفت المؤسسة", "success"); await loadTenants(); render(); } catch (e) { toast(e.message, "error"); } }
              }, "⏸ إيقاف")
            : el("button", { class: "btn sm success", style: "padding:5px 8px;font-size:11px",
                onclick: async () => { try { await api("/tenants/" + t.tenant_id + "/activate", { method: "POST", body: {} }); toast("نُشطت المؤسسة", "success"); await loadTenants(); render(); } catch (e) { toast(e.message, "error"); } }
              }, "▶ تنشيط"),
          el("button", { class: "btn", style: "padding:5px 8px;font-size:11px",
            onclick: async () => { try { await loadTenantInvestigators(t.tenant_id); render(); } catch (e) { toast(e.message, "error"); } }
          }, "👥 محققون"),
          el("button", { class: "btn danger", style: "padding:5px 8px;font-size:11px",
            onclick: () => deleteTenant(t.tenant_id)
          }, "🗑️"))),
    ));
  });

  box.appendChild(el("div", { class: "card" },
    el("h3", { style: "margin-bottom:12px" }, `📋 قائمة العملاء (${(state.tenants || []).filter(t => t.status !== "deleted").length})`),
    rows.length === 0
      ? el("div", { style: "color:var(--muted);text-align:center;padding:30px" }, "لا يوجد عملاء بعد. اضغط \"➕ إضافة عميل جديد\" لبدء الربط.")
      : el("table", {},
          el("thead", {}, el("tr", {},
            el("th", {}, "الاسم"), el("th", {}, "tenant_id"), el("th", {}, "النوع"),
            el("th", {}, "الدولة"), el("th", {}, "الخطة"), el("th", {}, "الحالة"), el("th", {}, "الإجراءات"))),
          el("tbody", {}, ...rows)
        )
  ));

  // Selected tenant details
  if (state.selectedTenant) box.appendChild(renderTenantDetail());

  // Tenant investigators panel
  if (state.tenantInvs && state.tenantInvsFor) box.appendChild(renderTenantInvestigators());

  return box;
}

function renderAddTenantForm() {
  const nameI = el("input", { class: "form-control", placeholder: "مثال: بنك اليمن الأهلي" });
  const typeI = el("select", { class: "form-control" },
    el("option", { value: "bank" }, "🏦 بنك"),
    el("option", { value: "wallet" }, "💳 محفظة"),
    el("option", { value: "payment" }, "💰 شركة دفع"),
  );
  const countryI = el("input", { class: "form-control", value: "YE", maxlength: "3" });
  const planI = el("select", { class: "form-control" },
    el("option", { value: "sandbox" }, "🧪 Sandbox (اختبار)"),
    el("option", { value: "production" }, "🚀 Production (إنتاج)"),
  );
  const emailI = el("input", { class: "form-control", type: "email", placeholder: "api@bank.example (اختياري)" });
  const phoneI = el("input", { class: "form-control", placeholder: "+967 77 123 4567 (اختياري)" });
  const limitI = el("input", { class: "form-control", type: "number", value: "5", min: "0", max: "500" });
  const tzI = el("input", { class: "form-control", value: "Asia/Aden", dir: "ltr" });
  const err = el("div", { style: "color:#FCA5A5;font-size:13px;margin-top:8px" });

  const btn = el("button", { class: "btn primary", style: "padding:12px 24px;font-size:14px" }, "✨ إنشاء + توليد المفاتيح");
  const form = el("form", {
    onsubmit: async e => {
      e.preventDefault();
      if (!nameI.value.trim()) { err.textContent = "الاسم مطلوب"; return; }
      btn.disabled = true; btn.textContent = "جارٍ الإنشاء…";
      try {
        const r = await api("/tenants", { method: "POST", body: {
          name: nameI.value.trim(),
          type: typeI.value,
          country: countryI.value.trim() || "YE",
          plan: planI.value,
          contact_email: emailI.value.trim() || null,
          contact_phone: phoneI.value.trim() || null,
          investigator_limit: Math.max(0, parseInt(limitI.value, 10) || 5),
          timezone: tzI.value.trim() || "Asia/Aden",
        }});
        state.lastCreated = r;
        state.showAddForm = false;
        await loadTenants();
        toast("✅ تم إنشاء العميل — انسخ المفاتيح الآن!", "success");
        render();
      } catch (ex) {
        err.textContent = ex.message;
        btn.disabled = false; btn.textContent = "✨ إنشاء + توليد المفاتيح";
      }
    }
  },
    el("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:12px" },
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "🏷️ الاسم *"), nameI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "📦 النوع *"), typeI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "🌍 الدولة"), countryI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "🎯 الخطة"), planI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "📧 بريد التواصل"), emailI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "📱 هاتف التواصل"), phoneI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "👥 حد المحققين (الافتراضي 5)"), limitI),
      el("div", {}, el("label", { style: "font-size:12.5px;color:var(--muted);display:block;margin-bottom:6px" }, "🌐 المنطقة الزمنية"), tzI),
    ),
    err,
    el("div", { style: "margin-top:14px;display:flex;gap:8px" }, btn),
  );

  return el("div", { class: "card", style: "border-color:var(--brand);border-width:2px" },
    el("h3", { style: "margin-bottom:12px" }, "➕ إضافة عميل جديد"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:14px" },
      "بمجرد الحفظ، سيولّد النظام تلقائياً: ",
      el("code", { style: "color:var(--accent)" }, "tenant_id"), " + ",
      el("code", { style: "color:var(--accent)" }, "api_key"), " + ",
      el("code", { style: "color:var(--accent)" }, "hmac_secret"),
    ),
    form,
  );
}

function renderNewCredsCard(t) {
  return el("div", { class: "card", style: "border:2px solid var(--success);background:linear-gradient(135deg,rgba(16,185,129,.1),rgba(6,182,212,.05))" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:14px" },
      el("h3", { style: "color:var(--success)" }, "🎉 تم إنشاء العميل بنجاح: " + t.name),
      el("button", { class: "btn", onclick: () => { state.lastCreated = null; render(); } }, "✕"),
    ),
    el("div", { style: "background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.4);padding:12px 14px;border-radius:10px;margin-bottom:14px;font-size:13px;color:#FCD34D" },
      "⚠️ ", el("strong", {}, "احفظ hmac_secret الآن!"), " هذه هي المرة الوحيدة التي يُعرض فيها بالكامل. سلّم هذه المفاتيح للعميل بأمان."),
    el("div", { class: "creds-box" },
      credRow("🆔 tenant_id", t.tenant_id),
      credRow("🔑 api_key", t.api_key),
      credRow("🔐 hmac_secret", t.hmac_secret, { masked: true }),
      credRow("🌐 endpoint", "/api/v1/wallet/webhook"),
    ),
    el("div", { style: "margin-top:14px;padding:14px;background:rgba(59,130,246,.08);border-radius:10px;font-size:13px;line-height:1.9" },
      el("strong", { style: "color:var(--accent)" }, "🚀 خطوات التسليم للعميل:"), el("br"),
      "1. انسخ الحقول أعلاه.", el("br"),
      "2. أرسلها للعميل عبر قناة آمنة (email مشفّر / رسالة رسمية).", el("br"),
      "3. العميل يفتح ", el("a", { href: "/merchant/", target: "_blank", style: "color:var(--accent);text-decoration:underline" }, "بوابة المؤسسة"), " ويسجّل دخول بمفاتيحه.", el("br"),
      "4. من تبويب \"🔌 إعدادات الربط\" يحصل على كود جاهز بلغته (cURL/Node.js/Python)."
    ),
  );
}

function renderTenantDetail() {
  const t = state.selectedTenant;
  const endpoint = "/api/v1/wallet/webhook";
  return el("div", { class: "card", style: "border-color:var(--accent);border-width:2px" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:14px" },
      el("h3", {}, "🔌 مفاتيح ربط: " + t.name),
      el("button", { class: "btn", onclick: () => { state.selectedTenant = null; state.selectedTenantId = null; render(); } }, "✕"),
    ),
    el("div", { class: "creds-box" },
      credRow("🆔 tenant_id", t.tenant_id),
      credRow("🔑 api_key", t.api_key),
      credRow("🔐 hmac_secret", t.hmac_secret, { masked: true }),
      credRow("🌐 endpoint", endpoint),
      credRow("📊 الحالة", t.status || "active"),
      credRow("📦 الخطة", t.plan || "sandbox"),
      credRow("📅 تاريخ الإنشاء", dt(t.created_at)),
    ),
    el("div", { style: "margin-top:14px;display:flex;gap:10px;flex-wrap:wrap" },
      el("button", { class: "btn danger",
        onclick: async () => {
          if (!confirm("سيتم إبطال HMAC Secret الحالي وتوليد جديد. متأكد؟")) return;
          try {
            const r = await api("/tenants/" + t.tenant_id + "/rotate-secret", { method: "POST" });
            toast("تم تدوير السر — انسخه فوراً!", "success");
            await loadTenantDetail(t.tenant_id);
            render();
          } catch (e) { toast(e.message, "error"); }
        }
      }, "🔄 تدوير HMAC Secret"),
    ),
    el("div", { style: "margin-top:16px" },
      el("h4", { style: "margin-bottom:10px;color:var(--accent)" }, "📖 مثال ربط جاهز (Node.js)"),
      el("pre", { class: "code-block" },
`const crypto = require('crypto');
const body = JSON.stringify({
  transaction: { transaction_id, amount, currency:'YER', timestamp, account_id, beneficiary_account_id },
  context: { channel:'web' }
});
const sig = crypto.createHmac('sha256', '${t.hmac_secret}')
  .update(body).digest('hex');
const r = await fetch('${endpoint}', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': '${t.api_key}',
    'x-wallet-signature': sig
  },
  body
});
const { decision, risk_score, reasoning_ar } = await r.json();`
      ),
    ),
  );
}

function renderTenantInvestigators() {
  const tid = state.tenantInvsFor;
  const data = state.tenantInvs || {};
  const invs = data.investigators || [];
  const limit = data.limit ?? 5, used = data.used ?? 0;
  const nm = el("input", { class: "form-control", placeholder: "اسم المحقق" });
  const em = el("input", { class: "form-control", type: "email", placeholder: "investigator@bank.com", dir: "ltr" });
  const pw = el("input", { class: "form-control", type: "password", placeholder: "كلمة المرور (8+)" });
  const rows = invs.map(v => el("tr", {},
    el("td", { style: "font-size:12px" }, v.name),
    el("td", { style: "font-size:12px" }, v.email),
    el("td", {}, el("span", { class: "badge " + (v.status === "active" ? "allow" : "block") }, v.status === "active" ? "نشط" : v.status)),
    el("td", { style: "font-size:11px" }, dt(v.created_at)),
    el("td", { style: "font-size:11px" }, v.last_login_at ? dt(v.last_login_at) : "لم يدخل"),
    el("td", {}, el("code", { style: "font-size:10.5px" }, tid)),
    el("td", {}, el("div", { style: "display:flex;gap:4px;flex-wrap:wrap" },
      v.status === "active" ? el("button", { class: "btn sm danger", onclick: async () => { if (!confirm("إيقاف المحقق؟")) return; try { await api("/tenants/" + tid + "/investigators/" + v.investigator_id + "/suspend", { method: "POST", body: {} }); toast("أُوقف", "success"); await loadTenantInvestigators(tid); render(); } catch (e) { toast(e.message, "error"); } } }, "⏸ إيقاف")
        : el("button", { class: "btn sm success", onclick: async () => { try { await api("/tenants/" + tid + "/investigators/" + v.investigator_id + "/activate", { method: "POST", body: {} }); toast("نُشط", "success"); await loadTenantInvestigators(tid); render(); } catch (e) { toast(e.message, "error"); } } }, "▶ تنشيط"),
      el("button", { class: "btn sm", onclick: async () => { const np = prompt("كلمة المرور الجديدة (8+ أحرف)"); if (!np || np.length < 8) return; try { await api("/tenants/" + tid + "/investigators/" + v.investigator_id + "/reset-password", { method: "POST", body: { password: np } }); toast("تم تغيير كلمة المرور", "success"); } catch (e) { toast(e.message, "error"); } } }, "🔑"),
      el("button", { class: "btn sm danger", onclick: async () => { if (!confirm("حذف المحقق؟")) return; try { await api("/tenants/" + tid + "/investigators/" + v.investigator_id, { method: "DELETE" }); toast("حُذف", "success"); await loadTenantInvestigators(tid); render(); } catch (e) { toast(e.message, "error"); } } }, "🗑")))));
  return el("div", { class: "card", style: "border-color:var(--accent);border-width:2px" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:12px" },
      el("h3", {}, "👥 محققو المؤسسة (" + (used) + "/" + limit + ")"),
      el("button", { class: "btn", onclick: () => { state.tenantInvs = null; state.tenantInvsFor = null; render(); } }, "✕")),
    el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:10px" }, nm, em, pw),
    el("button", { class: "btn primary", style: "margin-bottom:14px", onclick: async () => {
      if (!em.value.trim() || !nm.value.trim()) { toast("أدخل البريد والاسم", "error"); return; }
      try { await api("/tenants/" + tid + "/investigators", { method: "POST", body: { email: em.value.trim(), name: nm.value.trim(), password: pw.value } }); toast("تم إنشاء المحقق", "success"); nm.value = em.value = pw.value = ""; await loadTenantInvestigators(tid); render(); } catch (e) { toast(e.message, "error"); }
    } }, "➕ إضافة محقق"),
    rows.length === 0 ? el("div", { style: "color:var(--muted);text-align:center;padding:24px" }, "لا يوجد محققون لهذه المؤسسة")
    : el("table", {}, el("thead", {}, el("tr", {}, ["الاسم", "البريد", "الحالة", "أُنشئ", "آخر دخول", "المؤسسة", "إجراءات"].map(h => el("th", {}, h)))), el("tbody", {}, ...rows)));
}

async function deleteTenant(tid) {
  if (!confirm("سيتم تعطيل هذه المؤسسة. متأكد؟")) return;
  try {
    await api("/tenants/" + tid, { method: "DELETE" });
    toast("تم تعطيل المؤسسة", "success");
    await loadTenants();
    render();
  } catch (e) { toast(e.message, "error"); }
}

/* ─────────────────────────────────────────── PAGE: DECISIONS ─── */
function renderDecisions() {
  const box = el("div", {});
  box.appendChild(el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px" },
    el("div", {},
      el("h1", { style: "font-size:1.7rem;font-weight:900" }, "⚖️ قرارات الاحتيال (كل المؤسسات)"),
      el("p", { style: "color:var(--muted);font-size:13px;margin-top:4px" }, "مراقبة حية لكل قرار يصدر من AEGIS عبر كل المؤسسات المرتبطة"),
    ),
    el("button", { class: "btn primary",
      onclick: async () => { await loadDecisions(); render(); toast("تم التحديث", "success"); }
    }, "🔄 تحديث"),
  ));

  const rows = [];
  (state.decisions || []).forEach(d => {
    const dec = d.decision || "?";
    rows.push(el("tr", {},
      el("td", { style: "font-size:11px" }, dt(d.ts || d.timestamp || d.created_at)),
      el("td", {}, el("code", { style: "font-size:11px" }, (d.tx_id || "").slice(0, 16))),
      el("td", { style: "font-size:12.5px" }, d.tenant_name || d.tenant_id || "-"),
      el("td", {}, el("span", { class: "badge " + dec }, dec)),
      el("td", { style: "font-weight:700" }, ((d.risk_score || 0) * 100).toFixed(0) + "%"),
      el("td", { style: "font-size:12px" }, d.typology || "-"),
      el("td", { style: "font-size:11px;color:var(--muted);max-width:280px" }, (d.reasoning_ar || "").slice(0, 120)),
    ));
  });

  box.appendChild(el("div", { class: "card" },
    rows.length === 0
      ? el("div", { style: "color:var(--muted);text-align:center;padding:40px" }, "لا توجد قرارات بعد. أضف مؤسسة وأرسل معاملة اختبارية.")
      : el("table", {},
          el("thead", {}, el("tr", {},
            el("th", {}, "الوقت"), el("th", {}, "المعرّف"), el("th", {}, "المؤسسة"),
            el("th", {}, "القرار"), el("th", {}, "المخاطر"), el("th", {}, "النمط"), el("th", {}, "التفسير"))),
          el("tbody", {}, ...rows)
        )
  ));

  return box;
}

/* ─────────────────────────────────────────── PAGE: SETTINGS (real runtime) ─── */
function renderSettings() {
  const s = state.settings;
  if (!s) return el("div", { style: "color:var(--muted);text-align:center;padding:40px" }, "جارٍ التحميل…");
  const th = s.thresholds || {}, w = s.weights || {};
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "⚙️ إعدادات النظام"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "القيم الفعلية من الخادم (runtime) — ليست نصوصاً ثابتة"),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🎚️ عتبات القرار الفعلية"),
      el("div", { class: "creds-box" },
        credRow("✅ allow", "risk < " + th.challenge + " (يُنفَّذ فوراً)"),
        credRow("🔐 challenge", th.challenge + " ≤ risk < " + th.review + " (يطلب OTP)"),
        credRow("⏳ review", th.review + " ≤ risk < " + th.block + " (مراجعة يدوية)"),
        credRow("🛑 block", "risk ≥ " + th.block + " (يُرفض)"),
      ),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "⚖️ أوزان دمج المخاطر (Risk Fusion)"),
      el("div", { class: "creds-box" },
        credRow("قواعد (Rules)", w.rules),
        credRow("تعلّم آلي (ML)", w.ml),
        credRow("شبكة (Graph)", w.graph),
        credRow("امتثال (AML)", w.aml),
        credRow("سلوك (Behavior)", w.behavior),
      ),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🤖 الوكيل الذكي (AI)"),
      el("div", { class: "creds-box" },
        credRow("مُفعَّل", s.ai?.enabled ? "نعم" : "لا"),
        credRow("مفاتيح مهيأة", (s.ai?.keys_configured ?? 0) + " مفتاح"),
        credRow("حدّ أدنى للدرجة", s.ai?.min_score),
      ),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "📡 معلومات النظام"),
      el("div", { class: "creds-box" },
        credRow("الإصدار", s.version),
        credRow("البيئة", s.env),
        credRow("Public URL", s.public_url),
        credRow("Webhook Endpoint", s.webhook_endpoint),
        credRow("معدل الطلبات/دقيقة", s.rate_limit_per_min),
        credRow("قاعدة البيانات", s.db_path),
      ),
    ),
  );
}

/* ─────────────────────────────────────────── PAGE: DOCS ─── */
function renderDocs() {
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "📖 دليل التكامل"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "كيف تربط بنك أو محفظة بمنظومة AEGIS"),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🚀 خطوات التكامل السريع"),
      el("ol", { style: "line-height:2.2;padding-inline-start:20px;font-size:13.5px" },
        el("li", {}, "أنشئ عميلاً — من صفحة \"العملاء\" اضغط ", el("strong", {}, "➕ إضافة عميل"), " وأدخل النوع (بنك/محفظة/دفع/آخر)."),
        el("li", {}, "احصل على المفاتيح — بعد الإنشاء ستحصل على ", el("code", {}, "tenant_id"), " + ", el("code", {}, "api_key"), " + ", el("code", {}, "hmac_secret"), ". سلّم هذه للعميل."),
        el("li", {}, "العميل يرسل معاملة — لكل معاملة يحسب ", el("code", {}, "HMAC-SHA256(body, hmac_secret)"), " ويرسلها إلى webhook."),
        el("li", {}, "AEGIS يعيد القرار — ", el("code", {}, "risk_score"), " + ", el("code", {}, "allow/challenge/review/block"), " + ", el("code", {}, "reasoning_ar"), "."),
        el("li", {}, "العميل يتصرف — ", el("code", {}, "allow"), ": نفّذ · ", el("code", {}, "challenge"), ": OTP · ", el("code", {}, "review"), ": احجز · ", el("code", {}, "block"), ": ارفض."),
      ),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🌐 نقاط النهاية (Endpoints)"),
      el("pre", { class: "code-block" },
`🔵 استقبال معاملة للفحص:
   POST /api/v1/wallet/webhook
   Headers: X-API-Key + x-wallet-signature (HMAC-SHA256)
   Body   : { transaction: {...}, context: {...} }
   Return : { tx_id, decision, risk_score, reasoning_ar, tenant_id }

🟢 آخر القرارات:
   GET  /api/v1/decisions/recent?limit=50

🟡 إدارة العملاء (Owner):
   GET  /api/v1/admin/tenants
   POST /api/v1/admin/tenants
   GET  /api/v1/admin/tenants/{id}
   POST /api/v1/admin/tenants/{id}/rotate-secret
   DELETE /api/v1/admin/tenants/{id}
   GET  /api/v1/admin/overview

🟣 المؤسسة (Merchant):
   POST /api/v1/admin/merchant/login
   GET  /api/v1/admin/merchant/stats
   GET  /api/v1/admin/merchant/decisions
   GET  /api/v1/admin/merchant/integration
`),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🔗 روابط مفيدة"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px" },
        docLink("📘 OpenAPI Docs (Swagger)", "/docs"),
        docLink("📗 ReDoc", "/redoc"),
        docLink("✅ Health check", "/api/v1/system/version"),
        docLink("🏦 بوابة المؤسسة", "/merchant/"),
        docLink("🛡️ لوحة التحقيقات", "/investigator/"),
        docLink("💳 المحفظة", "/"),
      ),
    ),
  );
}

function docLink(label, href) {
  return el("a", { href, target: "_blank",
    style: "background:var(--surface);border:1px solid var(--border);padding:14px;border-radius:10px;text-decoration:none;color:var(--text);display:block;transition:.15s",
    onmouseenter: e => e.target.style.borderColor = "var(--accent)",
    onmouseleave: e => e.target.style.borderColor = "var(--border)"
  },
    el("div", { style: "font-weight:700;color:var(--accent)" }, label),
    el("div", { style: "font-size:11px;color:var(--muted);margin-top:4px;direction:ltr" }, href),
  );
}

/* ─────────────────────────────────────────── PAGE: INVESTIGATORS ─── */
function renderInvestigators() {
  const em = el("input", { class: "form-control", type: "email", placeholder: "investigator@aegis.local", dir: "ltr" });
  const nm = el("input", { class: "form-control", placeholder: "اسم المحقق" });
  const pw = el("input", { class: "form-control", type: "password", placeholder: "كلمة مرور (8+ أحرف)" });
  const rows = (state.investigators || []).map(v => el("tr", {},
    el("td", { style: "font-size:12px" }, v.email),
    el("td", { style: "font-size:12.5px;font-weight:700" }, v.name),
    el("td", {}, el("span", { class: "badge " + (v.status === "active" ? "allow" : "block") }, v.status === "active" ? "نشط" : "موقوف")),
    el("td", { style: "font-size:11px" }, dt(v.created_at)),
    el("td", { style: "font-size:11px" }, v.last_login_at ? dt(v.last_login_at) : "لم يدخل"),
    el("td", {}, v.status === "active" ? el("button", { class: "btn sm danger",
      onclick: async () => {
        if (!confirm("إيقاف حساب هذا المحقق؟")) return;
        try { await api("/investigators/" + v.investigator_id, { method: "DELETE" }); toast("تم الإيقاف", "success"); await loadInvestigators(); renderPage(); }
        catch (e) { toast(e.message, "error"); }
      } }, "⛔ إيقاف") : null),
  ));
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🛡️ المحققون"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "حسابات محللي الاحتيال التي تدخل منصة التحقيقات"),
    el("div", { class: "card", style: "border-color:var(--brand)" },
      el("h3", { style: "margin-bottom:12px" }, "➕ إضافة محقق"),
      el("div", { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-bottom:12px" }, em, nm, pw),
      el("button", { class: "btn primary", onclick: async () => {
        try {
          await api("/investigators", { method: "POST", body: { email: em.value.trim(), name: nm.value.trim(), password: pw.value } });
          toast("تم إنشاء المحقق", "success"); em.value = ""; nm.value = ""; pw.value = "";
          await loadInvestigators(); renderPage();
        } catch (e) { toast(e.message, "error"); }
      } }, "➕ إنشاء"),
    ),
    el("div", { class: "card" },
      rows.length === 0 ? el("div", { style: "color:var(--muted);text-align:center;padding:30px" }, "لا يوجد محققون. أنشئ أول حساب أعلاه.") :
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "البريد"), el("th", {}, "الاسم"), el("th", {}, "الحالة"), el("th", {}, "أُنشئ"), el("th", {}, "آخر دخول"), el("th", {}, ""))),
        el("tbody", {}, ...rows))),
  );
}

/* ─────────────────────────────────────────── PAGE: RULES ─── */
function renderRules() {
  if (state.ruleDetail) return renderRuleDetail();
  const rows = (state.rules || []).map(r => el("tr", { class: "clickable", onclick: async () => { await loadRuleDetail(r.id); renderPage(); } },
    el("td", {}, el("code", { style: "font-size:11px" }, r.id)),
    el("td", { style: "font-size:12.5px;font-weight:700" }, r.name),
    el("td", {}, el("span", { class: "badge " + r.severity }, r.severity)),
    el("td", { style: "font-weight:700" }, r.score),
    el("td", {}, el("span", { class: "badge " + (r.enabled ? "allow" : "block") }, r.enabled ? "مفعَّلة" : "معطَّلة")),
    el("td", { style: "font-size:11px;color:var(--muted)" }, (r.tags || []).join(", ")),
  ));
  return el("div", {},
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px" },
      el("div", {},
        el("h1", { style: "font-size:1.7rem;font-weight:900" }, "📜 قواعد الاحتيال"),
        el("p", { style: "color:var(--muted);font-size:13px;margin-top:4px" }, (state.rules || []).length + " قاعدة منصة نشطة — اضغط لعرض التفاصيل والتفعيل/التعطيل"),
      ),
      el("button", { class: "btn primary", onclick: async () => { try { await apiRoot("/rules/reload", { method: "POST" }); } catch(e){} await loadRules(); renderPage(); toast("أُعيد تحميل القواعد", "success"); } }, "🔄 إعادة تحميل"),
    ),
    el("div", { class: "card" },
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "المعرّف"), el("th", {}, "الاسم"), el("th", {}, "الخطورة"), el("th", {}, "النقاط"), el("th", {}, "الحالة"), el("th", {}, "الوسوم"))),
        el("tbody", {}, ...rows))),
  );
}

function renderRuleDetail() {
  const r = state.ruleDetail;
  return el("div", {},
    el("button", { class: "btn sm", style: "margin-bottom:14px", onclick: () => { state.ruleDetail = null; renderPage(); } }, "→ رجوع"),
    el("div", { class: "card" },
      el("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:12px" },
        el("h3", {}, r.name), el("span", { class: "badge " + r.severity }, r.severity)),
      el("div", { class: "creds-box" },
        credRow("المعرّف", r.id),
        credRow("النقاط", r.score),
        credRow("الحالة", r.enabled ? "مفعَّلة" : "معطَّلة"),
        credRow("الوسوم", (r.tags || []).join(", ")),
      ),
      el("p", { style: "color:var(--muted);font-size:13px;margin:12px 0;line-height:1.9" }, r.description || ""),
      el("h4", { style: "color:var(--accent);margin-bottom:8px" }, "شرط التفعيل (JSONLogic):"),
      el("pre", { class: "code-block" }, JSON.stringify(r.when, null, 2)),
      el("div", { style: "margin-top:14px" },
        el("button", { class: "btn " + (r.enabled ? "danger" : "success"),
          onclick: async () => {
            try {
              await apiRoot("/rules/" + encodeURIComponent(r.id) + "/toggle", { method: "POST", body: { enabled: !r.enabled } });
              toast(r.enabled ? "عُطّلت القاعدة" : "فُعّلت القاعدة", "success");
              state.ruleDetail = null; await loadRules(); renderPage();
            } catch (e) { toast(e.message, "error"); }
          } }, r.enabled ? "⛔ تعطيل القاعدة" : "✅ تفعيل القاعدة")),
    ),
  );
}

/* ─────────────────────────────────────────── PAGE: MODELS ─── */
function renderModels() {
  const m = state.modelsStatus;
  if (!m) return el("div", { style: "color:var(--muted);text-align:center;padding:40px" }, "جارٍ التحميل…");
  const md = m.metadata || {};
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🧠 نماذج التعلم الآلي"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "حالة وجاهزية نماذج كشف الاحتيال"),
    el("div", { class: "grid" },
      kpi("الوضع", m.mode === "trained" ? "مدرَّب" : "بديل حتمي", m.mode === "trained" ? "نماذج حقيقية محمَّلة" : "⚠️ يستخدم بديلًا", m.mode === "trained" ? "success" : "warn"),
      kpi("الجاهزية", m.ready ? "جاهز" : "غير جاهز", "درجة ML في الدمج", m.ready ? "success" : "danger"),
      kpi("النماذج", (m.models || []).length, "المحمَّلة في الذاكرة", "brand"),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "📦 النماذج المحمَّلة"),
      (m.models || []).length === 0 ? el("div", { style: "color:var(--muted)" }, "لا نماذج مدرَّبة — يعمل البديل الحتمي.") :
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "الاسم"), el("th", {}, "الإصدار"), el("th", {}, "النوع"))),
        el("tbody", {}, ...(m.models || []).map(x => el("tr", {},
          el("td", { style: "font-weight:700" }, x.name),
          el("td", {}, el("code", { style: "font-size:11px" }, x.version)),
          el("td", {}, el("span", { class: "badge " + (x.type === "trained" ? "allow" : "review") }, x.type)),
        ))))),
    md && Object.keys(md).length ? el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "ℹ️ بيانات التدريب"),
      el("pre", { class: "code-block" }, JSON.stringify(md, null, 2)),
    ) : null,
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🎚️ عتبات ML الداخلية"),
      el("div", { class: "creds-box" },
        credRow("block", m.ml_thresholds?.block),
        credRow("review", m.ml_thresholds?.review),
      ),
    ),
  );
}

/* ─────────────────────────────────────────── PAGE: GRAPH ─── */
function renderGraph() {
  const gs = state.graphStats, gi = state.graphInsights;
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🕸️ ذكاء الشبكة"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "علاقات الحسابات/الأجهزة/العناوين وكشف الحلقات"),
    el("div", { class: "grid" },
      kpi("العقد", gs ? gs.nodes : "—", "حسابات + معاملات + أجهزة + IP", "brand"),
      kpi("الأضلاع", gs ? gs.edges : "—", "العلاقات", "info"),
      kpi("حسابات احتيال معروفة", gs ? gs.known_fraud_accounts : "—", "من قضايا مؤكدة", "danger"),
    ),
    gi ? el("div", { class: "split" },
      el("div", { class: "card" },
        el("h3", { style: "margin-bottom:10px" }, "💻 أجهزة مشتركة"),
        (gi.shared_devices || []).length === 0 ? el("div", { style: "color:var(--muted);font-size:13px" }, "لا أجهزة مشتركة.") :
        el("table", {},
          el("thead", {}, el("tr", {}, el("th", {}, "الجهاز"), el("th", {}, "#حسابات"))),
          el("tbody", {}, ...gi.shared_devices.map(s => el("tr", {},
            el("td", {}, el("code", { style: "font-size:11px" }, s.device_id)),
            el("td", { style: "font-weight:700;color:var(--warn)" }, s.account_count)))))),
      el("div", { class: "card" },
        el("h3", { style: "margin-bottom:10px" }, "🌐 IP مشتركة"),
        (gi.shared_ips || []).length === 0 ? el("div", { style: "color:var(--muted);font-size:13px" }, "لا IP مشتركة.") :
        el("table", {},
          el("thead", {}, el("tr", {}, el("th", {}, "IP"), el("th", {}, "#حسابات"))),
          el("tbody", {}, ...gi.shared_ips.map(s => el("tr", {},
            el("td", {}, el("code", { style: "font-size:11px" }, s.ip)),
            el("td", { style: "font-weight:700;color:var(--warn)" }, s.account_count)))))),
    ) : null,
  );
}

/* ─────────────────────────────────────────── PAGE RENDERER ─── */
async function renderPage() {
  const c = $("#content");
  if (!c) return;
  c.innerHTML = "<div style='color:#94A3B8;text-align:center;padding:40px'>جارٍ التحميل…</div>";
  try {
    if (state.page === "overview") {
      await Promise.all([loadOverview(), loadTenants()]);
      c.replaceChildren(renderOverview());
    } else if (state.page === "tenants") {
      await loadTenants();
      c.replaceChildren(renderTenants());
    } else if (state.page === "decisions") {
      await loadDecisions();
      c.replaceChildren(renderDecisions());
    } else if (state.page === "settings") {
      await loadSettings();
      c.replaceChildren(renderSettings());
    } else if (state.page === "investigators") {
      await loadInvestigators();
      c.replaceChildren(renderInvestigators());
    } else if (state.page === "fx") {
      await Promise.all([loadFxCurrencies(), loadFxRates()]);
      c.replaceChildren(renderFx());
    } else if (state.page === "watchlists") {
      await loadWatchlist();
      c.replaceChildren(renderWatchlists());
    } else if (state.page === "policy") {
      await loadPolicyTenants();
      c.replaceChildren(renderPolicyStudio());
    } else if (state.page === "audit") {
      await loadAudit();
      c.replaceChildren(renderAudit());
    } else if (state.page === "rules") {
      await loadRules();
      c.replaceChildren(renderRules());
    } else if (state.page === "models") {
      await loadModels();
      c.replaceChildren(renderModels());
    } else if (state.page === "graph") {
      await loadGraph();
      c.replaceChildren(renderGraph());
    } else if (state.page === "docs") {
      c.replaceChildren(renderDocs());
    }
  } catch (e) {
    if (String(e.message).includes("401")) {
      state.token = null; localStorage.removeItem(TK); render(); return;
    }
    c.innerHTML = "";
    c.appendChild(el("div", { style: "color:#FCA5A5;text-align:center;padding:30px" }, "⚠️ خطأ: " + e.message));
  }
}

/* ─────────────────────────────────────────── MAIN RENDER ─── */
function render() {
  const root = $("#app");
  root.innerHTML = "";
  if (!state.token) { root.appendChild(renderLogin()); return; }

  const pages = [
    { id: "overview",  icon: "📊", label: tl("نظرة عامة") },
    { id: "tenants",   icon: "🏢", label: tl("العملاء (بنوك ومحافظ)") },
    { id: "decisions", icon: "⚖️", label: tl("قرارات الاحتيال") },
    { id: "investigators", icon: "🛡️", label: tl("المحققون") },
    { id: "rules",     icon: "📜", label: tl("قواعد الاحتيال") },
    { id: "models",    icon: "🧠", label: tl("نماذج ML") },
    { id: "graph",     icon: "🕸️", label: tl("ذكاء الشبكة") },
    { id: "fx",         icon: "💱", label: tl("العملات و FX") },
    { id: "watchlists", icon: "🚫", label: tl("قوائم المراقبة") },
    { id: "policy",     icon: "🎛️", label: tl("استوديو السياسات") },
    { id: "audit",      icon: "🧾", label: tl("سجل التدقيق") },
    { id: "settings",  icon: "⚙️", label: tl("إعدادات النظام") },
    { id: "docs",      icon: "📖", label: tl("دليل التكامل") },
  ];

  root.appendChild(el("div", { class: "layout" },
    el("header", { class: "top" },
      el("div", { style: "display:flex;align-items:center;gap:10px" },
        el("span", { style: "font-size:1.7rem" }, "👑"),
        el("span", { class: "brand-title" }, "AEGIS Owner Portal"),
        el("span", { style: "font-size:12px;color:var(--muted)" }, "· بوابة مالك المنظومة"),
      ),
      el("div", { style: "display:flex;gap:10px;align-items:center" },
        el("span", { class: "badge allow" }, "Super Admin"),
        el("button", { class: "btn danger",
          onclick: () => { localStorage.removeItem(TK); state.token = null; render(); }
        }, L("🚪 خروج", "🚪 Logout")), el("button", { class: "btn", onclick: toggleLang }, L("EN", "عربي")),
      )
    ),
    el("aside", {},
      ...pages.map(p => el("div", {
        class: "nav" + (state.page === p.id ? " active" : ""),
        onclick: () => { state.page = p.id; state.selectedTenant = null; state.lastCreated = null; state.showAddForm = false; state.ruleDetail = null; render(); }
      }, el("span", {}, p.icon), el("span", {}, p.label))),
      el("div", { style: "margin-top:24px;padding:14px;background:var(--surface);border-radius:10px;font-size:11.5px" },
        el("div", { style: "color:var(--muted);margin-bottom:6px" }, "بوابات أخرى:"),
        el("a", { href: "/merchant/", target: "_blank", style: "color:var(--accent);display:block;margin-bottom:4px;text-decoration:none" }, "🏦 بوابة المؤسسة"),
        el("a", { href: "/investigator/", target: "_blank", style: "color:var(--accent);display:block;margin-bottom:4px;text-decoration:none" }, "🛡️ لوحة التحقيقات"),
        el("a", { href: "/", target: "_blank", style: "color:var(--accent);display:block;text-decoration:none" }, "💳 المحفظة"),
      )
    ),
    el("main", { id: "content" }),
  ));

  renderPage();
}

render();

/* ═══════════ TASK 11 — advanced admin pages (FX / Watchlists / Policy / Audit) ═══════════ */
function fmtTs(iso) { if (!iso) return "-"; const s = String(iso); return s.slice(0, 16).replace("T", " "); }

async function loadFxCurrencies() {
  try { const r = await api("/fx/currencies"); state.fxCurrencies = r.currencies || []; } catch { state.fxCurrencies = []; }
}
async function loadFxRates() {
  try { const r = await api("/fx/rates"); state.fxRates = r.rates || []; } catch { state.fxRates = []; }
}
async function loadWatchlist() {
  try { const r = await api("/watchlist"); state.watchlistEntries = r.entries || []; } catch { state.watchlistEntries = []; }
}
async function loadPolicyTenants() {
  try { const r = await api("/tenants"); state.policyTenants = r.tenants || []; } catch { state.policyTenants = []; }
}
async function loadAudit() {
  try { const r = await api("/audit?limit=200"); state.auditLog = Array.isArray(r) ? r : (r.events || []); } catch { state.auditLog = []; }
}

function renderFx() {
  const cur = state.fxCurrencies || [];
  const rates = state.fxRates || [];
  const cc = el("input", { class: "form-control", placeholder: "USD", maxlength: 3, dir: "ltr", style: "width:90px" });
  const cn = el("input", { class: "form-control", placeholder: "اسم العملة", style: "width:170px" });
  const cmu = el("input", { class: "form-control", type: "number", value: 2, style: "width:80px" });
  const rb = el("input", { class: "form-control", placeholder: "YER", maxlength: 3, dir: "ltr", style: "width:80px" });
  const rq = el("input", { class: "form-control", placeholder: "USD", maxlength: 3, dir: "ltr", style: "width:80px" });
  const rr = el("input", { class: "form-control", type: "number", step: "any", placeholder: "0.000636", dir: "ltr", style: "width:130px" });
  const rsrc = el("input", { class: "form-control", value: "aegis_reference", dir: "ltr", style: "width:150px" });
  const fmsg = el("div", { style: "font-size:12.5px;min-height:16px;margin-top:6px" });
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "💱 إدارة العملات وأسعار الصرف"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "الأسعار تاريخية (append-only) — سعر جديد لا يُعدّل اللقطة التي اتُّخذ بها قرار سابق"),
    el("div", { class: "grid" },
      kpi("العملات", cur.length, "المسجَّلة", "brand"),
      kpi("أسعار الصرف", rates.length, "لقطات محفوظة", "info"),
      kpi("أزواج فريدة", new Set(rates.map(r => (r.base_ccy || "") + "/" + (r.quote_ccy || ""))).size, "Base/Quote", "purple"),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "🪙 العملات المدعومة"),
      el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px" }, cc, cn, cmu,
        el("button", { class: "btn success", onclick: async () => {
          fmsg.textContent = ""; fmsg.style.color = "var(--muted)";
          if (!cc.value.trim() || !cn.value.trim()) { fmsg.textContent = "أدخل الرمز والاسم"; fmsg.style.color = "#FCA5A5"; return; }
          try {
            await api("/fx/currencies", { method: "POST", body: { code: cc.value.trim().toUpperCase(), name: cn.value.trim(), minor_unit: Number(cmu.value || 2) } });
            toast("أُضيفت العملة", "success"); await loadFxCurrencies(); render();
          } catch (e) { fmsg.textContent = e.message; fmsg.style.color = "#FCA5A5"; }
        } }, "➕ إضافة عملة")),
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "الرمز"), el("th", {}, "الاسم"), el("th", {}, "الوحدة الصغرى"), el("th", {}, "التقريب"), el("th", {}, "الحالة"))),
        el("tbody", {}, ...cur.map(x => el("tr", {},
          el("td", { style: "font-weight:700" }, el("code", {}, x.code)),
          el("td", {}, x.name),
          el("td", {}, String(x.minor_unit)),
          el("td", {}, String(x.round_unit)),
          el("td", {}, el("span", { class: "badge " + (x.active ? "allow" : "block") }, x.active ? "نشطة" : "موقوفة")),
        ))))),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "📈 أسعار الصرف (لقطات تاريخية)"),
      el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px" }, rb, rq, rr, rsrc,
        el("button", { class: "btn success", onclick: async () => {
          fmsg.textContent = ""; fmsg.style.color = "var(--muted)";
          if (!rb.value.trim() || !rq.value.trim() || !rr.value) { fmsg.textContent = "أدخل الزوج والسعر"; fmsg.style.color = "#FCA5A5"; return; }
          try {
            await api("/fx/rates", { method: "POST", body: { base_ccy: rb.value.trim().toUpperCase(), quote_ccy: rq.value.trim().toUpperCase(), rate: Number(rr.value), source: rsrc.value.trim() || "aegis_reference" } });
            toast("أُضيف السعر (لقطة جديدة)", "success"); await loadFxRates(); render();
          } catch (e) { fmsg.textContent = e.message; fmsg.style.color = "#FCA5A5"; }
        } }, "➕ إضافة سعر")),
      fmsg,
      rates.length === 0 ? el("div", { style: "color:var(--muted)" }, "لا أسعار مسجَّلة بعد.") :
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "الزوج"), el("th", {}, "السعر"), el("th", {}, "النوع"), el("th", {}, "المصدر"), el("th", {}, "صالح من"), el("th", {}, "صالح إلى"), el("th", {}, "سُجّل"))),
        el("tbody", {}, ...rates.map(x => el("tr", {},
          el("td", { style: "font-weight:700" }, el("code", { style: "font-size:11px" }, (x.base_ccy || "") + "/" + (x.quote_ccy || ""))),
          el("td", {}, String(x.rate)),
          el("td", {}, x.rate_type || "mid"),
          el("td", {}, el("span", { class: "badge info" }, x.source || "")),
          el("td", { style: "font-size:11px" }, fmtTs(x.valid_from)),
          el("td", { style: "font-size:11px" }, x.valid_to ? fmtTs(x.valid_to) : "مفتوح"),
          el("td", { style: "font-size:11px" }, fmtTs(x.fetched_at)),
        ))))),
  );
}

function renderWatchlists() {
  const rows = state.watchlistEntries || [];
  const lt = el("select", { class: "form-control", style: "width:170px" },
    ...["sanctions", "high_risk_country", "pep", "custom"].map(o => el("option", { value: o }, o)));
  const val = el("input", { class: "form-control", placeholder: "IR / اسم / قيمة", dir: "ltr", style: "width:220px" });
  const wmsg = el("div", { style: "font-size:12.5px;min-height:16px;margin-top:6px" });
  const byType = {};
  rows.forEach(r => { const k = r.list_type || "custom"; byType[k] = (byType[k] || 0) + 1; });
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🚫 قوائم المراقبة (AML / Watchlists)"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "عقوبات، PEP، دول عالية المخاطر — تُستخدم في فحص AML قبل القرار"),
    el("div", { class: "grid" },
      kpi("إجمالي الإدخالات", rows.length, "كل القوائم", "brand"),
      kpi("عقوبات", byType.sanctions || 0, "sanctions", "danger"),
      kpi("دول عالية المخاطر", byType.high_risk_country || 0, "high_risk_country", "warn"),
      kpi("PEP", byType.pep || 0, "pep", "info"),
    ),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "➕ إضافة إدخال"),
      el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;align-items:center" }, lt, val,
        el("button", { class: "btn success", onclick: async () => {
          wmsg.textContent = ""; wmsg.style.color = "var(--muted)";
          if (!val.value.trim()) { wmsg.textContent = "أدخل القيمة"; wmsg.style.color = "#FCA5A5"; return; }
          try {
            await api("/watchlist", { method: "POST", body: { list_type: lt.value, value: val.value.trim() } });
            toast("أُضيف للقائمة", "success"); await loadWatchlist(); render();
          } catch (e) { wmsg.textContent = e.message; wmsg.style.color = "#FCA5A5"; }
        } }, "إضافة")),
      wmsg),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "📋 الإدخالات الحالية"),
      rows.length === 0 ? el("div", { style: "color:var(--muted)" }, "لا إدخالات.") :
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "النوع"), el("th", {}, "القيمة"), el("th", {}, "المؤسسة"))),
        el("tbody", {}, ...rows.map(x => el("tr", {},
          el("td", {}, el("span", { class: "badge " + (x.list_type === "sanctions" ? "block" : x.list_type === "high_risk_country" ? "review" : "info") }, x.list_type)),
          el("td", { style: "font-weight:700" }, el("code", {}, x.value)),
          el("td", { style: "font-size:11px;color:var(--muted)" }, x.tenant_id || "platform"),
        ))))),
  );
}

function renderPolicyStudio() {
  const tenants = state.policyTenants || [];
  const sel = state.policySelected;
  const pmsg = el("div", { style: "font-size:12.5px;min-height:16px;margin-top:6px" });
  const picker = el("select", { class: "form-control", style: "min-width:240px" },
    el("option", { value: "" }, "— اختر مؤسسة لتحرير سياستها —"),
    ...tenants.map(t => el("option", { value: t.tenant_id }, (t.name || t.tenant_id))));
  picker.value = sel ? sel.tenant_id : "";
  picker.addEventListener("change", async () => {
    const tid = picker.value;
    if (!tid) { state.policySelected = null; render(); return; }
    try { state.policySelected = await api("/tenants/" + tid); } catch (e) { state.policySelected = null; toast(e.message, "error"); }
    render();
  });

  let editor = el("div", { style: "color:var(--muted);padding:20px;text-align:center" }, "اختر مؤسسة لعرض سياستها وتحريرها.");
  if (sel) {
    let pol = {};
    try { pol = sel.policy_json ? (typeof sel.policy_json === "string" ? JSON.parse(sel.policy_json) : sel.policy_json) : {}; } catch { pol = {}; }
    const th = pol.thresholds || {};
    const tc = el("input", { class: "form-control", type: "number", step: "any", value: th.challenge != null ? th.challenge : "", style: "width:110px" });
    const tr = el("input", { class: "form-control", type: "number", step: "any", value: th.review != null ? th.review : "", style: "width:110px" });
    const tb = el("input", { class: "form-control", type: "number", step: "any", value: th.block != null ? th.block : "", style: "width:110px" });
    const fx = el("select", { class: "form-control", style: "width:160px" },
      ...["", "review", "block", "allow"].map(o => el("option", { value: o }, o === "" ? "افتراضي" : o)));
    fx.value = pol.fx_missing_action || "";
    editor = el("div", {},
      el("div", { class: "card" },
        el("h3", { style: "margin-bottom:10px" }, "🎛️ سياسة: " + (sel.name || sel.tenant_id)),
        el("div", { style: "font-size:12px;color:var(--muted);margin-bottom:12px" }, "عتبات القرار ومعالجة غياب سعر الصرف — تُحفظ فورًا وتُستخدم في القرارات القادمة"),
        el("div", { style: "display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end" },
          el("div", {}, el("label", { style: "font-size:12px;color:var(--muted);display:block;margin-bottom:4px" }, "عتبة Challenge"), tc),
          el("div", {}, el("label", { style: "font-size:12px;color:var(--muted);display:block;margin-bottom:4px" }, "عتبة Review"), tr),
          el("div", {}, el("label", { style: "font-size:12px;color:var(--muted);display:block;margin-bottom:4px" }, "عتبة Block"), tb),
          el("div", {}, el("label", { style: "font-size:12px;color:var(--muted);display:block;margin-bottom:4px" }, "عند غياب FX"), fx),
          el("button", { class: "btn success", onclick: async () => {
            pmsg.textContent = ""; pmsg.style.color = "var(--muted)";
            const body = {};
            const ths = {};
            if (tc.value !== "") ths.challenge = Number(tc.value);
            if (tr.value !== "") ths.review = Number(tr.value);
            if (tb.value !== "") ths.block = Number(tb.value);
            if (Object.keys(ths).length) body.thresholds = ths;
            if (fx.value) body.fx_missing_action = fx.value;
            try {
              await api("/tenants/" + sel.tenant_id + "/policy", { method: "PUT", body });
              toast("حُفظت السياسة", "success");
              state.policySelected = await api("/tenants/" + sel.tenant_id);
              render();
            } catch (e) { pmsg.textContent = e.message; pmsg.style.color = "#FCA5A5"; }
          } }, "💾 حفظ السياسة")),
        pmsg),
      el("div", { class: "card" },
        el("h3", { style: "margin-bottom:10px" }, "🔍 السياسة الحالية (JSON)"),
        el("pre", { class: "code-block" }, JSON.stringify(pol, null, 2))),
    );
  }
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🎛️ استوديو السياسات (Policy Studio)"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "تحرير سياسة القرار لكل مؤسسة — التغييرات تُسجَّل في سجل التدقيق"),
    el("div", { class: "card" }, el("label", { style: "font-size:12px;color:var(--muted);display:block;margin-bottom:6px" }, "المؤسسة"), picker),
    editor,
  );
}

function renderAudit() {
  const rows = state.auditLog || [];
  const vr = state.auditVerifyResult;
  return el("div", {},
    el("h1", { style: "font-size:1.7rem;font-weight:900;margin-bottom:6px" }, "🧾 سجل التدقيق (Audit Log)"),
    el("p", { style: "color:var(--muted);font-size:13px;margin-bottom:16px" }, "سجل مقاوم للعبث بسلسلة SHA-256 — تعديل أي قيد يكسر السلسلة ويُكشَف بالتحقق"),
    el("div", { class: "card" },
      el("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap" },
        el("button", { class: "btn success", onclick: async () => {
          try { state.auditVerifyResult = await api("/audit-verify"); } catch (e) { state.auditVerifyResult = { error: e.message }; }
          render();
        } }, "🔗 التحقق من سلامة السلسلة"),
        el("button", { class: "btn", onclick: async () => { await loadAudit(); render(); } }, "↻ تحديث"),
      ),
      vr ? el("pre", { class: "code-block", style: "margin-top:12px" }, JSON.stringify(vr, null, 2)) : null),
    el("div", { class: "card" },
      el("h3", { style: "margin-bottom:12px" }, "📜 الأحداث الأخيرة (" + rows.length + ")"),
      rows.length === 0 ? el("div", { style: "color:var(--muted)" }, "لا أحداث.") :
      el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "الوقت"), el("th", {}, "المؤسسة"), el("th", {}, "الفاعل"), el("th", {}, "الحدث"), el("th", {}, "المورد"), el("th", {}, "المعرف"))),
        el("tbody", {}, ...rows.map(x => el("tr", {},
          el("td", { style: "font-size:11px" }, fmtTs(x.created_at || x.timestamp)),
          el("td", { style: "font-size:11px" }, x.tenant_id || "platform"),
          el("td", {}, x.actor || x.actor_id || ""),
          el("td", {}, el("span", { class: "badge info" }, x.event_type || x.action || "")),
          el("td", { style: "font-size:11px" }, x.resource || ""),
          el("td", { style: "font-size:11px" }, el("code", {}, String(x.resource_id || "").slice(0, 18))),
        ))))),
  );
}
