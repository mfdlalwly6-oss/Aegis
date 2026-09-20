# AEGIS — Independent Full-System Reality Audit (Complete Report)
# تقرير التدقيق المستقل الشامل — النسخة الكاملة

> **التاريخ:** 2026-09-18 · **الحالة المدقَّقة:** HEAD `462ed87` (بدون أي تعديل، commit، أو push)
> **الأدلة:** CODE / LIVE / TEST / CONFIG / DATABASE / EXTERNAL RESEARCH / INFERENCE / UNKNOWN
> **البيئة الحية:** `aegis-platform` (healthy) + `aegis-postgres` (healthy) · `/health` ok · `/ready`: rules=21, ml_ready=true (GB+Iso v2026.08.13), graph_nodes=292, tenants=57 · DB: 23 جدولًا, decisions=132, transactions=122, alerts=82, cases=63, audit_log=733, fx_rates=11 · 24 migration (001→025)

---

# القسم 1 — الحكم التنفيذي

**البنية الهندسية ممتازة** (عزل مستأجرين متعدد الطبقات، idempotency ثنائية، guards إلزامية، fusion مع إعادة تطبيع، audit بسلسلة SHA-256، traceability شبه كاملة) — وهي الجزء الأصعب والأثمن في أي نظام fraud.
**لكن نواة الكشف غير صالحة إنتاجيًا**: النموذجان مدرَّبان على بيانات اصطناعية 100% بفصل تام (P/R/F1/ROC=1.0)، يريان مبالغ YER الحقيقية كـ «سليمة = 0.0» (مؤكد تجريبيًا)، وIsoForest يضخّم حتى العمليات السليمة إلى ≈0.93. القواعد + AML + Graph تحمل العبء الحقيقي حاليًا.

---

# القسم 2 — تقييم ML العلمي الحقيقي (TESTED هذه الجولة على النموذجين الفعليين)

| القياس | النتيجة | Evidence |
|--------|---------|----------|
| GB params | n_estimators=100, lr=0.1, max_depth=3, log_loss — افتراضيات sklearn كاملة | CODE+BINARY |
| GB test split | TP=300 FP=0 FN=0 TN=700؛ P=R=F1=ROC=PR-AUC=1.0؛ Brier=0.0 | TESTED |
| Calibration | فئتان فقط (0.0→0.0، 1.0→1.0) — «تطرّف» وليس معايرة | TESTED |
| IsoForest | corr(iso_prob,y)=0.849 لكن **mean_legit=0.928, mean_fraud=1.0** | TESTED — انحياز صعودي حرج |
| Feature importance | shared_device_count=0.588, tx_per_min=0.206, seconds_since_pw=0.117, amount_5m=0.090 — **10 من 20 feature أهميتها 0.0 حرفيًا** (amount, hour_sin/cos, merchants...) | TESTED |
| Adversarial: مبلغ 500,000 YER | gb_prob=0.0 لكل العينات | TESTED — OOD |
| Adversarial: تصفير metadata | recall يبقى 0.995 (الميزات الأقوى من DB) | TESTED — تخفيف جزئي لخطر self-reported fields |
| Adversarial: velocity=100/min | gb_prob=0.291 (لا يرتفع كما هو بديهي) | TESTED — سلوك OOD غير موثوق |

**الخلاصة العلمية:** metrics=1.0 ليست دليل أداء — هي دليل أن توزيع البيانات الاصطناعية سهل الفصل تافه. لا يمكن تقديم أي نتيجة منها كـ production evidence.

---

# القسم 3 — Findings السجل الكامل (بصيغة البرومت)

## F-01 CRITICAL — تدريب على بيانات اصطناعية
- **Evidence:** CODE generate_dataset.py + metadata.json («synthetic — NOT real fraud data») + TESTED (فصل تام).
- **Impacts:** Technical: نموذج بلا قيمة تنبؤية مثبتة · Security: المحتال الحقيقي غير ممثَّل · Business: قرارات مضللة · Operational: ثقة زائفة بالمقاييس.
- **Recommended:** إعادة تدريب على بيانات حقيقية/شبه حقيقية بواقعية توزيع YER. **Alternatives:** shadow-mode مع قواعد فقط حتى توفر البيانات؛ نماذج anomaly فقط بدون supervised. **Preferred:** shadow-mode → جمع بيانات → إعادة تدريب. **Complexity:** عالية · **Risk of change:** متوسط (يتطلب versioning) · **Priority:** P0.

## F-02 HIGH — IsoForest بانحياز صعودي
- **Evidence:** TESTED — legit≈0.928. **Impact:** ML Score مضخّم بنسبة 0.30×~0.9≈0.28 لكل معاملة — يرفع final بشكل مصطنع. **Fix:** معايرة isotonic/Platt على بيانات حقيقية؛ مؤقتًا خفض وزنه أو تصحيح التحويل. **Priority:** P0.

## F-03 HIGH — amount الخام في الـ vector (OOD لـ YER)
- **Evidence:** CODE features.py:116 (Feature#0 = amount خام) + TESTED (500k YER → 0.0). **Fix:** `amount_usd` في الـ vector + إعادة تدريب. **Priority:** P0.

## F-04 HIGH — 10 features ميتة في GB
- **Evidence:** TESTED feature_importances_. **Fix:** مع إعادة التدريب: إما إحياؤها ببيانات تحمل إشارة فعلية، أو حذفها من الـ vector (مع تحديث generate_dataset + features.vector + metadata معًا — الترتيب حرج). **Priority:** P1.

## F-05 HIGH — metadata ذاتية التقرير (7 من 20 feature)
- **Evidence:** CODE features.py + webhook. **TESTED:** التصفير لا يُسقط الكشف (recall 0.995) لكنها تضيف إشارات بلا تحقق. **Fix:** تصنيف الحقول trusted/self-reported؛ حساب impossible_travel داخليًا من geo+history؛ توثيق الباقي كـ trust-weighted. **Priority:** P1.

## F-06 HIGH — Behavior-missing يدخل بصفر ووزن كامل
- **Evidence:** CODE orchestrator.py:207-214 (degraded ≠ unavailable). **Impact:** «No evidence» يُحسب «No risk» — يعاقب المؤسسات ضعيفة التكامل (الأكثر شيوعًا في اليمن). **Fix:** behavior-missing ⇒ unavailable (إعادة توزيع الوزن) أو سياسة لكل مستأجر. **Tests المطلوبة:** تحديث test_confidence (0.95→1.0 للحالة الجديدة) + test_component_health. **Priority:** P1.

## F-07 HIGH — إرسال بيانات المعاملة لـ OpenRouter بلا redaction
- **Evidence:** CODE fraud_agent.py/openrouter.py (اقتطاع طول فقط). **Impact:** خصوصية/امتثال — بيانات مالية لطرف ثالث. **Fix:** redaction قائمة حقول (account/user/merchant) قبل الإرسال؛ و`AI_ENABLED=false` افتراضيًا في الإنتاج. **Priority:** P0 قبل أي بيانات حقيقية.

## F-08 MEDIUM — risk_sensitivity محسوبة غير مطبقة
- **Evidence:** CODE policy_engine.py:101-106 مقابل orchestrator (grep صفري). **Fix:** تطبيقها على final أو حذفها من السياسة والوثائق. **Priority:** P1.

## F-09 LOW — ML_THRESHOLD_* ميتة
- **Evidence:** CODE config.py:98-99. **Fix:** REMOVE بعد تأكيد عدم وجود مستهلك (فُحص: لا يوجد) أو توثيقها legacy. **Priority:** P3.

## F-10 MEDIUM — Idempotency بلا مقارنة حمولة عند نفس tx_id
- **Evidence:** CODE orchestrator.py:143-149. **Fix (بصيغة §67):**
  - **Current behavior:** نفس tx_id لنفس المستأجر بمفتاح جديد → إرجاع القرار المخزّن.
  - **Problem:** payload مختلف (مبلغ/مستفيد) بنفس tx_id يرث قرارًا قديمًا.
  - **Required:** hash الحقول الأساسية (amount+currency+sender+beneficiary) يُخزَّن مع القرار؛ عند الاختلاف → 409 conflict أو إعادة تسجيل كامل.
  - **Data model:** عمود `payload_hash` في decisions (migration جديد). **Concurrency:** نفس mark_seen الذرّي. **Failure:** hash مفقود في قرارات قديمة → معاملة كـ mismatch آمن (إعادة تسجيل). **Tests:** نفس tx+مبلغ مختلف ⇒ لا cached. **Priority:** P1.

## F-11 MEDIUM — Audit chain وكتابات متزامنة
- **Evidence:** CODE audit_repo.py (`prev` من ORDER BY id DESC LIMIT 1). **Impact:** سلسلتان متفرعتان صامتتان محتملتان؛ «tamper-evident عند التحقق» لا «immutable». **Fix:** قفل تسلسلي (SELECT ... FOR UPDATE أو advisory lock) + أداة `verify_chain` دورية. **Priority:** P2.

## F-12 MEDIUM — Rate limiting in-memory
- **Evidence:** CODE middleware.py (AuthRateLimit). **Impact:** حدود تتضاعف مع تعدد الـ instances. **Fix:** Redis عند التوسع الأفقي فقط. **Priority:** P2.

## F-13 MEDIUM — لا اختبارات حمل/أداء/property-based
- **Evidence:** TEST (25 ملفًا، لا perf suite). **Fix:** load test للـ webhook + property tests (invariants: final∈[0,1]، Σweights=1). **Priority:** P2.

## F-14 LOW — ازدواج إشارات السلوك (Rules × Behavior)
- **Evidence:** CODE R-BEH-001/002 وR-SE-001 مقابل _behavior_score. **Fix:** توثيق أنه مقصود (دفاع بطبقتين) أو إزالة التكرار. **Priority:** P3.

## F-15 LOW — EventBus يُسقط الأحداث صامتًا عند الامتلاء (queue=500)
- **Evidence:** CODE streaming/__init__.py. **Fix:** عدّاد dropped_events في metrics. **Priority:** P3.

## F-16 INFO — decisions لا يخزّن الأوزان الاسمية صراحة
- **Evidence:** DATABASE (34 عمودًا — component_health فيه applied فقط). **Fix:** عمود `applied_weights_json`. **Priority:** P3.

## F-17 HIGH (نشر) — لا TLS داخلي
- **Evidence:** CODE/CONFIG (HSTS مشروط بـ REQUIRE_HTTPS_PROXY). **Fix:** reverse proxy بشهادات + HSTS + TRUSTED_PROXIES. **Priority:** P0 للإنتاج (خارج الكود).

---

# القسم 4 — ما هو سليم: KEEP (بلا مجاملة)

عزل المستأجرين (RLS+ContextVar+Graph namespacing — E2E 12/12) · AML fail-closed (TEST) · sanctions→BLOCK (TEST) · fx_missing لا silent-allow (TEST) · Idempotency ثنائية (مع F-10) · إعادة تطبيع الأوزان (TEST) · component_health+confidence مخزّنان verbatim (TEST) · fx_proof immutable snapshot (TEST) · audit hash-chain (مع F-11) · HMAC+replay+suspended (LIVE 401/403/422) · PROTECTED_RULES · فهارس DB المركبة tenant-scoped · SSRF-guard في إشعارات الـ webhook · secrets guard للإنتاج + DATABASE_URL validation (29 security tests) · watchlist trigram GIN + sync log.

---

# القسم 5 — Fraud Detection Review (هل يكتشف احتيالًا حقيقيًا؟)

**الإجابة الصادقة: غير مثبت.** الأسباب المثبتة:
1. النموذج لم يرَ احتيالًا حقيقيًا (F-01) ويصمّم على توزيع USD-scale بينما السوق YER (F-03 — مؤكد تجريبيًا).
2. ML حاليًا echo للقواعد تقريبًا (أقوى feature لديه = shared_device_count الذي تقيسه R-DEV-005 أيضًا).
3. ثغرات تجاوز محتملة: velocity لكل مرسل فقط (لا cross-account velocity) → المحتال يوزّع على حسابات؛ structuring لكل مرسل فقط؛ جهاز/IP نظيف لكل عملية يُفلت من Graph إن لم يتشارك؛ metadata مزوَّرة (F-05).
4. **Coordinated fraud:** Graph يكشف العلاقات الثابتة (shared device/ip/hops≤2) لكن لا scoring للانفجارات الزمنية المتزامنة عبر عقدة مشتركة (fraud-ring burst).
5. **Drift:** لا drift detection ولا retraining pipeline — النموذج جامد.
6. **False positives:** القواعد الحتمية (round_amount+offshore=0.20...) قد تضرب تجارًا شرعيين في سوق نقدي كثيف التحويلات مثل اليمن — لا قياس FP حقيقي متاح.

---

# القسم 6 — Fusion: التحليل الرياضي

- **Correctness:** Σ(applied)=1 دائمًا وكل score∈[0,1] ⇒ final∈[0,1] — سليم (CODE+TEST).
- **Sensitivity:** ∂final/∂score_k = applied_weight_k — أقصى تأثير لمكوّن = وزنه بعد التطبيع (Rules: 0.35→0.467 عند سقوط ML).
- **Information loss:** عند إعادة التطبيع، القرار يقارَن بعتبات ثابتة رغم أن final صار على مقياس جزئي — مكوّن ساقط كان سيضيف 0 يرفع final نسبيًا، وكان سيضيف 1 يخفضها. هذا **انحياز اتجاهي غير معوَّض** — الـ confidence يسجّله لكن القرار لا يعدّل به. (INFERENCE — موثّق كفجوة تصميمية، لا خطأ.)
- **Zero scores:** مكوّن healthy بصفر يخفض final (صحيح)؛ unavailable يُستبعد (صحيح)؛ **degraded يدخل بصفر — F-06 هي الاستثناء الوحيد غير المتسق**.
- **Edge cases:** كل المكونات ساقطة → active_weight=0 → `final=0` مع degraded_reason — القرار ALLOW مع confidence≈0 (CODE: قسم الحماية في orch:232). **فجوة:** fail-open كامل عند انهيار شامل — يستحق guard (كل المكونات ساقطة ⇒ REVIEW إجباري). **ADD — P1.**

---

# القسم 7 — Threshold Analysis

العتبات (0.35/0.60/0.80 wallet) **قيم هندسية أولية بلا أساس بياني** (لا ROC/PR curves — سببها: غير مثبت في الكود). الحدود الدنيا/القصوى (0.20–0.50/0.40–0.75/0.60–0.95) معقولة كسياج أمان. **لا تُقدَّم كـ optimal.** عند توفر بيانات: تحليل challenge/review/block rates وFP/FN لكل profile.

---

# القسم 8 — Database / Concurrency / Performance

- **Schema:** 23 جدولًا، قيود uniqueness صحيحة (idempotency, watchlist uq)، فهارس مركبة tenant-first — **سليم**.
- **Concurrency:** idempotency عبر INSERT الذرّي؛ audit يحتاج قفلًا (F-11)؛ graph in-memory بلا أقفال (single-writer عمليًا عبر uvicorn worker واحد — يصبح خطرًا مع workers>1). **ADD توثيق: يجب workers=1 أو graph خارجي. P2.**
- **Performance:** ~8 استعلامات/معاملة + graph lookups في الذاكرة — مقبول للحجم الحالي؛ لا benchmark مثبت. bottleneck المتوقع: velocity queries عند TPS عالٍ ونمو transactions بلا partitioning. **ADD: سياسة retention/partitioning للجداول الكبيرة. P3.**

---

# القسم 9 — Reliability / Fail-open vs Fail-closed (لكل dependency)

| Dependency | السلوك الحالي | التقييم | القرار الصحيح |
|-----------|---------------|---------|----------------|
| DB | يصعد الاستثناء للمكوّن | غير موحّد | unify |
| Rules | fail-open (0 + استبعاد وزن) | مقبول | KEEP |
| ML | fail-open (مستبعد) | صحيح — لا دليل | KEEP |
| Graph | fail-open (مستبعد) | صحيح | KEEP |
| **AML** | **fail-closed (REVIEW)** | **صحيح أمنيًا** | **KEEP** |
| Behavior | يدخل بصفر | غير متسق | MODIFY (F-06) |
| FX missing | fail-closed (REVIEW/BLOCK) | صحيح | KEEP |
| LLM | fail-open (تفسير محلي) | صحيح — لا يمس القرار | KEEP |
| Notifications | best-effort | صحيح | KEEP |
| EventBus | best-effort (إسقاط صامت) | مقبول + عدّاد | MODIFY (F-15) |
| **انهيار شامل** | **fail-open (ALLOW)** | **خطر** | **ADD guard ⇒ REVIEW (P1)** |

---

# القسم 10 — Privacy: Data Inventory

| Field | Classification | Storage | Transmission | Masking | خطر خارجي |
|-------|---------------|---------|--------------|---------|-----------|
| sender/beneficiary account_id | حساس مالي | transactions (plain) | webhook response + **OpenRouter** | لا | **F-07** |
| user_id, merchant_name | PII | plain | **OpenRouter** | لا | **F-07** |
| device_id, ip | PII تقني | plain + graph | لا يخرج | لا | داخلي |
| amount/currency | مالي | plain | OpenRouter (ضمن tx) | لا | F-07 |
| hmac_secret | سرّي | **مشفّر** (migration: encryption event) | لا | نعم | لا |
| audit_log | أدلة | hash-chained | لا | — | داخلي |
**الخلاصة:** التشفير الداخلي للأسرار سليم؛ **الفجوة الوحيدة الجوهرية = قناة LLM (F-07)**.

---

# القسم 11 — LLM / FraudAgent: الدور الحقيقي

**ليس Decision Maker** (مثبت: يعمل بعد القرار، لا مسار كتابة للقرار). يرسل tx (≤600 حرف) + rules_hits (≤400) + ml_prob إلى OpenRouter (نماذج مجانية)، timeout=10s، بدون مفاتيح ⇒ لا إرسال. المخاطر: prompt injection عبر حقول المعاملة (اسم تاجر خبيث) — التأثير محصور بالتفسير فقط (لا يغيّر القرار) لكنه قد يضلل محققًا؛ hallucination في typology — يجب وسم النص «AI-generated, unverified». **ADD: وسم + redaction + تعطيل افتراضي إنتاجيًا. P0/P1.**

---

# القسم 12 — Observability & Decision Trace

بعد قرار خاطئ يمكن إعادة بناء: features (snapshot) · rules hits · ml_json · graph_json · aml_json+evidence · behavior_score · الأوزان المطبقة (component_health) · policy version · model version · config version · guards (degraded_reason) · confidence. **الناقص:** الأوزان الاسمية صراحة (F-16) + hash الحمولة (F-10). **الحكم: Traceability ممتازة (أفضل من معظم الأنظمة المماثلة) مع ثغرتين صغيرتين.**

---

# القسم 13 — Security Review الإضافي (فوق A1–A8 المغلقة)

- **SQL injection:** psycopg parameterized + placeholder conversion — لا حقن مباشر مرصود (CODE). **Prompt injection:** مقصور على التفسير (§11). **SSRF:** محمي في الإشعارات (`_safe_webhook_url`، no-redirects) — لكن **watchlist GenericCsvUrlProvider يجلب URL مُعدّ من المالك بلا SSRF-guard مماثل** (CODE watchlist_providers.py:121) — **ADD: نفس الفحص هناك. P2.**
- **Deserialization:** joblib.load على ملفات محلية موقَّعة بالمسار فقط — لا توقيع/تحقق سلامة للنماذج. **ADD: checksum/signature للـ joblib. P2.**

---

# القسم 14 — UX / Product Review

ثلاث بوابات (admin/merchant/investigator) ثابتة. workflow المحقق: queue → alert → assign → status (four-eyes للـ high severity — TEST) → case → resolve. الفجوات (CODE): لا empty-state/backpressure لازدحام الـ queue؛ SSE قد يُسقط أحداثًا صامتًا (F-15) فيضلل المحقق؛ reasoning_ar غير موسوم كـ AI-generated؛ لا bulk-actions موثقة. **التقييم: صالح للتشغيل اليومي لمؤسسة واحدة؛ يحتاج تشديدًا قبل تعدد فرق التحقيق الكبيرة.**

---

# القسم 15 — Global Research (EXTERNAL RESEARCH)

الممارسات العالمية ذات الصلة المثبتة: منصات fraud الحديثة تجمع rules+ML+graph+behavior بنفس نمط AEGIS (معمارياً AEGIS **متوافق مع الممارسة**)؛ الفروق الحاسمة: (1) التدريب على بيانات إنتاجية + feedback loop من قرارات المحققين (غائب — **ADD: حقل confirmed_fraud من قرار case يغذي إعادة التدريب. P1**)؛ (2) معايرة الاحتمالات قبل الدمج؛ (3) drift monitoring (PSI/KS) دوري؛ (4) champion/challenger للنماذج. لا شيء منها يتطلب graph database أو بنية معقدة الآن.

---

# القسم 16 — Yemen (EXTERNAL RESEARCH + حدود التحقق)

- **تنظيمي:** قانون AML/CFT معدّل + FIU يمنية + STR إلزامية نظريًا، امتثال عملي منخفض (State Dept 2015 — **مصدر قديم، يحتاج تحديثًا**)؛ FATF (يونيو 2025): اليمن عالج خطته تقنيًا. **Requires legal/regulatory confirmation** قبل أي mapping إلزامي.
- **السوق:** انقسام مصرفي (CBY صنعاء/عدن)، قطاع نقدي/وكيلي كثيف، محافظ موبايل نشطة (CAC Bank Mobile Money، Cash Wallet ~1500 وكيل)، تحويلات فورية جديدة (QIMB+TerraPay 2025)، عقوبات OFAC (31 CFR 552) + de-risking يرفعان كلفة القنوات الرسمية.
- **ملاءمة AEGIS:** FX متعدد المستويات + institution-rate trust budget مناسب جدًا لتعدد أسعار الصرف والانقسام؛ webhook خفيف يناسب بنى متفاوتة؛ watchlist مخصصة لكل مستأجر تناسب قوائم محلية. **الفجوات الأخطر يمنيًا:** F-06 (Behavior لن يتوفر لدى الجميع)، F-05 (metadata متفاوتة الجودة)، غياب التحقق من الأسماء العربية dialects في fuzzy matching (matching.py يدعم Unicode عربي — CODE — لكن بلا قواميس أسماء يمنية).
- **ما لم يُثبَت:** متطلبات CBY الرسمية التفصيلية، قوائم عقوبات محلية، متطلبات KYC لكل قطاع — **UNVERIFIED**.

---

# القسم 17 — Reference Yemen Architecture (منطقية — أسماء افتراضية)

```
Bank A / Bank B / Exchange Co. / Wallet / Payment Provider
        ↓  (كل مؤسسة: Adapter يوقّع HMAC + يطبّع الحقول)
AEGIS Gateway (webhook) → Auth → Normalize → FX → Engines → Fusion → Policy → Decision
        ↓                                                        ↓
   Institution Response (decision + confidence + trace)     Alerts/Cases/Investigators
```

**Integration Contract المقترح (مبني على الموجود فعليًا):** Request: `{transaction, context}` · Headers: `x-api-key`, `x-wallet-signature` (HMAC-SHA256 على الجسم الخام) · Response: `{decision, risk_score, risk_band, confidence, top_reasons, reasoning_ar, component_health, degraded_mode, alert, reference_amount}` · Idempotency: `X-Idempotency-Key` (أو tenant:tx_id) · Errors: 401/403/404/409?/422/429 · Timeout مقترح للمؤسسة: 5s + retry بنفس المفتاح · Versioning: rule_set_version+model_version+config_version في كل قرار (موجود) · Correlation: request_id (موجود).

**ما يجب أن توفره المؤسسة:** Required: amount, currency, sender, beneficiary, timestamp · Recommended: device_id, ip, geo, behavior · Optional: institution_rate, metadata التاريخية · Environment-dependent: biometrics · Sensitive: تُرسل عبر القناة الموقعة فقط · Not always available: previous_declines/chargebacks.

---

# القسم 18 — Decision Scenarios (14 — مبنية على الكود)

1. **Low risk** → ALLOW، تخزين كامل، لا alert. 2. **Challenge** → CHALLENGE + alert. 3. **Review** → REVIEW + alert + case + notify. 4. **Block** → BLOCK + alert + case + notify. 5. **AML down** → REVIEW إجباري + degraded_reason (TEST). 6. **FX missing** → REVIEW أو BLOCK حسب policy (لا silent allow). 7. **AEGIS down** → المؤسسة لا تستلم ردًا — **السلوك غير معرّف في الكود؛ يجب أن يكون قرارًا مؤسسيًا موثقًا في عقد التكامل (fail-open أو closed) — ADD توثيق. P1.** 8. **Bank down** → القرار مخزّن؛ إعادة الإرسال تعيده عبر idempotency. 9. **Duplicate** → cached + duplicate:true. 10. **Replay** → 422 خارج النافذة؛ داخلها idempotent. 11. **Sanctioned** → BLOCK مهما كان الـ score (TEST). 12. **Fraud ring** → graph: shared device/ip + hops≤2 (+0.30). 13. **False positive** → قناة investigator + four-eyes للـ high (TEST)؛ **لا feedback loop للنموذج (§15).** 14. **Customer dispute** → لا مسار مخصص (cases جزئيًا) — **ADD مستقبلي. P3.**

---

# القسم 19 — الزائد والناقص

**الزائد (مرشح، لا حذف دون تأكيد نهائي):** `ML_THRESHOLD_*` (F-09) · heuristic ML (يُنتج ولا يُحتسب — إبقاؤه للشرح فقط موثق) · risk_sensitivity غير المطبقة (F-08) · `_ensure_owner_token_valid` stub في tenants.py (لا مستهلك — مرشح cleanup).
**الناقص (ADD بأولوية):** feedback loop من قرارات المحققين (P1) · guard الانهيار الشامل ⇒ REVIEW (P1) · redaction للـ LLM (P0) · SSRF-guard لـ watchlist provider (P2) · توقيع النماذج (P2) · drift monitoring (P2) · عقد تكامل موثق لسلوك الأعطال (P1) · applied_weights_json (P3) · retention/partitioning (P3).

---

# القسم 20 — المعمارية المستقبلية + Migration

**Current:** monolith FastAPI + PostgreSQL + in-memory graph + نموذجان joblib. **Problems:** F-01..F-17 أعلاه. **Target (تدريجي، بلا big-bang):** (1) بيانات+إعادة تدريب+معايرة → (2) redaction/LLM + TLS → (3) feedback loop + drift monitoring → (4) Redis rate-limit + graph مستمر **فقط عند تعدد الـ instances** → (5) retention/partitioning. **Migration:** كل خطوة خلف flag؛ النماذج بنسخ model_version جديدة تتعايش (القرارات القديمة تشير لنسختها — موجود). **Risks:** كسر توافق الـ vector (الترتيب حرج — أي تغيير features = نموذج جديد إلزامًا)؛ تغيير F-06 يغيّر confidence المختبَر (تحديث test_confidence معه). **Rollback:** joblib السابقة تبقى على القرص؛ policy versions immutable (موجود — 017_policy_versions).

---

# القسم 21 — الخلاصة التنفيذية النهائية

**P0 (قبل أي إنتاج):** إعادة تدريب ببيانات واقعية YER (F-01+F-03+F-04) · معايرة IsoForest (F-02) · redaction/تعطيل LLM-egress (F-07) · TLS للنشر (F-17).
**P1:** F-05 (metadata trust) · F-06 (behavior-missing) · F-08 (risk_sensitivity) · F-10 (payload hash) · guard الانهيار الشامل · feedback loop · عقد التكامل.
**P2:** F-11, F-12, F-13, SSRF-watchlist, توقيع النماذج, drift.
**P3:** F-09, F-14, F-15, F-16, retention, dispute path.

**ما لم يُثبَت:** الأداء على بيانات حقيقية · سبب اختيار الأوزان/العتبات · متطلبات CBY التفصيلية (Requires legal/regulatory confirmation) · سلوك core-banking التنفيذي (خارج AEGIS).

**انضباط المهمة:** لا تعديل كود · لا DB · لا config · لا models · لا retrain · لا commit · لا push — Baseline سليم (`462ed87`).

*أُعدّ هذا التقرير بمنهجية مدقّق خارجي مستقل على الكود والبيئة الحية في 2026-09-18.*
