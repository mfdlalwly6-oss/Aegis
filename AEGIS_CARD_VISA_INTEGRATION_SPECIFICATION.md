# AEGIS — Stage 3: Final Card/Visa Integration Implementation Specification
# مواصفة تنفيذية نهائية لتكامل Card / Visa-compatible fraud-risk

> **التاريخ:** 2026-09-18 · **الحالة:** HEAD `462ed87` — **RESEARCH → SPECIFICATION → VALIDATION فقط. لا تعديل كود/DB/config/models/APIs، لا migrations، لا commit.**
> **وسوم الأدلة:** [CODE]=كود AEGIS فعلي (ملف/دالة) · [RESEARCH]=بحث عام موثق · [DOC]=مصدر أولي للمنصة · [INFERENCE]=استنتاج هندسي · [UNVERIFIED]=غير مؤكد.
> هذه المواصفة تحوّل تكامل Card/Visa من بحث عام إلى مواصفة تنفيذية بلا غموض معماري.

---

# التصحيحات العشرة الإلزامية (مطبَّقة على كامل المواصفة)

1. **AEGIS ليس جزءًا من VisaNet ولا نظام Visa.** هو **Real-Time Fraud Risk & Decisioning Engine** قابل للدمج مع Card Authorization/Authentication flows. [تصحيح مصطلحي]
2. **CHALLENGE ≠ 3DS تلقائيًا.** CHALLENGE/STEP-UP هو risk outcome؛ المؤسسة المدمَج معها تقرر التنفيذ (3DS/OTP/biometric/غيره). [CODE: `_decide` يعيد CHALLENGE فقط — orchestrator.py]
3. **نتائج ML الحالية (5000 سجل synthetic، metrics=1.0) = دليل اختبار صناعي فقط**، وليست production performance. [CODE: metadata.json «synthetic — NOT real fraud data»]
4. **معايرة IsoForest:** لا يُفترض Isotonic/Platt تلقائيًا. الخيارات الممكنة: (أ) Isotonic regression، (ب) Platt scaling (sigmoid)، (ج) Empirical percentile mapping، (د) إعادة تدريب IsoForest مع معايرة داخلية. **كلها يجب اختبارها تجريبيًا على بيانات حقيقية** — لا يُختار أيها دون تجربة. [UNVERIFIED أيها الأنسب]
5. **Idempotency محفوظة + إصلاح duplicate semantics:** إضافة `payload_hash` بحيث `same idempotency_key + different payload = conflict (409)`، لا إعادة نتيجة قديمة بشكل أعمى. [CODE: orchestrator.py:137-150 الحالي يعيد cached بلا مقارنة حمولة]
6. **فصل:** P1 = إصلاح semantics الـ missing/unavailable behavior · P3 = advanced sequence/entity behavioral profiling (Featurespace-style) — منفصلان تمامًا. [CODE: _behavior_score]
7. **Feedback = lifecycle كامل** (transaction→decision→case/dispute→investigation outcome→fraud label→dataset→validation→candidate model→shadow→champion)، وليس مجرد endpoint. [تصميم]
8. **Canonical model:** foundation قابلة للتوسع، **نبدأ Card rail فقط** — لا تُنفَّذ كل الـ rails الآن. [INFERENCE]
9. **FraudAgent/LLM = Explanatory/Investigator Copilot فقط:** لا يقرر fraud، لا يغيّر score، لا ينفّذ financial action، لا يكتب قرارًا في DB، لا يتواصل مع العميل. [CODE: fraud_agent.py يعمل بعد القرار ولا يكتب قرارًا]
10. **Rule backtesting = offline evaluation framework** أساسًا، وليس بالضرورة public API. [RESEARCH: Stripe/Adyen يدعمان backtesting]

---

# PART A — Card/Visa End-to-End Scenario

```
Cardholder
  → Merchant (يجمع بيانات البطاقة/الجهاز)
  → PSP/Gateway (يوجّه)
  → Acquirer (يمرّر للشبكة)
  → Card Network (Visa/Mastercard — توجيه)
  → Issuer (يمسك قرار الموافقة)
       │
       ├─→ [قبل قرار الموافقة] Issuer يستدعي AEGIS (risk evaluation)
       │        AEGIS → Risk Decision (ALLOW/CHALLENGE/REVIEW/BLOCK)
       │        Issuer → Institution Action (approve/decline/step-up)
       │        Authorization Response ← Issuer
       │
  ← Network ← Acquirer ← PSP ← Merchant ← Cardholder
```

**فصل حاسم [RESEARCH/DOC]:**
- **Authentication** (إثبات هوية حامل البطاقة — 3DS/OTP) ≠ **Authorization** (موافقة المُصدِر المالية).
- **Fraud scoring (AEGIS)** يحدث **قبل/أثناء قرار الـ Authorization** لدى المُصدِر.
- **3DS challenge** هو *نتيجة* محتملة لقرار CHALLENGE (تنفّذه المؤسسة)، لا القرار نفسه.
- **Step-up** = رفع مستوى التحقق (3DS challenge/biometric) عند CHALLENGE.
- **Decline** = رفض الـ authorization (عند BLOCK). **Review** = تعليق للمراجعة اليدوية (عند REVIEW).
- **[UNVERIFIED]** الموضع الدقيق داخل stack المُصدِر يعتمد على تكامل كل بنك (in-line vs sidecar).

---

# PART B — AEGIS Card Rail (كيف تدخل معاملة Card)

الـ 26 مرحلة — **موجود [CODE] / يحتاج إضافة [ADD] / يحتاج تعديل [MODIFY]**:

| # | المرحلة | الحالة | التفصيل |
|---|---------|--------|---------|
| 1 | Request lifecycle | [CODE] | متزامن عبر webhook |
| 2 | Endpoint | [CODE] | `POST /api/v1/webhook/wallet/webhook` — قابل لإعادة الاستخدام للبطاقة (webhook عام) |
| 3 | Authentication | [CODE] | `x-api-key` → tenant lookup |
| 4 | HMAC | [CODE] | `verify_signature` HMAC-SHA256 على الجسم الخام (webhook.py) |
| 5 | Replay protection | [CODE] | timestamp window (5min/72h) |
| 6 | Tenant isolation | [CODE] | RLS + ContextVar + namespacing |
| 7 | Idempotency | [CODE] | key + tx_id (orchestrator.py:137-150) |
| 8 | **payload_hash** | **[ADD]** | **غير موجود** — يضاف لإصلاح duplicate semantics (§G) |
| 9 | Normalization | [CODE] | `normalize_transaction` → Transaction schema |
| 10 | FX | [CODE] | `_apply_fx` → fx.normalize (4 tiers) |
| 11 | Feature extraction | [CODE] | FeatureExtractor.extract/vector (20) |
| 12 | Rules | [CODE] | RuleEngine (21 قاعدة) |
| 13 | ML | [CODE/⚠️] | GB — اصطناعي، يحتاج إعادة تدريب |
| 14 | Anomaly | [CODE/⚠️] | IsoForest — منحاز، يحتاج معايرة |
| 15 | Behavior | [MODIFY] | P1: إصلاح missing/unavailable semantics (F-06) |
| 16 | Graph | [CODE] | GraphEngine (tenant-namespaced) |
| 17 | AML | [CODE] | AMLService (sanctions/pep/watchlist/typologies) |
| 18 | Fusion | [CODE] | availability-aware weighted |
| 19 | Confidence | [CODE] | orchestrator (healthy/degraded/unavailable) |
| 20 | Guards | [CODE] | sanctions/watchlist/AML-down/FX-missing |
| 21 | Decision | [CODE] | `_decide` + thresholds |
| 22 | Reasons | [CODE] | top_reasons |
| 23 | Explanation | [CODE] | FraudAgent (بعد القرار، لا يغيّره) |
| 24 | Persistence | [CODE] | decisions (34 عمودًا) + transactions (28) |
| 25 | Audit | [CODE] | hash-chained audit_log |
| 26 | Response | [CODE] | decision + risk_score + confidence + component_health |
| — | **Card context ingestion** | **[ADD]** | حقول Card (§C) — بعضها موجود جزئيًا في Transaction schema |

**ملاحظة:** الـ endpoint الحالي `/wallet/webhook` عام فعليًا (يستقبل أي معاملة). لكن لتمييز Card rail بوضوح يُقترح [ADD] endpoint مخصص `POST /api/v1/risk/card` بنفس المنطق الداخلي مع card context — أو توثيق إعادة استخدام الموجود. **[INFERENCE]** — القرار النهائي عند التنفيذ.

---

# PART C — Card Canonical Data Model

## C.1 Transaction (موجود جزئيًا في [CODE] schemas.py:97)
`transaction_id, timestamp, amount, currency, merchant_id, channel, rail, country` — الحالي يحوي `tx_id, timestamp, amount, currency, merchant_id, channel` ويحتاج `rail` صريحًا.

## C.2 Card context — الحقول المطلوبة فعلًا
| الحقل | موجود في AEGIS؟ | canonical عام؟ | ملاحظة |
|-------|------------------|------------------|--------|
| card token/reference (token، لا PAN) | ⚠️ `card_bin`, `card_last4` موجودان [CODE schemas.py:139-140] | نعم | **token فقط — لا PAN أبدًا** |
| card-present / card-not-present | ❌ [ADD] | نعم | `card_present: bool` |
| entry mode | ❌ [ADD] | نعم (EMV generic) | `entry_mode` (chip/contactless/ecom/keyed) |
| merchant category (mcc) | ✅ `mcc` [CODE schemas.py:141] | نعم | موجود |
| issuer/acquirer context | ❌ [ADD] | نعم (generic ids) | `issuer_id`, `acquirer_id` (generic — ليس Visa-specific) |
| recurring indicator | ❌ [ADD] | نعم | `recurring: bool` |
| tokenized payment indicator | ❌ [ADD] | نعم | `tokenized: bool` |
| card age / account age | ⚠️ `account_age_days` في metadata [CODE features] | نعم | يُشتق داخليًا إن أمكن |
| authorization context | ❌ [ADD] | نعم | `auth_context` (auth code placeholder) |
**لا تُخترع حقول Visa-proprietary. كل ما فوق generic/EMV-level. [DOC: emvco.com]**

## C.3 Authentication / 3DS (generic EMV 3DS، لا proprietary)
| الحقل | canonical؟ | ملاحظة |
|-------|-----------|--------|
| `three_ds_present: bool` | نعم | هل مُرّرت عبر 3DS |
| `three_ds_version: str` | نعم | "2.1"/"2.2" (generic) |
| `authentication_result` | نعم | frictionless/challenge/failed (generic) |
| `challenge_or_frictionless: str` | نعم | "frictionless"/"challenge" |
| `authentication_value` (CAVV/AAV) | ⚠️ | generic EMV — لكن **يُخزَّن كمرجع لا كسرّ**؛ [UNVERIFIED] التخزين الآمن يحتاج تأكيد PCI |
| `risk_context` | نعم | سياق إضافي |
**[DOC: emvco.com]** 3DS2 frictionless عند انخفاض الخطر، challenge عند ارتفاعه.

---

# PART D — Exact API Contracts

## D.1 Card Risk Evaluation
**Request:**
```json
{
  "transaction": {
    "tx_id": "...", "timestamp": "...", "amount": 250.0, "currency": "USD",
    "sender_account_id": "acct_...", "beneficiary_account_id": "merch_...",
    "merchant_id": "...", "mcc": "5411", "channel": "card",
    "card": {"token": "tok_...", "card_present": false, "entry_mode": "ecom",
             "recurring": false, "tokenized": true},
    "device": {...}, "geo": {...}, "behavior": {...}
  },
  "context": {"authentication": {"three_ds_present": false}}
}
```
**Headers:** `x-api-key`, `x-wallet-signature` (HMAC-SHA256), `X-Idempotency-Key`.
**Response (200):**
```json
{"decision":"challenge","risk_score":0.42,"risk_band":"medium","confidence":0.95,
 "top_reasons":[...],"reasoning_ar":"...","component_health":{...},"degraded_mode":false,
 "reference_amount":250.0,"reference_currency":"USD","alert":null,"request_id":"..."}
```
**Status codes [CODE/ADD]:**
| Code | الحالة | المصدر |
|------|--------|--------|
| 200 | نجاح | [CODE] |
| 400 | malformed / amount invalid / validation error | [CODE] |
| 401 | missing/invalid api_key أو signature | [CODE] |
| 403 | tenant_suspended | [CODE] |
| 404 | tenant not found | [CODE] |
| **409** | **idempotency conflict (same key + different payload_hash)** | **[ADD]** |
| 422 | currency_disabled / replay window | [CODE] |
| 429 | rate limit | [CODE] |
| 5xx | engine unavailable (graceful — degraded) | [CODE] |

## D.2 Authentication / 3DS Context
**القرار:** authentication context يدخل **مع** الـ risk request (ضمن `context.authentication`) — **لا endpoint منفصل**. **السبب [INFERENCE]:** الـ 3DS نتيجة للقرار، فالسياق يجب أن يسبقه في نفس الطلب. endpoint منفصل غير مبرر الآن. **[ADD field، لا endpoint].**

## D.3 Feedback Contract
**[ADD] `POST /api/v1/feedback`** — يُرسل من المؤسسة بعد تأكيد النتيجة:
```json
{"tx_id":"...","outcome":"confirmed_fraud|confirmed_legitimate|suspected_fraud|chargeback|dispute|unknown",
 "source":"chargeback|investigator|scheme","occurred_at":"...","confidence":0.9,"case_id":"...","notes":"..."}
```
- **من يرسل:** المؤسسة (نظام disputes/chargebacks أو المحقق).
- **متى:** بعد تأكيد النتيجة (قد يتأخر أيامًا).
- **الربط:** بـ `tx_id` (+ `case_id` إن وُجد).
- **منع duplicate labels:** uniqueness على `(tx_id, outcome_type, source)` أو upsert.
- **يُحفظ:** source, timestamp, confidence — كـ label للتدريب المستقبلي.

---

# PART E — Fraud Detection Scenarios (21 سيناريو)

كل سيناريو: Input → Signals → Rules → ML → Behavior → Graph → AML → Fusion → Guards → Decision → Institution action. **[CODE-مشتق — القرار يعتمد على المنطق الموثق، لا مُختار مسبقًا]**

| # | السيناريو | الإشارات الرئيسية | القرار المتوقع (مشتق) | إجراء المؤسسة |
|---|-----------|-------------------|------------------------|----------------|
| 1 | شراء عادي | كل شيء طبيعي | ALLOW | approve |
| 2 | جهاز جديد | first_seen_today=1 | CHALLENGE (R-DEV) | step-up (3DS/OTP) |
| 3 | دولة جديدة | geo شاذ | CHALLENGE/REVIEW | step-up |
| 4 | مبلغ عالٍ | amount_usd>حد | CHALLENGE/REVIEW | step-up/review |
| 5 | Velocity attack | tx_per_min>6 | CHALLENGE (R-VEL-001) | step-up |
| 6 | Card testing | declines>5 + مبالغ صغيرة | BLOCK/CHALLENGE (R-CT-001) | decline/review |
| 7 | ATO | pw تغيّر+جهاز جديد+مستفيد جديد | REVIEW/BLOCK (R-ATO critical) | hold |
| 8 | جهاز مخترق | emulator/rooted | BLOCK (R-DEV-002 critical) | decline |
| 9 | تاجر مشبوه | high_risk_merchant | REVIEW | review |
| 10 | 3DS frictionless ناجح | auth=frictionless+خطر منخفض | ALLOW | approve |
| 11 | 3DS challenge | CHALLENGE → المؤسسة تطلب challenge | CHALLENGE | 3DS challenge |
| 12 | 3DS فشل | auth=failed | REVIEW/BLOCK | decline/review |
| 13 | جهاز/IP مرتبط باحتيال معروف | graph hops≤2 +0.30 | REVIEW/BLOCK | hold |
| 14 | بطاقات متعددة على جهاز واحد | graph shared_device + velocity | REVIEW (§F) | review |
| 15 | بيانات سلوك مفقودة | behavior unavailable | (بعد P1: يُستبعد وزنه) degraded | per policy |
| 16 | ML unavailable | ml_prob=None | degraded, وزن يُعاد توزيعه | per policy |
| 17 | Graph unavailable | graph unavailable | degraded | per policy |
| 18 | AML unavailable | aml down | **REVIEW إجباري (fail-closed)** | review [TEST] |
| 19 | كل المحركات unavailable | active_weight=0 | **GAP حالي: ALLOW — يُضاف guard ⇒ REVIEW [ADD P1]** | review |
| 20 | Duplicate request | same key + same payload | cached + duplicate:true | idempotent |
| 21 | Same key + modified payload | payload_hash مختلف | **409 conflict [ADD]** | reject |
**لا يُفترض أن كل حالة BLOCK — القرار يعتمد على الـ score الفعلي + thresholds + guards.**

---

# PART F — Card Testing / Enumeration (أقل تصميم)

**المشكلة:** AEGIS transaction-centric؛ الهجوم = multiple cards + same device/IP + small amounts + high velocity + repeated attempts.

**الحل الأدنى (بلا إعادة بناء):**
- **[CODE موجود]** Graph يتتبع shared_device / shared_ip عبر الحسابات (graph/engine.py) — **يعيد الاستخدام**.
- **[ADD minimal]** velocity counters عبر-بطاقات على جهاز/IP: نمط `declines_per_device_1h` و`distinct_cards_per_device_1h` — يُحسبان من `transactions` (device_id) بنفس نمط velocity الموجود (FeatureExtractor) — **لا Redis الآن**؛ PostgreSQL كافٍ للحجم الحالي.
- **[ADD]** قاعدة: `distinct_cards_per_device_1h > N AND avg_amount < threshold AND declines > M` ⇒ REVIEW/BLOCK.
- **لا** attack entity ولا temporary aggregation ولا Redis الآن — أقل تصميم يحقق الكشف.
**[INFERENCE]** Redis يؤجَّل للتوسع الأفقي فقط (§M).

---

# PART G — Exact AEGIS Changes

| Component | Current implementation | Required change | Priority | Files/functions | DB change | API change | Tests |
|-----------|------------------------|-----------------|----------|-----------------|-----------|------------|-------|
| Idempotency | key+tx_id، بلا payload compare [orchestrator.py:137-150] | أضف payload_hash → 409 عند الاختلاف | P1 | orchestrator.evaluate_and_persist, decision_repo.create | +payload_hash | +409 | conflict test |
| Behavior missing | degraded→يدخل بصفر [orchestrator:207-214] | اعتبره unavailable (إعادة توزيع) | P1 | orchestrator health logic | — | — | update test_confidence |
| Card context | جزئي (card_bin/last4/mcc) [schemas.py:139-141] | أضف card context fields | P1 | schemas.Transaction | +card fields | +card في request | schema tests |
| 3DS context | ❌ NOT FOUND | أضف context.authentication | P1 | schemas + normalize | +auth context | +field | contract test |
| Feedback | ❌ NOT FOUND | feedback endpoint + lifecycle | P1 | جديد feedback.py + repo | +feedback table | +POST /feedback | feedback tests |
| Rule backtesting | ❌ NOT FOUND | offline harness (لا public API) | P2 | scripts/ أو module داخلي | — | — | backtest tests |
| All-down guard | ❌ NOT FOUND | كل المحركات ساقطة ⇒ REVIEW | P1 | orchestrator guards | — | — | failure-injection test |
| ML retrain | synthetic [train_models.py] | بيانات حقيقية + temporal split + calibration | P0 | training/* + ml/ensemble | +model metadata | — | eval tests |
| Iso calibration | خطية يدوية [ensemble.py:100] | اختبر isotonic/Platt/percentile تجريبيًا | P0 | ensemble.py | — | — | calibration tests |
| Redaction LLM | ❌ [fraud_agent.py] | redact PII قبل الإرسال | P0 | fraud_agent.py | — | — | redaction test |
| Feature amount | خام [features.py:116] | amount_usd في vector | P0 | features.vector + retrain | — | — | vector order test |
**كل ما فوق مربوط بأسماء ملفات/دوال حقيقية من الـ repository.**

---

# PART H — Database (migrations المطلوبة فقط)

| Migration | السبب | Fields | Indexes | Constraints | Relationships |
|-----------|-------|--------|---------|-------------|---------------|
| card_context | سياق البطاقة | card_token, card_present, entry_mode, recurring, tokenized, mcc, issuer_id, acquirer_id | idx(tx_id) | token NOT NULL | → transactions |
| payload_hash | duplicate semantics | payload_hash | idx(tenant,tx_id) | — | → decisions |
| applied_weights_json | trace الأوزان الاسمية | applied_weights_json | — | — | → decisions |
| feedback | labels | tx_id, outcome, source, occurred_at, confidence, case_id, notes | idx(tx_id), uq(tx_id,outcome,source) | outcome IN (...) | → transactions, cases |
| auth_context | سياق 3DS | three_ds_present, version, result, flow, auth_value_ref | idx(tx_id) | — | → transactions |
| model_metadata | governance | version, trained_at, metrics_json, artifact_hash | — | version UNIQUE | → (ملفات النموذج) |
**لا جداول إضافية لمجرد الإمكان.**

---

# PART I — Decision Semantics (فصل صريح)

| المستوى | من يملكه | القيم | المعنى |
|---------|----------|-------|--------|
| **AEGIS Risk Decision** | AEGIS `_decide` | ALLOW / CHALLENGE / REVIEW / BLOCK | تقييم مخاطرة فقط |
| **Institution Payment Decision** | المؤسسة | approve / decline / hold | قرار الدفع الفعلي |
| **Authentication Action** | المؤسسة | none / 3DS / OTP / biometric | رفع التحقق (ليس مساويًا لـ CHALLENGE) |
| **Authorization Response** | Issuer/Network | approved / declined | الرد النهائي على الشبكة |
**AEGIS يعيد Risk Decision فقط؛ الباقي مسؤولية المؤسسة. CHALLENGE من AEGIS قد يقود المؤسسة لأي authentication action (3DS أو غيره).**

---

# PART J — Security (Card)

- **PAN:** **لا يُخزَّن أبدًا** — card token/reference فقط [تصميم]. **CVV:** لا يُخزَّن ولا يُمرَّر. **PCI boundaries:** AEGIS خارج نطاق PCI إن لم يمس PAN/CVV — يبقى على tokenized references.
- **encryption:** hmac_secret مشفّر (موجود)؛ باقي البيانات حساسة لكن ليست PCI. **HMAC:** على الجسم الخام [CODE]. **replay:** timestamp window [CODE]. **idempotency + payload_hash:** §G. **TLS:** reverse proxy (نشر). **tenant isolation:** RLS [CODE]. **audit:** hash-chain [CODE].
- **log redaction:** لا تُسجَّل حقول حساسة كاملة. **LLM redaction:** P0 (F-07). **SSRF:** محمي في الإشعارات؛ **[ADD] لـ watchlist provider** (فجوة). **model integrity:** **[ADD] artifact_hash/tوقيع للـ joblib** (model_metadata).

---

# PART K — Testing (test matrix)

| الطبقة | أمثلة (Given/When/Then) |
|--------|--------------------------|
| **Unit** | Given قاعدة، When condition يتحقق، Then RuleHit.score_contribution=rule.score |
| **Integration** | Given tx كاملة، When webhook، Then decision + كل component scores مخزنة |
| **Contract** | Given request بالـ schema، When POST، Then response يطابق contract (status/fields) |
| **Security** | Given توقيع خاطئ، Then 401 · Given tenant A، Then لا يرى بيانات B |
| **Failure injection** | Given ML down، Then degraded + وزن مُعاد توزيعه · Given كل المحركات down، Then REVIEW |
| **Property-based** | For all inputs: final ∈ [0,1]، Σ applied_weights = 1، decision ∈ {4 قيم} |
| **Load** | webhook يتحمل N TPS بلا تدهور p99 < حد |
| **Card fraud** | سيناريوهات §E الـ 21 كلها كاختبارات Given/When/Then |

---

# PART L — Observability

**Metrics:** authorization latency (p50/p95/p99) · decision distribution · FP indicators · engine availability · degraded decisions · 3DS challenge rate · block/review rates · ML drift (PSI) · feature drift · feedback rate · model_version · rule_set_version.
**Audit لكل decision [CODE موجود + ADD]:** كل component scores + component_health + applied_weights_json [ADD] + policy/model/config versions + confidence + degraded_reason + top_reasons + reasoning_ar + payload_hash [ADD].

---

# PART M — Production Architecture (ملاءمة الحجم، لا تقليد)

| المرحلة | المعمارية | ملاحظة |
|---------|-----------|--------|
| **NOW** | Monolith FastAPI + PostgreSQL + in-memory graph + joblib | كافٍ للحجم الحالي — **KEEP** |
| **NEXT (Card rail)** | + feedback endpoint + card/auth context + payload_hash + redaction + backtest harness | إضافات محدودة على الموجود |
| **LATER (scale حقيقي)** | Redis (rate-limit + velocity عند تعدد instances) · graph persistence (عند الحجم) · Kafka/EventBus خارجي (عند الحاجة) · microservices (عند الحاجة فقط) | **يؤجَّل — لا يُبنى الآن** |
**لا microservices/Kafka/K8s/Graph DB الآن — لأن الحجم لا يبررها (INFERENCE).**

---

# PART N — Final Implementation Roadmap

## P0 (قبل اعتبار Card integration آمنًا)
- ML retrain ببيانات حقيقية + temporal split (dep: بيانات · risk: توافق vector · rollback: نموذج سابق بالإصدار · test: eval).
- Iso calibration (اختبار تجريبي للخيارات) · Redaction LLM · Feature amount_usd.

## P1 (Card rail functional)
- payload_hash + 409 · behavior-missing semantics · card context · auth context · feedback endpoint+lifecycle · all-down guard.

## P2 (production maturity)
- Rule backtesting (offline) · drift monitoring · champion/challenger · SSRF-watchlist · توقيع النماذج.

## P3 (يؤجَّل)
- Canonical multi-rail (غير Card) · sequence behavioral profiling · Redis/graph-persistence/Kafka/microservices (عند scale).

---

# الخلاصة النهائية (12 بندًا)

1. **Final Card/Visa Integration Architecture:** AEGIS كـ Real-Time Risk & Decisioning Engine يُدمج issuer/PSP-side قبل الـ authorization (PART A/M).
2. **Final API Contracts:** risk evaluation + feedback (PART D) — status codes محددة بما فيها 409 للـ payload conflict.
3. **Final Data Model:** Transaction + card context + auth context (PART C) — generic/EMV فقط، لا proprietary.
4. **Final Fraud Scenarios:** 21 سيناريو (PART E) — قرارات مشتقة لا مختارة.
5. **Exact Repository Changes:** جدول G بأسماء ملفات/دوال حقيقية.
6. **Exact DB Changes:** 6 migrations (PART H) — بلا إضافات غير ضرورية.
7. **Exact Tests:** test matrix (PART K) — Given/When/Then قابلة للقياس.
8. **Dependency Graph:** ML retrain → (Iso calib, amount_usd) · card context → contract tests · feedback → lifecycle → retrain dataset.
9. **Implementation Order:** P0 → P1 → P2 → P3 (PART N).
10. **Risks:** توافق الـ vector (ترتيب حرج) · تغيير behavior يؤثر على test_confidence · feedback lifecycle يحتاج تكامل مؤسسي.
11. **Open Questions:** الموضع الدقيق داخل stack كل بنك [UNVERIFIED] · تخزين authentication_value الآمن (PCI) [UNVERIFIED] · متطلبات CBY التفصيلية [Requires legal/regulatory confirmation].
12. **Items UNVERIFIED:** أي خيار calibration للـ Iso (يُختبر تجريبيًا) · أداء ML على بيانات حقيقية · تفاصيل Visa-proprietary (غير مستخدمة عمدًا).

> **هذه المرحلة RESEARCH → SPECIFICATION → VALIDATION فقط. لم يُعدَّل أي كود، لا migrations، لا APIs، لا models، لا architecture. HEAD `462ed87` سليم. المواصفة خالية من الغموض المعماري والافتراضات غير الموثقة.**
