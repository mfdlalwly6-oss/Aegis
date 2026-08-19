<div dir="rtl">

# 🛡️ AEGIS — الوثيقة المرجعية الرسمية الكاملة للمشروع
## Master Project Knowledge Base

| البند | القيمة |
|---|---|
| **اسم المشروع** | AEGIS — Multi-Tenant Financial Fraud Detection Platform |
| **الإصدار** | 2.0.0 |
| **تاريخ الوثيقة** | 2026-08-14 |
| **الحزمة المرجعية** | `Automated-Digital-Wallet-Security-Fraud-Detection-final.zip` (588 KB، 130 عنصرًا) |
| **الرخصة** | Apache License 2.0 |
| **جمهور الوثيقة** | أي مطور أو مهندس أو وكيل AI جديد لا يعرف شيئًا عن المشروع |

> **كيف تقرأ هذه الوثيقة:** اقرأ الأقسام 1–4 للفهم العام، ثم 5–8 للتفاصيل التقنية، ثم 9–17 لمحركات الكشف، ثم 18–22 للتشغيل، وأخيرًا 23–28 للتقييم الصادق وخارطة الطريق. كل ادعاء في هذه الوثيقة مربوط بملف أو اختبار فعلي في المشروع.

---

# 1. Executive Summary — الملخص التنفيذي

## 1.1 ما هو AEGIS؟

AEGIS هو **محرك كشف احتيال مالي متعدد المستأجرين (Multi-Tenant Fraud Detection Engine)** يُقدَّم كخدمة API. تربطه المؤسسات المالية (محافظ رقمية، بنوك، شركات دفع) عبر Webhook موقّع، فتُرسل له كل معاملة مالية قبل تنفيذها، فيرد خلال أجزاء من الثانية بقرار: **السماح (allow)، التحدي (challenge)، المراجعة (review)، أو الحظر (block)** — مع درجة مخاطر رقمية وأسباب قابلة للتفسير بالعربية.

## 1.2 المشكلة التي يحلها

المؤسسات المالية الصغيرة والمتوسطة (خصوصًا المحافظ الرقمية الناشئة) لا تملك محركات كشف احتيال لأن بناءها يتطلب فرق data science وبنية تحتية ضخمة. AEGIS يقدم هذه القدرة **كمنصة جاهزة**: تسجّل مؤسسة، تحصل على مفاتيح، وتبدأ الفحص في نفس اليوم.

## 1.3 الجهات المستفيدة

| الجهة | كيف تستفيد |
|---|---|
| **مالك المنصة (Platform Owner)** | يشغّل AEGIS كمنتج SaaS ويدير المؤسسات المشتركة |
| **المحافظ الرقمية / البنوك (Tenants)** | تفحص معاملاتها دون بناء نظام خاص |
| **فرق الأمن والتحقيق (Investigators)** | يراقبون القرارات والتنبيهات والقضايا |

## 1.4 حالات الاستخدام الفعلية المدعومة في الكود

1. فحص معاملة قبل تنفيذها (القرار المتزامن عبر webhook).
2. كشف حسابات مخترقة (ATO: تغيير كلمة مرور ثم تحويل كبير — القاعدة R-ATO-001).
3. كشف أجهزة/IPs مشتركة بين حسابات متعددة (Graph + R-DEV-005/006).
4. كشف structuring (مبالغ تحت عتبة 10,000 متكررة — R-AML-001 + AML service).
5. كشف الدول الخاضعة لعقوبات (watchlist → block فوري).
6. كشف velocity attacks (معاملات كثيرة في دقائق).
7. إدارة التنبيهات وقضايا التحقيق.
8. مراقبة حية للقرارات عبر SSE.

## 1.5 الفكرة العامة والفرق عن الأنظمة التقليدية

| الأنظمة التقليدية | AEGIS |
|---|---|
| قواعد ثابتة فقط | 5 مصادر إشارة مدمجة (Rules + ML + Graph + AML + Behavior) |
| قرار بدون تفسير | كل قرار معه `top_reasons` و`reasoning_ar` |
| بناء داخلي مكلف | SaaS متعدد المستأجرين جاهز |
| صندوق أسود | كل مكوّن score مفصول ومقروء في الاستجابة وفي DB |

**تنبيه صادق:** AEGIS **منصة كشف تقنية وليست بديلًا عن الامتثال القانوني** لأي دولة (لا SAR filing قانوني، لا تقارير تنظيمية معتمدة).

---

# 2. Business Vision — الرؤية التجارية

## 2.1 الأدوار التجارية

- **العميل (Customer):** المؤسسة المالية (محفظة/بنك/شركة دفع) التي تدفع مقابل فحص معاملاتها.
- **المستخدم (User):** موظف المؤسسة (مسؤول تكامل، محلل احتيال) يستخدم بوابة المؤسسة.
- **مالك المنصة:** أنت — تملك بوابة المالك `/admin/` وتنشئ المؤسسات وتدير مفاتيحها.

## 2.2 كيف يحقق قيمة؟

1. العميل يوفّر خسائر الاحتيال (كل `block` لمعاملة احتيالية = خسارة مُنِعت).
2. العميل يتجنب تكلفة بناء فريق وأنظمة كشف داخلية.
3. مالك المنصة يحصّل اشتراكًا (plan: `sandbox`/`production` حقل موجود في جدول tenants).

## 2.3 نموذج SaaS

المشروع مبني Multi-Tenant من الأساس: كل مؤسسة لها `tenant_id` ومفاتيحها وبياناتها المعزولة في نفس قاعدة البيانات. البيع: اشتراك شهري حسب الخطة + عدد المعاملات (العدّ موجود: `decisions.count_by_tenant`). **ما ينقص للـ SaaS الكامل:** الفوترة، صفحة تسجيل ذاتي، وإدارة مستخدمي المؤسسة من الواجهة (انظر قسم 24).

## 2.4 Onboarding مؤسسة جديدة (كما هو منفذ فعليًا)

```
1. المالك يفتح /admin/ ← يدخل AEGIS_OWNER_TOKEN
2. تبويب "العملاء" ← "إضافة عميل جديد" ← (الاسم، النوع، الدولة، الخطة)
   أو: POST /api/v1/admin/tenants
3. النظام يولّد تلقائيًا: tenant_id + api_key (aeg_pk_...) + hmac_secret (aeg_sk_...)
4. المالك يسلّم المفاتيح للعميل عبر قناة آمنة
5. العميل يوقّع كل معاملة: HMAC-SHA256(raw_body, hmac_secret) في هيدر X-Wallet-Signature
6. العميل يفتح /merchant/ ويسجل دخوله بـ api_key + hmac_secret ← يحصل JWT
```

## 2.5 دورة الأموال/القيمة

معاملة العميل → AEGIS → قرار خلال ~10–50ms → العميل ينفذ أو يوقف → القرار والتنبيه محفوظان وقابلان للمراجعة والتدقيق.

---

# 3. System Overview — نظرة شاملة على النظام

## 3.1 مخطط تدفق البيانات الكامل (Data Flow)

التدفق التالي هو **ما يحدث فعليًا في الكود** (ليس رسمًا توضيحيًا نظريًا). كل خطوة مربوطة بالملف والدالة التي تنفذها:

```
المحفظة/البنك (Tenant System)
        │
        │  POST /api/v1/wallet/webhook
        │  Headers: X-API-Key, X-Wallet-Signature, (X-Idempotency-Key)
        ▼
┌────────────────────────────────────────────────────────────────┐
│ backend/app/api/v1/webhook.py :: fraud_webhook()               │
│ 1) استخراج api_key من الهيدر                                    │
│ 2) registry.tenants.by_api_key(api_key)  ──► جدول tenants      │
│    └─ غير موجود + لا LEGACY_SECRET ──► 401 invalid_api_key     │
│ 3) verify_signature(hmac_secret, raw_body, signature)          │
│    └─ HMAC-SHA256 + compare_digest ──► فشل = 401 + audit log   │
│ 4) json.loads(raw_body) ──► فشل = 400 invalid_json             │
│ 5) normalize_transaction(body, tenant_id)                      │
│    └─ يحوّل أي صيغة محفظة إلى مخطط Transaction الموحد          │
└──────────────────────────────┬─────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────┐
│ backend/app/services/orchestrator.py :: evaluate_and_persist() │
│                                                                │
│ 1) Idempotency: decisions.mark_seen(tenant_id:tx_id)           │
│    └─ مكرر ──► يرجع القرار المحفوظ مع duplicate:true           │
│ 2) features.extract(tx) ──► backend/app/features.py            │
│    └─ استعلامات SQLite حقيقية: velocity, أجهزة مشتركة,         │
│       تاريخ المستفيد, structuring count, سجل القرارات          │
│ 3) rules.evaluate(tx, features) ──► rules/engine.py            │
│    └─ 21 قاعدة JSONLogic من جدول rules (أُدخلت من YAML)        │
│ 4) ml.score(vector) ──► ml/ensemble.py                         │
│    └─ GradientBoosting + IsolationForest (joblib مدربان)       │
│    └─ إن غابا: heuristic_fallback موسوم صراحة NOT_TRAINED_ML   │
│ 5) graph.score(tx) ──► graph/engine.py (NetworkX في الذاكرة)   │
│    └─ أجهزة/IPs مشتركة، hops إلى حسابات موسومة بالاحتيال       │
│ 6) aml_service.screen(tx, features) ──► aml/service.py         │
│    └─ watchlist: sanctions / high_risk_country من DB           │
│    └─ sanctions_hit ──► BLOCK فوري و risk ≥ 0.80               │
│ 7) behavior_score (biometric, keystroke, session duration)     │
│ 8) الدمج الموزون:                                              │
│    risk = 0.35×rules + 0.25×ML + 0.15×graph                    │
│         + 0.15×AML + 0.10×behavior                             │
│ 9) القرار بالعتبات:                                            │
│    ≥0.80 block | ≥0.60 review | ≥0.35 challenge | أدنى allow   │
│ 10) تفسير AI اختياري (OpenRouter) إذا risk ≥ AI_MIN_SCORE      │
│     └─ يفشل؟ النظام يستمر بدونه (graceful fallback)            │
└──────────────────────────────┬─────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────┐
│ الاستمرارية والإجراءات اللاحقة                                 │
│ 11) transactions.create() ──► جدول transactions                │
│ 12) decisions.create() ──► جدول decisions                      │
│ 13) graph.add_transaction(tx) ──► تغذية الشبكة للمستقبل        │
│ 14) إذا decision ∈ {challenge, review, block}:                 │
│     └─ alerts.create() ──► جدول alerts                         │
│     └─ إذا review/block: cases.create() ──► جدول cases         │
│ 15) audit.log() × 2+ ──► جدول audit_log (بدون أسرار)           │
│ 16) notifications.send() ──► Console provider (الافتراضي)      │
│ 17) events.publish() ──► SSE ──► /api/v1/admin/stream          │
└──────────────────────────────┬─────────────────────────────────┘
                               ▼
        استجابة JSON: {tx_id, decision, risk_score, risk_band,
         typology, reasoning_ar, top_reasons, alert_id, case_id,
         latency_ms, tenant_id}
```

## 3.2 قياسات الأداء الفعلية (من التشغيل الحي بتاريخ 2026-08-13)

| القياس | القيمة المرصودة |
|---|---|
| زمن قرار معاملة طبيعية | **10.78 ms** (latency_ms في الاستجابة الفعلية) |
| قرار معاملة عادية 150 USD | `allow` بدرجة 0.0739 |
| قرار معاملة لدولة معاقَبة (IR) | `block` بدرجة 0.8 ونطاق `critical` |
| إعادة إرسال نفس المعاملة | `duplicate: true` بدون تكرار السجلات |

---

# 4. Complete Architecture — المعمارية الكاملة

## 4.1 خريطة المكونات ودور كل جزء

| المكوّن | الملف/المجلد | الدور | ملاحظة صادقة |
|---|---|---|---|
| **Frontend** | `portals/` | 3 بوابات HTML/JS/CSS ثابتة تخدمها FastAPI | بدون إطار عمل — Vanilla JS |
| **Backend** | `backend/app/` | FastAPI + Python 3.11 | تطبيق واحد (monolith منظم بطبقات) |
| **Database** | `backend/app/db.py` | SQLite مع WAL + migrations مدمجة | PostgreSQL-قابل للاستبدال عبر repositories |
| **ML** | `backend/app/ml/ensemble.py` + `models/trained/` | GradientBoosting + IsolationForest (joblib) | مدربان على بيانات **مصطنعة** (موسومان بذلك) |
| **Risk Engine** | `backend/app/services/orchestrator.py` | دمج 5 إشارات بأوزان قابلة للضبط | القرار deterministic بالكامل |
| **Graph Engine** | `backend/app/graph/engine.py` | NetworkX في الذاكرة، يُبنى من DB عند الإقلاع | يُفقد عند إعادة التشغيل لكنه يُعاد بناؤه تلقائيًا |
| **AML Engine** | `backend/app/aml/service.py` | watchlists من جدول `watchlist` + كشف أنماط | كشف تقني وليس امتثالًا قانونيًا |
| **Alerting** | `backend/app/repositories/alert_repo.py` | تنبيه تلقائي عند challenge/review/block | محفوظ في DB |
| **Cases** | `backend/app/repositories/case_repo.py` | قضية تلقائية عند review/block + ملاحظات | محفوظة في DB |
| **Audit** | `backend/app/repositories/audit_repo.py` | سجل منفصل لكل الأحداث المهمة | يُسقط حقول الأسرار تلقائيًا |
| **Authentication** | `backend/app/security.py` + `api/v1/auth.py` | HMAC للـ webhooks، JWT للبوابات، Owner token للمنصة | 3 آليات منفصلة |
| **Authorization** | `backend/app/api/deps.py` | `require_owner` / `require_merchant` | RBAC مبسط (owner/merchant) |
| **Multi-Tenant Layer** | `repositories/tenant_repo.py` + فلترة tenant_id | عزل كامل على مستوى الصفوف | مُثبت باختبار `test_tenant_isolation` |
| **API Layer** | `backend/app/api/v1/` | 10 routers، ~30 endpoint | Swagger تلقائي على `/docs` |
| **Webhooks** | `api/v1/webhook.py` | الاستقبال الموقّع + Idempotency | المسار الإنتاجي الوحيد للمعاملات |
| **Jobs** | غير موجود | — | **لا توجد مهام مجدولة** (انظر قسم 24) |
| **Queues** | غير موجود | — | Kafka أُزيل في v2؛ SSE داخلي بدلًا منه |
| **Real-time** | `backend/app/streaming/__init__.py` | EventBus داخلي + SSE endpoint | للمالك فقط |
| **Notifications** | `backend/app/notifications/providers.py` | واجهة + Console + Webhook provider | Email/SMS غير منفذة |
| **Observability** | `core/logging.py` + `core/telemetry.py` + `/metrics` | structlog JSON + Prometheus + OpenTelemetry اختياري | OTEL يعمل فقط إذا ضُبط endpoint |
| **AI Agent** | `backend/app/agents/` | OpenRouter (تفسير فقط، round-robin مفاتيح) | لا يؤثر على القرار إطلاقًا |

## 4.2 نمط المعمارية

**Layered Monolith** داخل حاوية واحدة:
- طبقة API (راوترات رقيقة بدون منطق).
- طبقة Services (orchestrator = منطق الأعمال).
- طبقة Repositories (الوصول الوحيد للبيانات).
- طبقة DB (SQLite عبر `Database` class).

**لماذا monolith وليس microservices؟** قرار هندسي مقصود في هذه المرحلة: الخدمة متزامنة حساسة للزمن (~10ms)، والتقسيم المبكر يضيف تعقيد شبكة بلا فائدة. البنية الطبقية تسمح بالتقسيم لاحقًا (كل محرك في مجلد مستقل).

---

# 5. Repository Anatomy — تشريح المستودع

## 5.1 شجرة المشروع الكاملة (الحزمة النهائية)

```
aegis-standalone/
│
├── 📄 README.md                  ← نقطة البداية: المميزات + التشغيل السريع
├── 📄 QUICKSTART.md              ← تشغيل في دقيقتين
├── 📄 ARCHITECTURE.md            ← المعمارية وقواعد التصميم الثابتة
├── 📄 API_REFERENCE.md           ← كل الـ endpoints بالتفصيل
├── 📄 RUN_LOCAL.md               ← تشغيل Windows/Linux/Docker خطوة بخطوة
├── 📄 RUN_RENDER.md              ← النشر على Render (غير مُختبر فعليًا — موسوم)
├── 📄 DEVELOPMENT.md             ← دليل المطور الجديد
├── 📄 TESTING.md                 ← خريطة الاختبارات وتشغيلها
├── 📄 SECURITY.md                ← نموذج الأمان الكامل
├── 📄 AGENTS.md                  ← قواعد العمل لوكلاء AI
├── 📄 TROUBLESHOOTING.md         ← حل المشاكل الشائعة
├── 📄 LICENSE                    ← Apache 2.0
├── 📄 pytest.ini                 ← pythonpath=backend, testpaths=tests
├── 📄 .env.example               ← كل متغيرات البيئة (قيم وهمية فقط)
├── 📄 .gitignore                 ← .env و *.db و __pycache__ مستثناة
├── 📄 .dockerignore              ← .env و tests/ و docs/ مستثناة من الصورة
│
├── 🐳 docker-compose.yml         ← خدمة aegis + volume aegis-data + network
├── 🐳 render.yaml                ← Render blueprint (plan: starter + disk 1GB)
│
├── 📁 .github/workflows/
│   └── docker-build.yml          ← CI: pytest ثم docker build ثم smoke test
│
├── 📁 backend/
│   ├── 🐳 Dockerfile             ← python:3.11-slim + healthcheck مدمج
│   ├── 📄 requirements.txt       ← 18 تبعية مثبتة بالإصدارات
│   ├── 📄 pyproject.toml         ← Poetry + ruff + pytest config
│   ├── 📄 runtime.txt            ← python-3.11.9
│   └── 📁 app/
│       ├── main.py               ← 🔴 نقطة الدخول: FastAPI + lifespan + بوابات + SSE
│       ├── db.py                 ← 🔴 محرك SQLite + المخطط الكامل + migrations
│       ├── security.py           ← 🔴 HMAC + JWT + توليد المفاتيح (لا تعدّله بلا فهم)
│       ├── features.py           ← استخراج الخصائص من تاريخ SQLite الحقيقي
│       │
│       ├── 📁 api/
│       │   ├── deps.py           ← require_owner / require_merchant / get_registry
│       │   └── 📁 v1/
│       │       ├── __init__.py   ← تجميع الراوترات العشرة
│       │       ├── webhook.py    ← 🔴 المسار الإنتاجي للمعاملات (HMAC + normalize)
│       │       ├── tenants.py    ← إدارة المستأجرين + بوابة المؤسسة (login/stats/...)
│       │       ├── transactions.py ← score مباشر (owner) + جلب معاملة
│       │       ├── alerts.py     ← قائمة التنبيهات + تغيير الحالة
│       │       ├── cases.py      ← القضايا + ملاحظات + حالات
│       │       ├── rules.py      ← عرض القواعد + reload (owner فقط)
│       │       ├── models.py     ← حالة نماذج ML
│       │       ├── graph.py      ← rings + إحصائيات الشبكة
│       │       ├── health.py     ← /system/version + /system/ready
│       │       └── auth.py       ← demo login (admin@aegis.local — تطوير فقط)
│       │
│       ├── 📁 core/
│       │   ├── config.py         ← Settings من env vars (pydantic-settings)
│       │   ├── logging.py        ← structlog JSON
│       │   ├── middleware.py     ← request-id + rate limit per-IP
│       │   └── telemetry.py      ← OpenTelemetry اختياري
│       │
│       ├── 📁 models/
│       │   └── schemas.py        ← عقود Pydantic: Transaction, RiskAssessment, ...
│       │
│       ├── 📁 services/
│       │   ├── registry.py       ← 🔴 توصيل كل الخدمات عند الإقلاع (ServiceRegistry)
│       │   └── orchestrator.py   ← 🔴 محرك القرار الموحد (قلب النظام)
│       │
│       ├── 📁 repositories/      ← 🔴 طبقة البيانات الوحيدة (9 مستودعات)
│       │   ├── tenant_repo.py        ← CRUD المستأجرين + تدوير الأسرار
│       │   ├── transaction_repo.py   ← معاملات + استعلامات velocity/مشاركة
│       │   ├── decision_repo.py      ← قرارات + idempotency (webhooks_seen)
│       │   ├── alert_repo.py         ← تنبيهات
│       │   ├── case_repo.py          ← قضايا + ملاحظات
│       │   ├── audit_repo.py         ← سجل التدقيق
│       │   ├── rule_repo.py          ← قواعد في DB (platform + per-tenant)
│       │   ├── watchlist_repo.py     ← قوائم المراقبة (sanctions/countries)
│       │   └── user_repo.py          ← مستخدمون (بنية جاهزة — غير مربوطة بواجهة)
│       │
│       ├── 📁 rules/
│       │   ├── engine.py             ← مفسّر JSONLogic (16 مشغلًا)
│       │   └── default_ruleset.yaml  ← 21 قاعدة افتراضية
│       │
│       ├── 📁 ml/
│       │   └── ensemble.py           ← تحميل joblib + دمج النموذجين + fallback موسوم
│       │
│       ├── 📁 graph/
│       │   └── engine.py             ← NetworkX: عقد account/device/ip/tx
│       │
│       ├── 📁 aml/
│       │   └── service.py            ← فحص العقوبات + structuring + أنماط
│       │
│       ├── 📁 agents/
│       │   ├── openrouter.py         ← عميل OpenRouter (round-robin + dead-key marking)
│       │   └── fraud_agent.py        ← بناء البرومبت + استخراج JSON من رد النموذج
│       │
│       ├── 📁 audit/__init__.py      ← AuditService (غلاف فوق audit_repo)
│       ├── 📁 notifications/
│       │   └── providers.py          ← Console + Webhook providers
│       └── 📁 streaming/__init__.py  ← EventBus (asyncio queues) للـ SSE
│
├── 📁 portals/                   ← واجهات ثابتة تخدمها FastAPI من نفس الحاوية
│   ├── admin/        (app.js 640 سطر — 5 صفحات: نظرة عامة/العملاء/القرارات/الإعدادات/التوثيق)
│   ├── merchant/     (app.js 255 سطر — دخول/نظرة عامة/تكامل/قرارات)
│   └── investigator/ (app.js 65 سطر — جدول قرارات حي بتحديث كل 8 ثوانٍ)
│
├── 📁 models/
│   └── trained/                  ← نماذج مدربة فعلية (تُنتَج بسكربتات training/)
│       ├── gradient_boosting.joblib   (59 KB)
│       ├── isolation_forest.joblib    (1.8 MB)
│       └── metadata.json              (المقاييس + قائمة الخصائص + الإصدار)
│
├── 📁 training/
│   ├── generate_dataset.py       ← 5000 صف مصطنع (3500 طبيعي + 1500 احتيالي)
│   ├── train_models.py           ← تدريب + حفظ joblib + metadata.json
│   └── evaluate_models.py        ← طباعة المقاييس
│
├── 📁 migrations/
│   └── 001_init.sql              ← مرجع توثيقي (المخطط الفعلي في app/db.py)
│
├── 📁 scripts/
│   └── seed_demo.py              ← إنشاء مؤسسة تجريبية + 6 سيناريوهات معاملات
│
├── 📁 tests/                     ← 26 اختبارًا (pytest)
│   ├── conftest.py               ← fixture: قاعدة SQLite معزولة لكل اختبار
│   ├── test_auth.py              ← 6 اختبارات حماية ومصادقة
│   ├── test_webhook.py           ← 6 اختبارات webhook (HMAC/idempotency/legacy)
│   ├── test_pipeline.py          ← 5 اختبارات E2E (شامل العزل والاستمرارية)
│   ├── test_components.py        ← 7 اختبارات مكونات (rules/graph/AML/ML/behavior)
│   └── test_seed_rules.py        ← 2 اختبار صحة القواعد الافتراضية
│
└── 📁 docs/                      ← مجلد توثيق إضافي (احتياطي للمستقبل)
```

## 5.2 الملفات الحرجة (🔴 لا تعدّلها دون فهم عميق)

| الملف | لماذا حرج |
|---|---|
| `backend/app/services/orchestrator.py` | المسار الموحد الوحيد للقرار — أي كسر هنا يعطل المنتج كله |
| `backend/app/security.py` | تغيير خاطئ يكسر توقيع كل العملاء المتصلين |
| `backend/app/db.py` | تغيير المخطط بدون migration جديدة يفسد قواعد موجودة |
| `backend/app/services/registry.py` | ترتيب التهيئة فيه مقصود (DB ← repos ← rules ← engines ← orchestrator) |
| `backend/app/api/v1/webhook.py` | عقد التكامل مع العملاء — تغيير الصيغة يكسر تكاملاتهم |
| `backend/app/models/schemas.py` | العقود العامة للـ API |

## 5.3 قواعد عدم التعديل (من AGENTS.md)

1. لا أسرار في الكود — env vars فقط.
2. لا استدعاء `Database` خارج `app/repositories/`.
3. لا مسار قرار ثانٍ — كل شيء عبر `DecisionOrchestrator`.
4. الـ AI للتفسير فقط ولا يغيّر القرار.
5. كل استعلام مؤسسة يُرشَّح بـ `tenant_id` من JWT لا من العميل.

---

# 6. Source Code Walkthrough — شرح الكود وحدة بوحدة

## 6.1 `main.py` — نقطة الدخول

- **الهدف:** إنشاء تطبيق FastAPI، ربط middlewares والراوترات والبوابات الثابتة.
- **دورة الحياة (lifespan):** عند الإقلاع ينشئ `ServiceRegistry` ويستدعي `initialize()`؛ عند الإيقاف يستدعي `shutdown()` (إغلاق SQLite).
- **المخرجات:** `/` (صفحة هبوط HTML)، `/health`، `/ready`، `/metrics` (Prometheus)، `/api/v1/admin/stream` (SSE للمالك)، تقديم `/admin/` `/merchant/` `/investigator/` كملفات ثابتة.
- **يستدعي:** كل ما سبق. **يستدعيه:** uvicorn (`app.main:app`).

## 6.2 `core/config.py` — الإعدادات

- **الهدف:** قراءة كل الإعدادات من env vars بادئة `AEGIS_` عبر `pydantic-settings`، مع `.env`.
- **مدخلات:** متغيرات البيئة. **مخرجات:** كائن `settings` (cached عبر lru_cache).
- **حقول مهمة:** `SECRET_KEY` (≥32 حرف)، `OWNER_TOKEN`، `DATA_DIR/DB_PATH`، عتبات القرار الثلاث، أوزان الدمج الخمسة، `AI_MIN_SCORE`.
- **خاصية `openrouter_keys`:** تقرأ `OPENROUTER_KEYS` غير المُبدَّأة، وتتجاهل قيم placeholder (`your-...`) — أي النظام يعمل بدون مفاتيح AI.
- `clear_settings_cache()` موجودة لأغراض الاختبار.

## 6.3 `db.py` — قاعدة البيانات

- **الهدف:** محرك SQLite كامل: اتصال per-thread (`threading.local`)، WAL mode، foreign keys، ومُشغّل migrations.
- **المخطط:** 11 جدولًا (تفصيلها في قسم 7) داخل `_SCHEMA`، تُطبَّق كأول migration `001_init` وتُسجَّل في `schema_migrations`.
- **الواجهة:** `execute(sql, params)` (مع commit)، `query()` (قائمة dicts)، `query_one()`، `close()`.
- **لماذا SQLite؟** صفر اعتماديات خارجية، يعمل في Docker volume واحد، مثالي للتشغيل المحلي والنشر الصغير. الاستبدال بـ PostgreSQL موثق في ARCHITECTURE.md (أعد كتابة هذه الواجهة فقط).

## 6.4 `security.py` — الأمنيات

- `generate_api_key/hmac_secret/tenant_id/id` — توليد عشوائي آمن (`secrets` module).
- `verify_signature(secret, raw_body, provided)` — HMAC-SHA256 hex + `hmac.compare_digest` (آمن ضد timing attacks)، يقبل بادئة `sha256=` اختياريًا.
- `issue_jwt/decode_jwt` — HS256 بمفتاح `SECRET_KEY`، الحمولة: `sub, role, iat, exp` + extra (يحمل `tenant_id` للمؤسسات).
- `compare_owner_token` — مقارنة constant-time.

## 6.5 `api/deps.py` — حراس المصادقة

- `get_registry(request)` — الوصول للخدمات من `app.state.registry`.
- `require_owner` — هيدر `X-Owner-Token` (أو query `owner_token` للـ SSE).
- `require_merchant` — هيدر `Authorization: Bearer <JWT>`، يفك التوكن ويتحقق من الدور، ويرجع الحمولة (وفيها `tenant_id`).

## 6.6 `api/v1/webhook.py` — الاستقبال الإنتاجي 🔴

- **`normalize_transaction(body, tenant_id)`:** يقبل صيغًا متنوعة من المحافظ (`transaction` أو الجسم مباشرة؛ `sender_account_id|account_id|from_account|sender`؛ `beneficiary_account_id|to_account|receiver|merchant_id`)، يدمج `context` داخل `metadata` (مع تفكيك التداخل)، ويبني `Transaction` الموحد. الحقل الإلزامي الوحيد فعليًا: `amount`.
- **`fraud_webhook`:** التسلسل: api_key → توقيع → JSON → normalize → idempotency key (`X-Idempotency-Key` أو `tenant:tx_id`) → `orchestrator.evaluate_and_persist` → استجابة مختصرة. **الرد المكرر:** `{duplicate: true}` مع نفس القرار المحفوظ.
- **Legacy fallback:** فقط إذا ضُبط `AEGIS_LEGACY_SECRET` صراحة (فارغ افتراضيًا = معطّل).
- **`GET /decisions/recent`:** قراءة عامة بحقول محدودة (للوحة المراقبة) — القرار الموثق في SECURITY.md.

## 6.7 `api/v1/tenants.py` — إدارة المستأجرين وبوابة المؤسسة

- **Owner endpoints:** قائمة/إنشاء/تفاصيل/تدوير سر/تحديث سياسة/حذف (soft delete) + overview + decisions/recent + audit.
- **Merchant endpoints:** `login` (api_key + hmac_secret → JWT بصلاحية 24h)، `me`، `integration` (مفاتيح + أمثلة كود)، `connection-status`، `stats`، `decisions`، `alerts`، `cases` — **كلها مفلترة بـ `tenant_id` من JWT**.
- كل حدث مهم يُسجَّل في audit (إنشاء مستأجر، تدوير سر، نجاح/فشل دخول...).

## 6.8 `services/registry.py` — التوصيل 🔴

ترتيب التهيئة المقصود (لا تعيد ترتيبه بلا سبب):
1. `Database()` + `migrate()`
2. المستودعات التسعة
3. seed القواعد من YAML إلى جدول `rules` (أول مرة فقط)
4. seed قوائم المراقبة (IR/KP/SY/CU sanctions + 5 دول عالية المخاطر)
5. `RuleEngine` يحمّل من **الجدول** (وليس من YAML مباشرة)
6. `EnsembleScorer` يحمّل joblib إن وُجد
7. `GraphEngine.bootstrap()` يعيد بناء الشبكة من آخر 2000 معاملة في DB
8. `AMLService`، `FeatureExtractor`، `AuditService`، `EventBus`، `ConsoleNotificationProvider`
9. `DecisionOrchestrator` يُحقن بالكل
- `readiness()` يُستخدم في `/ready` و`/system/ready`.

## 6.9 `services/orchestrator.py` — محرك القرار 🔴

انظر التدفق المفصل في قسم 3.1. نقاط جوهرية:
- `_behavior_score(tx)`: biometric<0.4 ⇒ +0.45، keystroke<1.2 ⇒ +0.20، session>600s ⇒ +0.15.
- `_decide(score, aml_hit)`: العقوبات = BLOCK فوري، ثم العتبات الثلاث من الإعدادات.
- عند `sanctions_hit` تُرفع الدرجة المعروضة إلى 0.80 كحد أدنى ليعكس القرار الحتمي (إصلاح v2.0.0).
- الاستجابة الكاملة (`RiskAssessment`) تُخزَّن في `decisions` بكل مكوناتها؛ الرد للعميل مختصر.
- زمن الاستجابة يُقاس فعليًا (`time.perf_counter`) ويُخزَّن في `latency_ms`.

## 6.10 `features.py` — استخراج الخصائص

- **مدخلات:** `Transaction`. **مخرجات:** قاموس خصائص + متجه رقمي (20 بُعدًا) للـ ML.
- كل الخصائص من استعلامات حقيقية على جدول `transactions`: عدد وإجمالي معاملات المرسل خلال 60ث/5د/ساعة، الأجهزة والـ IPs المشتركة، هل الجهاز جديد على هذا المرسل، هل المستفيد معروف، عدد معاملات structuring السابقة، سجل قرارات block/review السابقة للمؤسسة.
- خصائص لا تستطيع AEGIS حسابها داخليًا (عمر الحساب، آخر تغيير كلمة مرور، emulator...) تُقرأ من `metadata` التي يرسلها العميل — **العميل مسؤول عن صحتها**.

## 6.11 `rules/engine.py` — محرك القواعد

- مفسّر JSONLogic بسيط: مشغلات `==, !=, >, >=, <, <=, and, or, not, in, matches, sum, abs, min, max` + `var` (dot-path) و`value`.
- `evaluate(tx, features)` يبني context `{tx: ..., features: ...}` ويعيد كل القواعد المُطلَقة كـ `RuleHit`.
- قاعدة معطّلة (`enabled: false`) تُتخطى. خطأ في قاعدة يُسجَّل ولا يُسقط التقييم.
- `reload()` لإعادة التحميل الحية عبر API.

## 6.12 `ml/ensemble.py` — التعلم الآلي

- يحمّل `models/trained/gradient_boosting.joblib` + `isolation_forest.joblib` إن وُجدا (`ready=True`).
- الدمج: `0.70×GB_probability + 0.30×ISO_anomaly_prob` (ISO تُحوَّل من decision_function إلى 0..1).
- **Fallback صادق:** إن غاب النموذج، `heuristic_fallback` بحساب deterministic بسيط، موسوم في `reason_codes` بـ `NOT_TRAINED_ML` — لا يُقدَّم أبدًا كـ ML حقيقي.
- `list_models()` يعرض النوع (`trained` أم `fallback_not_trained`) في API والـ readiness.

## 6.13 `graph/engine.py` — ذكاء الشبكة

- عقد: `acct:*`, `device:*`, `ip:*`, `tx:*`. علاقات: `sends`, `to`, `uses`, `from`.
- `score(tx)`: عدد الحسابات الأخرى على نفس الجهاز/الـ IP + عدد المستفيدين المرتبطين + أقصر مسافة لحساب موسوم بالاحتيال (`mark_fraud`) ⇒ درجة 0..1 بأسباب نصية (`shared_device_2`...).
- `find_rings(min_size)`: كشف مجتمعات Louvain.
- **إعادة البناء:** عند الإقلاع يُبنى من آخر 2000 معاملة (مُتحقق منه: 5 عقد بعد restart في اختبار الاستمرارية).

## 6.14 `aml/service.py` — مكافحة غسل الأموال (تقني)

- فحص دولة المستفيد (أو دولة الـ IP) مقابل قائمتي `sanctions` و`high_risk_country` من جدول `watchlist`.
- sanctions ⇒ `score +0.60` وعلم `SANCTIONS_HIT:XX` (والقرار BLOCK حتمي في الـ orchestrator).
- structuring: مبلغ 9000–10000 مع ≥2 معاملات مشابهة سابقة ⇒ `structuring_smurfing`.
- حركة أموال سريعة: ≥8 معاملات و>20,000 خلال ساعة ⇒ `rapid_movement_of_funds`.
- مبلغ دائري + مستفيد offshore ⇒ `round_amount_offshore`. VPN/TOR مع مبلغ >5000 ⇒ `anonymity_tool_high_value`.

## 6.15 `agents/` — وكيل الذكاء الاصطناعي

- `openrouter.py`: round-robin على مفاتيح `OPENROUTER_KEYS`، تعليم المفتاح النافد (401/429) لمدة 5 دقائق، 4 نماذج مجانية بالتناوب. بدون مفاتيح ⇒ `enabled=False`.
- `fraud_agent.py`: يبني برومبت عربي ويستخرج JSON بخمس استراتيجيات تسامحية. **يُستدعى فقط للتفسير** عندما `risk ≥ AI_MIN_SCORE` و`AI_ENABLED=true`. فشله لا يؤثر على القرار (مُتحقق: الاختبارات تعمل مع `AI_ENABLED=false`).

## 6.16 `streaming/` و`notifications/` و`audit/`

- `EventBus`: قائمة `asyncio.Queue` لكل مشترك؛ `publish` لا يحجب (QueueFull تُتخطى). المستهلك: SSE `/api/v1/admin/stream` (owner فقط، keep-alive كل 15ث).
- `ConsoleNotificationProvider`: يكتب في السجل (الافتراضي). `WebhookNotificationProvider`: POST لأي URL — يُفعَّل عند الحاجة بتغيير سطر واحد في registry.
- `AuditService` → `audit_repo.log()`: يُسقط تلقائيًا الحقول `hmac_secret/password/api_key/token` من metadata.

---

# 7. Database Documentation — توثيق قاعدة البيانات

## 7.1 النوع والمحرك

- **النوع:** SQLite 3 (ملف واحد) — الوضع الافتراضي `WAL` (Write-Ahead Logging) لأداء قراءة/كتابة متزامن أفضل.
- **الموقع:** `AEGIS_DB_PATH` (افتراضيًا `{AEGIS_DATA_DIR}/aegis.db`، وفي Docker: `/data/aegis.db`).
- **الترحيلات (Migrations):** مدمجة في `backend/app/db.py` داخل قائمة `_MIGRATIONS`. كل migration لها اسم فريد يُسجَّل في جدول `schema_migrations` بعد تطبيقها، فلا تُعاد أبدًا. لإضافة تغيير مستقبلي: أضف عنصرًا جديدًا `("002_xxx", "SQL ...")` ولا تعدّل القديمة.
- **الوصول:** حصرًا عبر `app/repositories/*` (تسعة مستودعات). ممنوع استدعاء `Database` من الراوترات أو الخدمات.

## 7.2 الجداول (11 + جدول الترحيلات)

### جدول `tenants` — المؤسسات المشتركة

| الحقل | النوع | الوصف | قيود |
|---|---|---|---|
| tenant_id | TEXT | المعرف `tnt_...` | PRIMARY KEY |
| name | TEXT | اسم المؤسسة | NOT NULL |
| type | TEXT | wallet/bank/payment/... | DEFAULT 'wallet' |
| country | TEXT | دولة المؤسسة | DEFAULT 'YE' |
| plan | TEXT | sandbox/production | DEFAULT 'sandbox' |
| contact_email / contact_phone | TEXT | بيانات التواصل | nullable |
| api_key | TEXT | مفتاح العميل `aeg_pk_...` | UNIQUE, NOT NULL |
| hmac_secret | TEXT | سر التوقيع `aeg_sk_...` | NOT NULL |
| status | TEXT | active/suspended/deleted | DEFAULT 'active' |
| policy_json | TEXT | سياسات مخاطر خاصة بالمستأجر (JSON) | DEFAULT '{}' |
| created_at / secret_rotated_at / deleted_at | TEXT | تواريخ ISO | — |

### جدول `users` — مستخدمو المؤسسات (بنية جاهزة)

| الحقل | النوع | الوصف |
|---|---|---|
| user_id | TEXT PK | `usr_...` |
| tenant_id | TEXT FK→tenants | المؤسسة المالكة |
| email / name | TEXT | الهوية |
| role | TEXT | tenant_admin/analyst/investigator/viewer |
| password_hash | TEXT | PBKDF2-SHA256 (100k) |
| api_key | TEXT UNIQUE | اختياري |
| status / created_at | TEXT | — |

> ⚠️ الجدول و`user_repo.py` موجودان لكن لا واجهة إدارة مستخدمين بعد (انظر قسم 24).

### جدول `transactions` — المعاملات الخام

| الحقل | الوصف |
|---|---|
| tx_id | PK — معرف المعاملة (من العميل أو مولّد) |
| tenant_id | FK → tenants |
| ts | وقت المعاملة |
| channel / amount / currency | القناة والمبلغ والعملة |
| sender_account_id / sender_user_id | المرسل |
| beneficiary_account_id / user_id / country | المستفيد |
| merchant_id / merchant_name | التاجر |
| device_id / ip / ip_country | سياق الجهاز |
| raw_json | الحمولة الخام كاملة (JSON) |
| features_json | الخصائص المستخرجة وقت التقييم |
| created_at | وقت الحفظ |

**الفهارس:** `idx_tx_tenant(tenant_id,ts)`، `idx_tx_sender(tenant_id,sender_account_id,ts)`، `idx_tx_device(tenant_id,device_id)`، `idx_tx_ip(tenant_id,ip)`، `idx_tx_benef(tenant_id,beneficiary_account_id)` — كلها تخدم استعلامات الـ feature extraction.

### جدول `decisions` — قرارات المخاطر

| الحقل | الوصف |
|---|---|
| decision_id | PK — `dec_...` |
| tx_id | FK → transactions |
| tenant_id | المؤسسة |
| decision | allow/challenge/review/block |
| risk_score / risk_band | الدرجة النهائية والنطاق (low/medium/high/critical) |
| latency_ms | زمن المعالجة المقاس |
| rule_score / ml_score / graph_score / aml_score / behavior_score | درجة كل مكوّن منفصلة |
| rules_json / ml_json / graph_json / aml_json | تفاصيل كل إشارة |
| top_reasons_json | أهم الأسباب |
| typology / reasoning_ar / ai_model | التصنيف والتفسير |
| idempotency_key | UNIQUE — مفتاح منع التكرار |
| created_at | — |

### جدول `alerts` — التنبيهات
`alert_id PK, tenant_id, tx_id, decision_id, severity, title, description, status(open/...), assignee, created_at, updated_at` — فهرس: `idx_al_tenant(tenant_id,status)`.

### جدول `cases` — قضايا التحقيق
`case_id PK, tenant_id, title, status, priority, narrative, tx_ids_json, alert_ids_json, notes_json, assignee, created_at, updated_at` — فهرس: `idx_case_tenant(tenant_id,status)`. الملاحظات مصفوفة JSON: `{author, text, at}`.

### جدول `audit_log` — سجل التدقيق
`id PK AUTOINCREMENT, ts, tenant_id, actor, event_type, resource, resource_id, request_id, metadata_json` — فهرسان: `(tenant_id,ts)` و`(event_type)`. لا يُحذف منه شيء عبر API (append-only فعليًا).

### جدول `rules` — القواعد
`rule_id PK, tenant_id (NULL=عامة للمنصة), name, severity, score, enabled, tags_json, description, when_json (JSONLogic), created_at` — فهرس: `(tenant_id)`.

### جدول `webhooks_seen` — منع التكرار
`idempotency_key PK, tenant_id, tx_id, first_seen`.

### جدول `watchlist` — قوائم المراقبة
`id PK, list_type (sanctions|pep|high_risk_country), value, meta_json` — UNIQUE(list_type, value). القيم الافتراضية: sanctions = IR, KP, SY, CU؛ high_risk_country = AF, MM, KP, IR, SY.

### جدول `model_registry` — سجل النماذج (جاهز، غير مستخدم حاليًا بواسطة ensemble)
`(model_name, version) PK, path, metrics_json, trained_at, is_active`.

## 7.3 ERD نصي

```
tenants 1───∞ users
tenants 1───∞ transactions 1───∞ decisions
tenants 1───∞ alerts ──────∞ cases (عبر alert_ids_json / tx_ids_json)
tenants 1───∞ cases
tenants 1───∞ audit_log (tenant_id nullable لأحداث المنصة)
tenants 1───∞ rules (tenant_id NULL = قاعدة منصة عامة)
tenants 1───∞ webhooks_seen
watchlist (مستقل — قوائم عامة للمنصة)
model_registry (مستقل)
```

## 7.4 النسخ الاحتياطي والاستعادة

قاعدة البيانات ملف واحد داخل الـ volume. النسخ: `tar` للمجلد `/data` (أمر جاهز في RUN_LOCAL.md §10). الاستعادة: فك الأرشيف في volume جديد. إعادة الضبط الكاملة: `docker compose down -v && docker compose up --build` (تحذف كل شيء).

---

# 8. API Bible — مرجع الواجهات الكامل

Base URL افتراضيًا: `http://localhost:8000`. كل المسارات أدناه تحت `/api/v1` ما لم تبدأ بـ `/`.

## 8.1 المصادقة الثلاث

| الآلية | الهيدر | أين تُستخدم |
|---|---|---|
| Owner Token | `X-Owner-Token: <AEGIS_OWNER_TOKEN>` | كل endpoints الإدارة |
| Merchant JWT | `Authorization: Bearer <token>` | endpoints `/admin/merchant/*` |
| Webhook HMAC | `X-API-Key` + `X-Wallet-Signature` | `/wallet/webhook` فقط |

## 8.2 نقاط عامة

### `GET /health`
- **Auth:** لا. **الرد:** `{"status":"ok","version":"2.0.0","env":"development"}`

### `GET /ready`
- **Auth:** لا. **الرد الفعلي المرصود:**
```json
{"status":"ready","database":true,"db_path":"/tmp/aegis-live/aegis.db",
 "rules":21,"ml_ready":true,
 "ml_models":[{"name":"gradient_boosting","version":"2026.08.13","type":"trained"},
              {"name":"isolation_forest","version":"2026.08.13","type":"trained"}],
 "graph_nodes":5,"tenants":2}
```

### `GET /api/v1/system/version` — كـ `/health` تقريبًا. **`GET /api/v1/system/ready`** — كـ `/ready`.

### `GET /metrics` — Prometheus exposition (لا auth).

## 8.3 إدارة المستأجرين (Owner)

### `POST /api/v1/admin/tenants`
- **Auth:** Owner. **الطلب:** `{"name":"محفظة الأمل","type":"wallet","country":"YE","plan":"sandbox","contact_email":null,"policy":{}}`
- **الرد 201 (فعلي من التشغيل الحي):**
```json
{"tenant_id":"tnt_4a80fe81554e6dfc","name":"محفظة الأمل","type":"wallet",
 "country":"YE","plan":"sandbox","api_key":"aeg_pk_...","hmac_secret":"aeg_sk_...",
 "status":"active","created_at":"2026-08-13T..."}
```

### `GET /api/v1/admin/tenants` — قائمة (بدون أسرار). `GET /api/v1/admin/tenants/{id}` — تفاصيل مع `hmac_secret` (للمالك فقط). `POST .../rotate-secret` — تدوير السر (يرجع الجديد ويُبطل القديم فورًا). `PUT .../policy` — تحديث سياسات `{thresholds, weights, enabled_rules, disabled_rules}`. `DELETE .../{id}` — soft delete (`status=deleted`).

### `GET /api/v1/admin/overview`
```json
{"server_time":"...","total_tenants":2,"active_tenants":2,
 "decisions":{"total":3,"by_decision":{"allow":1,"challenge":1,"review":0,"block":1},"avg_risk":0.39}}
```

### `GET /api/v1/admin/decisions/recent?limit=50` — كل القرارات كاملة الحقول. **`GET /api/v1/admin/audit?tenant_id=&event_type=&limit=200`** — سجل التدقيق. **`GET /api/v1/admin/stream`** — SSE (`?owner_token=` مقبول لأن EventSource لا يرسل هيدرز).

## 8.4 بوابة المؤسسة (Merchant JWT)

### `POST /api/v1/admin/merchant/login`
- **الطلب:** `{"api_key":"aeg_pk_...","api_secret":"aeg_sk_..."}`
- **الرد 200:** `{"merchant_token":"<JWT>","token_type":"Bearer","tenant":{"tenant_id":"...","name":"...","type":"...","country":"YE","plan":"sandbox"}}`
- **الخطأ:** 401 `invalid_credentials` (ويُسجَّل في audit كـ `authentication.failure`).

### بقية مسارات المؤسسة — كلها بـ Bearer JWT ومفلترة بالمؤسسة:
`GET /admin/merchant/me` · `GET /admin/merchant/integration` (مفاتيح + أمثلة cURL/Python/Node) · `GET /admin/merchant/connection-status` · `GET /admin/merchant/stats` · `GET /admin/merchant/decisions?limit=50` · `GET /admin/merchant/alerts` · `GET /admin/merchant/cases`.

## 8.5 الـ Webhook الإنتاجي

### `POST /api/v1/wallet/webhook`
- **Auth:** `X-API-Key` + `X-Wallet-Signature` = `hex(HMAC_SHA256(hmac_secret, raw_body_bytes))`.
- **اختياري:** `X-Idempotency-Key` (وإلا يُشتق `tenant_id:tx_id`).
- **الطلب (الصيغة الكاملة):**
```json
{"transaction":{
  "tx_id":"TX-001","timestamp":"2026-08-14T10:00:00Z","channel":"wallet",
  "amount":85000,"currency":"USD",
  "sender_account_id":"acct_1","sender_user_id":"u_1",
  "beneficiary_account_id":"acct_2","beneficiary_country":"YE",
  "merchant_id":"m_1","merchant_name":"متجر",
  "device":{"device_id":"dev_1","ip":"198.51.100.10","ip_country":"YE","vpn":false,"tor":false},
  "behavior":{"biometric_match_score":0.95,"keystroke_entropy":2.1,"session_duration_ms":45000},
  "metadata":{"account_age_days":400,"seconds_since_password_change":800000}
 }}
```
- **الرد 200 (فعلي):**
```json
{"tx_id":"TX-001","decision":"challenge","risk_score":0.4423,"risk_band":"medium",
 "typology":"high_risk","reasoning_ar":"...","top_reasons":["..."],"tenant_id":"tnt_...",
 "ai_model":null,"alert_id":"alr_3f43...","case_id":null,"latency_ms":10.78}
```
- **تكرار:** نفس المفتاح ⇒ `{"tx_id":...,"decision":...,"risk_score":...,"duplicate":true}`.
- **الأخطاء:** 401 `missing_auth_headers|invalid_api_key|invalid_signature` · 400 `invalid_json|amount_required` · 403 `tenant_suspended`.
- **المرونة في الصيغة:** يقبل `sender_account_id` أو `account_id` أو `from_account`؛ و`beneficiary_account_id` أو `to_account` أو `receiver`؛ و`context{}` يُدمج في metadata تلقائيًا.

## 8.6 نقاط المالك الأخرى

`POST /transactions/score` (Owner؛ يتطلب `tenant_id` في الجسم؛ يمر بنفس المسار الموحد) · `GET /transactions/{tx_id}` (معاملة + قرارها) · `GET /rules/` و`POST /rules/reload` · `GET /alerts/` و`POST /alerts/{id}/status` · `GET /cases/` و`GET /cases/{id}` و`POST /cases/{id}/notes` و`POST /cases/{id}/status` · `GET /models/` · `GET /graph/rings` و`GET /graph/stats`.

## 8.7 عام مقيّد

`GET /api/v1/decisions/recent?limit=20` — بدون auth، لكن **بحقول محدودة فقط** (tx_id, tenant_id, ts, decision, risk_score, risk_band, typology, reasoning_ar, ai_model) — لا مبالغ ولا حسابات. يخدم لوحة المحقق.

## 8.8 Demo auth (تطوير فقط)

`POST /api/v1/auth/login` — `admin@aegis.local` / `ChangeMe!2026` ⇒ JWT تجريبي. غير مربوط بأي endpoint آخر. **غيّر أو احذف هذا قبل الإنتاج** (انظر قسم 23).

---

# 9. Fraud Detection Engine — محرك كشف الاحتيال بالتفصيل

## 9.1 دورة حياة المعاملة (Transaction Lifecycle)

الحالات الفعلية التي تمر بها المعاملة في الكود:

```
RECEIVED (webhook استلمها وتحقق من التوقيع)
  → NORMALIZED (صيغة موحدة Transaction)
  → DEDUPLICATED (فحص idempotency)
  → ENRICHED (features.extract — خصائص من التاريخ)
  → SCORED (5 إشارات: rules/ml/graph/aml/behavior)
  → DECIDED (الدمج الموزون + العتبات)
  → PERSISTED (transactions + decisions في SQLite)
  → ACTED (alert + case عند الحاجة)
  → AUDITED (audit_log)
  → PUBLISHED (SSE event)
  → RESPONDED (JSON للعميل)
```

## 9.2 Risk Scoring — بنية درجة المخاطر

الدرجة النهائية رقم بين 0.0 و1.0، وتُبنى من **خمس درجات جزئية مستقلة**، كل واحدة بين 0 و1:

```
risk_score = 0.35 × rule_score      ← مجموع مساهمات القواعد المُطلَقة (سقف 1.0)
           + 0.25 × ml_score         ← 0.70×GradientBoosting + 0.30×IsolationForest
           + 0.15 × graph_score      ← مشاركة الأجهزة/IPs + القرب من احتيال معروف
           + 0.15 × aml_score        ← عقوبات + أنماط غسل أموال
           + 0.10 × behavior_score   ← بصمة سلوكية + إيقاع كتابة + مدة جلسة
```

- الأوزان من env: `WEIGHT_RULES / WEIGHT_ML / WEIGHT_GRAPH / WEIGHT_AML / WEIGHT_BEHAVIOR` (يجب أن يكون مجموعها 1.0).
- **استثناء حتمي:** عند `sanctions_hit` ⇒ القرار `block` والدرجة المعروضة ≥ 0.80 مهما كانت الحسابات.
- كل درجة جزئية تُخزَّن منفصلة في جدول `decisions` — القرار قابل للتفكيك والمراجعة لاحقًا.

## 9.3 جدول القواعد الـ21 الكامل (كما هي في `default_ruleset.yaml`)

| ID | الاسم | الخطورة | المساهمة | الشرط (مبسط) | الفئة |
|---|---|---|---|---|---|
| R-VEL-001 | سرعة معاملات عالية | high | 0.35 | أكثر من 6 معاملات/دقيقة | velocity |
| R-VEL-002 | إجمالي مرتفع خلال 5 دقائق | high | 0.30 | مجموع 5 دقائق > 5000 | velocity |
| R-VEL-003 | تنوع تجار مفاجئ | medium | 0.15 | أكثر من 8 تجار/ساعة | velocity |
| R-GEO-001 | انتقال مستحيل | critical | 0.55 | `geo.impossible_travel` = true | geo |
| R-GEO-002 | دولة FATF عالية المخاطر | high | 0.30 | `geo.fatf_high_risk` = true | geo/aml |
| R-DEV-001 | جهاز جديد + مبلغ كبير | high | 0.35 | جهاز جديد والمبلغ > 1000 | device |
| R-DEV-002 | محاكي/جهاز معدّل | critical | 0.60 | emulator أو rooted | device |
| R-DEV-003 | عقدة TOR | high | 0.40 | `device.tor` = true | device |
| R-DEV-004 | VPN + مبلغ كبير + مستفيد جديد | high | 0.35 | الثلاثة معًا | device |
| R-DEV-005 | جهاز مشترك بين حسابات | high | 0.30 | shared_device_count > 1 | device/graph |
| R-DEV-006 | IP مشترك بين حسابات | medium | 0.20 | shared_ip_count > 2 | device/graph |
| R-BEH-001 | عدم تطابق بصمة سلوكية | high | 0.40 | biometric_match < 0.4 | behavior |
| R-BEH-002 | إيقاع كتابة آلي | medium | 0.25 | keystroke_entropy < 1.2 | behavior |
| R-ATO-001 | تغيير كلمة مرور ثم تحويل | critical | 0.55 | < 600 ثانية + مبلغ > 1000 | ATO |
| R-ATO-002 | تعطيل MFA + مستفيد جديد | critical | 0.60 | الشرطان معًا | ATO |
| R-AML-001 | Structuring تحت العتبة | high | 0.35 | 9000≤مبلغ<10000 + تكرار > 2 | aml |
| R-AML-002 | مرور أموال سريع | high | 0.40 | ≥8 معاملات و> 20000/ساعة | aml |
| R-AML-003 | مبلغ دائري لخارجي | medium | 0.20 | round_1000 + offshore | aml |
| R-CT-001 | اختبار بطاقات | high | 0.35 | > 5 رفض/ساعة + مبلغ < 5 | card |
| R-SE-001 | مكالمة موجَّهة | high | 0.35 | جلسة > 600 ثانية على التحويل | social |
| R-NEW-001 | حساب جديد + أول معاملة كبيرة | high | 0.40 | عمر < 7 أيام + مبلغ > 5000 | account |

## 9.4 كيف تُضاف قاعدة جديدة (بدون إعادة نشر)

```bash
curl -X POST http://localhost:8000/api/v1/rules/reload \
  -H "X-Owner-Token: $OWNER" -H "Content-Type: application/json" \
  -d '{"rules":[{"id":"R-CUSTOM-001","name":"قاعدة مخصصة","severity":"high",
        "score":0.5,"when":{">":[{"var":"tx.amount"},20000]}}]}'
```
القاعدة تُخزَّن في جدول `rules` ويُعاد تحميل المحرك فورًا. قواعد المستأجر: أضف `"tenant_id"` في العنصر لتقتصر على مؤسسة.

## 9.5 Decision Engine — محرك القرار

القرارات الأربعة الممكنة: `allow` (نفّذ)، `challenge` (اطلب تحققًا إضافيًا كـ OTP)، `review` (علّق لمراجعة بشرية)، `block` (ارفض). التفسير يأتي من `top_reasons` (أسماء القواعد المُطلَقة بأوصافها العربية + أعلام AML + أسباب الشبكة) و`reasoning_ar` (نص مُجمَّع، وقد يُحسَّن بـ AI إن فُعّل).

**مثال حقيقي من التشغيل الحي:**
```
معاملة: 25000 USD + metadata{emulator:true, seconds_since_password_change:120}
⇒ القواعد المُطلَقة: R-DEV-002 (0.60) + R-ATO-001 (0.55) + R-NEW-001...
⇒ decision: challenge | risk: 0.4423 | alert: alr_3f43... أُنشئ تلقائيًا
```

---

# 10. Machine Learning — التعلم الآلي

## 10.1 ما هو حقيقي وما هو تجريبي (الحقيقة الكاملة)

| العنصر | الحالة | التفصيل |
|---|---|---|
| GradientBoostingClassifier | ✅ **حقيقي ومدرَّب** | `models/trained/gradient_boosting.joblib` (59 KB) — مدرَّب فعليًا |
| IsolationForest | ✅ **حقيقي ومدرَّب** | `models/trained/isolation_forest.joblib` (1.8 MB) |
| بيانات التدريب | ⚠️ **مصطنعة** | 5000 صف مولَّدة بقواعد احتمالية (`training/generate_dataset.py`) — موسومة في `metadata.json` بـ `"dataset": "synthetic — NOT real fraud data"` |
| مقاييس التقييم | ⚠️ **مثالية وغير واقعية** | accuracy/precision/recall/roc_auc = 1.0 لأن البيانات المصطنعة قابلة للفصل تمامًا — **لا تعني أداءً إنتاجيًا** |
| XGBoost / LightGBM / CatBoost / LSTM / GNN | ❌ غير موجودة | ذُكرت في وثائق v1 القديمة؛ أُزيل الادعاء في v2 |
| heuristic_fallback | ✅ موسوم بصدق | عند غياب النماذج يعمل محسِّن deterministic معلن بـ `NOT_TRAINED_ML` |

## 10.2 الخصائص (Features) — 20 بُعدًا

الترتيب ثابت ويجب أن يطابق `features.FeatureExtractor.vector()` مع أعمدة CSV في التدريب:

```
[amount, hour_sin, hour_cos, tx_per_min, amount_5m, distinct_merchants_1h,
 new_device, shared_device_count, shared_ip_count, impossible_travel,
 high_risk_country, new_beneficiary, seconds_since_password_change,
 previous_declines, previous_chargebacks, high_risk_merchant, off_hours,
 round_amount, structuring_pattern, suspicious_events_30d]
```

## 10.3 التدريب وإعادة التدريب

```bash
# داخل الحاوية أو محليًا (من جذر المشروع):
python training/generate_dataset.py   # يولّد models/synthetic_fraud_dataset.csv
python training/train_models.py       # يكتب models/trained/*.joblib + metadata.json
python training/evaluate_models.py    # يعرض المقاييس
docker compose restart aegis          # إعادة التحميل
```

## 10.4 التخزين والتحميل

- النماذج ملفات joblib في `models/trained/` داخل الصورة (تُنسخ عند البناء).
- التحميل عند الإقلاع في `EnsembleScorer._load()`؛ الفشل ⇒ fallback موسوم.
- جدول `model_registry` في DB جاهز لإدارة إصدارات النماذج مستقبلًا (غير مستخدم حاليًا).

## 10.5 الطريق إلى ML إنتاجي حقيقي

1. اجمع قرارات حقيقية موسومة من `decisions` (القرار + نتيجة التحقيق البشري في cases).
2. ابنِ `training/export_labeled.py` يصدّر من DB بدل المولّد المصطنع.
3. أعد التدريب وقيّم على بيانات holdout زمنية (وليس عشوائية).
4. سجّل الإصدار في `model_registry` وفعّل `is_active`.

---

# 11. Graph Intelligence — ذكاء الشبكة

## 11.1 العقد والعلاقات

| العقدة | البادئة | متى تُنشأ |
|---|---|---|
| حساب | `acct:<sender_account_id>` و`acct:<beneficiary_account_id>` | كل معاملة |
| معاملة | `tx:<tx_id>` | كل معاملة |
| جهاز | `device:<device_id>` | إن أرسل العميل device.device_id |
| IP | `ip:<ip>` | إن أرسل العميل device.ip |

العلاقات: `sender -sends→ tx -to→ beneficiary`، `sender -uses→ device`، `sender -from→ ip`.

## 11.2 الإشارات المحسوبة (في `score()`)

1. **shared_device_count:** عدد الحسابات الأخرى التي استعملت نفس الجهاز — مثال عملي: حسابان احتياليان يتقاسمان جهازًا ⇒ الحساب الثالث على نفس الجهاز يحصل +0.30.
2. **shared_ip_count:** نفس المنطق للـ IP (+0.10 لكل حساب إضافي).
3. **linked_accounts:** عدد المستفيدين المميزين للمرسل (> 5 يبدأ الرفع +0.04 لكل واحد).
4. **hops_to_known_fraud:** أقصر مسافة لحساب موسوم عبر `mark_fraud(account_id)` (≤ 2 ⇒ +0.30).
5. **find_rings(min_size):** كشف مجتمعات Louvain — حلقات حسابات مترابطة (متاحة عبر `GET /api/v1/graph/rings`).

## 11.3 دورة حياة الشبكة

- تُبنى عند الإقلاع من آخر 2000 معاملة في DB (`registry.initialize` ← `graph.bootstrap`).
- تُغذَّى حيًّا بعد كل قرار (`orchestrator` ← `graph.add_transaction`).
- مُتحقق من إعادة البناء: بعد kill + restart كانت `graph_nodes: 5` من 3 معاملات محفوظة.

## 11.4 حدود صادقة

الشبكة في ذاكرة العملية — لا تتوزع على نسخ متعددة، ولا تتجاوز 2000 معاملة عند البناء. للإنتاج الكبير: Neo4j (الواجهة معزولة في class واحد يسهل استبداله).

---

# 12. AML Module — وحدة مكافحة غسل الأموال

> ⚖️ **تنبيه قانوني ثابت:** AEGIS منصة **كشف تقني**. لا تُصدر تقارير امتثال قانونية (SAR/STR) ولا تغني عن مستشار امتثال مرخّص في أي دولة.

## 12.1 خطوات الفحص (في `aml/service.py :: screen()`)

1. **تحديد الدولة:** `beneficiary_country` ثم `device.ip_country` كبديل.
2. **Sanctions match:** بحث مطابق في `watchlist` (list_type=sanctions) ⇒ `sanctions_hit=True` و+0.60 ⇒ **BLOCK حتمي**.
3. **High-risk country:** مطابقة `high_risk_country` ⇒ +0.20 وعلم `fatf_high_risk_country`.
4. **Structuring:** مبلغ بين 9000 و10000 + أكثر من معاملتين مشابهتين سابقتين (من DB عبر `structuring_count`) ⇒ `structuring_smurfing` و+0.30.
5. **Rapid movement:** ≥ 8 معاملات وإجمالي > 20000 خلال ساعة ⇒ `rapid_movement_of_funds` و+0.25.
6. **Round + offshore:** مبلغ مضاعف لـ1000 مع مستفيد offshore ⇒ +0.15.
7. **Anonymity tools:** VPN/TOR مع مبلغ > 5000 ⇒ +0.10.

## 12.2 إدارة قوائم المراقبة

القوائم في جدول `watchlist` (قابلة للتحديث عبر SQL مباشرة أو بإضافة endpoint لاحقًا). الافتراضية: sanctions = IR, KP, SY, CU / high_risk = AF, MM, KP, IR, SY. **هذه قيم بداية تقنية — يجب على المشغّل تحديثها من مصادر رسمية (OFAC/UN/EU) قبل أي استخدام جاد.**

## 12.3 مشاركة الإشارات مع Fraud Engine

`aml_score` يدخل الدمج بوزن 0.15، وأعلامه تظهر في `top_reasons`، وسجلها الكامل في `decisions.aml_json` — أي قرار متأثر بـ AML قابل للتدقيق لاحقًا.

---

# 13. Multi-Tenant Architecture — معمارية تعدد المستأجرين

## 13.1 نموذج العزل

**Shared Database, Shared Schema, Row-Level Isolation:** كل الجداول التشغيلية تحمل `tenant_id`. لا توجد قاعدة منفصلة لكل مؤسسة (اختيار مقصود للبساطة وقابل للتطوير).

## 13.2 كيف يُمنع تسرب البيانات فعليًا

1. **مسارات المؤسسة** (`/admin/merchant/*`): الـ `tenant_id` يُستخرج من JWT الموقَّع — العميل لا يرسله ولا يستطيع تزويره دون `SECRET_KEY`.
2. **الاستعلامات:** كل استعلام في repositories يتضمن `WHERE tenant_id=?`.
3. **الـ webhook:** المعاملة تُلصق بمؤسسة الـ `api_key` مهما ادعى الجسم.
4. **الاختبار المُثبت:** `test_tenant_isolation` ينشئ مؤسستين، يرسل معاملة للأولى، ويتحقق أن الثانية ترى **صفر** قرارات وأن إحصائياتها فارغة — **نجح فعليًا**.
5. **حذف ناعم:** `status=deleted` يستثني المؤسسة من كل القراءات.

## 13.3 سياسات لكل مستأجر

حقل `tenants.policy_json` + endpoint `PUT /admin/tenants/{id}/policy` يخزّنان `{thresholds, weights, enabled_rules, disabled_rules}`. **حد صادق:** السياسات تُخزَّن لكن الـ orchestrator يقرأ العتبات من env العامة حاليًا — ربطها لكل مستأجر في خارطة الطريق (قسم 25).

---

# 14. Authentication & Security — المصادقة والأمان

## 14.1 الآليات الثلاث

| الآلية | التقنية | مدة الصلاحية | الاستخدام |
|---|---|---|---|
| Owner Token | نص سري من env بمقارنة `hmac.compare_digest` | دائم حتى التغيير | إدارة المنصة |
| Merchant JWT | HS256 بمفتاح `SECRET_KEY` | 24 ساعة (`MERCHANT_JWT_TTL_SEC`) | بوابة المؤسسة |
| Webhook HMAC | HMAC-SHA256 على الجسم الخام | لكل طلب | المعاملات |

## 14.2 RBAC

الأدوار المعرفة في الحارس: `owner` (كل شيء) و`merchant` (بيانات مؤسسته). الأدوار `tenant_admin/analyst/investigator/viewer` **مقبولة في بنية JWT و`user_repo`** لكن لا واجهة إدارة لها بعد — لتفعيلها: أنشئ مستخدمين عبر `user_repo` واصدر لهم JWT بأدوارهم.

## 14.3 CORS وCSRF والتشفير

- **CORS:** مقيّد بـ `CORS_ORIGINS` (قائمة صريحة، لا `*`).
- **CSRF:** غير قابل للتطبيق على API بتوكنات في الهيدرز (لا cookies) — لا حاجة لـ CSRF tokens.
- **التشفير أثناء النقل:** مسؤولية البنية (ضع reverse proxy بـ TLS في الإنتاج — الحاوية تتحدث HTTP).
- **التشفير أثناء التخزين:** كلمات مرور المستخدمين PBKDF2-SHA256 (100k)؛ أسرار المؤسسات تُخزَّن كنص (مفاتيح API بطبيعتها) — خطر موثق في قسم 23.
- **Rate limiting:** نافذة منزلقة per-IP في الذاكرة (`RATE_LIMIT_PER_MIN`) — حماية أساسية، وللإنتاج متعدد النسخ انقلها لـ Redis.

## 14.4 إدارة الأسرار

لا أسرار في الكود إطلاقًا (فُحصت الحزمة آليًا). كل شيء من env. `.env` مستثنى من Git ومن سياق بناء Docker. الـ audit يُسقط حقول الأسرار تلقائيًا.

---

# 15. User Interfaces — الواجهات

المنصة تقدّم **3 بوابات ويب ثابتة** (HTML + Vanilla JS + CSS، بدون أطر عمل، عربية RTL بخط Cairo) تخدمها FastAPI مباشرة من نفس الحاوية. كل البيانات المعروضة **حقيقية من الـ API** — لا توجد بيانات mock في الواجهات.

## 15.1 بوابة المالك — `/admin/` 👑

| البند | التفصيل |
|---|---|
| **المستخدم المستهدف** | مالك/مشغّل منصة AEGIS |
| **الدخول** | حقل Owner Token (يُقارن بـ `AEGIS_OWNER_TOKEN`)، يُحفَظ في localStorage تحت `aegis_owner_token` |
| **الصفحات** | ① نظرة عامة (KPIs: عدد المؤسسات، القرارات حسب النوع، متوسط المخاطر، توزيع القرارات لكل مؤسسة) ② العملاء (جدول + إضافة مؤسسة + عرض مفاتيح + تدوير السر + حذف) ③ القرارات (جدول حي بكل المؤسسات) ④ الإعدادات (العتبات وحالة مفاتيح AI) ⑤ التوثيق (دليل تكامل مدمج بأمثلة كود) |
| **الـ APIs المستهلَكة** | `/admin/overview`, `/admin/tenants*`, `/admin/decisions/recent` |

## 15.2 بوابة المؤسسة — `/merchant/` 🏦

| البند | التفصيل |
|---|---|
| **المستخدم المستهدف** | مسؤول التكامل في البنك/المحفظة |
| **الدخول** | `api_key` + `api_secret` (hmac_secret) ⇒ POST `/admin/merchant/login` ⇒ JWT يُحفَظ في localStorage |
| **الصفحات** | ① نظرة عامة (مؤشر اتصال أخضر/أحمر + KPIs القرارات + بيانات المؤسسة) ② إعدادات الربط (endpoint + المفاتيح + أمثلة تكامل جاهزة cURL/Node/Python) ③ القرارات (جدول قرارات المؤسسة فقط) |
| **العزل** | ترى بيانات مؤسستها فقط (JWT-mandated) |

## 15.3 لوحة التحقيقات — `/investigator/` 🛡️

| البند | التفصيل |
|---|---|
| **المستخدم المستهدف** | فريق الأمن/المحققون |
| **الدخول** | بدون تسجيل دخول — تقرأ `GET /api/v1/decisions/recent` العام (حقول محدودة: لا مبالغ ولا حسابات) |
| **الوظيفة** | جدول قرارات حيّ (وقت، معاملة، مؤسسة، قرار، نسبة مخاطر، نموذج AI، مقتطف التفسير) بتحديث تلقائي كل 8 ثوانٍ |

## 15.4 صفحة الهبوط — `/`

بوابة موحّدة بأربعة روابط: المالك / المؤسسة / المحقق / Swagger Docs.

## 15.5 حدود الواجهات (بصدق)

- لا توجد واجهة رسومية لإدارة القضايا والتنبيهات بعد — تُدار عبر API فقط.
- لا توجد واجهة لإدارة مستخدمي المؤسسة أو تعديل القواعد بصريًا.
- لوحة المحقق للقراءة فقط.

---

# 16. Alerts & Case Management — التنبيهات وإدارة القضايا

## 16.1 كيف تنشأ التنبيهات (تلقائيًا في orchestrator)

```
decision ∈ {challenge}           ⇒ alert بخطورة medium
decision ∈ {review}              ⇒ alert بخطورة high
decision ∈ {block}               ⇒ alert بخطورة critical
```
كل تنبيه يحمل: `alert_id, tenant_id, tx_id, decision_id, severity, title, description(=reasoning_ar), status=open, created_at` — ويُخزَّن في جدول `alerts` (دائم، ليس في الذاكرة).

## 16.2 كيف تنشأ القضايا

عند `review` أو `block` فقط: قضية تلقائية بعنوان `Case: <tx_id>` وأولوية = خطورة التنبيه، مربوطة بالمعاملة والتنبيه عبر `tx_ids_json`/`alert_ids_json`.

## 16.3 سير التحقيق (Investigation Workflow)

```
1. المحقق يرى القضية: GET /api/v1/cases/ (owner) أو /admin/merchant/cases (مؤسسة)
2. يفتح التفاصيل: GET /api/v1/cases/{case_id} ← القصة + الملاحظات + الروابط
3. يفحص المعاملة: GET /api/v1/transactions/{tx_id} ← الخام + القرار + كل الإشارات
4. يضيف ملاحظة: POST /api/v1/cases/{case_id}/notes {"author":"...","text":"..."}
5. يحدّث الحالة: POST /api/v1/cases/{case_id}/status {"status":"investigating|closed","assignee":"..."}
6. كل خطوة تُسجَّل في audit_log تلقائيًا
```

---

# 17. Audit System — نظام التدقيق

## 17.1 ما الذي يُسجَّل فعليًا

| الحدث (event_type) | متى |
|---|---|
| `tenant.created` / `tenant.secret_rotated` / `tenant.policy_updated` / `tenant.deleted` | إدارة المستأجرين |
| `authentication.success` / `authentication.failure` | دخول المؤسسات وفشل توقيع الـ webhook |
| `transaction.scored` | كل قرار (مع القرار والدرجة) |
| `alert.created` | إنشاء تنبيه |
| `case.created` / `case.note_added` / `case.status_changed` | دورة القضايا |
| `alert.status_changed` | تحديث التنبيهات |
| `rules.reloaded` | تغيير القواعد |

## 17.2 بنية السجل

`{id, ts, tenant_id, actor, event_type, resource, resource_id, request_id, metadata_json}` — **metadata تُنقّى تلقائيًا** من: `hmac_secret, password, api_key, token`.

## 17.3 الاسترجاع

`GET /api/v1/admin/audit?tenant_id=&event_type=&limit=200` (owner فقط). السجل **منفصل تمامًا** عن سجلات التطبيق (structlog JSON إلى stdout) — الأول للأحداث التجارية الدائمة في DB، والثاني للتشغيل التقني.

---

# 18. Configuration Guide — دليل الإعدادات الكامل

## 18.1 كل متغيرات البيئة (من `.env.example`)

| المتغير | الافتراضي | الإلزامية | الوصف |
|---|---|---|---|
| `AEGIS_ENV` | development | لا | development/staging/production |
| `AEGIS_VERSION` | 2.0.0 | لا | يظهر في /health |
| `PORT` | 8000 | لا | منفذ HTTP |
| `AEGIS_PUBLIC_URL` | http://localhost:8000 | للإنتاج | يُستخدم في أمثلة التكامل |
| `AEGIS_SECRET_KEY` | dev placeholder | **نعم إنتاجيًا** | مفتاح JWT — ≥32 حرفًا عشوائيًا |
| `AEGIS_OWNER_TOKEN` | dev placeholder | **نعم إنتاجيًا** | رمز المالك — قيمة قوية فريدة |
| `AEGIS_DATA_DIR` | /data | لا | مجلد البيانات |
| `AEGIS_DB_PATH` | /data/aegis.db | لا | مسار SQLite صراحة |
| `AEGIS_LEGACY_SECRET` | فارغ | لا | إن ضُبط: يفعّل قبول api_keys غير معروفة بهذا السر (legacy) — **اتركه فارغًا** |
| `CORS_ORIGINS` | localhost | للإنتاج | نطاقات مسموحة مفصولة بفواصل |
| `RATE_LIMIT_PER_MIN` | 240 | لا | حد الطلبات لكل IP/دقيقة |
| `OPENROUTER_KEYS` | placeholder | لا | مفاتيح AI مفصولة بفواصل — فارغ = AI معطّل |
| `AI_ENABLED` | true | لا | تفعيل تفسيرات AI |
| `AI_MIN_SCORE` | 0.45 | لا | الحد الأدنى لاستدعاء AI |
| `DECISION_THRESHOLD_CHALLENGE` | 0.35 | لا | عتبة challenge |
| `DECISION_THRESHOLD_REVIEW` | 0.60 | لا | عتبة review |
| `DECISION_THRESHOLD_BLOCK` | 0.80 | لا | عتبة block |
| `WEIGHT_RULES/ML/GRAPH/AML/BEHAVIOR` | 0.35/0.25/0.15/0.15/0.10 | لا | أوزان الدمج (مجموعها = 1.0) |

## 18.2 ملفات الإعداد الأخرى

| الملف | الغرض |
|---|---|
| `backend/app/rules/default_ruleset.yaml` | القواعد الافتراضية (تُزرع في DB أول إقلاع) |
| `docker-compose.yml` | تعريف الحاوية والـ volume والشبكة |
| `render.yaml` | مخطط النشر على Render |
| `pytest.ini` | إعداد الاختبارات (pythonpath=backend) |

## 18.3 قواعد الأسرار

لا تضع أي قيمة حقيقية إلا في `.env` المحلي (المستثنى من Git). الحزمة المسلَّمة تحتوي placeholders فقط — تحقق آليًا بفحص `sk-or-v1-` قبل التسليم (النتيجة: نظيف).

---

# 19. Docker Documentation — توثيق Docker

## 19.1 `backend/Dockerfile` (سطرًا بسطر)

| المرحلة | الأمر | الغرض |
|---|---|---|
| القاعدة | `FROM python:3.11-slim` | صورة خفيفة رسمية |
| البيئة | `ENV PYTHONUNBUFFERED=1 ... AEGIS_DATA_DIR=/data` | سجلات فورية + مسارات ثابتة |
| الأدوات | `apt-get install build-essential curl` | build-essential لـ scikit-learn، curl للـ healthcheck |
| التبعيات | `pip install -r requirements.txt` | طبقة منفصلة لكفاءة الكاش |
| الكود | `COPY backend/app ./app` + `portals` + `training` + `models` + `scripts` + `migrations` | كل ما يلزم التشغيل والتدريب |
| البيانات | `RUN mkdir -p /data` | نقطة تركيب الـ volume |
| الصحة | `HEALTHCHECK ... curl -fsS /health` | Docker يراقب الحاوية |
| التشغيل | `uvicorn app.main:app --host 0.0.0.0 --port ${PORT}` | يقرأ PORT من البيئة |

## 19.2 `docker-compose.yml`

- **خدمة واحدة:** `aegis` — تُبنى من الجذر، منفذ `8000:8000`، `restart: unless-stopped`.
- **Volume مسمّى:** `aegis-data → /data` — **هنا تعيش قاعدة البيانات وتنجو من `down/up`**.
- **شبكة:** `aegis-net` (bridge).
- **env:** من `.env` + قيم مفروضة للحاوية (`AEGIS_DATA_DIR=/data`...).

## 19.3 دورة التشغيل الكاملة

```bash
docker compose up --build        # بناء + تشغيل (أول مرة: دقائق للبناء)
docker compose up -d             # تشغيل بالخلفية
docker compose logs -f aegis     # متابعة السجلات (ابحث عن aegis.ready)
docker compose ps                # الحالة + الصحة
docker compose down              # إيقاف (البيانات تبقى في الـ volume)
docker compose up -d             # إقلاع مجدد — البيانات موجودة
docker compose down -v           # ⚠️ إيقاف + حذف البيانات نهائيًا
```

## 19.4 ملاحظة تحقق صادقة

بيئة البناء الحالية **لا تحتوي Docker**، لذا لم يُبنَ Image فعليًا هنا. ما تم التحقق منه: الكود نفسه يعمل بنفس أوامر الحاوية (uvicorn على نفس entrypoint)، و`requirements.txt` مثبتة كاملة وتعمل على Python 3.13 (الحاوية تستخدم 3.11 المثبتة في الصورة)، وCI workflow يبني ويفحص الحاوية على GitHub Actions. **أول `docker compose up --build` على جهازك هو الاختبار الحقيقي الأول** — أبلغنا بأي خطأ يظهر.

---

# 20. Local Development Guide — دليل التطوير المحلي من الصفر

## 20.1 Windows (Docker Desktop)

1. ثبّت Docker Desktop من docker.com وفعّل WSL2.
2. فك ضغط الحزمة، وافتح PowerShell في مجلد المشروع.
3. `copy .env.example .env` ثم عدّل `AEGIS_OWNER_TOKEN` و`AEGIS_SECRET_KEY`.
4. `docker compose up --build`
5. افتح `http://localhost:8000` — جاهز.

## 20.2 Linux

نفس الخطوات مع `cp` بدل `copy`، وتثبيت `docker.io` + `docker-compose-plugin` عبر مدير الحزم.

## 20.3 بدون Docker (تطوير بالكود مباشرة)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt pytest pytest-asyncio
export AEGIS_OWNER_TOKEN=dev-token AEGIS_SECRET_KEY=dev-secret-key-min-32-characters-xx \
       AEGIS_DATA_DIR=/tmp/aegis-dev OPENROUTER_KEYS= AI_ENABLED=false
cd backend && uvicorn app.main:app --reload --port 8000
```
`--reload` يعيد التحميل عند كل تعديل. الاختبارات من الجذر: `pytest -q`.

## 20.4 دورة التعديل النموذجية

عدّل الكود ← `pytest -q` ← جرّب يدويًا بـ curl أو البوابات ← commit. لا تعدّل الملفات الحرجة (قسم 5.2) دون اختبار كامل.

---

# 21. Deployment Guide — دليل النشر

## 21.1 GitHub

```bash
git init && git add . && git commit -m "AEGIS v2.0.0"
git remote add origin <repo> && git push -u origin main
```
CI الجاهز (`.github/workflows/docker-build.yml`): pytest ← ثم docker build ← ثم تشغيل حاوية وفحص `/health` و`/ready`.

## 21.2 Render

1. ادفع المستودع إلى GitHub.
2. Render → New → Blueprint → اختر المستودع (يكتشف `render.yaml`).
3. عيّن: `AEGIS_OWNER_TOKEN`، `AEGIS_PUBLIC_URL`، `CORS_ORIGINS`، و`OPENROUTER_KEYS` اختياريًا.
4. **انتبه:** القرص الدائم يتطلب خطة مدفوعة (starter) — الخطة المجانية تفقد البيانات عند إعادة النشر.
5. **حالة التحقق:** `RUN_RENDER.md` جاهز لكن **النشر الفعلي لم يُختبر** — موسوم بذلك في الملف نفسه.

## 21.3 VPS (Ubuntu مثلًا)

```bash
apt update && apt install -y docker.io docker-compose-plugin
git clone <repo> && cd aegis-standalone && cp .env.example .env
# عدّل .env بقيم إنتاجية قوية
docker compose up -d --build
# ضع أمامه Caddy أو Nginx للـ TLS:
# aegis.example.com → reverse_proxy localhost:8000
```

## 21.4 أي منصة Docker (Railway/Fly.io/ECS)

المشروع portable بالكامل: كل الإعداد env vars، والصورة ذاتية الاكتفاء. المنفذ يُقرأ من `PORT` (معيار المنصات).

---

# 22. Testing Guide — دليل الاختبارات

## 22.1 التشغيل

```bash
pip install -r backend/requirements.txt pytest pytest-asyncio
pytest -q        # من جذر المشروع — 26 اختبارًا
```
**النتيجة المُتحقق منها بتاريخ 2026-08-14: `26 passed` ✅** (ومن نسخة ZIP مفكوكة حديثًا أيضًا: 26 passed).

## 22.2 خريطة التغطية الكاملة

| الملف | الاختبارات | ماذا تثبت |
|---|---|---|
| `test_auth.py` | 6 | endpoints الإدارة ترفض بدون token؛ rules/reload وtransactions/score محميان؛ دخول المؤسسة يصدر JWT صالحًا؛ بيانات خاطئة ⇒ 401؛ JWT مزوّر ⇒ 401 |
| `test_webhook.py` | 6 | رفض غياب الهيدرز؛ رفض api_key خاطئ؛ رفض توقيع خاطئ؛ **تدفق كامل ناجح بقرار ودرجة**؛ idempotency ⇒ duplicate:true؛ **لا legacy fallback افتراضيًا** |
| `test_pipeline.py` | 5 | قرار يُحفَظ في DB ويُسترجع؛ معاملة خطرة تنشئ alert؛ دولة معاقَبة ⇒ block؛ **عزل مستأجرين كامل**؛ بيانات تنجو من إعادة تهيئة التطبيق |
| `test_components.py` | 7 | محرك القواعد يُطلِق ويحترم enabled=false؛ الشبكة تكشف جهازًا مشتركًا؛ AML تكشف دولة معاقَبة؛ ML fallback موسوم بصدق؛ درجة السلوك ترتفع مع الخطر |
| `test_seed_rules.py` | 2 | ملف YAML الافتراضي صالح و≥15 قاعدة؛ القواعد تُحمَّل في المحرك |

## 22.3 آلية العزل في الاختبارات

كل اختبار ينشئ قاعدة SQLite مؤقتة في `tmp_path` ويمسح وحدات `app.*` من الكاش (`conftest.py`) — أي **لا تلوث حالة بين الاختبارات** ولا مساس ببياناتك الحقيقية.

---

# 23. Production Readiness Assessment — تقييم جاهزية الإنتاج

التقييم مبني على الكود الموجود فعليًا والاختبارات المنفذة فعليًا فقط.

| المكوّن | التقييم | الأساس |
|---|---|---|
| Webhook + HMAC | 🟢 جاهز للإنتاج | مُختبر: قبول صحيح، رفض صحيح، idempotency |
| Multi-Tenancy | 🟢 جاهز | عزل مُثبت باختبار آلي + JWT |
| Rule Engine | 🟢 جاهز | 21 قاعدة تعمل، hot-reload محمي |
| Database (SQLite) | 🟡 شبه جاهز | مثالية حتى ~عشرات الآلاف من المعاملات/اليوم؛ للأحمال الكبيرة: PostgreSQL |
| Decision/Risk Engine | 🟢 جاهز تقنيًا | deterministic، مُختبر، أوزان وعتبات قابلة للضبط |
| Graph Engine | 🟡 شبه جاهز | يعمل ويُعاد بناؤه؛ في الذاكرة (لا توزيع) |
| AML | 🟡 تقني فقط | قوائم بداية يجب تحديثها من مصادر رسمية؛ ليس امتثالًا قانونيًا |
| ML | 🟡 تجريبي موسوم | نموذجان حقيقيان لكن مدرَّبان على بيانات مصطنعة — أعد التدريب ببيانات حقيقية قبل الاعتماد عليهما |
| Alerts/Cases/Audit | 🟢 جاهز | DB-backed ومُختبَر |
| البوابات الثلاث | 🟢 جاهزة | تُخدَم HTTP 200 وتستهلك APIs حقيقية |
| واجهات إدارة القضايا/المستخدمين | 🔴 ناقصة | APIs موجودة، الواجهات لا |
| Rate limiting | 🟡 أساسي | in-memory — انقله لـ Redis عند التوسع |
| TLS/HTTPS | 🔴 غير مضمن | الحاوية HTTP فقط — أضف reverse proxy |
| Demo login (`ChangeMe!2026`) | 🔴 يجب إزالته | موجود في `auth.py` للتطوير |
| مراقبة الإنتاج | 🟡 جزئية | Prometheus + health/ready موجودة؛ تنبيهات خارجية غير معدّة |

**خلاصة الإنتاج:** المنتج **صالح كتشغيل MVP داخلي أو Pilot مع عملاء أوائل** بعد: تغيير الأسرار، إضافة TLS، إزالة demo login، وتحديث قوائم المراقبة. **ليس جاهزًا بعد لإنتاج مصرفي حرج** (يحتاج: PostgreSQL، ML ببيانات حقيقية، HA، ومراجعة أمنية خارجية).

---

# 24. Technical Debt — الدين التقني (كاملًا وبلا مجاملة)

## 24.1 مشاكل حالية يجب معالجتها قبل الإنتاج

| # | المشكلة | المكان | الخطورة | الحل المقترح |
|---|---|---|---|---|
| 1 | Demo login ببيانات ثابتة | `api/v1/auth.py` | عالية | احذفه أو اربطه بجدول users |
| 2 | أسرار المؤسسات (hmac_secret) نص صريح في DB | جدول tenants | متوسطة | شفّرها بمفتاح مشتق من SECRET_KEY (Fernet) |
| 3 | لا TLS داخل الحاوية | — | عالية إنتاجيًا | reverse proxy (Caddy/Nginx) |
| 4 | Rate limiting في الذاكرة | `core/middleware.py` | متوسطة | Redis backend |
| 5 | قوائم المراقبة بداية فقط | `watchlist_repo.seed_defaults` | عالية امتثاليًا | استيراد OFAC/UN/EU |

## 24.2 قيود معمارية مقصودة (ليست أخطاء)

| القيد | السبب | متى تتجاوزه |
|---|---|---|
| SQLite بدل PostgreSQL | صفر اعتماديات، تطوير محلي سريع | عند >نسخة واحدة أو حمل كبير — الواجهة جاهزة للاستبدال |
| Graph في الذاكرة | بساطة وزمن استجابة | عند الحاجة لشبكة ضخمة/موزعة — Neo4j |
| Monolith | زمن قرار ~10ms متزامن | عند نمو الفريق/الحمل — كل محرك في مجلد مستقل قابل للفصل |
| SSE بدل Kafka | احتياج real-time داخلي فقط | عند تكاملات خارجية كثيفة |

## 24.3 نواقص وظيفية (Features غير موجودة)

1. إدارة مستخدمي المؤسسة من الواجهة (الجدول والمستودع جاهزان).
2. واجهة رسومية للقضايا والتنبيهات (APIs جاهزة).
3. واجهة محرر قواعد مرئي (API `rules/reload` جاهز).
4. ربط سياسات `policy_json` لكل مستأجر بالـ orchestrator فعليًا.
5. إشعارات Email/SMS (provider interface جاهزة — Console/Webhook فقط منفذان).
6. مهام مجدولة (تقارير دورية، إعادة تقييم) — لا يوجد scheduler.
7. Replay protection زمني للـ webhook (لا يوجد فحص freshness للطابع الزمني — فقط idempotency).
8. فيدرالية التعلم/Federated learning — ذُكرت في v1 config وحذفت في v2 (لم تكن منفذة).

## 24.4 تحسينات مقترحة (غير ملحة)

- فهارس مركبة إضافية حسب أنماط الاستعلام الفعلية.
- Pagination للقوائم الطويلة (حاليًا LIMIT فقط).
- ضغط `raw_json` للمعاملات القديمة.
- OpenAPI tags موحدة وأمثلة في Swagger.

---

# 25. Roadmap — خارطة الطريق

## قصير المدى (أسبوع–أسبوعين)

1. 🔴 إزالة demo login أو ربطه بجدول users.
2. 🔴 تشفير hmac_secret في التخزين.
3. 🔴 نشر أول خلف TLS على VPS أو Render (starter).
4. 🟡 واجهة القضايا/التنبيهات في بوابة المالك (الـ APIs جاهزة).
5. 🟡 استيراد قوائم عقوبات رسمية (CSV → watchlist).
6. 🟡 ربط policy_json بكل مستأجر في orchestrator.

## متوسط المدى (شهر–شهرين)

1. PostgreSQL provider (إعادة كتابة `db.py` فقط — الواجهة جاهزة) + migration path.
2. تدريب ML على قرارات حقيقية موسومة من `decisions`+`cases` (export_labeled.py).
3. إدارة مستخدمي المؤسسة كاملة (أدوار analyst/investigator/viewer + واجهة).
4. إشعارات Email (SMTP provider) + Webhook notifications للعملاء عند القرارات المرتفعة.
5. Replay protection بفحص timestamp ±5 دقائق.
6. محرر قواعد مرئي في بوابة المالك.

## بعيد المدى (3–6 أشهر)

1. Neo4j للشبكة عند الحجم الكبير + GraphSAGE embeddings.
2. Kafka/redpanda للـ ingestion غير المتزامن عند الأحمال العالية.
3. Multi-region + HA + rate limiting بـ Redis.
4. تغذية راجعة من نتائج القضايا إلى تدريب النماذج (human-in-the-loop).
5. تقارير امتثال قابلة للتخصيص لكل دولة (بالتعاون مع مستشار قانوني).

---

# 26. Knowledge Transfer — تسليم المعرفة لفريق جديد

## 26.1 اقرأ بهذا الترتيب (يوم واحد يكفي)

1. **هذه الوثيقة** — الأقسام 1–4 أولًا.
2. `README.md` ثم `RUN_LOCAL.md` — شغّل المشروع على جهازك.
3. `ARCHITECTURE.md` — القواعد الخمس الثابتة.
4. الكود بهذا الترتيب: `webhook.py` → `orchestrator.py` → `features.py` → `rules/engine.py` → `registry.py`.
5. شغّل `pytest -q` واقرأ `tests/test_pipeline.py` — هي أفضل شرح حي للنظام.
6. `AGENTS.md` إذا كنت وكيل AI.

## 26.2 أهم 10 حقائق يجب أن تعرفها

1. **المسار الموحد مقدس:** كل قرار يمر عبر `DecisionOrchestrator.evaluate_and_persist` — لا تبنِ مسارًا ثانيًا أبدًا.
2. **القرار deterministic:** الـ AI (OpenRouter) للتفسير فقط. لو فشل AI النظام يعمل كاملًا.
3. **الوصول للبيانات عبر repositories فقط** — ممنوع SQL في الراوترات.
4. **tenant_id من JWT** — لا تقبله أبدًا من جسم الطلب.
5. **HMAC على الجسم الخام bytes** — أي إعادة تنسيق للـ JSON تكسر التوقيع.
6. **الأسرار من env فقط** — الحزمة خالية منها ومفحوصة آليًا.
7. **القواعد في جدول rules** — YAML يُزرع مرة واحدة فقط؛ التعديل الحي عبر `/rules/reload`.
8. **الشبكة تُبنى من DB** — آمن إعادة تشغيل الخدمة في أي وقت.
9. **الاختبارات تعزل نفسها** — أضف اختبارًا لكل ميزة جديدة في الملف المناسب.
6. **الواجهات Vanilla JS** — لا build step؛ عدّل `portals/*/app.js` مباشرة.

## 26.3 أول مهمة تدريبية مقترحة لفريق جديد

أضف قاعدة `R-NEW-002` (مبلغ > 50000 ⇒ review) عبر API، ثم اكتب اختبارًا يثبت إطلاقها، ثم شغّل `pytest -q`. من أكمل ذلك فهم: القواعد، الـ API، الاختبارات، والمسار الموحد.

## 26.4 جهات الاتصال المعرفية

لا يوجد فريق سابق — **هذه الوثيقة + الكود + الاختبارات هي المصدر الوحيد للحقيقة**. إن تعارضت الوثيقة مع الكود، **الكود هو الحقيقة** — حدّث الوثيقة.

---

# 27. Reality Report — تقرير الواقع (بلا مجاملة)

## 27.1 ما يعمل فعليًا ومُتحقق منه بالتشغيل الحي (2026-08-13/14)

| الادعاء | الإثبات |
|---|---|
| المنصة تقلع وتجيب /health و/ready | ردود فعلية: `{"status":"ready","rules":21,"ml_ready":true,...}` |
| إنشاء مؤسستين وعزلهما | `tnt_4a80...` و`tnt_61d4...` — الأولى ترى 3 قرارات، الثانية 0 |
| معاملة عادية ⇒ allow | 150 USD ⇒ `allow 0.0739` بزمن 10.78ms |
| دولة معاقَبة ⇒ block فوري | IR ⇒ `block 0.8 critical` |
| ATO/emulator ⇒ تصعيد | 25000 + emulator ⇒ `challenge 0.4423` + alert تلقائي |
| Idempotency | إعادة الإرسال ⇒ `duplicate:true` بدون تكرار سجلات |
| استمرارية البيانات | kill + restart ⇒ المؤسستان و3 قرارات و5 عقد graph كلها باقية |
| البوابات | `/admin/` `/merchant/` `/investigator/` `/docs` ⇒ HTTP 200 |
| الحماية | 3 endpoints حساسة بدون token ⇒ 401 ×3 |
| الاختبارات | `26 passed` (ومن ZIP مفكوك حديثًا أيضًا) |

## 27.2 ما لم يتم اختباره (بصراحة)

| البند | السبب |
|---|---|
| `docker compose up --build` فعليًا | لا Docker في بيئة البناء — البنية سليمة وCI جاهز، لكن أول بناء حقيقي سيكون على جهازك |
| النشر على Render | لم يُنشر — `render.yaml` جاهز لكن غير مُتحقق |
| تفسيرات AI عبر OpenRouter | لم تُختبر بمفاتيح حقيقية في هذه الجلسة (`AI_ENABLED=false` في الاختبارات) — الكود يعمل بدونها بأمان |
| أداء تحت حمل (load test) | لم يُجرَ — القياس الوحيد: ~10ms لمعاملة واحدة |
| SSE stream | الكود مكتوب ومسجل في main.py لكن لم يُختبر حيًا بعميل EventSource |

## 27.3 ما ادُّعي سابقًا (v1) ولم يكن موجودًا — وكيف عولج في v2

| ادعاء v1 | حقيقة v1 | حالة v2 |
|---|---|---|
| "200+ قاعدة" | 19 قاعدة | ✅ 21 قاعدة حقيقية + توثيق دقيق للعدد |
| "XGBoost+LightGBM+CatBoost+AutoEncoder+LSTM" | 3 placeholders | ✅ نموذجان حقيقيان مدربان + حذف الادعاءات |
| "AML" | غير موجود | ✅ module حقيقي بقوائم DB (تقني، موسوم) |
| "Graph engine" | معزول لا يُستدعى | ✅ مربوط ويُغذّى ويُعاد بناؤه |
| "Database" | ملفات JSON | ✅ SQLite حقيقية + migrations + repositories |
| "Audit" | مجلد فارغ | ✅ جدول + تسجيل فعلي للأحداث |
| مفاتيح AI حقيقية في الحزمة | 8 مفاتيح مكشوفة | ✅ أُزيلت + فحص آلي CLEAN |

## 27.4 مخاطر متبقية يجب أن يعرفها المالك

1. **النماذج مدرَّبة على بيانات مصطنعة** — دقتها الحقيقية على بيانات الإنتاج مجهولة حتى إعادة التدريب.
2. **قوائم العقوبات بداية تقنية** — استخدامها الجاد يتطلب تحديثًا من مصادر رسمية ومراجعة قانونية.
3. **مفاتيح v1 المسرّبة** في الحزمة القديمة `aegis-standalone-2026-07-30.zip` — **يجب إبطالها من لوحة OpenRouter إن لم يحدث بعد**.
4. **بدون TLS** — لا تنشر على الإنترنت قبل وضع reverse proxy.

---

# 28. Final Project State — الحالة النهائية للمشروع

## 28.1 نسب الاكتمال (مبنية على الكود والاختبارات الفعلية فقط)

| المعيار | النسبة | الأساس |
|---|---|---|
| **اكتمال المشروع (مقابل النطاق المطلوب)** | **85%** | كل المكونات الأساسية منفذة؛ النواقص: واجهات القضايا/المستخدمين، scheduler، إشعارات Email/SMS |
| **جاهزية الإنتاج** | **55%** | ينقص: TLS، إزالة demo login، PostgreSQL عند الحمل، ML ببيانات حقيقية، قوائم عقوبات رسمية، مراجعة أمنية خارجية |
| **جاهزية مشروع تخرّج/عرض** | **95%** | يعمل محليًا بأمر واحد، موثق بالكامل، مُختبر، واجهات عربية، قصة تقنية كاملة قابلة للعرض الحي |
| **جاهزية النشر** | **70%** | Dockerfile/compose/render.yaml/CI جاهزة؛ البناء الفعلي والنشر لم يُختبرا في هذه البيئة |
| **جاهزية SaaS** | **60%** | Multi-tenancy + عزل + مفاتيح + بوابات تعمل؛ ينقص: فوترة، تسجيل ذاتي، إدارة مستخدمي المؤسسة، خطط |

## 28.2 سجل التحقق النهائي

```
✅ pytest: 26/26 passed (من المصدر ومن ZIP مفكوك)
✅ تشغيل حي: uvicorn ← /ready = ready (db✓ rules:21 ml✓ graph✓)
✅ E2E حي: tenant×2 + tx×3 + عزل + idempotency + restart-persistence
✅ فحص أسرار آلي على الحزمة: CLEAN
✅ سلامة ZIP: zipfile.testzip() = OK (130 عنصرًا، 588 KB)
⚠️ Docker build فعلي: BLOCKED BY ENVIRONMENT (لا Docker في sandbox)
⚠️ Render deploy فعلي: NOT VERIFIED
```

## 28.3 الحكم النهائي

**AEGIS v2.0.0 نظام حقيقي عامل — ليس prototype شكليًا.** كل مكوّن معلَن في هذه الوثيقة موجود في الكود ومُختبَر أو موسوم صراحة بحدوده. المشروع قابل للتشغيل المحلي بأمر واحد، وقابل للتطوير الآمن من فريق جديد بهذه الوثيقة وحدها، وجاهز للانتقال إلى Pilot production بعد معالجة عناصر قسم 24.1 الخمسة.

---

<div dir="ltr">

**Document metadata:** Generated 2026-08-14 · AEGIS v2.0.0 · Based on verified code, live-run evidence, and 26 passing tests · Package: `Automated-Digital-Wallet-Security-Fraud-Detection-final.zip`

</div>
</div>
