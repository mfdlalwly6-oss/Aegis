# AEGIS — Stage 3.1: Card/Visa Integration Pre-Implementation Verification Gate
# بوابة التحقق قبل التنفيذ — تدقيق المواصفة مقابل الـ repository الحقيقي

> **التاريخ:** 2026-09-18 · **الحالة:** HEAD `462ed87` — **AUDIT → VERIFY → CORRECT → READINESS فقط. لا تعديل كود/DB/migrations/APIs/models/config، لا commit، لا push.**
> **الغرض:** التحقق من `AEGIS_CARD_VISA_INTEGRATION_SPECIFICATION.md` حرفيًا مقابل الـ repository الحالي.

---

# 1. Executive Verification Summary

فُحصت كل claims المواصفة مقابل الكود الفعلي. **النتيجة: المواصفة سليمة البنية لكنها تحتوي على overstatements يجب تصحيحها، وعناصر موسومة [ADD] هي فعليًا غير موجودة (غياب حقيقي مؤكد).** التفاصيل أدناه. **لا blockers تمنع بدء التنفيذ بعد التصحيحات الموثقة أدناه.**

---

# 2. Repository Evidence (مؤكد من الفحص المباشر)

| العنصر | الدليل الفعلي | الحالة |
|--------|---------------|--------|
| Webhook endpoint | `POST /api/v1/webhook/wallet/webhook` — webhook.py | ✅ CODE |
| HMAC verify | `verify_signature` — webhook.py | ✅ CODE |
| Replay window | timestamp 5min/72h — webhook.py | ✅ CODE |
| Idempotency | `mark_seen`/`get_by_idempotency`/`get_by_tx` — orchestrator.py:137-150 + decision_repo | ✅ CODE |
| **payload_hash** | `grep payload_hash backend/ migrations/` → **لا نتائج** | ❌ **NOT FOUND** |
| **risk/card endpoint** | `grep risk/card` → **لا نتائج** | ❌ **NOT FOUND** (الموجود `/wallet/webhook`) |
| **Feedback endpoint/table** | لا endpoint؛ `feedback` يظهر فقط ككلمات في investigator/webhook/features (سياق آخر) | ❌ **NOT FOUND** |
| All-engines-down guard | orchestrator.py:216-235 — عند active_weight=0 → `final=0` → ALLOW، **لا guard** | ❌ **NOT FOUND (GAP)** |
| Card fields في schema | `card_bin`, `card_last4`, `mcc` — schemas.py:139-141 | ✅ CODE (جزئي) |
| 3DS/auth context | `grep 3ds/authentication في webhook` → لا (فقط card_declines_1h + authentication.failure audit) | ❌ **NOT FOUND** |
| Channel enum | `CARD_PRESENT`, `CARD_NOT_PRESENT`, ... موجودة — schemas.py:11-22 | ✅ CODE |
| DeviceContext/BehaviorSignals | كاملة — schemas.py:71-89 | ✅ CODE |
| Idempotency constraint | `idempotency_key TEXT UNIQUE` — 001_init.sql:98 | ✅ CODE |

---

# 3. `[CODE]` Verification — التصحيحات المطلوبة

| SPECIFICATION CLAIM | ACTUAL | SUPPORTED? | EVIDENCE | REQUIRED CORRECTION |
|---|---|---|---|---|
| webhook endpoint عام يقبل card | `/wallet/webhook` فقط؛ لا `/risk/card` | PARTIAL | webhook.py | المواصفة ذكرت إعادة استخدام أو endpoint جديد — **الصحيح: `/wallet/webhook` موجود ويعمل؛ `/risk/card` غير موجود (ADD)** |
| Card fields موجودة | card_bin/card_last4/mcc فقط | PARTIAL | schemas.py:139-141 | باقي card context (entry_mode, recurring, tokenized, 3DS) **غير موجود = ADD** |
| 3DS context | غير موجود | NO | grep صفري | **ADD** — ليس جزئيًا |
| payload_hash | غير موجود | NO | grep صفري | **ADD** (تصحيح: ليس "إصلاح semantics موجود" بل **إضافة جديدة**) |
| Feedback | غير موجود | NO | grep صفري | **ADD** |
| All-engines-down ⇒ REVIEW | **غير موجود — عند كل المكونات down: final=0 → ALLOW** | **NO — CONFLICT** | orchestrator.py:216-235 | **SPECIFICATION CONFLICT**: السيناريو 19 في المواصفة وسمه "GAP يُضاف" — مؤكد: **الكود الحالي يفشل ALLOW عند انهيار شامل (fail-open)**. يجب [ADD] guard. |
| Guards (sanctions/watchlist/AML-down/FX) | موجودة | YES | orchestrator.py:266-300 | لا تصحيح |
| Fusion availability-aware | موجود | YES | orchestrator.py:216-235 | لا تصحيح |
| Confidence | موجود (healthy=1/degraded=0.5/unavailable=0) | YES | orchestrator.py:248-264 | لا تصحيح |

---

# 4. `[ADD]` / `[MODIFY]` Verification

| العنصر | التصنيف الصحيح | Current | Required | Exact file/function | API | DB | ML | Tests | Risk | Rollback |
|---|---|---|---|---|---|---|---|---|---|---|
| payload_hash | **ADD** | غير موجود | hash الحمولة → 409 | orchestrator.evaluate_and_persist + decision_repo.create | +409 | +col | — | conflict test | منخفض | إزالة الفحص |
| behavior missing semantics | **MODIFY** | degraded→يدخل بصفر (orch:207-214) | unavailable→يُستبعد وزنه | orchestrator health logic | — | — | — | update test_confidence | يغيّر confidence | عكس التغيير |
| card context | **ADD** | جزئي (bin/last4/mcc) | +entry_mode/recurring/tokenized/card_present | schemas.Transaction + normalize | +fields | +cols | — | schema tests | منخفض | — |
| 3DS/auth context | **ADD** | غير موجود | context.authentication | schemas + normalize | +field | +cols | — | contract test | منخفض | — |
| feedback | **ADD** | غير موجود | endpoint + lifecycle + labels | جديد feedback.py + repo | +POST | +table | يغذي retrain | feedback tests | متوسط | — |
| all-engines-down guard | **ADD** | ALLOW عند الانهيار الشامل | ⇒ REVIEW إجباري | orchestrator guards | — | — | — | failure-injection test | منخفض | — |
| ML retrain | **REBUILD** | synthetic | بيانات حقيقية + temporal split + calibration | training/* + ml/ensemble | — | +model_metadata | نعم | eval tests | عالٍ (توافق vector) | نموذج سابق بالإصدار |
| Iso calibration | **MODIFY** (تجريبي) | خطية يدوية ensemble.py:100 | اختبر 4 خيارات (§10) | ensemble.py | — | — | نعم | calibration tests | متوسط | الاحتفاظ بالحالي |
| amount_usd في vector | **CANDIDATE — EXPERIMENT REQUIRED** (§9) | خام amount features.py:116 | قيد التحقق | features.vector | — | — | نعم | vector order test | يكسر الـ artifacts | لا تغيير قبل التجربة |
| LLM redaction | **ADD** | لا redaction fraud_agent.py | redact PII | fraud_agent.py | — | — | — | redaction test | منخفض | — |

---

# 5. Unsupported Claims — التصنيف

| Claim | التصنيف | السبب |
|---|---|---|
| webhook/HMAC/replay/idempotency/tenant-isolation/guards/fusion/confidence موجودة | SUPPORTED | CODE |
| payload_hash, feedback, 3DS context, all-down guard, /risk/card | (موسومة ADD في المواصفة) — غيابها **مؤكد** | CODE (غياب) |
| الموضع الدقيق داخل stack كل بنك | UNVERIFIED | يعتمد على التكامل |
| تخزين authentication_value الآمن | UNVERIFIED | يحتاج تقييم PCI |
| متطلبات CBY التفصيلية | UNVERIFIED | Requires legal/regulatory confirmation |
| أي خيار calibration للـ Iso هو الأنسب | UNVERIFIED | يُختبر تجريبيًا (§10) |
| أداء ML على بيانات حقيقية | UNVERIFIED | لا بيانات حقيقية |

---

# 6. Card Token / BIN / Last4 Correction (إلزامي)

**الفصل الصريح (مؤكد من schemas.py:139-141):**
- **AEGIS الحالي يقبل `card_bin` و`card_last4` فقط** — لا `card_token` منفصل ولا PAN ولا CVV.
- **التصحيح الإلزامي للمواصفة:**
  - `PAN` → **NEVER** يُقبل/يُخزَّن في AEGIS.
  - `CVV` → **NEVER** يُقبل/يُخزَّن.
  - `card_token_reference` → token/reference **منفصل** (يُضاف) — **لا يُعتبر BIN+Last4 بديلًا عنه**.
  - `card_bin` → metadata فقط (routing/BIN intelligence).
  - `card_last4` → display/reference metadata فقط.
- **BIN + Last4 ≠ token.** المواصفة يجب أن تضيف `card_token_reference` كحقل مستقل وتُبقي BIN/Last4 كـ metadata. **[تصحيح مواصفة — مطبَّق].**
- **التحقق:** card_bin/card_last4 حاليًا في schema لكن **لا يدخلان ML vector ولا قواعد ولا graph بشكل موثق** — استخدامهما الحالي محدود (مرجعية). [CODE: features.py لا يقرأهما في vector].

---

# 7. PCI Boundary Correction

**الصياغة المُصحَّحة (تستبدل أي claim بأن AEGIS خارج PCI):**
> "AEGIS is designed to **minimize PCI DSS scope** by avoiding PAN/CVV processing and storage. **Final PCI DSS scope must be determined by the institution's PCI/QSA/compliance assessment and deployment architecture.**"
**التحقق:** PAN/CVV/card_token/CAVV/AAV — AEGIS **لا يخزّن PAN/CVV** (CODE)؛ CAVV/AAV يُعامَل كمرجع لا سرّ لكن تخزينه **UNVERIFIED — يخضع لتقييم PCI**؛ logs/audit لا يجب أن تحمل PAN/CVV (لا يوجد حاليًا — CODE)؛ LLM/external providers: redaction إلزامية (F-07).

---

# 8. Final API Contracts (implementation-grade)

## POST /api/v1/risk/card **[ADD — endpoint جديد]**
(الموجود الفعلي `/wallet/webhook` — هذا endpoint مخصص مقترح)

**Headers:** `x-api-key` (str, required, secret) · `x-wallet-signature` (str, required, HMAC-SHA256 hex) · `X-Idempotency-Key` (str, required) · `X-Request-Id` (str, optional, correlation).

**Request fields:**
| name | type | req/opt | nullable | validation | sensitivity | storage |
|---|---|---|---|---|---|---|
| transaction.tx_id | str | required | no | unique per tenant | low | transactions |
| transaction.timestamp | ISO8601 | required | no | replay window | low | transactions |
| transaction.amount | float | required | no | >0 | medium | transactions |
| transaction.currency | str | required | no | 3-letter ISO | low | transactions |
| transaction.sender_account_id | str | required | no | — | high | transactions |
| transaction.beneficiary_account_id | str | required | no | — | high | transactions |
| transaction.merchant_id / mcc | str | optional | yes | — | low | transactions |
| transaction.channel | enum | optional | yes | Channel enum | low | transactions |
| transaction.card.card_token_reference | str | optional | yes | token only | **high** | card_context [ADD] |
| transaction.card.card_bin / card_last4 | str | optional | yes | metadata | medium | card_context [ADD] |
| transaction.card.card_present / entry_mode / recurring / tokenized | — | optional | yes | — | low | card_context [ADD] |
| context.authentication.three_ds_present/version/result/flow | — | optional | yes | — | medium | auth_context [ADD] |
| device / geo / behavior | obj | optional | yes | schemas | medium | transactions |
**Response schema:** `decision, risk_score, risk_band, confidence, top_reasons, reasoning_ar, component_health, degraded_mode, degraded_reason, reference_amount, reference_currency, alert, request_id, model_version, rule_set_version` — `model_version`/`rule_set_version` موجودان في decisions لكن **[ADD]** للتأكد من ظهورهما في response.

## POST /api/v1/feedback **[ADD]**
`tx_id`(req), `outcome`(req, enum: confirmed_fraud/confirmed_legitimate/suspected_fraud/chargeback/dispute/unknown), `source`(req), `occurred_at`(req), `confidence`(0-1, opt), `case_id`(opt), `notes`(opt).

---

# 9. Integration Failure Contract (رسمي)

| الحالة | HTTP | AEGIS decision | Institution action | retry | idempotency | audit | alert | fail policy |
|---|---|---|---|---|---|---|---|---|
| timeout | — | — | per institution | نفس key | محفوظ | — | — | institution-defined |
| AEGIS 5xx | 5xx | — | per institution | نفس key | محفوظ | logged | — | institution-defined |
| AEGIS 4xx | 400/401/403/404/409/422 | — | لا retry (أصلح الطلب) | لا | — | logged | — | **fail-closed (لا تمرير)** |
| ML unavailable | 200 | degraded decision | استخدم القرار (وزن مُعاد) | — | محفوظ | degraded_mode=1 | اختياري | **fail-open جزئي (degraded)** |
| Graph unavailable | 200 | degraded | ← | — | ← | ← | ← | fail-open جزئي |
| AML unavailable | 200 | **REVIEW إجباري** | review | — | ← | ← | نعم | **fail-closed** |
| Behavior unavailable | 200 | degraded (P1: يُستبعد) | ← | — | ← | ← | ← | fail-open جزئي |
| FX unavailable | 200 | REVIEW/BLOCK per policy | review | — | ← | ← | نعم | fail-closed |
| DB unavailable | 503 | — | per institution | نعم | — | — | — | institution-defined |
| **All engines unavailable** | 200 | **REVIEW [ADD guard]** — حاليًا ALLOW (GAP) | review | — | ← | ← | نعم | **fail-closed (مطلوب)** |
| partial response | 200 | degraded | ← | — | ← | ← | ← | fail-open جزئي |
| duplicate request | 200 | cached + duplicate:true | استخدم المخزّن | — | idempotent | — | — | n/a |
| **payload mismatch** | **409** | — | لا تمرّر | لا | conflict | logged | نعم | **fail-closed** |

---

# 10. 21-Scenario Verification (static)

كل سيناريو فُحص مقابل الكود. **الحالات غير المثبتة موسومة:**
- **1-5, 7-10, 13** (normal/new device/new country/high-value/velocity/ATO/compromised/suspicious merchant/frictionless/graph-linked): **PARTIALLY IMPLEMENTED** — القواعد/الإشارات موجودة لكن card-specific context (card_present, entry_mode) **غير موجود [ADD]**.
- **6 (Card testing):** PARTIALLY — R-CT-001 موجود لكن cross-card velocity per device **غير موجود [ADD §F]**.
- **11-12 (3DS challenge/failure):** NOT IMPLEMENTED — لا 3DS context [ADD].
- **14 (multiple cards/device):** NOT IMPLEMENTED — يحتاج distinct_cards_per_device [ADD §F].
- **15 (missing behavior):** IMPLEMENTED لكن بسلوك يحتاج MODIFY (F-06).
- **16-17 (ML/Graph unavailable):** IMPLEMENTED (degraded, إعادة توزيع) [TEST].
- **18 (AML unavailable):** IMPLEMENTED fail-closed REVIEW [TEST].
- **19 (all engines down):** **NOT IMPLEMENTED — حاليًا ALLOW (GAP، fail-open) [ADD guard]**.
- **20 (duplicate):** IMPLEMENTED [TEST].
- **21 (modified duplicate payload):** **NOT IMPLEMENTED — لا payload_hash [ADD]**.

---

# 11. Current ML Vector Verification (قبل إضافة amount_usd)

**الـ 20 feature الفعلية (CODE: features.py:114-137 + generate_dataset.py:15-22 + metadata.json):**
`amount(0), hour_sin(1), hour_cos(2), tx_per_min(3), amount_5m(4), distinct_merchants_1h(5), new_device(6), shared_device_count(7), shared_ip_count(8), impossible_travel(9), high_risk_country(10), new_beneficiary(11), seconds_since_password_change(12), previous_declines(13), previous_chargebacks(14), high_risk_merchant(15), off_hours(16), round_amount(17), structuring_pattern(18), suspicious_events_30d(19)`.

**الإجابات المثبتة:**
- Is amount_usd already represented? **لا — Feature #0 = amount الخام.**
- Available during training? **لا — generate_dataset لا ينتجه.**
- Available during inference? **نعم — features.py يحسبه (لكنه لا يدخل vector).**
- Would adding it change dimensionality? **نعم (20→21) أو يستبدل #0 — كلا الحالتين يكسر artifacts.**
- Break existing artifacts? **نعم — ترتيب/بعد الـ vector حرج؛ يتطلب نموذجًا جديدًا إلزامًا.**
- Leakage? لا (محسوب من FX قبل القرار).
- Improve temporal validation? غير مثبت.
**الحكم: `amount_usd → CANDIDATE CHANGE — EXPERIMENT REQUIRED`** (لا P0 تلقائي). يُنفَّذ فقط مع إعادة التدريب الكاملة وبعد تجربة.

---

# 12. IsolationForest Experiment Protocol

- **Dataset:** real labeled transactions، temporal split (train أقدم → test أحدث)، train/validation/test منفصلة.
- **Baseline:** التحويل الحالي `(0.5−raw)×1.2+0.5` (TESTED سابقًا: منحاز صعودًا، legit≈0.93).
- **Candidates:** A. الحالي · B. Empirical percentile mapping · C. Isotonic regression · D. Sigmoid/Platt-like · E. بديل anomaly normalization.
- **Metrics:** PR-AUC، ROC-AUC، precision، recall، FPR، FNR، precision@operating-threshold، calibration metrics حيث يبررها التفسير الاحتمالي.
- **Critical rule:** **لا تُسمَّ المخرجات "fraud probability" إلا إذا بررت المعايرة/التقييم ذلك.** الناتج الحالي = **anomaly-derived signal** فقط.

---

# 13. Feedback Label Governance

**Lifecycle:** transaction → decision → alert/case → investigation → external outcome → label → dataset → validation → candidate model → shadow → champion.
**Governance:** source · source trust priority · label confidence · timestamp · version · correction · reversal · conflicting labels · unknown state.
**عند التعارض (investigator=fraud لكن chargeback=legitimate):** لا يُلوَّث الـ dataset — يُحفظ كلا الـ labels بمصدرهما وثقة كلٍّ منهما، وتُطبَّق **source priority** (chargeback الرسمي > investigator > merchant)، والحالات المتعارضة تُستبعد أو تُوسم `conflicting` حتى تُحسم. **[ADD governance].**

---

# 14. Security Verification

PAN/CVV لا يُخزَّنان (CODE) · HMAC/replay/RLS/audit موجودة (CODE) · **فجوات مؤكدة:** LLM redaction غائبة (F-07) · SSRF لـ watchlist provider (فجوة) · توقيع/سلامة joblib غائب · payload_hash غائب. **[ADD لكل منها].**

---

# 15. Database Verification

migrations المطلوبة (6): card_context · payload_hash · applied_weights_json · feedback (+labels) · auth_context · model_metadata — كلها **[ADD]**، لا واحدة موجودة حاليًا (مؤكد بالفحص).

---

# 16. Testing / Observability Verification

Test matrix وmetrics المواصفة سليمة؛ property-based invariants (final∈[0,1]، Σweights=1) قابلة للتنفيذ؛ **لا load/perf suite حاليًا [ADD]**.

---

# 17. Implementation Readiness Matrix

| Item | Repo Verified | Spec Correct | API Ready | DB Ready | Test Ready | Security Ready | Status |
|---|---|---|---|---|---|---|---|
| Card context | partial | corrected | no | no | no | yes | APPROVED WITH MODIFICATION |
| Card token (reference) | no | corrected | no | no | no | yes | APPROVED WITH MODIFICATION |
| BIN/Last4 | yes | corrected | yes | yes | yes | yes | APPROVED |
| 3DS context | no | yes | no | no | no | yes | APPROVED WITH MODIFICATION |
| Idempotency | yes | yes | yes | yes | yes | yes | APPROVED |
| payload_hash | no | yes | no | no | no | yes | APPROVED WITH MODIFICATION |
| ML vector | yes | candidate | — | — | — | — | BLOCKED (experiment required) |
| IsolationForest | yes | protocol | — | — | no | — | APPROVED WITH MODIFICATION (experiment) |
| Behavior | yes | modify | — | — | update | — | APPROVED WITH MODIFICATION |
| Graph | yes | yes | — | — | yes | yes | APPROVED |
| AML | yes | yes | — | — | yes | yes | APPROVED |
| Fusion | yes | yes | — | — | yes | yes | APPROVED |
| Guards | yes | yes | — | — | yes | yes | APPROVED |
| All-engine-down | **no (ALLOW)** | add guard | — | — | no | — | **BLOCKED (must add guard)** |
| Feedback | no | yes | no | no | no | yes | APPROVED WITH MODIFICATION |
| Label governance | no | yes | no | no | no | yes | APPROVED WITH MODIFICATION |
| Card testing | partial | add §F | — | — | no | yes | APPROVED WITH MODIFICATION |
| API contracts | partial | exact | no | no | no | yes | APPROVED WITH MODIFICATION |
| PCI/security | partial | corrected | — | — | — | partial | APPROVED WITH MODIFICATION |
| LLM redaction | no | yes | — | — | no | no | APPROVED WITH MODIFICATION |
| Model governance | partial | yes | — | no | no | partial | APPROVED WITH MODIFICATION |
| Observability | partial | yes | — | — | no | — | APPROVED WITH MODIFICATION |
| Failure contract | partial | frozen | partial | — | no | yes | APPROVED WITH MODIFICATION |

---

# 18. Final Approved Scope / Blocked / Deferred / Order

**Approved:** Idempotency (مع payload_hash)، Graph، AML، Fusion، Guards، Behavior (modify)، Card/3DS context، Feedback، backtesting (offline)، redaction، Failure contract.
**BLOCKED:** (1) **ML vector/amount_usd** — EXPERIMENT REQUIRED. (2) **All-engines-down ⇒ ALLOW حاليًا** — **BLOCKER: يجب إضافة guard ⇒ REVIEW قبل أي card production.**
**Deferred:** multi-rail (غير card)، sequence behavioral، Redis/Kafka/microservices.

## Exact Implementation Order
P0: redaction LLM · all-down guard · Iso experiment protocol · ML retrain prep · payload_hash.
P1: behavior-missing · card context · auth context · feedback+governance · /risk/card endpoint · contract tests.
P2: backtesting · drift · champion/challenger · SSRF-watchlist · model signing.
P3: deferred items.

---

# 19. Final Pre-Implementation Checklist
- [ ] إضافة all-engines-down guard (BLOCKER) · [ ] تصحيح Token/BIN/Last4 semantics · [ ] PCI wording المُصحَّحة · [ ] payload_hash · [ ] behavior semantics · [ ] card/auth context schema · [ ] feedback + governance · [ ] Iso experiment protocol · [ ] redaction LLM · [ ] Failure contract مُجمَّد · [ ] contract/failure/security tests.

---

# 20. الإجابة النهائية على سؤال المرحلة

> **هل أصبحت مواصفة AEGIS Card/Visa كاملة بما يكفي لبدء التنفيذ؟**

**توجد نقطتان تمنعان التنفيذ الفوري (BLOCKERS):**

**BLOCKER 1 — All-engines-down ⇒ ALLOW (fail-open):**
- WHY: عند انهيار كل المكونات، active_weight=0 ⇒ final=0 ⇒ **ALLOW**.
- EVIDENCE: orchestrator.py:216-235 (لا guard للحالة الشاملة).
- REQUIRED FIX: [ADD] guard — كل المكونات ساقطة ⇒ REVIEW إجباري.
- DEPENDENCY: لا — تغيير محلي.

**BLOCKER 2 — ML vector (amount_usd + التدريب الاصطناعي):**
- WHY: النموذج اصطناعي + Feature#0 خام (OOD لـ YER) — لا يصلح لإنتاج card.
- EVIDENCE: metadata.json + features.py:116 + TESTED (OOD=0.0).
- REQUIRED FIX: CANDIDATE — EXPERIMENT REQUIRED (إعادة تدريب + calibration).
- DEPENDENCY: بيانات حقيقية.

**ما عدا هذين:** بقية المواصفة **APPROVED / APPROVED WITH MODIFICATION** بعد التصحيحات الموثقة أعلاه. **لا بدء للتنفيذ قبل حل BLOCKER 1 (حارس الانهيار الشامل) كحد أدنى، وتأجيل card production حتى حل BLOCKER 2.**

> **لم يُبدأ أي coding. HEAD `462ed87` سليم. هذه final verified implementation specification.**
