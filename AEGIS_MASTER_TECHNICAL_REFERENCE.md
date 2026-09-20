# AEGIS — Master Technical Reference
# المرجع التقني الرئيسي لمنصة AEGIS (نسخة نهائية موحدة)

> **بُني هذا المرجع بإعادة فحص المستودع الحالي مباشرة** (HEAD = `462ed87`) — ملفات الكود قُرأت كاملة (orchestrator, features, rules+YAML, ensemble, graph, aml, webhook, fx, policy_engine, config, registry, decision_repo, streaming, audit_repo, fraud_agent, openrouter, training/*)، وقاعدة البيانات الحية والحاوية الجارية فُحصتا في 2026-09-17 (`rules: 21`, `ml_ready: true`, `graph_nodes: 292`, `tenants: 55`, `/health` ok, `/ready` ready).
> **لا تثق بالدليلين السابقين منفردين** — هذه النسخة دمجتهما وصحّحت تعارضاتهما (انظر PART Z).
> وسوم التحقق: **CODE** (مثبت بملف:سطر) · **CONFIG** · **POLICY** · **TEST** · **LIVE** (من التشغيل/DB الحية) · **DOC** (توثيق فقط) · **BINARY** (داخل joblib، لا يُفكك من المصدر) · **«غير مثبت في الكود الذي تم فحصه»**.
> لا كود عُدّل، لا تدريب، لا commit، لا push.

---

# PART A — ما هو AEGIS؟ (من الصفر)

AEGIS منصة **كشف احتيال مالي متعددة المستأجرين** (Python 3.11 + FastAPI + Uvicorn + PostgreSQL). تستقبل معاملة عبر Webhook موقَّع (API Key + HMAC-SHA256)، تحسب **Risk Score ∈ [0,1]** بدمج 5 محركات مستقلة، وتُصدر **قرارًا واحدًا**: `ALLOW / CHALLENGE / REVIEW / BLOCK`، ثم تخزّن كل الأدلة للتدقيق.

**لماذا 5 محركات؟** كل واحد يرى نمطًا مختلفًا: القواعد حتمية ومفسَّرة، ML يلتقط الأنماط غير الخطية، Graph يرى العلاقات، AML إلزام قانوني، Behavior يرى «من ينفّذ» لا «ماذا».

## الفروق الجوهرية (احفظها)
`Feature` (قيمة محسوبة) → `RuleHit` (قاعدة تحققت) → `Component Score` (درجة محرك واحد) → `Risk Score` (الدمج الموزون) → `Decision` (عتبات + Guards). **Score رقم، Decision فعل — لا تخلط بينهما.**

## المعمارية العليا — الترتيب الفعلي المُصحَّح (CODE: webhook.py + orchestrator.py)
```
POST /api/v1/webhook/wallet/webhook
 1. Auth: x-api-key + HMAC-SHA256 على الجسم الخام        [webhook.py:181-216]
 2. RLS tenant context (platform ثم المستأجر)           [webhook.py:189,216]
 3. Replay guard على timestamp (>5min مستقبل / >72h قديم → 422) [webhook.py:218-241]
 4. Tenant suspended → 403 hard block                   [webhook.py:243-254]
 5. JSON parse → 400                                    [webhook.py:256-259]
 6. Normalization → Transaction schema                  [webhook.py:23-155]
 7. FX resolution (_apply_fx → fx.normalize)            [webhook.py:158-178,262]
 8. → DecisionOrchestrator.evaluate_and_persist:
     Idempotency                                        [orchestrator.py:137-150]
     Feature Extraction (PostgreSQL)                    [:153]
     Rules → rule_score                                 [:161-170]
     ML (GB+Iso) → ml_prob                              [:172-184]
     Graph → graph_sig                                  [:186-193]
     AML → aml_sig                                      [:195-205]
     Behavior → behavior_score                          [:207-214]
     Fusion (availability-aware) → final                [:216-235]
     Confidence                                         [:248-264]
     Guards (sanctions/watchlist/AML-down/FX-missing)   [:266-300]
     Decision (_decide + thresholds)                    [:298,115-125]
     Top reasons                                        [:303-312]
     FraudAgent explanation (بعد القرار، لا يغيّره)      [:314-331]
     Persist tx + decision                              [:387-411]
     graph.add_transaction                              [:414]
     Alert + Case (للقرارات المرتفعة)                    [:416-442]
     Audit (hash-chained)                               [:444-463]
     Notifications + EventBus publish                   [:465-471]
```
⚠️ تصحيحان عن الرسوم التمهيدية: **FX قبل orchestrator** (ليس بعد Features)، و**Idempotency قبل Feature Extraction**.

---

# PART B — Glossary
| المصطلح | التعريف | المرجع |
|---|---|---|
| Transaction | pydantic schema للمعاملة (amount>0 إلزامي، currency 3 أحرف) | schemas.py:97,117-118 |
| Feature | قيمة من المعاملة/تاريخها (قاموس) | features.py:21 |
| Feature Vector | 20 رقمًا بترتيب حرج للنموذجين | features.py:114-137 |
| Rule / Condition / RuleHit | JSONLogic `when` → hit بـ score_contribution | engine.py:115-163 |
| Rule Score | `min(1, Σ contributions)` | orch:164 |
| Signal | GraphSignal / AMLSignal | schemas.py:179,190 |
| Model Output | gb_prob / iso_raw | ensemble.py:82,99 |
| ML Score | `0.70·gb + 0.30·iso` | ensemble.py:115 |
| Fusion | دمج موزون مع إعادة تطبيع | orch:216-235 |
| Threshold / Policy | عتبات لكل profile من PolicyEngine | policy_engine.py |
| Guard | تجاوز إلزامي فوق الـ score | orch:266-300 |
| Override | rule_overrides لكل مستأجر | rule_repo.py |
| Degraded / Confidence | حالة مكوّن / ثقة القرار | orch:237-264 |
| Audit | سجل append-only بسلسلة SHA-256 | audit_repo.py |

---

# PART C — System Architecture
**Wiring عند الإقلاع** (registry.py): `db.migrate()` → repositories → `platform_admin` bootstrap (env-only) → تشفير hmac القديمة → `currency_repo.seed_defaults()` → `rule_repo.seed_defaults(yaml)` → `watchlist_repo.seed_defaults()` → `RuleEngine` → `EnsembleScorer()` → `GraphEngine()+bootstrap(recent_txs)` → `AMLService(fuzzy=0.87)` → `FeatureExtractor` → `DecisionOrchestrator`.
LIVE: `/ready` → db=postgresql, rules=21, ml_ready=true, models=[GB, Iso] v2026.08.13, graph_nodes=292, tenants=55.

---

# PART D — Transaction Lifecycle (لكل مرحلة: ملف → دالة → في/خرج → قرار؟ → تخزين؟ → فشل؟)
| # | المرحلة | File:Function | يدخل القرار؟ | يُخزَّن؟ | عند الفشل |
|---|---|---|---|---|---|
| 1 | Auth+HMAC | webhook.fraud_webhook | بوابة | audit | 401 |
| 2 | Replay | نفسه | لا | لا | 422 |
| 3 | Suspended | نفسه | لا | audit | 403 |
| 4 | Normalize | normalize_transaction | نعم | tx.raw_json | 400 |
| 5 | FX | _apply_fx → fx.normalize | عبر amount_usd + guard | reference_*, fx_proof | عملة معطّلة→422؛ مفقودة→REVIEW/BLOCK |
| 6 | Idempotency | orch:137-150 | يمنع إعادة الحساب | idempotency_key | duplicate→cached |
| 7 | Features | features.extract | نعم | features_json, features_snapshot_json | — |
| 8 | Rules | rules.evaluate | نعم | rules_json, rule_score | unavailable |
| 9 | ML | ensemble.score | نعم | ml_json, ml_score | ml_prob=None |
| 10 | Graph | graph.score | نعم | graph_json | unavailable |
| 11 | AML | aml.screen | نعم+guards | aml_json | **fail-closed REVIEW** |
| 12 | Behavior | _behavior_score | نعم | behavior_score | 0.0/degraded |
| 13 | Fusion | orch:216-235 | **هو الـ Risk** | risk_score | — |
| 14 | Guards | orch:266-300 | نعم | degraded_reason | — |
| 15 | Decision | _decide | — | decision | — |
| 16 | Reasons | orch:303-312 | شرح | top_reasons_json | نص افتراضي |
| 17 | AI | fraud_agent.analyze | **لا يغيّر القرار** | reasoning_ar, ai_model | يبقى المحلي |
| 18 | Persist | tx_repo/decision_repo | — | transactions+decisions | — |
| 19 | Graph feed | add_transaction | للمعاملات القادمة | in-memory | — |
| 20 | Alert/Case | alerts/cases.create | لا | alerts/cases | — |
| 21 | Audit | audit.log | لا | audit_log (مسلسل) | — |
| 22 | Notify/Events | notifications + events.publish | لا | — | best-effort |

**Idempotency** (CODE orch:137-150): مفتاح مكرر → cached + duplicate؛ **نفس tx_id بمفتاح جديد لنفس المستأجر → يُعيد القرار المخزّن** (لا إعادة تسجيل)؛ تصادم tx_id بين مستأجرين لا يتسرب أبدًا.

---

# PART E — Features (20، ترتيب حرج)
**CODE**: `extract()` ينفّذ استعلامات PostgreSQL حقيقية (velocity 60/300/3600s، shared_device/ip، known_beneficiary، structuring_count، count_by_tenant). الترتيب في `vector()` = ترتيب `FIELDS` في generate_dataset.py:15-22 = `metadata.json.features` — **مطابق (LIVE)**.

| # | vector name | المصدر | Default |
|---|---|---|---|
| 0 | amount | tx.amount | إلزامي (>0) |
| 1-2 | hour_sin/hour_cos | tx.timestamp | ساعة الآن |
| 3 | tx_per_min | velocity 60s (DB) | 0 |
| 4 | amount_5m | velocity 300s (عملة مرجعية) | 0 |
| 5 | distinct_merchants_1h | meta | 0 |
| 6 | new_device | first_seen_today (DB) | False |
| 7 | shared_device_count | DB | 0 |
| 8 | shared_ip_count | DB | 0 |
| 9 | impossible_travel | meta | False |
| 10 | high_risk_country | meta.fatf_high_risk | False |
| 11 | new_beneficiary | not known_benef (DB) | True إن مجهول |
| 12 | seconds_since_password_change | meta | **999999** |
| 13 | previous_declines | meta | 0 |
| 14 | previous_chargebacks | meta | 0 |
| 15 | high_risk_merchant | tx.metadata | False |
| 16 | off_hours | hour<6 أو >22 | False |
| 17 | round_amount | is_round_1000 | محسوب |
| 18 | structuring_pattern | count_9k_10k_30d > 2 | False |
| 19 | suspicious_events_30d | block+review للـ tenant (DB) | 0 |

**لا scaling/encoding/normalization** — خام float32 (ensemble.py:69). **لا أوزان features يدوية** في الاستدلال (داخل joblib = BINARY).
**تُستخرج ولا تدخل الـ vector** (CODE features.py:68-112): `amount_usd, currency, vpn, tor, proxy, emulator, rooted, ip_country, account_age_days, mfa_recently_disabled, offshore, tx_count_5min/1h, amount_1h, card_declines_1h, billing_country` → تخدم **Rules/AML فقط**.

---

# PART F — Rules Engine (21 قاعدة — LIVE)
**LIVE**: جدول rules يحوي **21 قاعدة** (وليس 22 كما في وثائق قديمة). التعريف: `default_ruleset.yaml` → `rule_repo.seed_defaults()` → `RuleEngine`. القيم الحية (id | severity | score):

R-VEL-001 high 0.35 (tx_per_min>6) · R-VEL-002 high 0.30 (amount_5min>5000 USD) · R-VEL-003 medium 0.15 (merchants>8) · R-GEO-001 critical 0.55 (impossible_travel) · R-GEO-002 high 0.30 (fatf) · R-DEV-001 high 0.35 (new device+>1000) · R-DEV-002 critical 0.60 (emulator/rooted) · R-DEV-003 high 0.40 (TOR) · R-DEV-004 high 0.35 (VPN+>500+new benef) · R-DEV-005 high 0.30 (shared_dev>1) · R-DEV-006 medium 0.20 (shared_ip>2) · R-BEH-001 high 0.40 (biometric<0.4) · R-BEH-002 medium 0.25 (keystroke<1.2) · R-ATO-001 critical 0.55 (pw<600s+>1000) · R-ATO-002 critical 0.60 (mfa_disabled+new benef) · R-AML-001 high 0.35 (9000≤usd<10000 وcount>2) · R-AML-002 high 0.40 (tx_1h≥8 وamount_1h>20000) · R-AML-003 medium 0.20 (round+offshore) · R-CT-001 high 0.35 (declines_1h>5 وusd<5) · R-NEW-001 high 0.40 (account<7d وusd>5000) · R-SE-001 high 0.35 (session>600000ms)

**المعادلة (CODE orch:164)**: `rule_score = min(1.0, Σ score_contribution)`، و`score_contribution = rule.score` (engine.py:161).
- **severity لا تدخل المعادلة** — فقط في Guard (أرضية CHALLENGE عند high + behavior غير healthy، orch:276-280) وseverity التنبيه.
- **لا priority / لا normalization / cap=1.0.**
- **Dedup**: `by_id` (engine.py:195-200) — override المستأجر يستبدل قاعدة المنصة بنفس id؛ قواعد المستأجرين الآخرين لا تُقيَّم؛ نفس الـ id لا يتكرر.
- **قاعدة لا تُصدر BLOCK مباشرة** — ترفع score فقط.
- حقل None → القاعدة لا تتحقق (False، engine.py:83-84).
- **PROTECTED_RULES** = {R-AML-001, R-AML-002, R-AML-003, R-GEO-002} لا يمكن تعطيلها (policy_engine.py:28,126-135).
**أمثلة**: قاعدة واحدة 0.35→0.35 · 0.35+0.55=0.90 · 0.35+0.30+0.55+0.40+0.35=1.95→**1.00** (cap) · كل الـ21 (≈6.85)→**1.00**.
**TEST**: test_rule_overrides.* (استبدال/تعطيل/استعادة لكل مستأجر).

---

# PART G — Gradient Boosting
CODE train_models.py:37: `GradientBoostingClassifier(random_state=42)` — **بقية المعلمات افتراضية**. fit على `X_train,y_train`. الاستدلال `gb_prob = predict_proba(X)[0][1]` (ensemble.py:82). **لا calibration/scaling/clamp** على gb_prob. معنى 0.72 = تقدير P(fraud=1) — **كيف بالضبط = BINARY** (أشجار داخل joblib). Metrics=1.0 على بيانات **اصطناعية** فقط (metadata.json) — ليست دليل إنتاج. Confusion matrix/PR-AUC: **غير مثبت**.

---

# PART H — Isolation Forest
CODE train_models.py:42: `IsolationForest(random_state=42, contamination=0.18)` — **unsupervised** (`iso.fit(X_train)` بلا labels). الاستدلال `iso_raw = decision_function(X)[0]` (ensemble.py:99)، ثم **المعادلة المؤكدة حرفيًا** (ensemble.py:100): `iso_prob = clamp((0.5 − iso_raw) × 1.2 + 0.5, 0, 1)`. **ليست احتمال احتيال** — تحويل خطي يدوي لدرجة شذوذ. تقييم مستقل/معايرة: **غير مثبت**. مثال: raw=−0.083→1.1996→**1.0** (clamped)؛ raw=0.2→**0.86**.

---

# PART I — ML Ensemble
CODE ensemble.py: **تسلسلي** (GB ثم Iso) على **نفس الـ vector**. `fused = gb×0.70 + iso×0.30` (سطر 115) → clamp+round4. مثال: 0.72/0.40 → 0.504+0.120 = **0.624**. ⚠️ وزن GB=0.70 **داخل ML** ≠ وزن ML=0.25 **داخل Fusion** — طبقتان مختلفتان.

**Heuristic fallback** (ensemble.py:118-153): معادلة حتمية (amount/40000 + tx_per_min×0.03 + new_device×0.10 + ...) موسومة `NOT_TRAINED_ML` — **لكن orch:176-180 يضبط ml_prob=None عند ready=False**، أي heuristic **لا يدخل Fusion أبدًا** («explainable but NOT evidence»).

---

# PART J — Graph Engine
CODE graph/engine.py: NetworkX `MultiDiGraph` في الذاكرة. عقد مُسمّاة `t:{tenant}|{kind}:{id}` (acct/tx/device/ip)، حواف sends/to/uses/from — **لا حواف بين مستأجرين** (عزل بنيوي). **المعادلة (engine.py:136-138)**: `score = min(1, shared_dev×0.15 + shared_ip×0.10 + max(0,linked−5)×0.04)`؛ إن hops≤2 إلى known_fraud: `+0.30`. مثال: 3 dev + 2 ip + 8 linked + hops=2 → min(1, 0.45+0.20+0.12)=0.77 → +0.30 → **1.00**.

---

# PART K — AML
CODE aml/service.py — `screen()`:
1. **الدول**: beneficiary_country (أو ip_country) → sanctions: `sanctions_hit=True` +0.60؛ high_risk: `fatf_high_risk_country` +0.20.
2. **الأسماء** (fuzzy عبر matching.py): sender/beneficiary/customer/merchant ضد sanctions +0.60×score، pep +0.35×score، custom +0.25×score.
3. **الحسابات** (مطابقة **تامة**): sanctions → `sanctions_hit` +0.60؛ custom → `watchlist_account_hit` +0.30.
4. **Typologies**: structuring (9000≤amount<10000 وcount≥2) +0.30؛ rapid (tx_1h≥8 وamount_1h>20000) +0.25؛ round+offshore +0.15؛ tor/vpn مع amount>5000 +0.10.
5. `signal.score = min(1, Σ)` — cap فقط. كل hit بأدلة point-in-time في `watchlist_evidence`.
**matching.py**: normalize (NFKD+تجريد) + similarity (SequenceMatcher / Jaccard / containment×0.92)، عتبة fuzzy=0.87، تصنيف confirmed/potential.
**الفرق**: `aml_score` يدخل Fusion (وزن 0.15)؛ `sanctions_hit`/`watchlist_account_hit` = **Guards** خارج الـ score.

---

# PART L — Behavior
CODE orch:90-103: `0.45×[biometric<0.4] + 0.20×[keystroke<1.2] + 0.15×[session_ms>600000]`، cap=1.0. **بدون payload → 0.0 لكن status=`degraded`** (ليس unavailable) — **يدخل Fusion بصفر وبوزن كامل**؛ الوزن لا يُعاد توزيعه (فرق جوهري عن ML). إشارة واحدة=0.45، اثنتان=0.65، ثلاث=0.80.

---

# PART M — FX
CODE fx_service.py `_lookup` — الأولوية: **1) Tenant FX Override** (يفوز دائمًا) → **2) Institution rate** (فقط إن موثوق: >0 وضمن `FX_INSTITUTION_TRUST_PCT`=divergence×2 من المرجع، بمقارنة الاتجاهين) → **3) Reference Group** للمستأجر → **4) General rates** (الأعلى `_rank` ثم الأحدث). ثم cross-rate عبر المرجعية → stale fallback (`is_stale=True`) → MISSING.
**CONFIG**: REFERENCE=USD, DISPLAY=YER, DIVERGENCE=3.0%, STALE=24h.
**FxStatus**: NATIVE / OK / STALE / DIVERGENT / MISSING. عملة معطّلة → 422؛ مجهولة → MISSING → Guard REVIEW/BLOCK (policy.fx_missing_action، لا silent allow — policy_engine.py:137-142).
**الأثر**: يدخل عبر `features.amount_usd` (قواعد R-VEL-002/DEV-001/DEV-004/ATO-001/AML-001/AML-002/CT-001/NEW-001) وعبر fx_missing guard. **لا يدخل ML vector** (الخام `amount` هو Feature#0). القرار التاريخي لا يتغير — `fx_proof` يُخزَّن.
**مثال**: 500,000 YER بسعر USD/YER=545 معكوسًا → reference ≈ **917.43 USD**.
TEST: test_fx.* (native/direct/inverse/cross/unknown/stale/divergent/immutable).

---

# PART N — Risk Fusion
**CODE orch:216-235**:
```
policy  = _resolve_policy(tenant_id)     # PolicyEngine.resolve
weights = policy["weights"]
comp_scores[k] = score_k if health[k]=="healthy" else None
active_weight   = Σ weights[k] لـ healthy
applied_weights = weights[k]/active_weight
final = clamp(Σ comp_scores[k]×applied_weights[k], 0, 1)
```
**الأوزان (CONFIG config.py:107-111)**: 0.35/0.25/0.15/0.15/0.10. **POLICY**: المستأجر يعيد قياس كل وزن **±25% فقط** (0.75–1.25) ثم إعادة تطبيع لمجموع 1 (policy_engine.py:108-124).
**مثال** (كلها healthy): 0.80/0.70/0.40/0.60/0.20 → 0.280+0.175+0.060+0.090+0.020 = **0.625**.
**Confidence (orch:251-264)**: `Σ state_factor×nominal_weight` (healthy=1.0, degraded=0.5, unavailable=0.0) — TEST: 1.0 كاملة، ≈0.75 ML down، ≈0.95 behavior مفقود.
⚠️ **تناقض موثّق**: `risk_sensitivity` (0.5–1.5) محسوبة في policy_engine.py:101-106 لكن **غير مطبَّقة** في orchestrator (DOC ≠ CODE).

---

# PART O — Failure / Renormalization
`active_weight = Σ weights(healthy)`؛ `applied = w/active_weight`. **مثال ML down**: active=0.75 → applied: rules 0.4667, graph 0.20, aml 0.20, behavior 0.1333 → بقيم 0.80/0.40/0.60/0.20: final = **0.60**. `degraded_mode = any(≠healthy)`؛ `degraded_reason` نصي. **سبب استبعاد ML**: ready=False → ml_prob=None (orch:176-180) — heuristic لا يُحتسب. TEST: test_component_health (weight_applied=0, degraded=True) + test_aml_unavailable_fails_closed.

---

# PART P — Policy Engine (فك الخلط)
**Risk Engine ≠ Policy Engine.** من يحسب Risk: orchestrator (orch:235). من يقرأ Thresholds: `PolicyEngine.resolve` يُنتجها، `_decide`/`_band` يقرآنها. من يحوّل Score→Action: `_decide` (orch:115-125) + Guards. Policy = settings defaults ← institution profile ← tenant `policy_json` (مقيّدة بالحدود).

---

# PART Q — Thresholds (لكل profile — POLICY policy_engine.py:42-60)
| Profile | challenge | review | block |
|---|---|---|---|
| wallet / payment | 0.35 | 0.60 | 0.80 |
| merchant / merchant_retail | 0.40 | 0.65 | 0.85 |
| merchant_wholesale / real_estate | 0.45 | 0.70 | 0.88 |
| exchange | 0.30 | 0.55 | 0.78 |
| remittance | 0.40 | 0.65 | 0.85 |
| individual/consumer/bank (default) | 0.35 | 0.60 | 0.80 |
**CONFIG defaults** (config.py:102-104): 0.35/0.60/0.80. حدود: challenge∈[0.20,0.50]، review∈[0.40,0.75]، block∈[0.60,0.95]، ترتيب مفروض challenge+0.05≤review+0.05≤block.
**أمثلة (wallet)**: 0.20→ALLOW · 0.34→ALLOW · 0.35→CHALLENGE · 0.59→CHALLENGE · 0.60→REVIEW · 0.79→REVIEW · 0.80→BLOCK · 0.90→BLOCK.
TEST: test_decide_ladder + test_band_boundaries + test_tenant_thresholds.
⚠️ `ML_THRESHOLD_BLOCK=0.90/REVIEW=0.65` (config.py:98-99) **غير مستخدمة** في مسار القرار.

---

# PART R — Mandatory Guards (الترتيب الفعلي — CODE orch:266-300)
1. `watchlist_account_hit` (غير sanctions) → `final = max(final, review_th)` (أرضية REVIEW).
2. قاعدة severity=high + behavior≠healthy → `final = max(final, challenge_th)`.
3. **AML unavailable** → `decision = REVIEW` + أرضية review + وسم `AML_UNAVAILABLE_FAIL_CLOSED` (fail-closed).
4. **fx_missing** → policy: `block`→BLOCK+أرضية block؛ وإلا REVIEW+أرضية review.
5. وإلا → `_decide(final, sanctions_hit, policy)`: **sanctions_hit → BLOCK فورًا مهما كان score** (orch:117-118).
6. sanctions_hit وfinal<block → `final = block_th` (أرضية رقمية للتقرير).
**مثال**: Risk=0.20 مع sanctions_hit → **BLOCK** وfinal→0.80. TEST: test_decide_sanctions_forces_block_even_at_zero_score.

---

# PART S — Final Decision
`Decision ∈ {ALLOW, CHALLENGE, REVIEW, BLOCK}`؛ `risk_band`: LOW/MEDIUM/HIGH/CRITICAL بنفس العتبات. يُنتَج في `_decide`، يُعدَّل بالـ Guards، ثم يُخزَّن ويُبنى عليه: alert (CHALLENGE+)، case (REVIEW+)، notifications (REVIEW/BLOCK)، event `decision.created`.

---

# PART T — Persistence & Audit
**decisions (LIVE: 34 عمودًا)**: decision_id, tx_id, tenant_id, ts, decision, risk_score, risk_band, latency_ms, **rule_score, ml_score, graph_score, aml_score, behavior_score**, rules_json, ml_json, graph_json, aml_json, top_reasons_json, typology, reasoning_ar, ai_model, idempotency_key, created_at, tx_snapshot_json, features_snapshot_json, fx_proof_json, rule_set_version, model_version, config_version, request_id, component_health_json, degraded_mode, degraded_reason, confidence.
**transactions (LIVE: 28 عمودًا)**: tx_id, tenant_id, ts, channel, amount, currency, sender/beneficiary ids, beneficiary_country, merchant_id/name, device_id, ip, ip_country, raw_json, features_json, created_at, reference_amount, reference_currency, fx_snapshot_id, fx_status, region, event_type, direction, is_internal, linked_tx_id.
**Audit (audit_repo.py)**: append-only **بسلسلة SHA-256** — `entry_hash = SHA256(prev_hash|ts|tenant|actor|event|resource|...)`؛ أي عبث يكسر السلسلة ويكشف نفسه. Graph يُغذَّى بكل معاملة (`add_transaction`).

---

# PART U — FraudAgent / Explanation
CODE orch:314-331 + fraud_agent.py + openrouter.py: يُستدعى **بعد القرار** فقط إن `final ≥ AI_MIN_SCORE (0.45) و AI_ENABLED (True)`. المدخلات: `tx.model_dump()` (≤600 حرف) + `rules_hits` (≤400 حرف) + `ml_prob` — **لا يستقبل risk_score النهائي ولا القرار**. المخرجات: `{typology, reasoning_ar}` — إن وُجد reasoning_ar يحل محل النص المحلي (`" ؛ ".join(top_reasons[:4])`). **لا يغيّر القرار أو أي score — لا مسار كتابة منه** (مؤكد). OpenRouter: env `OPENROUTER_KEYS` (مفصولة بفواصل، round-robin)، primary `google/gemma-2-9b-it:free` + 3 fallbacks، timeout=10s، 401/429→مفتاح ميت 300s. **بدون مفاتيح**: `{"ok":False,"error":"no_keys"}` → reasoning_ar=None → **يبقى التفسير المحلي**. ⚠️ بيانات المعاملة تُرسل خارجيًا باقتطاع طول فقط — **لا redaction**.

---

# PART V — WHO CALCULATES / DECIDES / EXECUTES
**Calculates**: Features→FeatureExtractor · Rules→RuleEngine+sum · gb/iso→joblib · ML→EnsembleScorer · Graph→GraphEngine · AML→AMLService · Behavior→_behavior_score · **Risk Score→orchestrator** · Confidence→orchestrator.
**Decides**: `orchestrator._decide` + Guards + thresholds من PolicyEngine. **لا** Rules/ML/Graph/AML/Behavior/FraudAgent منفردًا.
**Executes**: AEGIS يعيد القرار في استجابة Webhook (webhook.py:292-317). **التنفيذ الفعلي (إيقاف/تمرير الحوالة) خارج AEGIS لدى البنك/المحفظة — غير مثبت في الكود.**

---

# PART W — End-to-End Examples (حقائق كود + مدخلات افتراضية مميّزة)
**W.1 كامل**: 500,000 YER، جهاز مشترك بـ3، مستفيد جديد، 3 فجرًا، biometric=0.3 → FX≈917.43 USD · Rules: R-DEV-005 (0.30) → rule_score=0.30 · ML (BINARY — نفترض gb=0.40, iso=0.50): 0.28+0.15=**0.43** · Graph: 3dev → min(1,0.45)=**0.45** · AML=0 · Behavior: 0.3<0.4 → **0.45** · Fusion (كلها healthy): 0.105+0.1075+0.0675+0+0.045=**0.325** → wallet: <0.35 → **ALLOW/LOW** · confidence=1.0. **Final Decision Owner = orchestrator._decide + wallet policy**.
**W.2 sanctions**: final=0.20 + sanctions_hit → **BLOCK**، final→0.80 (TEST مؤكد).
**W.3 ML down**: ml_prob=None → active=0.75 → applied (0.4667/0.20/0.20/0.1333) → بقيم W.1: 0.14+0.09+0+0.06=**0.29** → ALLOW · degraded=true · reason="ml=unavailable" · confidence≈0.75.
**W.4 Rule-heavy**: R-GEO-001(0.55)+R-ATO-001(0.55)+R-DEV-005(0.30) → min(1,1.40)=**1.00** → وحدها: 1.0×0.35=0.35 → **CHALLENGE**.
**W.5 ML-heavy**: gb=0.95, iso_raw=−0.2 → iso_prob=(0.7)×1.2+0.5=1.34→**1.0** → ml=0.665+0.30=**0.965** → وحدها: 0.965×0.25=0.241 → مع قاعدة high واحدة (0.35): 0.241+0.1225=0.3635 → **CHALLENGE**.

---

# PART X — Failure Modes
| الفشل | الاكتشاف | Fallback | أثر Score | أثر القرار | Degraded? |
|---|---|---|---|---|---|
| Models مفقودة/load error | ready=False, log | heuristic للشرح فقط، ml_prob=None | وزن ML يُوزَّع | طفيف | نعم |
| ML raise | try/except orch:181 | ml_prob=None | كذلك | كذلك | نعم |
| Rules raise | orch:166 | 0، unavailable | الوزن يُوزَّع | +أرضية challenge إن high hit | نعم |
| Graph raise | orch:190 | GraphSignal() فارغ | الوزن يُوزَّع | — | نعم |
| **AML raise** | orch:201 | **fail-CLOSED REVIEW إجباري** | مستبعد | **≥REVIEW** | نعم+وسم |
| Behavior غائب | tx.behavior=None | 0.0، degraded (يدخل بصفر!) | الوزن يبقى | أرضية challenge إن high hit | نعم |
| FX مفقود | fx_status=missing | reference=None؛ policy REVIEW|block | amount_usd=raw fallback | REVIEW/BLOCK | عبر reason |
| OpenRouter فشل | r.ok=False | reasoning_ar محلي | لا أثر | لا أثر | لا |
| Policy تالفة | resolve(None) | defaults+clamps | — | عتبات آمنة | لا (TEST) |
| DB error في repo | يصعد للمكوّن المستدعي | حسب المكوّن | حسبه | حسبه | حسبه |

---

# PART Y — Tests as Evidence
| الادعاء | الاختبار |
|---|---|
| سلم العتبات | test_decision_engine.test_decide_ladder, test_band_boundaries |
| sanctions→BLOCK عند 0 | test_decide_sanctions_forces_block_even_at_zero_score |
| الأوزان مجموعها 1 | test_weights_sum_to_one |
| عملة مجهولة→REVIEW | test_unknown_currency_forces_review_not_allow |
| ML down→مستبعد+weight 0+degraded | test_component_health.test_ml_unavailable_excluded_from_score_and_flagged |
| AML down→fail-closed REVIEW | test_aml_unavailable_fails_closed_to_review |
| health يُخزَّن | test_component_health_persists_verbatim_in_decisions_table |
| confidence 1.0/0.75/0.95 | test_confidence.* |
| عتبات المستأجر تغيّر القرار | test_tenant_policy.test_tenant_thresholds_are_scoped_and_change_decision |
| سياسة تالفة→defaults | test_missing_or_malformed_policy_uses_safe_defaults |
| override لكل مستأجر | test_rule_overrides.* |
| FX | test_fx.* |

---

# PART Z — DOCUMENT vs CODE vs TEST
| الموضوع | Document | Code | Test | الحالة النهائية |
|---|---|---|---|---|
| عدد القواعد | «22» (وثائق قديمة) | YAML+DB=**21** | rule_engine.loaded=21 | **21** |
| risk_sensitivity | «تُضرب في fused score» | **غير مطبَّقة** | لا يوجد | **غير مفعَّلة — تناقض** |
| ترتيب FX | رسوم: بعد Features | webhook قبل orchestrator | — | **FX قبل Features** |
| توازي النموذجين | — | تسلسلي GB ثم Iso | — | تسلسلي |
| ML heuristic | يُرجع score | ml_prob=None، لا يدخل Fusion | test_ml_unavailable | **heuristic ≠ دليل** |
| metrics=1.0 | metadata | على بيانات اصطناعية | — | ليست دليل إنتاج |
| decisions cols | «33» (تقدير سابق) | LIVE=**34** | — | **34** |
| transactions cols | — | LIVE=**28** | — | **28** |

---

# PART AA — Mathematical Specification (المعادلات المثبتة فقط)
```
RulesScore  = min(1, Σ hit.score_contribution)                        [orch:164]
GBProb      = GBC.predict_proba(X)[0][1]                              [ensemble:82]  (BINARY)
IsoRaw      = IsoForest.decision_function(X)[0]                       [ensemble:99]  (BINARY)
IsoProb     = clamp((0.5 − IsoRaw)×1.2 + 0.5, 0, 1)                   [ensemble:100]
MLScore     = clamp(0.70×GBProb + 0.30×IsoProb, 0, 1)                 [ensemble:115]
GraphScore  = min(1, dev×0.15 + ip×0.10 + max(0,linked−5)×0.04
                  + (0.30 if hops≤2))                                 [graph:136-138]
AMLScore    = min(1, Σ signals)  (0.60/0.20/0.60s/0.35s/0.25s/0.30/0.30/0.25/0.15/0.10)  [aml/service]
Behavior    = min(1, 0.45[bio<0.4] + 0.20[key<1.2] + 0.15[sess>600000])  [orch:90-103]
ActiveWeight   = Σ w_k لـ healthy                                     [orch:229]
AppliedWeight_k = w_k / ActiveWeight                                  [orch:230-231]
FinalRisk   = clamp(Σ score_k × AppliedWeight_k, 0, 1)                [orch:235]
Confidence  = clamp(Σ {healthy:1.0,degraded:0.5,unavailable:0.0}_k × w_nominal_k, 0, 1)  [orch:251-264]
Decision    = BLOCK if sanctions_hit                                  [orch:117]
              else REVIEW if aml_unavailable                          [orch:281-283]
              else ≥block→BLOCK, ≥review→REVIEW, ≥challenge→CHALLENGE, else ALLOW
Guards      = watchlist_account→final≥review ; high-rule+behavior↓→final≥challenge ;
              fx_missing→REVIEW|BLOCK ; sanctions→final≥block         [orch:266-300]
HeuristicFallback = min(0.25,amount/40000) + min(0.15,txpm×0.03) + new_dev×0.10 +
                    min(0.10,shared_dev×0.05) + impossible×0.20 + high_risk_country×0.15 +
                    new_benef×0.05 + pw_recent×0.15  (capped)  — NOT scored in fusion  [ensemble:129-139]
```

---

# PART AB — Number Traceability
| الرقم | المعنى | المصدر | الموقع |
|---|---|---|---|
| 0.70/0.30 | أوزان GB/Iso داخل ML | CODE | ensemble.py:115 |
| 0.35/0.25/0.15/0.15/0.10 | أوزان Fusion الافتراضية | CONFIG | config.py:107-111 |
| ±25% (0.75–1.25) | حد إعادة قياس أوزان المستأجر | POLICY | policy_engine.py:38 |
| 0.35/0.60/0.80 | عتبات القرار الافتراضية | CONFIG | config.py:102-104 |
| 0.20-0.50/0.40-0.75/0.60-0.95 | حدود العتبات | POLICY | policy_engine.py:31-35 |
| 1.2 / 0.5 | ميل/مركز Iso | CODE | ensemble.py:100 |
| 0.15/0.10/0.04/0.30 | إشارات Graph | CODE | graph/engine.py:136-138 |
| 0.45/0.20/0.15 | إشارات Behavior | CODE | orch:98-102 |
| 0.4 / 1.2 / 600000 | عتبات Behavior | CODE | orch:96-101 |
| 0.60/0.20/0.35/0.25/0.30/0.25/0.15/0.10 | أوزان AML | CODE | aml/service.py |
| 0.87 | عتبة fuzzy للأسماء | CODE | aml/service.py:66 |
| 0.18 | contamination | TRAIN | train_models.py:42 |
| 42 | random_state/seed | TRAIN | train+generate |
| 0.2 / 3500 / 1500 | test_size / أحجام | TRAIN | train:35, generate:81-84 |
| 999999 | default pw-seconds | CODE | features.py:87 |
| 9000-10000/≥2, ≥8/>20000, >5000 | typology thresholds | CODE | aml/service.py |
| 5min / 72h | replay bounds | CODE | webhook.py:242-245 |
| 0.45 / True | AI_MIN_SCORE / AI_ENABLED | CONFIG+LIVE | config.py |
| 0.90/0.65 | ML_THRESHOLD_* | CONFIG | config.py:98-99 — **غير مستخدمة** |

---

# PART AC — Complete Tables
| Component | Input | Processing | Formula | Output | Range | Fusion Weight | Can Override? | Source |
|---|---|---|---|---|---|---|---|---|
| Rules | tx+features | JSONLogic 21 قاعدة | min(1,Σ) | rule_score | 0..1 | 0.35 | لا (أرضية challenge فقط) | rules/engine.py |
| ML | vector[20] | GB+Iso | 0.70GB+0.30Iso | ml_prob | 0..1 | 0.25 | لا | ml/ensemble.py |
| Graph | tx+graph | tenant signals | PART AA | graph_score | 0..1 | 0.15 | لا | graph/engine.py |
| AML | tx+features+lists | country/name/account/typology | min(1,Σ) | aml_score | 0..1 | 0.15 | **نعم (sanctions→BLOCK)** | aml/service.py |
| Behavior | tx.behavior | 3 إشارات | min(1,Σ) | behavior_score | 0..1 | 0.10 | لا | orchestrator.py |

**ما لا يدخل الحساب**: amount_usd (Rules فقط)، vpn/tor/proxy (Rules+AML)، severity (لا تدخل rule_score)، tags، risk_sensitivity (غير مطبقة)، ML_THRESHOLD_*، FraudAgent output (شرح).

---

# PART AD — Code Reference Map
| Functionality | File | Class | Function | Vars |
|---|---|---|---|---|
| Webhook | api/v1/webhook.py | — | fraud_webhook, normalize_transaction, _apply_fx | idem_key |
| Pipeline | services/orchestrator.py | DecisionOrchestrator | evaluate_and_persist, _decide, _band, _behavior_score | final, health, applied_weights |
| Features | features.py | FeatureExtractor | extract, vector | velocity/device/geo/account |
| Rules | rules/engine.py | RuleEngine, Rule | evaluate | _OPS, by_id |
| Rules seed | rules/default_ruleset.yaml + rule_repo.seed_defaults | — | — | 21 |
| ML | ml/ensemble.py | EnsembleScorer | score, _real_score, _heuristic_score | ready, 0.70/0.30 |
| Graph | graph/engine.py | GraphEngine | score, mark_fraud, add_transaction, bootstrap | _ns, _known_fraud |
| AML | aml/service.py, aml/matching.py | AMLService | screen, _screen_*, match_name | fuzzy=0.87 |
| Policy | services/policy_engine.py | PolicyEngine | resolve | PROFILES, PROTECTED_RULES |
| FX | services/fx_service.py | FxService | normalize, _lookup, cross_rate | 4 tiers |
| Config | core/config.py | Settings | — | WEIGHT_*, DECISION_THRESHOLD_*, AI_* |
| Decisions | repositories/decision_repo.py | DecisionRepository | create, mark_seen, get_by_idempotency | 34 cols |
| Tx | repositories/transaction_repo.py | TransactionRepository | create, velocity, shared_* | 28 cols |
| Audit | repositories/audit_repo.py | AuditRepository | log | SHA-256 chain |
| Events | streaming/__init__.py | EventBus | subscribe/publish | tenant-scoped |
| Wiring | services/registry.py | ServiceRegistry | initialize | — |
| AI | agents/fraud_agent.py, agents/openrouter.py | FraudAgent, OpenRouterClient | analyze, chat | OPENROUTER_KEYS |
| Training | training/generate_dataset.py, train_models.py, evaluate_models.py | — | main | seed 42 |
| Schemas | models/schemas.py | Transaction, RiskAssessment, AMLSignal, GraphSignal, RuleHit, ModelScore | — | — |

---

# PART AE — Manual Transaction Calculation Procedure
1. استخرج الحقول (normalize_transaction). 2. **FX**: tiers (override→institution→reference→general→cross→stale→missing) → amount_usd=reference_amount. 3. **Features**: استعلامات velocity/shared/known_benef/structuring على تاريخ المرسل (PostgreSQL). 4. **Rules**: قيّم `when` لكل قاعدة → min(1,Σ). 5. **ML**: joblib (لا يدويًا بلا النموذج) → 0.70gb+0.30iso. 6. **Graph**: من الحالة in-memory → المعادلة. 7. **AML**: القوائم → min(1,Σ) + sanctions_hit. 8. **Behavior**: 3 إشارات. 9. **Health**: أي≠healthy→None. 10. **active/applied**: PART O. 11. **final=clamp(Σ)**. 12. **Policy**: profile→عتبات. 13. **Guards**: PART R بالترتيب. 14. **Decision**: _decide. 15. **التخزين**: الجدولان+health+confidence. 16. **Explanation**: top_reasons→محلي أو FraudAgent.
⚠️ لا يمكن يدويًا بالكامل: gb_prob/iso_raw (BINARY)، حالة الـ graph، fuzzy matching — تحتاج تشغيل الكود.

---

# PART AF — Known Limitations / Unknowns
**Verified**: 1) النماذج على بيانات **اصطناعية بالكامل** (metrics=1.0 لا تعني إنتاجًا). 2) `risk_sensitivity` غير مطبقة (تناقض). 3) لا تقييم مستقل لـ IsoForest ولا معايرة للتحويل. 4) لا confusion matrix/PR-AUC/leakage/validation set. 5) CSV التدريبي غير موجود بالريبو (يُولَّد). 6) Graph in-memory — يُعاد بناؤه عند الإقلاع. 7) بيانات المعاملة لـ OpenRouter بلا redaction. 8) Behavior المفقود يدخل بصفر ووزن كامل (degraded≠unavailable).
**غير مثبت في الكود الذي تم فحصه**: سبب اختيار الأوزان؛ الأداء على بيانات حقيقية؛ تنفيذ القرار لدى core banking؛ تقييم IsoForest مستقل؛ خوارزمية fuzzy التفصيلية (matching.py استُخدم عبر واجهته: NFKD+SequenceMatcher/Jaccard/containment، عتبة 0.87).
**مستقبلي (لا تعديل الآن)**: معايرة IsoProb، metrics حقيقية، redaction قبل LLM، ربط أو حذف risk_sensitivity.

---

*أُعدّ هذا المرجع الموحد بإعادة فحص المستودع الحالي (HEAD 462ed87) والبيئة الحية في 2026-09-17، مع تصحيح تعارضات الدليلين السابقين. لا كود عُدّل، لا تدريب، لا commit، لا push.*
