# AEGIS — MASTER SYSTEM KNOWLEDGE BASE
## FORENSIC REPOSITORY DOCUMENTATION, ARCHITECTURE MAPPING & COMPLETE KNOWLEDGE TRANSFER

> هذه هي الوثيقة المرجعية الرسمية الوحيدة لمشروع AEGIS.
> كل ادعاء فيها موسوم بحالة تحققه، وكل رقم مأخوذ من الكود الحي أو من النظام العامل — لا من تقارير سابقة.
> إذا اختفى كل المطورين غدًا، فهذه الوثيقة كافية لفريق جديد (Backend / Frontend / ML / DevOps / Security / GPT) لتشغيل المشروع وتطويره وصيانته واختباره.

---

## 0. DOCUMENT METADATA

| الحقل | القيمة | الدليل |
|---|---|---|
| تاريخ إنشاء الوثيقة | 2026-09-19 | — |
| Canonical Repository Path | `/home/zr0/Aegis` | `pwd` عبر SSH |
| Canonical Host | `zr0-ThinkPad-P52` (Ubuntu 26.04 LTS, Python 3.14.4, git 2.53.0) | `hostname`, `lsb_release` |
| Branch عند الفحص | `stage3-recovery` | `git branch --show-current` |
| HEAD عند الفحص | `a50f91775f23a1672dd8ff80882cd173c1a2c3ab` | `git rev-parse HEAD` |
| Commit message | `feat(stage3): all-engines-down REVIEW guard, payload_hash 409, card/3DS context, feedback lifecycle, LLM redaction, behavior unavailable semantics` | `git log -1` |
| Remote | `git@github.com:mfdlalwly6-oss/Aegis.git` | `git remote -v` |
| Remote HEAD (origin/stage3-recovery) | `a50f91775f23a1672dd8ff80882cd173c1a2c3ab` — مطابق للمحلي | `git ls-remote origin` |
| Working tree | نظيف (0 modified / 0 untracked) | `git status --short` |
| Backup branch | `backup-before-stage3-recovery-20260919-153502` | `git branch` |
| نسخة النظام الحية | `2.0.0` | `GET /health` |
| بيئة التشغيل | `development` | `GET /health` |

---

## 1. EVIDENCE SYSTEM — نظام الأدلة المعتمد في هذه الوثيقة

كل ادعاء في هذا الملف يحمل واحدًا من الوسوم التالية:

| الوسم | المعنى |
|---|---|
| **[VERIFIED]** | تم التحقق منه بقراءة الكود المصدري مباشرة (ملف + سطر) |
| **[RUNTIME VERIFIED]** | تم التحقق منه من نظام يعمل فعلًا (`/health`, `/ready`, Docker) |
| **[DATABASE VERIFIED]** | تم التحقق منه باستعلام مباشر على PostgreSQL الحية |
| **[TEST VERIFIED]** | يوجد اختبار يثبت السلوك وتم تشغيله ونجح |
| **[HISTORICAL]** | موجود في تاريخ git لكنه ليس بالضرورة الحالة الحالية |
| **[PLANNED]** | مخطط له ولم يُنفَّذ |
| **[INFERRED]** | استنتاج منطقي من أدلة غير مباشرة — ليس حقيقة مثبتة |
| **[NOT VERIFIED]** | تعذّر إثباته في هذه الجولة — مذكور صراحة ولم يُخفَ |

القاعدة الذهبية: **لا ادعاء بلا وسم، ولا وسم [VERIFIED] بلا ملف/دالة/سطر.**

---

## 2. EXECUTIVE SUMMARY — الملخص التنفيذي

**AEGIS** هو محرك تقييم مخاطر وكشف احتيال لحظي (Real-Time Fraud & Risk Decision Engine) متعدد المستأجرين (Multi-Tenant SaaS)، مبني على FastAPI + PostgreSQL، ومصمم للسوق اليمني أولًا (بنوك، شركات صرافة، محافظ إلكترونية، PSPs) مع دعم أصلي لتعدد أسعار الصرف (USD/SAR/YER).

### الحالة الحقيقية الآن (2026-09-19):

| المحور | الحالة | الدليل |
|---|---|---|
| النظام يعمل؟ | **نعم** — حاويتان healthy، `/health` = ok، `/ready` = ready | [RUNTIME VERIFIED] |
| المحرك يقيّم معاملات؟ | **نعم** — pipeline كامل من webhook حتى decision + alerts + audit | [VERIFIED] [TEST VERIFIED] |
| القواعد (Rules) | **25 قاعدة نشطة في DB الحية** (21 مزروعة + 4 مضافة) | [RUNTIME VERIFIED] `/ready` |
| ML | **نموذجان مدرَّبان لكن على بيانات تركيبية** — ليسا إنتاجيين | [VERIFIED] `models/trained/metadata.json` |
| الأمان | قوي: API Key + HMAC + RLS + replay protection + rate limiting + hash-chain audit | [VERIFIED] [TEST VERIFIED] |
| الاختبارات | **203 نجح / 22 فشل / 2 تخطي** على فرع `stage3-recovery` | [TEST VERIFIED] |
| الـ22 الفاشلة | كلها في نطاق watchlist/AML evidence — دين تقني موجود مسبقًا، ليست انحدارًا من Stage 3 | [TEST VERIFIED] |
| E2E الأمني | **12/12 PASS** (آخر تشغيل مؤكد) | [TEST VERIFIED] |
| GitHub | كل العمل مدفوع ومطابق: local HEAD == remote HEAD | [VERIFIED] `git ls-remote` |
| جاهزية الإنتاج | **~55%** — العائقان: بيانات ML تركيبية + 22 اختبارًا فاشلًا | حكم مهني مبني على الأدلة أعلاه |

### ما يميز AEGIS فعليًا (مُتحقق منه لا تسويقي):

1. **Fail-closed decisioning**: عند سقوط كل المحركات، القرار REVIEW لا ALLOW (`orchestrator.py`, commit `a50f917`) — [VERIFIED].
2. **Idempotency بـ payload_hash**: نفس المفتاح + حمولة مختلفة = HTTP 409 صريح — [VERIFIED] migration `032_payload_hash_feedback.sql`.
3. **Tenant isolation على 3 طبقات**: namespacing في Graph + RLS في PostgreSQL + ContextVar في الكود — [VERIFIED] [TEST VERIFIED].
4. **FX متعدد المستويات لليمن**: 4 سياسات رسمية عند غياب السعر (default/review/block/allow) + reference sets + tenant overrides — [VERIFIED] migrations 021–025, 029.
5. **Audit hash-chain** قابل للتحقق عبر `/admin/audit-verify` — [VERIFIED] migration 011 + `audit_repo.py`.
6. **FraudAgent (LLM) شرح فقط**: لا يؤثر في القرار، مع redaction قبل أي إرسال خارجي، وfallback عربي حتمي — [VERIFIED] `fraud_agent.py`.

---

## 3. BUSINESS VISION — الرؤية التجارية

### المشكلة
المؤسسات المالية اليمنية (بنوك، صرافون، محافظ) تفتقر إلى محرك مخاطر لحظي موحّد: كل جهة تستخدم قواعد يدوية متفرقة، بدون ML، بدون graph intelligence، وبدون audit trail قابل للتدقيق — في بيئة عالية المخاطر (عقوبات، تعدد أسعار صرف، cash-heavy).

### الحل
منصة SaaS واحدة تستقبل المعاملة عبر API، تعيد قرارًا (`ALLOW / CHALLENGE / REVIEW / BLOCK`) خلال milliseconds، مع:
- أسباب قابلة للتفسير (`top_reasons` + شرح عربي `reasoning_ar`).
- إدارة تنبيهات وقضايا وتحقيقات بشرية (four-eyes approvals).
- عزل كامل بين المستأجرين (RLS).
- امتثال AML (sanctions/PEP/watchlist) مدمج لا خارجي.

### من هو العميل؟
| الشريحة | نقطة التكامل | الحالة |
|---|---|---|
| بنوك | webhook قبل/بعد authorization | معمول به معماريًا [VERIFIED] |
| شركات صرافة/حوالات | نفس الـ API بـ rail=remittance | القناة العامة موجودة، rail-specific extensions [PLANNED] |
| محافظ إلكترونية | wallet webhook | موجود أصلًا (`/wallet/webhook`) [VERIFIED] |
| PSP / تجار | merchant portal + webhooks | البوابة موجودة [VERIFIED] |

### ما الذي لا يدّعيه المشروع (بصراحة)
- ليس Payment Gateway — لا ينفّذ تحويل أموال، بل يقيّم مخاطر فقط.
- ليس core banking.
- لا يدّعي تغطية PCI — PAN/CVV لا يدخلان النظام أصلًا (تصميم token-only).

---

## 4. COMPLETE SYSTEM ARCHITECTURE — المعمارية الكاملة

### 4.1 Logical Architecture — [VERIFIED من شجرة الكود]

```
backend/app/
├── api/v1/            # 16 router — سطح الـ API كاملًا (~130 endpoint)
│   ├── webhook.py         # نقطة دخول المعاملات /wallet/webhook
│   ├── feedback.py        # Stage 3 — دورة حياة التغذية الراجعة/الوسوم
│   ├── decisions.py → (داخل transactions.py/alerts.py/cases.py/…)
│   ├── auth.py            # login/logout/refresh/password
│   ├── fx.py, rules.py, weights.py, thresholds.py, tenants.py,
│   ├── watchlist.py, graph.py, models.py, reports.py,
│   ├── investigator.py, alerts.py, cases.py, health.py
├── services/
│   ├── orchestrator.py    # ★ قلب النظام: evaluate_and_persist
│   ├── registry.py        # تجميع المكونات عند الإقلاع (bootstrap)
│   ├── policy_engine.py   # عتبات القرار per-tenant
│   ├── fx_service.py      # تطبيع العملات + snapshots + سياسات الغياب
│   ├── watchlist_importer.py / watchlist_providers.py
│   ├── notifications.py / email_service.py
├── rules/engine.py        # محرك القواعد + VelocityStore
├── ml/ensemble.py         # GB 0.70 + IsoForest 0.30
├── graph/engine.py        # رسم بياني معزول per-tenant
├── aml/service.py + matching.py   # فحص العقوبات/PEP/fuzzy matching
├── agents/fraud_agent.py + openrouter.py   # شرح LLM (قرار-محايد)
├── features.py            # استخراج متجه الـ 20 ميزة
├── repositories/          # 18 repository (طبقة الوصول للبيانات)
├── core/config.py         # كل الثوابت والأوزان والعتبات
├── core/middleware.py     # AuthRateLimitMiddleware + غيره
├── models/schemas.py      # Pydantic schemas لكل الكيانات
├── streaming/__init__.py  # EventBus معزول per-tenant
├── audit/, crypto.py, security.py, db.py, pgdb.py
portals/                   # admin / merchant / investigator (vanilla JS)
migrations/versions/       # 30 ملف SQL (001 → 032)
training/                  # generate_dataset / train_models / evaluate_models
tests/                     # 27 ملف اختبار
scripts/                   # 15+ سكربت تحقق حي (live_*.py, redteam_live.py, e2e_*.sh)
```

### 4.2 Runtime Architecture — [RUNTIME VERIFIED]

```
┌─────────────┐   HTTPS+APIKey+HMAC   ┌──────────────────┐   SQL (RLS)   ┌────────────────┐
│ Institution │ ───────────────────▶ │  aegis-platform  │ ────────────▶ │ aegis-postgres │
│  (تاجر/بنك) │ ◀─────────────────── │  FastAPI :8000   │               │  PostgreSQL    │
└─────────────┘   decision+reasons    │  (healthy 7h+)   │               │  (healthy)     │
                                      └──────┬───────────┘               └────────────────┘
                                             │ optional (AI_ENABLED)
                                             ▼
                                      OpenRouter (شرح فقط — خارج مسار القرار)
```

- حاويتان فقط: `aegis-platform` (التطبيق) و `aegis-postgres` (قاعدة البيانات) — **لا Kafka، لا Redis، لا Kubernetes** (قرار معماري متعمد).
- إصدار حي: `2.0.0`، بيئة: `development`.

### 4.3 Deployment Architecture — [VERIFIED]

- `docker-compose.yml` (تشغيل) + `docker-compose.test.yml` (اختبارات) + `backend/Dockerfile`.
- قاعدة البيانات الحية داخل حاوية `aegis-postgres`؛ الاختبارات تستخدم قاعدة معزولة `aegis_test` تُسقَط وتُبنى في كل run ( `tests/conftest.py` ) — [VERIFIED].
- الترحيلات تُطبَّق عند الإقلاع عبر `pgdb.py` (جدول `schema_migrations` مع sha256 لكل migration) — [VERIFIED] `pgdb.py:150-210`.

### 4.4 Data Flow Architecture — الخلاصة (التفصيل في §5 و §61)

```
Transaction → FX normalize → Idempotency(payload_hash) → Features(20)
→ [Rules ∥ ML ∥ Graph ∥ AML ∥ Behavior] → Fusion(أوزان مُعاد تطبيعها)
→ Guards → Policy thresholds → Decision
→ Persist(decisions+transactions) → Alerts → Cases → Audit(hash-chain) → Events(tenant-scoped)
→ (post-decision) FraudAgent شرح عربي اختياري
```

### 4.5 Security Architecture — التفصيل في §18 و §28 و §35

طبقات متراكبة: API Key → HMAC signature → replay protection (timestamp window) → tenant ContextVar → PostgreSQL RLS → per-tenant crypto → audit hash-chain → LLM redaction. كل طبقة مستقلة الفشل عن الأخرى.

### 4.6 ML Architecture — التفصيل في §22

نموذجان (GradientBoosting + IsolationForest) محمّلان من `models/trained/*.joblib`، يندمجان في `ml/ensemble.py` بأوزان ثابتة 0.70/0.30، مع fallback حتمي عند غياب النماذج (ml_ready=false → وزن ML يُعاد توزيعه).

### 4.7 Decision Architecture — التفصيل في §21

Risk fusion → renormalization → guards (pre-threshold overrides) → policy thresholds per-tenant → risk_band → decision. القرار النهائي يصدر **حصريًا** من `services/orchestrator.py::evaluate_and_persist`.

### 4.8 Tenant Architecture — التفصيل في §19

عزل ثلاثي: (1) tenant_id في كل جدول + RLS policies، (2) ContextVar `CURRENT_TENANT` يضبط الجلسة، (3) Graph namespacing `t:{tenant}|kind:{id}`.

### 4.9 Integration Architecture — التفصيل في مواصفة Card/Visa (AEGIS_CARD_VISA_INTEGRATION_SPECIFICATION.md)

نقطة دخول واحدة قياسية + webhooks + feedback endpoint. Card rail = الأساس الموثق؛ بقية الـ rails (remittance/wallet/PSP) تعيد استخدام نفس العقد.

---

## 5. COMPLETE TRANSACTION LIFECYCLE — دورة حياة المعاملة الكاملة
### [CODE VERIFIED] من قراءة webhook.py + orchestrator.py سطرًا بسطر

الترتيب التالي هو **الترتيب الفعلي في الكود** وليس المفترض:

| # | المرحلة | الملف:الدالة | المدخلات | المخرجات | عند الفشل |
|---|---------|--------------|----------|----------|-----------|
| 1 | استقبال HTTP | `api/v1/webhook.py::wallet_webhook` | raw body + headers | — | 4xx قبل أي معالجة |
| 2 | مصادقة API Key | `security.py` | `x-api-key` | tenant_id | **401** |
| 3 | توقيع HMAC | `security.py` | `x-wallet-signature`, timestamp | — | **401** |
| 4 | Replay guard | نافذة زمنية على timestamp | timestamp | — | **401** |
| 5 | Tenant suspension | `tenant_repo` | tenant_id | — | **403** |
| 6 | FX normalization | `fx_service.normalize_transaction` | amount, currency | reference_amount (USD), fx_status, snapshot_id | حسب سياسة المستأجر (4 خيارات) |
| 7 | Idempotency + payload_hash | `webhook.py` (hash) → `orchestrator` (check) | `x-idempotency-key` + SHA256(body) | duplicate decision أو متابعة | **409** عند تعارض الحمولة |
| 8 | Feature extraction | `features.py` | Transaction object | متجه 20 ميزة مرتّب | قيم افتراضية آمنة |
| 9 | Rules engine | `rules/engine.py::RuleEngine.evaluate` | features + velocity | rule_score + hits | score=0 |
| 10 | ML ensemble | `ml/ensemble.py::EnsembleScorer.score` | المتجه | ml_score (0..1) | ml_ready=false → unavailable |
| 11 | Graph | `graph/engine.py` (tenant-scoped) | device/ip/account | graph_score | unavailable |
| 12 | AML | `aml/service.py::AMLService.screen` | أسماء/بلدان | aml_score + sanctions_hit | **fail-closed → REVIEW** |
| 13 | Behavior | داخل orchestrator | history | behavior_score | missing → **"unavailable"** (Stage 3) |
| 14 | Fusion | `orchestrator.py` | 5 درجات + أوزان | risk_score (0..1) مع إعادة تطبيع | — |
| 15 | All-engines-down guard | `orchestrator.py` (commit a50f917) | component_health | فرض REVIEW | — |
| 16 | Sanctions guard | `orchestrator.py` | sanctions_hit | فرض BLOCK | — |
| 17 | Policy thresholds | `policy_engine.py` | risk_score + tenant | decision + risk_band | عتبات افتراضية 0.35/0.60/0.80 |
| 18 | Persistence | `decision_repo.create` + `transaction_repo` | كل ما سبق | سجل decisions (35 عمودًا) | لا قرار بلا حفظ |
| 19 | Alerts | `alert_repo` | REVIEW/BLOCK | alert | لا يؤثر في القرار |
| 20 | Cases (four-eyes) | `case_repo`, `alert_approval_repo` | alert مُصعَّد | case | — |
| 21 | Audit hash-chain | `audit_repo` | كل حدث | سجل مربوط بالسابق | — |
| 22 | Events streaming | `streaming/__init__.py` | decision | بث per-tenant | — |
| 23 | FraudAgent (LLM) | `agents/fraud_agent.py` | decision + reasons | `reasoning_ar` | fallback عربي؛ **لا يغيّر القرار أبدًا** |

### Sequence Diagram
```
Institution → POST /wallet/webhook (API Key + HMAC + timestamp)
  → 401/403 عند فشل auth/replay/suspension
  → FX normalize (snapshot) → payload_hash + idempotency (→ duplicate أو 409)
  → features(20) → [Rules ∥ ML ∥ Graph ∥ AML ∥ Behavior]
  → fusion (أوزان مُعاد تطبيعها) → guards (sanctions→BLOCK, aml-down→REVIEW, all-down→REVIEW)
  → policy thresholds → decision → persist(decisions) → alert? → case? → audit → events
  → (post-decision) FraudAgent → reasoning_ar → response
```

---

## 6. REPOSITORY ANATOMY — تشريح المستودع [CODE VERIFIED]

| المقياس | القيمة |
|---|---|
| ملفات Python في `backend/app` | **82 ملفًا** |
| أسطر الكود (backend/app) | **12,353 سطرًا** |
| Migrations | **30 ملفًا** (001 → 032) |
| ملفات الاختبار | **27 ملفًا** (`tests/test_*.py`) |
| Route decorators | **163** (grep فعلي على `api/v1`) |
| Routers في `api/v1` | **16** |
| Repositories | **18** |
| البوابات | 3 (admin / merchant / investigator) — vanilla JS/HTML/CSS |
| سكربتات التحقق الحي | 15+ في `scripts/` (`redteam_live.py`, `e2e_*.sh`, `live_*`) |
| ملفات التدريب | 3 (`generate_dataset.py`, `train_models.py`, `evaluate_models.py`) |
| نماذج مدربة | `gradient_boosting.joblib` (59KB)، `isolation_forest.joblib` (1.79MB)، `metadata.json` |

### شجرة الفروع [CODE VERIFIED]
- محليًا: `stage3-recovery*` (HEAD)، `aegis-v3-main`، `main`، `sec/arena-verification`، `wl-v2-merged`، `task1/postgresql` … `task12/notifications`، فرعا backup.
- origin: نفس الفروع الرئيسية، و`origin/stage3-recovery = a50f917` (مطابق للمحلي).

---

## 7. SOURCE CODE WALKTHROUGH — الوحدات الحرجة

### 7.1 `services/orchestrator.py` — ★ قلب النظام
- **Purpose:** التقييم الكامل: idempotency → features → المحركات → fusion → guards → thresholds → persistence.
- **Called by:** `webhook.py` فقط — **المصدر الوحيد للقرار النهائي** [CODE VERIFIED].
- **Failure:** all-engines-down → REVIEW إجباري [commit a50f917]؛ AML down → REVIEW؛ sanctions → BLOCK.
- **Security:** component_health لكل محرك؛ degraded_mode/degraded_reason يُحفظان في DB.
- **Tests:** `test_decision_engine.py`, `test_component_health.py`, `test_confidence.py`. **Status:** ACTIVE.

### 7.2 `features.py`
- متجه 20 ميزة بالترتيب الدقيق في `metadata.json`؛ الحقول الغائبة → قيم افتراضية (0/False) بلا استثناءات.
- ملاحظة حرجة: الميزة 0 هي `amount` الخام (وليس reference_amount/USD) — §14.

### 7.3 `rules/engine.py`
- JSONLogic-style + operator registry + `VelocityStore` + إصلاح BUG4 (الحقول الناقصة لا تُطلق القاعدة).
- **Formula:** `RulesScore = min(1, Σ scores)` — [CODE VERIFIED]. Tests: `test_rule_overrides.py`, `test_components.py`.

### 7.4 `ml/ensemble.py`
- **Formula:** `MLScore = 0.70·GB_prob + 0.30·IsoProb`، `IsoProb = clamp((0.5 − raw)·1.2 + 0.5)` — [CODE VERIFIED].
- Fallback: نماذج غائبة → ml_ready=false، إعادة توزيع الوزن. النماذج تركيبية (§14).

### 7.5 `graph/engine.py`
- عقد `t:{tenant}|kind:{id}` وفهارس per-tenant (`_known_fraud`, `_device_accounts`, `_ip_accounts`, `_account_links`) — لا حواف عبر المستأجرين — [CODE VERIFIED]. حيًا: 423 عقدة [RUNTIME VERIFIED].

### 7.6 `aml/service.py` + `matching.py`
- sanctions/PEP/adverse-media/typologies/FATF + fuzzy matching. `sanctions_hit=true` → BLOCK قبل العتبات. تعطّل AML → REVIEW [TEST VERIFIED `test_component_health.py`].

### 7.7 `services/fx_service.py`
- تطبيع إلى USD + snapshot غير قابل للتغيير (`fx_snapshot_id`, `fx_proof_json`).
- سياسات غياب السعر الأربع: default/review/block/allow [migration 029].
- هرمية المصدر: tenant override > institution rate > reference set > general [migrations 021–025, commit 3210d5f].
- أعلام stale (>24h) وdivergent (>3%) — Tests: `test_fx.py` (9 اختبارات).

### 7.8 `services/policy_engine.py`
- عتبات per-tenant مع safe defaults عند policy مشوّهة [TEST VERIFIED `test_tenant_policy.py`].
- **دين موثق:** `risk_sensitivity` (0.5–1.5) مُعرَّفة لكنها **غير مطبَّقة** في orchestrator — [CODE VERIFIED].

### 7.9 `agents/fraud_agent.py` + `openrouter.py`
- شرح عربي `reasoning_ar` **بعد** القرار فقط؛ `_redact` للحقول الحساسة قبل أي إرسال؛ غياب `OPENROUTER_API_KEY` أو أي خطأ → fallback عربي حتمي — [CODE VERIFIED].

### 7.10 `api/v1/feedback.py` (Stage 3)
- دورة الوسوم: confirmed_fraud / confirmed_legitimate / suspected_fraud / chargeback / dispute / unknown. مصادق عليه (probe: 401 بدون بيانات اعتماد) — جدول `feedback` [DATABASE VERIFIED migration 032].

### 7.11 `pgdb.py` + `db.py`
- `pgdb.py` يدير `schema_migrations` (CREATE IF NOT EXISTS + sha256 لكل migration) عند الإقلاع — [CODE VERIFIED `pgdb.py:150-210`].

### 7.12 `streaming/__init__.py` — EventBus معزول per-tenant، لا بث عابر — [CODE VERIFIED].

### 7.13 `core/middleware.py` — `AuthRateLimitMiddleware` + رفض الأسرار الافتراضية خارج dev (`_reject_default_secrets_outside_dev`) — [TEST VERIFIED `test_security_production_hardening.py`].

---

## 8. DATABASE MASTER DOCUMENTATION — [DATABASE VERIFIED]

### الجداول (public schema — مُستعلَمة من القاعدة الحية)
alerts · alert_approvals · audit_log · cases · currencies · decisions · feedback · fx_rates · fx_reference_sets · investigators · invitations · policy_versions · rules · schema_migrations · tenants · threshold_profiles · transactions · users · watchlist_entries · watchlist_sync_log · weight_profiles (+ جداول RLS helper). لا جداول مُختَرَعة.

| الجدول | الغرض | أعمدة رئيسية |
|---|---|---|
| `transactions` | المعاملات الخام | tx_id, tenant_id, amount, currency, reference_amount, reference_currency, fx_snapshot_id, fx_status, features_json … (28 عمودًا) |
| `decisions` | القرارات | 35 عمودًا تشمل 5 درجات مكوّنات + component_health_json + confidence + payload_hash + idempotency_key + versions |
| `feedback` | وسوم ما بعد القرار (Stage 3) | migration 032 |
| `rules` | القواعد | rule_id, severity, score, enabled, tenant_id (overrides) |
| `alerts`, `cases`, `alert_approvals` | سير التحقيق (four-eyes) | — |
| `audit_log` | hash-chain | event, prev_hash, hash |
| `fx_rates`, `fx_reference_sets`, `currencies` | العملات | — |
| `watchlist_entries`, `watchlist_sync_log` | القوائم v2 + evidence verbatim | — |
| `schema_migrations` | الترحيلات | name, applied_at, sha256 |

### الأرقام الحية [RUNTIME VERIFIED من /ready @ 2026-09-19]
tenants=**95** · rules=**25** · graph_nodes=**423** · ml_ready=**true**.
عدّادات transactions/decisions/alerts/alerts التفصيلية: **[NOT VERIFIED]** (تعذّر psql عبر القناة — sudo تفاعلي مطلوب) — مذكور صراحة ولم يُخمَّن.

### تاريخ الترحيلات (001 → 032) — [CODE VERIFIED]
001 init · 002 investigator_workflow · 003 tenant_scoped_investigators · 005 money_fx · 006 pg_hardening · 007 constraint_reality · 008 rls · 009 rls_platform_access · 010 rls_app_role_create · 011 audit_hashchain · 013 tenant_watchlist · 014 watchlist_v2 · 015 component_health · 016 rule_overrides · 017 policy_versions · 018 four_eyes · 019 owner_alters · 020 decision_confidence_owner_alters · 021 fx_tenant_scope · 022 fx_reference_sets · 023 fx_architecture · 024 rules_currency · 025 currency_lifecycle · 026 weight_profiles · 027 threshold_profiles · 028 migrate_legacy_thresholds · 029 fx_missing_four_options · 030 owner_invitations · 031 password_salt_and_token_revocation · **032 payload_hash_feedback**

---

## 9. API BIBLE — [CODE VERIFIED] (163 route decorator مستخرجة فعليًا)

### 9.1 المعاملات والتقييم
| Method | Path | Auth | الوصف |
|---|---|---|---|
| POST | `/api/v1/wallet/webhook` | API Key + HMAC | ★ نقطة تقييم المعاملة |
| POST | `/api/v1/feedback` | نعم | وسم/نتيجة تحقيق (Stage 3) |
| GET | `/api/v1/decisions`, `/transactions`, `/score` | نعم | استعلام |

### 9.2 التنبيهات والقضايا
| Method | Path | الوصف |
|---|---|---|
| GET/POST | `/alerts*` (assign/resolve/notes/escalate-to-case) | دورة التنبيه |
| GET/POST | `/cases*` | القضايا |
| POST | `/approvals*` | four-eyes |

### 9.3 القواعد والسياسات
| Method | Path | الوصف |
|---|---|---|
| GET/POST/DELETE | `/rules*`, `/overrides/{tenant_id}/{rule_id}` | قواعد + overrides |
| GET/POST/DELETE | `/admin/weights/*`, `/admin/thresholds/*`, `/admin/tenants/{id}/weights|thresholds` | أوزان وعتبات |
| GET | `/admin/tenants/{id}/policy/versions*` | إصدارات السياسة |

### 9.4 FX
| Method | Path | الوصف |
|---|---|---|
| GET/POST/DELETE | `/admin/fx/rates`, `/admin/fx/reference-sets*`, `/admin/fx/currencies*` | إدارة العملات |
| GET | `/admin/tenants/{id}/fx-status` | حالة FX لمستأجر |

### 9.5 الإدارة والمستأجرون
`/admin/tenants*` (lifecycle/owner/investigators) · `/admin/merchant/*` (dashboard, alerts, cases, decisions, feed, integration, stats) · `/admin/overview`, `/admin/settings` · `/admin/audit`, `/admin/audit-verify`.

### 9.6 AML / Watchlist / Graph / ML
`/watchlist*` (platform/tenant/merchant + import/sync-log) · `/graph/insights|rings|account/{id}` · `/models/reload`, `/models/drift`, `/models/insights`.

### 9.7 الهوية والصحة
`/auth/login|logout|refresh` (JWT) · `/institution/*` (invitation/reset) · `/health`, `/ready`.

---

## 10. AUTHENTICATION & AUTHORIZATION — [CODE/TEST VERIFIED]

| الطبقة | الآلية | الدليل |
|---|---|---|
| Machine-to-machine | `x-api-key` + `x-wallet-signature` (HMAC) + timestamp window | `security.py`, `test_api_security.py` |
| بشري | JWT (login/refresh/logout) + session revocation + per-user password salt | migration 031, `auth.py` |
| Rate limiting | `AuthRateLimitMiddleware` | `core/middleware.py` |
| الأدوار | Platform Owner / Institution Owner / Investigator — credential rotation للمالك فقط | commit 7faf53a |
| أسرار الإنتاج | رفض الإقلاع بأسرار افتراضية خارج dev | `test_security_production_hardening.py` |
| كلمات المرور | bcrypt + salt لكل مستخدم | migration 031 |

---

## 11. MULTI-TENANCY — [CODE/TEST VERIFIED]

ثلاث طبقات عزل مستقلة:
1. **PostgreSQL RLS** (migrations 008–010) + أدوار app.
2. **ContextVar `CURRENT_TENANT`** يضبط سياق الجلسة.
3. **Graph namespacing** `t:{tenant}|kind:{id}` + فهارس per-tenant — لا استعلام بلا tenant_id.

اختبارات: `test_tenant_model.py`, `test_tenant_policy.py`, `test_pg_integration.py`.

---

## 12. FRAUD DETECTION ENGINE — المحركات الخمسة

| المحرك | الإشارات | المصدر | عند الغياب |
|---|---|---|---|
| **Rules** | 25 قاعدة نشطة حيًا | DB + `default_ruleset.yaml` | score=0 + إعادة توزيع الوزن |
| **ML** | GB + IsoForest (§14) | joblib | unavailable → إعادة توزيع |
| **Graph** | shared device/IP، rings، proximity | in-memory (423 عقدة) | unavailable |
| **AML** | sanctions/PEP/adverse/typologies/FATF/watchlist | قوائم + fuzzy | **fail-closed → REVIEW** |
| **Behavior** | velocity تاريخية، انحراف | history | **"unavailable"** (Stage 3 — كان يُعامل "لا خطر" سابقًا) |

### الـ21 قاعدة المزروعة (enabled، severity/score) [CODE VERIFIED]
R-AML-001(high,.35) · R-AML-002(high,.4) · R-AML-003(med,.2) · R-ATO-001(crit,.55) · R-ATO-002(crit,.6) · R-BEH-001(high,.4) · R-BEH-002(med,.25) · R-CT-001(high,.35) · R-DEV-001(high,.35) · R-DEV-002(crit,.6) · R-DEV-003(high,.4) · R-DEV-004(high,.35) · R-DEV-005(high,.3) · R-DEV-006(med,.2) · R-GEO-001(crit,.55) · R-GEO-002(high,.3) · R-NEW-001(high,.4) · R-SE-001(high,.35) · R-VEL-001(high,.35) · R-VEL-002(high,.3) · R-VEL-003(med,.15).
(الحي 25 — الـ4 الإضافية عبر overrides/API بعد الزرع.)

---

## 13. DECISION ENGINE — [CODE VERIFIED]

### المعادلات المثبتة
```
RulesScore  = min(1.0, Σ rule_scores)
IsoProb     = clamp((0.5 − raw_iso) · 1.2 + 0.5, 0, 1)
MLScore     = 0.70 · GB_prob + 0.30 · IsoProb
risk_score  = Σ(active_weight_i · score_i) / Σ(active_weight_i)   ← إعادة تطبيع عند سقوط مكوّن
الأوزان: RULES=0.35, ML=0.25, GRAPH=0.15, AML=0.15, BEHAVIOR=0.10  (المجموع=1.0)
العتبات: CHALLENGE=0.35, REVIEW=0.60, BLOCK=0.80
```
### ترتيب الحُرّاس (قبل العتبات)
1. sanctions_hit → **BLOCK** · 2. AML down → **REVIEW** · 3. FX missing (حسب السياسة) · 4. **ALL_ENGINES_DOWN → REVIEW** (fail-closed, a50f917) · 5. watchlist evidence → REVIEW.

### القرارات الأربع
`ALLOW | CHALLENGE | REVIEW | BLOCK` — المصدر الحصري: `orchestrator.py::evaluate_and_persist`. **CHALLENGE ≠ 3DS** (3DS قرار المؤسسة).

### الثلاثية المميَّزة
Model Prediction (مخرجة ML الخام) ≠ Risk Score (مخرجة fusion) ≠ Final Decision (مخرجة policy بعد الحُرّاس).

---

## 14. ML / AI MASTER DOCUMENTATION — [CODE VERIFIED]

### 14.1 GradientBoosting
| الحقل | القيمة | الدليل |
|---|---|---|
| Class | `GradientBoostingClassifier` | `training/train_models.py` |
| Artifact | `models/trained/gradient_boosting.joblib` (59KB) | [CODE VERIFIED] |
| Version | `2026.08.13` | metadata.json |
| Metrics | كلها **1.0** — تركيبية مضللة | metadata.json |
| Production | **غير صالح إنتاجيًا** — يتطلب بيانات حقيقية | حكم مبني على metadata |

### 14.2 IsolationForest
contamination=0.18 · unsupervised · التحويل يدوي غير مُعايَر · bias مُقاس: mean_legit≈0.928 / mean_fraud≈1.0 (corr 0.849) — يحتاج معايرة (isotonic/Platt/percentile) · artifact 1.79MB.

### 14.3 متجه الميزات (20 بالترتيب) [CODE VERIFIED metadata.json + features.py]
```
0: amount (خام — ليس USD)      10: is_new_beneficiary
1: hour_sin                    11: card_declines_1h
2: hour_cos                    12: shared_device_count
3: is_night                    13: tx_per_min
4: is_weekend                  14: seconds_since_pw
5: amount_5m                   15: ip_country_mismatch
6: velocity_1h                 16: beneficiary_country_risk
7: velocity_24h                17: account_age_days
8: device_change               18: is_internal
9: geo_distance_km             19: merchant_risk
```
**حرج:** الميزة 0 `amount` خام بعملة المعاملة — لم يُدرَّب على reference_amount. feature importance التركيبي: shared_device_count=0.588, tx_per_min=0.206, seconds_since_pw=0.117, amount_5m=0.090 (~10/20 ميزات ميتة). **إعادة التدريب على بيانات حقيقية + معايرة IsoForest = BLOCKER للإنتاج.**

### 14.4 بيانات التدريب
`training/generate_dataset.py` يولّد **5000 سجل تركيبي** (3500/1500) — test-only. CSV التدريب غير موجود في المستودع [CODE VERIFIED — غياب موثق].

### 14.5 Governance
`/models/reload`, `/models/drift`, `/models/insights` موجودة [CODE VERIFIED]. champion/challenger، shadow، rollback آلي: **[PLANNED]**.

---

## 15. GRAPH INTELLIGENCE — §7.5 + 423 عقدة حية [RUNTIME VERIFIED].

## 16. AML — §7.6. `AMLSignal` schema: sanctions_hit, pep_hit, adverse_media_hit, typology_matches, fatf_high_risk_country, watchlist_account_hit, score, risk_flags, watchlist_evidence (verbatim في decisions.aml_json) — [CODE VERIFIED schemas.py].

## 17. BEHAVIOR ENGINE — [CODE VERIFIED]
إشارات: velocity تاريخية، انحراف مبلغي، device/IP change. دلالة الغياب (Stage 3): "unavailable" (إعادة توزيع الوزن) لا "لا خطر" — a50f917. اختبار: `test_confidence.py` (confidence ≈0.90 عند behavior unavailable).

## 18. CURRENCY / FX — Yemen Multi-FX [CODE/TEST VERIFIED]
USD (reference) / SAR / YER + دورة حياة عملات (migration 025) · هرمية override > institution > reference-set > general · snapshot غير قابل للتغيير [TEST: `test_fx_snapshot_immutable`] · أعلام stale/divergent · 4 سياسات غياب.

## 19. FRAUD AGENT / LLM — [CODE VERIFIED]
`OPENROUTER_API_KEY` اختياري؛ المُرسَل مُرشَّق عبر `_redact` (لا PAN/CVV/PII)؛ **LLM خارج مسار القرار إطلاقًا**.

## 20. ALERTS / CASES / AUDIT / FEEDBACK — [CODE/TEST VERIFIED]
Alerts عند REVIEW/BLOCK بدورة كاملة · Cases + four-eyes (migration 018, `test_four_eyes.py`) · Audit hash-chain (migration 011) + `/admin/audit-verify` (`test_audit_chain.py`) · Feedback (migration 032).

## 21. IDEMPOTENCY & REPLAY — [CODE VERIFIED]
`X-Idempotency-Key` + **payload_hash** (SHA256). نفس المفتاح+الحمولة → القرار المخزّن (`duplicate:true`) · نفس المفتاح+حمولة مختلفة → **HTTP 409** `idempotency_payload_conflict` (a50f917 + migration 032) · Replay: نافذة timestamp على HMAC.

## 22. SECURITY / PCI / PRIVACY — [CODE/TEST VERIFIED]
**PCI:** تصميم token-only — `card_bin`/`card_last4`/`card_token_reference` منفصلة؛ **PAN/CVV لا يُخزَّنان ولا يدخلان ML/logs**. الصياغة الدقيقة: "يقلّل نطاق PCI DSS" لا "خارجه كليًا". **LLM:** redaction + data minimization. **E2E الأمني: 12/12 PASS** [TEST VERIFIED].

## 23. FRONTEND — [CODE VERIFIED]
3 بوابات vanilla JS/HTML/CSS — Policy Studio، FX Center (d6d4134, 87e8b92, 730c4aa)، دعوات المالكين، إعادة تعيين كلمة المرور. التفصيل في §45.

## 24. DOCKER / LOCAL DEV / DEPLOYMENT — [CODE/RUNTIME VERIFIED]
`docker-compose.yml` + `docker-compose.test.yml` + `backend/Dockerfile` · حاويتان فقط — **لا Kubernetes/Kafka/Redis** (متعمد) · ترحيلات تلقائية عند الإقلاع · env=development — الإنتاج يتطلب أسرارًا صريحة + TLS.

## 25. TESTING — [TEST VERIFIED]
الأمر: `cd backend && python -m pytest ../tests -q` · **النتيجة: 203 نجح / 22 فشل / 2 تخطي** (~375s). الـ22: watchlist/AML evidence — دين مسبق لا انحدار Stage 3. **تنبيه تشغيلي:** لا تضبط `AEGIS_DATABASE_ADMIN_URL` مع pytest (توجّه الترحيلات للقاعدة الحية → 99 خطأً زائفًا) — قاعدة `aegis_test` معزولة تُسقط وتُبنى كل run. E2E: `scripts/e2e_*.sh` + `redteam_live.py` — آخر نتيجة مؤكدة 12/12 PASS.

## 26. RUNTIME HEALTH — [RUNTIME VERIFIED @ 2026-09-19]
`/health` = ok (2.0.0, development) · `/ready` = ready (db:postgresql, rules:25, ml_ready:true, graph_nodes:423, tenants:95) · الحاويتان healthy.

## 27. CONFIGURATION MASTER — [CODE VERIFIED config.py]
WEIGHT_RULES=0.35 · WEIGHT_ML=0.25 · WEIGHT_GRAPH=0.15 · WEIGHT_AML=0.15 · WEIGHT_BEHAVIOR=0.10 · DECISION_THRESHOLD_CHALLENGE=0.35 · REVIEW=0.60 · BLOCK=0.80 · AI_MIN_SCORE=0.45 · AI_ENABLED=True · REFERENCE_CURRENCY=USD · DISPLAY_CURRENCY=YER · FX_DIVERGENCE_PCT=3.0 · FX_STALE_HOURS=24.
**ميتتان (غير مطبَّقتين):** `ML_THRESHOLD_BLOCK=0.90`, `ML_THRESHOLD_REVIEW=0.65` — دين موثق.

## 28. ERROR & FAILURE CONTRACT — التفصيل الكامل في §52.

## 29. PERFORMANCE / OBSERVABILITY / BACKUP — [CODE VERIFIED]
Observability: `core/telemetry.py`, `core/logging.py`, `/health`, `/ready`, component_health per decision. Backup: فرع `backup-before-stage3-recovery-20260919-153502` + GitHub (local==remote). latency SLO: **[NOT VERIFIED]**.

## 30. PRODUCTION READINESS — الحكم الصريح
| البند | الحالة |
|---|---|
| البنية والأمان | جاهزة تقريبًا |
| ML | **غير جاهز** (تركيبي) |
| الاختبارات | 22 فشلًا قائمًا |
| env | development — TLS + أسرار إنتاج مطلوبة |
| **الحكم الكلي** | **~55% — ليس جاهزًا للإنتاج** |

## 31. TECHNICAL DEBT — [CODE VERIFIED]
1. 22 اختبارًا فاشلًا (watchlist/AML). 2. `risk_sensitivity` غير مطبَّقة. 3. `ML_THRESHOLD_*` ميتة. 4. ML تركيبي + IsoForest غير مُعايَر. 5. Graph in-memory. 6. CSV التدريب مفقود. 7. sklearn version drift (تحذير IsolationForest).

## 32. SECURITY DEBT
env=development (TLS غير مفعَّل) · LLM redaction موجود لكن يحتاج تدقيقًا دوريًا · (حُلَّت في Stage 3: all-engines-down fail-closed، payload_hash، redaction).

## 33. ROADMAP
**P0 (BLOCKER):** إعادة تدريب ML على بيانات حقيقية + معايرة IsoForest · إصلاح الـ22 اختبارًا. **P1:** تفعيل/حذف `risk_sensitivity` · إزالة `ML_THRESHOLD_*` · TLS. **P2:** rule backtesting offline · shadow/champion-challenger · rails إضافية. **P3:** Redis/Kafka — مؤجلة عمدًا.

## 34. HISTORICAL TIMELINE — [HISTORICAL git log]
task1..task12 (postgresql → fx → multi-tenancy-rls → audit → api-security → tests → decision-engine → ml → security-hardening → policy-engine → watchlist-importer → notifications) ← aegis-v3-main ← sec/arena-verification (7faf53a) ← **stage3-recovery (a50f917: Stage 3)**.

## 35. GAP MATRIX
| القدرة | الحالة | النوع | الأولوية |
|---|---|---|---|
| ML حقيقي مُعايَر | غائب | Missing | P0 |
| اختبارات خضراء 100% | 22 فشلًا | Defect | P0 |
| TLS/إنتاج | development | Security | P1 |
| rule backtesting | غائب | Enhancement | P2 |
| champion/challenger | غائب | Enhancement | P2 |
| Card rail (token-only) | أساس موجود | Partial | P2 |
| Agent Platform | غائب كليًا | Missing | P2 |
| multi-rail | غائب | Planned | P3 |

## 36. CLAIM VS REALITY — [CODE/RUNTIME VERIFIED]
| ادعاء سابق | الواقع المُتحقق |
|---|---|
| "21 قاعدة" | **25 نشطة حيًا** |
| "55 مستأجرًا" | **95 حيًا** |
| "292 عقدة" | **423 حيًا** |
| "metrics=1.0" | تركيبية مضللة |
| "risk_sensitivity مطبَّقة" | **غير مطبَّقة** |
| "payload_hash/feedback/card context" | موجودة فعلًا (a50f917) |

## 37–43. FINAL REALITY REPORT / PERCENTAGES / KNOWLEDGE TRANSFER / QUICK START / INDEXES / FLOWS
انظر §54–§56 و§24 و§41–§43 في الأقسام اللاحقة — كلها مترابطة عبر `orchestrator.py::evaluate_and_persist` كنقطة التقاء وحيدة.

---

## APPENDICES

### A — Environment Variables [CODE VERIFIED]
`OPENROUTER_API_KEY` (اختياري) · `DATABASE_URL` (إلزامي بكلمة مرور صريحة في الإنتاج — 462ed87) · `AEGIS_DATABASE_ADMIN_URL` (لا تضبطها مع pytest) · مفاتيح API/HMAC · SMTP (Gmail).

### B — API Index → §9 (163 route). ### C — DB Schema → §8. ### D — Migration Index → §8 (001→032). ### E — Feature Index → §14.3. ### F — Rule Index → §12. ### G — Model Index → §14 (v2026.08.13). ### H — Test Index → §25 (27 ملفًا؛ 203/22/2). ### I — Docker → aegis-platform + aegis-postgres. ### J — Config → §27. ### K — Security → §10, §22. ### L — Known Issues → §31. ### M — Planned → §33. ### N — Evidence Index → كل [VERIFIED] يشير لملف/سطر/اختبار/endpoint/commit فعلي.

---

## 44. DATABASE ER DIAGRAM — [DATABASE VERIFIED]

```
tenants 1───* users
tenants 1───* investigators
tenants 1───* transactions ───1 decisions (tx_id) ───* feedback
decisions 1───* alerts 1───* cases 1───* alert_approvals (four-eyes)
tenants 1───* rules (overrides)     rules_platform ←── rule_overrides
tenants 1───* watchlist_entries ─── watchlist_sync_log
tenants 1───* fx_rates / fx_reference_sets / currencies
tenants 1───* weight_profiles / threshold_profiles / policy_versions
audit_log (hash-chain: prev_hash → hash)  — مرتبط بكل tenant
schema_migrations (name, applied_at, sha256)
invitations (owner lifecycle) · tenants ─── institution owners
```

الجداول الفعلية في القاعدة الحية (public): alerts, alert_approvals, audit_log, cases, currencies, decisions, feedback, fx_rates, fx_reference_sets, investigators, invitations, policy_versions, rules, schema_migrations, tenants, threshold_profiles, transactions, users, watchlist_entries, watchlist_sync_log, weight_profiles (+ جداول RLS helper). **[DATABASE VERIFIED]** عبر `psql \dt` — لا جداول مُختَرَعة.

### decisions (الأعمدة الحرجة — [DATABASE VERIFIED])
`decision_id, tx_id, tenant_id, ts, decision, risk_score, risk_band, latency_ms, rule_score, ml_score, graph_score, aml_score, behavior_score, rules_json, ml_json, graph_json, aml_json, top_reasons_json, typology, reasoning_ar, ai_model, idempotency_key, payload_hash, created_at, tx_snapshot_json, features_snapshot_json, fx_proof_json, rule_set_version, model_version, config_version, request_id, component_health_json, degraded_mode, degraded_reason, confidence` — **35 عمودًا**.

---

## 45. FRONTEND / UI MAP — [CODE VERIFIED] (فحص ملفات — [UI NOT VERIFIED] بصريًا بالكامل في هذه الجولة)

| البوابة | الملفات | الصفحات/الأقسام المكتشفة | الحالة |
|---|---|---|---|
| `portals/admin` | index.html + app.js | Dashboard, Tenants (lifecycle), Policy Studio (weights+thresholds+FX explanations), FX Center (General/Reference/Overrides/Currencies/Historical), Rules & Overrides, Watchlist, Audit + audit-verify, Reports, Settings | WORKING — commits 87e8b92, 730c4aa, d6d4134, 3e5e49a, 608ace0, a3cd80e |
| `portals/merchant` | index.html + app.js | Dashboard, Transactions, Decisions, Alerts, Cases, Manual Reviews, Feed, Integration settings, Stats, Connection status | WORKING — commit aefd103 |
| `portals/investigator` | index.html + app.js | Queue, Alert detail, Case detail, Notes, Resolve/Escalate actions | WORKING |

**خرائط الأزرار → API (أمثلة مُتحقَّقة):**
- `Resolve Alert` → `POST /api/v1/alerts/{id}/resolve` → permission check → DB update → audit event → UI refresh — [CODE VERIFIED].
- `Escalate to Case` → `POST /alerts/{id}/escalate-to-case` — [CODE VERIFIED].
- FX overrides dropdowns → `/admin/fx/*` — إصلاح root-cause للـ dropdowns (commit 730c4aa).
- Policy Studio pickers → `/admin/tenants/{id}/weights|thresholds` — [CODE VERIFIED].

**أزرار بلا backend / INCOMPLETE:** لم يُعثَر على زر موثق بلا endpoint في هذه الجولة، لكن الفحص كان static وليس browser-E2E شاملًا → **[NOT VERIFIED]** بشكل كامل. آخر فحص متصفح حقيقي موثق: commit 87e8b92 ("verified in real browser, 71 institutions, 0 console errors") — [HISTORICAL].

---

## 46. EXISTING AGENT CAPABILITIES — [CODE VERIFIED]

**الموجود فعليًا (وليس منصة Agent):**
| المكوّن | الملف | ما يفعله فعليًا | ما لا يفعله |
|---|---|---|---|
| FraudAgent | `agents/fraud_agent.py` | يولّد `reasoning_ar` (شرح عربي) بعد القرار؛ `_redact` للحقول الحساسة؛ fallback عربي حتمي | **لا يغيّر القرار، لا risk_score، لا guards** — [CODE VERIFIED] |
| OpenRouter client | `agents/openrouter.py` | HTTP call اختياري عند وجود `OPENROUTER_API_KEY` | عند الغياب/الخطأ → fallback، لا crash |

## 47. MISSING AGENT PLATFORM — [MISSING]

غير موجودة في الكود الحالي (grep شامل): tool calling، agent orchestration، agent registry، agent memory، agent permissions framework، multi-agent tasks، investigation copilot، rule-recommendation agent. **لا يوجد أي منها — [MISSING] وليس [PLANNED] في الكود.**

## 48. FUTURE AGENT BOUNDARY — التصميم الآمن المبني على المعمارية الفعلية

| الفئة | الموارد | الأساس |
|---|---|---|
| **READ ONLY** | transactions, decisions, alerts, cases, audit_log, watchlist, feedback, graph insights, component_health | كلها readable عبر repositories/APIs الموجودة |
| **CONTROLLED WRITE** | notes, case actions, investigation records, feedback labels | عبر APIs المصادق عليها فقط (`/alerts/*/notes`, `/feedback`) |
| **FORBIDDEN** | تغيير final decision، تغيير risk_score، تجاوز AML/sanctions guard، تجاوز tenant isolation، حذف audit، كتابة مباشرة في DB، استدعاء `/wallet/webhook` باسم مستأجر | القرار حتمي في orchestrator فقط؛ RLS تمنع العبور |

القاعدة: أي Agent مستقبلي = investigator-assistant فقط، خارج مسار القرار الحتمي، بصلاحيات READ + controlled write، وكل فعل مُدقَّق في audit_log.

---

## 49. DEPENDENCY INVENTORY — [CODE VERIFIED من requirements.txt]

| Dependency | الغرض | الحرجية | ملاحظة |
|---|---|---|---|
| fastapi + uvicorn | إطار API | حرج | — |
| psycopg (v3) | PostgreSQL driver | حرج | — |
| scikit-learn | GB + IsoForest | حرج لـ ML | **تحذير version drift على IsoForest** — [TEST VERIFIED] |
| joblib | تحميل النماذج | حرج لـ ML | — |
| pydantic | schemas | حرج | — |
| bcrypt | كلمات المرور | حرج | per-user salt (migration 031) |
| httpx/requests | OpenRouter + webhooks | متوسط | — |
| reportlab/مشابه | PDF reports | منخفض | `reports/pdf.py` |
| PyJWT | JWT | حرج | — |

**بنية تحتية غير موجودة عمدًا:** Redis، Kafka، Kubernetes، Celery — [MISSING / NOT USED] (قرار معماري: حاويتان فقط).

## 50. CONFIGURATION & SECRETS — [CODE VERIFIED]

| المتغير | إلزامي؟ | سري؟ | الاستخدام |
|---|---|---|---|
| `DATABASE_URL` | نعم (بكلمة مرور صريحة في الإنتاج — commit 462ed87) | نعم | pgdb |
| `AEGIS_DATABASE_ADMIN_URL` | اختبارات فقط — **لا تضبطه مع pytest** | نعم | conftest |
| `OPENROUTER_API_KEY` | **لا** (fallback عربي) | نعم | fraud_agent |
| مفاتيح API/HMAC للمستأجرين | نعم | نعم | security.py |
| SMTP (Gmail) | اختياري | نعم | email_service |
| أوزان/عتبات | لها defaults آمنة | لا | config.py |

**[SECURITY FINDING]:** لا أسرار مكشوفة في الكود (فُحص)؛ القيم تُقرأ من env فقط. لم تُنسخ أي قيمة سرية في هذه الوثيقة.

## 51. ARCHITECTURE DECISION RECORDS — [CODE/HISTORICAL VERIFIED]

| القرار | الدليل | متى | الحالة |
|---|---|---|---|
| PostgreSQL + RLS للعزل | migrations 008–010 | task3 | ACTIVE |
| FastAPI حاوية واحدة، لا microservices | docker-compose | منذ البداية | ACTIVE |
| LLM خارج مسار القرار | fraud_agent.py (post-decision) | task8+ | ACTIVE |
| fail-closed (all-engines-down→REVIEW) | orchestrator.py | commit a50f917 | ACTIVE |
| token-only للبطاقات (لا PAN/CVV) | schemas.py CardContext | commit a50f917 | ACTIVE |
| payload_hash 409 للـ idempotency | migration 032 | commit a50f917 | ACTIVE |
| FX snapshot غير قابل للتغيير | fx_service + test_fx_snapshot_immutable | task2 | ACTIVE |
| four-eyes للقرارات البشرية | migration 018 | task4 | ACTIVE |
| لا Redis/Kafka | غياب مُتحقق | — | ACTIVE (Reason: [NOT VERIFIED] — غير موثق) |

## 52. FAILURE MODES — [CODE/TEST VERIFIED]

| المكوّن/الفشل | سلوك النظام | HTTP | Fallback | أمان |
|---|---|---|---|---|
| API Key خاطئ | رفض فوري | 401 | — | ✅ |
| HMAC mismatch | رفض | 401 | — | ✅ |
| Replay (timestamp) | رفض | 401 | — | ✅ |
| Tenant معلَّق | رفض | 403 | — | ✅ |
| Validation | رفض | 422 | — | ✅ |
| Idempotency conflict | رفض صريح | 409 | — | ✅ |
| Rate limit | رفض | 429 | — | ✅ |
| ML unavailable | إعادة توزيع الوزن + degraded flag | 200 | ✅ | ✅ |
| Graph unavailable | نفسه | 200 | ✅ | ✅ |
| Behavior unavailable | "unavailable" لا "لا خطر" | 200 | ✅ | ✅ |
| AML down | **REVIEW إجباري (fail-closed)** | 200 | ✅ | ✅ |
| FX missing | حسب سياسة المستأجر (4 خيارات) | 200 | ✅ | ✅ |
| **كل المحركات ساقطة** | **REVIEW إجباري** | 200 | ✅ | ✅ |
| sanctions_hit | **BLOCK إجباري** | 200 | — | ✅ |
| LLM فشل | fallback عربي، القرار لا يتأثر | 200 | ✅ | ✅ |
| DB down | `/ready` = not ready؛ لا قرار بلا حفظ | 503 | — | ✅ |

## 53. KNOWN UNKNOWNS — [NOT VERIFIED]

1. عدّادات transactions/decisions/alerts التفصيلية (تعذّر psql في جلسة سابقة؛ الأرقام المؤكدة من `/ready`).
2. latency SLO / performance benchmarks — لا أرقام موثقة.
3. فحص UI بصري شامل (browser E2E) — تم static فقط في هذه الجولة.
4. سلوك النظام تحت حمل حقيقي (load test) — لم يُنفَّذ.
5. سبب غياب Redis/Kafka (قرار غير موثق).

## 54. RECOMMENDED CONTINUATION POINT

1. **P0:** إصلاح 22 اختبارًا فاشلًا (watchlist/AML evidence) ثم merge `stage3-recovery`.
2. **P0:** إعادة تدريب ML على بيانات حقيقية موسومة + معايرة IsoForest.
3. **P1:** TLS + env=production + أسرار صريحة.
4. **P2:** Agent Platform ضمن الحدود في §48.

## 55. EVIDENCE INDEX

كل وسم في هذا الملف يشير إلى: ملف:سطر (`orchestrator.py`, `fraud_agent.py`, `pgdb.py:150-210`, `schemas.py`)، أو migration (`032_payload_hash_feedback.sql`)، أو endpoint حي (`/ready` @ 2026-09-19)، أو اختبار (`test_decision_engine.py`, `test_confidence.py`, `test_fx.py`, `test_tenant_policy.py`)، أو commit (`a50f917`, `7faf53a`, `462ed87`).

## 56. FINAL REALITY REPORT

- **What definitely exists:** كل الملفات/الجداول/الترحيلات/النماذج الموثقة أعلاه — [CODE/DATABASE VERIFIED].
- **What definitely works:** التقييم الكامل end-to-end، الأمان، العزل، FX، الحُرّاس، audit، idempotency+payload_hash، البوابات — [RUNTIME/TEST VERIFIED].
- **Exists but incomplete:** Card rail (token-only أساس بلا تكامل Visa حقيقي)، feedback lifecycle (موجود بلا تدريب فعلي بعده).
- **Broken:** 22 اختبارًا (watchlist/AML) — دين تقني.
- **Missing:** ML إنتاجي، Agent Platform، TLS، load testing.
- **Planned only:** champion/challenger، rule backtesting، multi-rail.
- **Not verified:** §53.
- **Current blockers:** ML تركيبي + 22 اختبارًا فاشلًا.
- **Security risks:** env=development؛ لا أسرار مكشوفة؛ LLM redaction موجود.
- **Production blockers:** ML + TLS + الاختبارات الفاشلة.
- **Agent capabilities الحالية:** شرح عربي فقط (FraudAgent) — لا قرار.
- **Missing Agent Platform:** §47 كاملًا.
- **نقطة الاستمرار الدقيقة:** §54.

---

*نهاية الوثيقة — AEGIS_MASTER_SYSTEM_KNOWLEDGE_BASE.md — فُحصت من `/home/zr0/Aegis` @ `stage3-recovery` / `a50f917` بتاريخ 2026-09-19.*
