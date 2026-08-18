/* AEGIS Owner Portal — Super Admin (Multi-Tenant Control) */
const API = "/api/v1/admin";
const AEGIS_ROOT = "/api/v1";
const TK = "aegis_owner_token";

const state = {
  token: localStorage.getItem(TK),
  page: "overview",
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
  if (!r.ok) throw new Error(d.detail || d.message || ("خطأ " + r.status));
  return d;
}

async function apiRoot(path, opts = {}) {
  const h = { "Content-Type": "application/json", "X-Owner-Token": state.token, ...(opts.headers || {}) };
  const r = await fetch(AEGIS_ROOT + path, { ...opts, headers: h, body: opts.body ? JSON.stringify(opts.body) : undefined });
  const txt = await r.text();
  let d = {};
  try { d = txt ? JSON.parse(txt) : {}; } catch { d = { raw: txt }; }
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
      el("td", {}, el("span", { class: "badge allow" }, t.status || "active")),
      el("td", {},
        el("button", { class: "btn", style: "padding:5px 10px;font-size:11px;margin-left:4px",
          onclick: async () => { try { await loadTenantDetail(t.tenant_id); render(); } catch (e) { toast(e.message, "error"); } }
        }, "🔌 عرض المفاتيح"),
        el("button", { class: "btn danger", style: "padding:5px 10px;font-size:11px",
          onclick: () => deleteTenant(t.tenant_id)
        }, "🗑️")),
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
    { id: "overview",  icon: "📊", label: "نظرة عامة" },
    { id: "tenants",   icon: "🏢", label: "العملاء (بنوك ومحافظ)" },
    { id: "decisions", icon: "⚖️", label: "قرارات الاحتيال" },
    { id: "investigators", icon: "🛡️", label: "المحققون" },
    { id: "rules",     icon: "📜", label: "قواعد الاحتيال" },
    { id: "models",    icon: "🧠", label: "نماذج ML" },
    { id: "graph",     icon: "🕸️", label: "ذكاء الشبكة" },
    { id: "settings",  icon: "⚙️", label: "إعدادات النظام" },
    { id: "docs",      icon: "📖", label: "دليل التكامل" },
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
        }, "🚪 خروج"),
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
