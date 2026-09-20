# AEGIS — المرجع التقني الشامل + التدقيق المستقل الكامل
# Complete Technical Reference & Independent Audit — Single Consolidated File

> **تاريخ الإصدار:** 2026-09-18 · **الحالة:** HEAD `462ed87` (بدون تعديل كود / DB / config / models / commit / push)
> **هذا الملف الواحد يغني عن كل التقارير السابقة** — يحوي ثلاثة أجزاء مترابطة:
>
> **الجزء الأول:** المرجع التقني الرئيسي (Master Technical Reference) — بنية القرار والمخاطر كاملة من الكود الفعلي، PART A→AF، المعادلات المثبتة بالأسطر، Number Traceability، Failure Modes، Tests as Evidence، DOCUMENT vs CODE vs TEST، دليل إعادة الحساب اليدوي، خريطة الكود.
>
> **الجزء الثاني:** تقرير بنية ML/AI وآلية القرار — جرد النموذجين، الـ20 Feature بترتيبها الحرج، التدريب، Ensemble، FraudAgent/OpenRouter، حالات UNKNOWN/NOT FOUND.
>
> **الجزء الثالث:** التدقيق المستقل الشامل (71 قسمًا) — Baseline حي، أول تقييم ML علمي حقيقي (TESTED)، 17 Findings بصيغة Evidence/Severity/Impact/Recommendation/Priority، تحليل Fusion الرياضي، Fail-open/Fail-closed لكل dependency، Privacy Data Inventory، Security إضافي، UX، البحث العالمي، دراسة اليمن، المعمارية المرجعية وعقد التكامل، 14 سيناريو قرار، الزائد/الناقص، المعمارية المستقبلية + Migration/Rollback، Architecture Decision Matrix.
>
> **وسوم الأدلة الموحدة:** CODE (ملف:سطر) · LIVE (التشغيل/DB الحية 2026-09-17/18) · TEST · CONFIG · DATABASE · EXTERNAL RESEARCH · BINARY (داخل joblib) · INFERENCE · UNKNOWN/«غير مثبت في الكود الذي تم فحصه».

---
---

# ═══════════════════════════════════════════
# الجزء الأول — AEGIS MASTER TECHNICAL REFERENCE
# ═══════════════════════════════════════════

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

---
---

# ═══════════════════════════════════════════
# الجزء الثاني — ML/AI & DECISION ARCHITECTURE REPORT
# ═══════════════════════════════════════════

# AEGIS — تقرير بنية الـ ML / AI وآلية اتخاذ القرار
# AEGIS ML / AI & Decision Architecture Report

> **نطاق التقرير**: دراسة تقنية وصفية للحالة الحالية الفعلية للكود والملفات والنماذج الموجودة في المستودع.
> لم يتم إجراء أي تعديل على الكود، ولا إعادة تدريب، ولا تغيير للنماذج أو الإعدادات أو الـ Features.
> كل معلومة موسومة بحالة تحقق: **VERIFIED** (مثبت من الكود/الملفات) · **PARTIALLY VERIFIED** · **INFERRED** · **UNKNOWN** · **NOT FOUND**.
> لا يعرض هذا التقرير أي مفاتيح أو أسرار حقيقية.

---

## 1. Executive Summary

منصة AEGIS تستخدم **نموذجَي ML مدرَّبَين فعليًا** فقط:

| # | النموذج | النوع | الملف | الحالة |
|---|---------|-------|-------|--------|
| 1 | Gradient Boosting | `sklearn.ensemble.GradientBoostingClassifier` (supervised) | `models/trained/gradient_boosting.joblib` | VERIFIED — مدرب |
| 2 | Isolation Forest | `sklearn.ensemble.IsolationForest` (unsupervised) | `models/trained/isolation_forest.joblib` | VERIFIED — مدرب |

لا يوجد نموذج ML ثالث. **FraudAgent ليس نموذج ML** — هو غلاف (wrapper) اختياري حول خدمة OpenRouter الخارجية (LLM) هدفه **توليد تفسير عربي فقط**، و**لا يستطيع تغيير القرار**.

**القرار النهائي** يصدره **Risk Engine** (دالة `_decide` في `backend/app/services/orchestrator.py`) اعتمادًا على `risk_score` المُدمج وعلى `policy` المؤسسة — وليس أي نموذج ML منفردًا.

النماذج مدرّبة على **بيانات اصطناعية بالكامل** (`models/synthetic_fraud_dataset.csv`) — موصوفة في `metadata.json` بـ «synthetic — NOT real fraud data». لذلك **لا يصح ادعاء دقة إنتاجية** رغم أن مقاييس الاختبار المسجلة = 1.0 (انظر §13).

---

## 2. Current ML/AI Architecture

```
Transaction (webhook)
    │
    ▼
Idempotency check ────────────────────────────────► (cached decision if duplicate)
    │
    ▼
FeatureExtractor.extract(tx)          ← استعلامات حقيقية من PostgreSQL
    │
    ├──► Rules Engine  → rule_score
    ├──► ML (EnsembleScorer.score)     → ml_prob      [GB + IsolationForest]
    ├──► GraphEngine.score             → graph_sig.score
    ├──► AMLService.screen             → aml_sig.score
    └──► _behavior_score               → behavior_score
    │
    ▼
Weighted fusion (policy weights, availability-aware renormalization)
    │
    ▼
risk_score (0..1)
    │
    ▼
_decide(score, aml_hit, policy)  →  ALLOW / CHALLENGE / REVIEW / BLOCK
    │
    ▼
Decision persisted + EventBus publish + audit
    │
    └──► [إن final ≥ AI_MIN_SCORE و AI_ENABLED] FraudAgent.analyze(...) → reasoning_ar (تفسير فقط)
```

المسار أعلاه **VERIFIED** من `backend/app/services/orchestrator.py` (دالة القرار الرئيسية).

---

## 3. All ML Models — الجرد الكامل

### 3.1 ملفات النماذج (Model Files)

| العنصر | القيمة | الحالة |
|--------|--------|--------|
| مسار النماذج | `models/trained/` | VERIFIED |
| ملف GB | `models/trained/gradient_boosting.joblib` | VERIFIED |
| ملف IsoForest | `models/trained/isolation_forest.joblib` | VERIFIED |
| ملف الوصف | `models/trained/metadata.json` | VERIFIED |
| إصدار النموذج | `2026.08.13` (من metadata) | VERIFIED |
| تاريخ التدريب | `2026-08-13T23:43:20Z` (من metadata) | VERIFIED |

### 3.2 أين تُحمَّل وأين تُستدعى

| العنصر | القيمة | الحالة |
|--------|--------|--------|
| التحميل | `EnsembleScorer._load()` في `backend/app/ml/ensemble.py` — `joblib.load()` لكلا الملفين | VERIFIED |
| اكتشاف المسار | `_find_models_dir()` يبحث تصاعديًا عن `models/trained/metadata.json` (يدعم بنية الريبو والحاوية) | VERIFIED |
| الاستدعاء | `EnsembleScorer.score(features)` → `_real_score(X)` | VERIFIED |
| مَن يستدعيه | `orchestrator.py` → `self.ml.score(vector)` حيث `vector = self.features.vector(tx, features)` | VERIFIED |
| الدخل | `list[float]` بطول **20** (يُحوَّل إلى `np.float32` ويُعاد تشكيله `(1, -1)`) | VERIFIED |
| الخرج | `tuple[float, list[ModelScore]]` = (احتمال مدمج 0..1, تقرير لكل نموذج) | VERIFIED |

---

## 4. Gradient Boosting

| العنصر | القيمة | الحالة |
|--------|--------|--------|
| النوع | `GradientBoostingClassifier(random_state=42)` — بقية الـ hyperparameters = **افتراضيات sklearn** | VERIFIED (لا توجد معلمات مخصصة في `train_models.py`) |
| الهدف | تصنيف احتمالي supervised: P(fraud) | VERIFIED |
| التدريب | `gb.fit(X_train, y_train)` | VERIFIED |
| الاستدلال | `gb.predict_proba(X)[0][1]` → `gb_prob` | VERIFIED |
| التقييم | accuracy / precision / recall / roc_auc (كلها 1.0 في metadata) | VERIFIED (لكن انظر §13 — بيانات اصطناعية) |
| Confusion matrix | NOT FOUND (لا تُحسب ولا تُحفظ) | NOT FOUND |
| PR-AUC | NOT FOUND | NOT FOUND |
| سبب اختيار الـ hyperparameters | NOT FOUND (غير موثق؛ استُخدمت الافتراضيات) | NOT FOUND |

---

## 5. Isolation Forest

| العنصر | القيمة | الحالة |
|--------|--------|--------|
| النوع | `IsolationForest(random_state=42, contamination=0.18)` | VERIFIED |
| طبيعته | **Unsupervised** — `iso.fit(X_train)` بدون labels | VERIFIED |
| معنى الـ anomaly | درجة شذوذ من `decision_function` (قيم سالبة = أكثر شذوذًا) | VERIFIED |
| الاستدلال | `iso_raw = iso.decision_function(X)[0]` ثم تحويله إلى [0,1] | VERIFIED |
| تحويل الشذوذ إلى score | `iso_prob = clamp( (0.5 − iso_raw) * 1.2 + 0.5 , 0..1 )` — **معادلة خطية مضبوطة يدويًا** | VERIFIED |
| **هل يعطي قرار Fraud مباشرة؟** | **لا.** يعطي **Anomaly Score (0..1)** يدخل كإشارة في الـ fusion وليس قرارًا | VERIFIED |
| طريقة تقييمه | NOT FOUND — لا توجد مقاييس تقييم للـ IsoForest في الكود أو metadata | NOT FOUND |

> **الإجابة المباشرة**: Isolation Forest **لا يُصدر قرار Fraud**؛ يعطي درجة شذوذ تُدمج في درجة ML الكلية.

---

## 6. Features — لكل نموذج (VERIFIED من `features.py` + `metadata.json`)

النموذجان يتشاركان **نفس الـ vector** المكوّن من **20 feature** بنفس الترتيب. الترتيب **حرج** — موثّق في `generate_dataset.py`: «field order MUST match features.FeatureExtractor.vector() output order».

| # | Feature (code name) | المعنى | المصدر | معالجة |
|---|---------------------|--------|--------|--------|
| 0 | `amount` | مبلغ العملية بالعملة الأصلية | Transaction | `float(tx.amount)` |
| 1 | `hour_sin` | sin دوري لساعة اليوم | Transaction timestamp | `math.sin((hour/24)*2π)` |
| 2 | `hour_cos` | cos دوري لساعة اليوم | Transaction timestamp | `math.cos((hour/24)*2π)` |
| 3 | `tx_per_min_card` | عدد العمليات/دقيقة للمرسل | سجل العمليات (velocity 60s) | استعلام DB |
| 4 | `amount_5min_account` | مجموع المبالغ/5 دقائق | سجل العمليات (velocity 300s) | استعلام DB |
| 5 | `distinct_merchants_1h` | تجار مميزون/ساعة | `tx.metadata` | قراءة metadata |
| 6 | `first_seen_today` | جهاز جديد (لم يُستخدم من قبل) | DB shared_device + sender | `bool → float` |
| 7 | `shared_device_count` | عدد الحسابات المشاركة للجهاز | DB | `len(...) → float` |
| 8 | `shared_ip_count` | عدد الحسابات المشاركة للـ IP | DB | `len(...) → float` |
| 9 | `impossible_travel` | سفر مستحيل جغرافيًا | `tx.metadata` | `bool → float` |
| 10 | `fatf_high_risk` | دولة عالية المخاطر FATF | `tx.metadata` | `bool → float` |
| 11 | `beneficiary.new` | مستفيد جديد | DB known_beneficiary | `not known → float` |
| 12 | `seconds_since_password_change` | ثوانٍ منذ تغيير كلمة المرور | `tx.metadata` | رقم |
| 13 | `previous_declines` | رفوض سابقة | `tx.metadata` | رقم |
| 14 | `previous_chargebacks` | chargebacks سابقة | `tx.metadata` | رقم |
| 15 | `high_risk_merchant` | تاجر عالي المخاطر | `tx.metadata` | `bool → float` |
| 16 | `off_hours` | خارج ساعات العمل (<6 أو >22) | Transaction timestamp | `bool → float` |
| 17 | `is_round_1000` | مبلغ مدوّر ≥1000 | Transaction amount | `bool → float` |
| 18 | `count_9k_10k_30d > 2` | نمط structuring | DB structuring_count | `>2 → bool → float` |
| 19 | `suspicious_events_30d` | أحداث مشبوهة/30 يوم | DB decisions (block+review) | عدد |

**معالجة عامة**: لا يوجد **scaling/normalization أو encoding** — القيم تُمرَّر خامًا كـ `float`. **Missing-value handling**: قيم افتراضية داخل `extract()` (مثل `seconds_since_password_change` الافتراضي = `999999`). **VERIFIED**.

> **تعارض/ملاحظة**: الـ `extract()` يُنتج حقولًا إضافية (`amount_usd`, `currency`, `vpn`, `tor`, `proxy`, `emulator`, `account_age_days`, ...) **لا تدخل الـ vector** — موجودة للـ Rules/AML لكنها **ليست** Features للنموذجين. هذا **VERIFIED** من `vector()` الذي يختار 20 فقط.

---

## 7. Training Data

| العنصر | القيمة | الحالة |
|--------|--------|--------|
| مولّد البيانات | `training/generate_dataset.py` | VERIFIED |
| ملف البيانات | `models/synthetic_fraud_dataset.csv` | VERIFIED (المسار معرّف) |
| **وجود الملف حاليًا في بيئة الفحص** | `ls` لم يُظهره في المخرجات — **UNKNOWN** (قد يكون مولَّدًا وغير ملتزَم به في git) | UNKNOWN |
| النوع | **اصطناعية بالكامل** (سطر التوثيق: «SYNTHETIC DATA ONLY») | VERIFIED |
| الحجم | 3500 سليمة + 1500 احتيالية = **5000 سجل** + header | VERIFIED (من الكود) |
| Label | العمود الأخير `label` (0/1) — يُحدَّد بـ `int(fraud)` في المولّد | VERIFIED |
| الفصل بين النموذجين | **لا** — نفس الـ CSV ونفس الـ features لكليهما | VERIFIED |
| التقسيم | `train_test_split(test_size=0.2, random_state=42, stratify=y)` — **لا يوجد validation منفصل** | VERIFIED |
| Class imbalance | 3500/1500 = 70%/30% — **لا يوجد معالجة صريحة** (لا SMOTE/weights) | VERIFIED |
| Reproducibility | `random.seed(42)` و `random_state=42` — قابل للتكرار | VERIFIED |
| فحص Data leakage | NOT FOUND — لا يوجد فحص تسرّب | NOT FOUND |
| أمر التدريب | `python training/generate_dataset.py && python training/train_models.py` | VERIFIED |

---

## 8. Training Pipeline

```
python training/generate_dataset.py   → models/synthetic_fraud_dataset.csv
python training/train_models.py       → models/trained/{gradient_boosting.joblib,
                                                       isolation_forest.joblib,
                                                       metadata.json}
python training/evaluate_models.py    → يطبع metrics من metadata.json فقط
```
**VERIFIED**. ملاحظة: `evaluate_models.py` **لا يعيد التقييم** — يقرأ فقط ما خزّنه `train_models.py`.

---

## 9. Model Loading & Inference — VERIFIED

`EnsembleScorer` يحمّل النموذجين عند الإنشاء. عند غياب أحدهما أو فشل joblib → `ready=False` ويتحول إلى `_heuristic_score` (بديل حتمي موسوم `NOT_TRAINED_ML`). في `orchestrator` عند `ready=False` يُضبط `ml_prob=None` — أي **البديل heuristic لا يُحتسب كدليل** في الـ fusion.

---

## 10. ML Ensemble — `ml/ensemble.py` (VERIFIED)

* النموذجان يعملان على **نفس الـ 20-feature vector**.
* يُشغَّلان **تسلسليًا** (GB ثم Iso) داخل `_real_score` — **ليس بالتوازي**.
* **Fusion**: `fused = gb_prob * 0.70 + iso_prob * 0.30` ثم `clamp(0..1)` وتقريب 4 خانات.
* **لا يوجد normalization إضافي** لناتج كل نموذج قبل الدمج (الـ Iso فقط يُحوَّل خطيًا).
* **الأوزان**: GB=0.70 / Iso=0.30 — **ثابتة في الكود** وليست من الـ policy.
* **الناتج النهائي للـ ML** = احتمال مدمج 0..1 يُمرَّر إلى Risk Engine كـ `ml_prob`.

---

## 11. Risk Engine — (VERIFIED من `orchestrator.py` + `policy_engine.py`)

### 11.1 المدخلات ونتيجة كل محرك

| المكوّن | الناتج | المصدر |
|---------|--------|--------|
| Rules | `rule_score = min(1, Σ score_contribution)` | `rules.evaluate` |
| ML | `ml_prob` (أو `None` إن heuristic) | `ml.score` |
| Graph | `graph_sig.score` | `graph.score(tx)` |
| AML | `aml_sig.score` | `aml_service.screen` |
| Behavior | `behavior_score` (0 إن غاب payload) | `_behavior_score` |

### 11.2 الأوزان — تحقق فعلي

الأوزان **ليست ثابتة في orchestrator** بل تُقرأ من `policy["weights"]` وتُعاد تطبيعها حسب المكوّنات «healthy»:

```
active_weight   = Σ weights[k]  للمكوّنات السليمة
applied_weights = weights[k] / active_weight
final           = clamp( Σ comp_scores[k] * applied_weights[k] , 0..1 )
```

* القيم المرجعية للأوزان (rules/ml/graph/aml/behavior) تُؤخذ من إعدادات/سياسة المؤسسة. القيم المبدئية المفترضة (0.35/0.25/0.15/0.15/0.10) **لم تُثبَّت كنص حرفي في orchestrator** — هي **PARTIALLY VERIFIED** (مصدرها `settings`/`policy`، وتُعاد تطبيعها ديناميكيًا).
* ميزة مهمة (VERIFIED): مكوّن معطوب **لا يُحتسب 0** بل يُعاد توزيع وزنه، ويُوسم القرار `degraded`.

### 11.3 Thresholds → القرار (VERIFIED من `policy_engine.py`)

العتبات تختلف حسب **نوع المؤسسة (tenant profile)**:

| Profile | challenge | review | block |
|---------|-----------|--------|-------|
| wallet / payment | 0.35 | 0.60 | 0.80 |
| merchant / merchant_retail | 0.40 | 0.65 | 0.85 |
| merchant_wholesale / real_estate | 0.45 | 0.70 | 0.88 |
| (أخرى) | 0.30 | 0.55 | 0.78 |
| (أخرى) | 0.40 | 0.65 | 0.85 |

القرار (`_decide`): `score ≥ block → BLOCK` · `≥ review → REVIEW` · `≥ challenge → CHALLENGE` · وإلا **ALLOW**، مع معالجة خاصة لـ `aml_hit` (fail-closed) و `fx_missing_action`.

---

## 12. من يُصدر القرار النهائي؟

| المفهوم | المعنى | المصدر |
|---------|--------|--------|
| **Model Prediction** | `gb_prob` / `iso_prob` — احتمالات خام لكل نموذج | `ensemble.py` |
| **Risk Score** | `final` — دمج موزون لكل المحركات (0..1) | `orchestrator` §11 |
| **Final Decision** | ALLOW/CHALLENGE/REVIEW/BLOCK | `orchestrator._decide` + `policy_engine.resolve` |

**الجهة المُصدِرة للقرار النهائي = Risk Engine (`orchestrator._decide`)** مدفوعًا بسياسة المؤسسة من `PolicyEngine`. **لا** نموذج ML منفرد، **ولا** FraudAgent.

---

## 13. FraudAgent — تحقق فعلي (`backend/app/agents/fraud_agent.py`)

| السؤال | الإجابة | الحالة |
|--------|---------|--------|
| ما هو؟ | غلاف async حول OpenRouter — **ليس نموذج ML** | VERIFIED |
| ماذا يستقبل؟ | `analyze(tx, rules_hits, ml_prob)` | VERIFIED |
| هل يستقبل risk_score/final decision؟ | **لا** — فقط `tx` و`rules_hits` و`ml_prob` | VERIFIED |
| متى يعمل؟ | **بعد** حساب `final` — شرط: `final ≥ settings.AI_MIN_SCORE and settings.AI_ENABLED` (سطر 317 في orchestrator) | VERIFIED |
| هل يغيّر القرار؟ | **لا.** يُرجع `reasoning_ar` فقط؛ لو نجح يستبدل نص التفسير المولّد محليًا | VERIFIED |
| ماذا يرسل؟ | prompt عربي: `transaction`(≤600 حرف) + `rules_hits`(≤400 حرف) + `ml_prob`، ويطلب JSON `{"typology","reasoning_ar"}` | VERIFIED |
| ماذا يستقبل؟ | JSON يُستخرج بـ `_extract_json` (يتسامح مع ```json fences) | VERIFIED |

---

## 14. OpenRouter (`backend/app/agents/openrouter.py`) — VERIFIED

| العنصر | القيمة |
|--------|--------|
| Env var | **`OPENROUTER_KEYS`** (قائمة مفاتيح مفصولة بفواصل — تدعم round-robin) |
| المطلوبية | **اختياري** — `enabled = bool(keys)` |
| النماذج | Primary: `google/gemma-2-9b-it:free` + fallbacks: `llama-3.2-3b`, `mistral-7b`, `phi-3-mini` |
| Endpoint | `https://openrouter.ai/api/v1/chat/completions` |
| Timeout | 10 ثوانٍ (`timeout=10.0`) |
| عند 401/429 | يوسم المفتاح dead 300s وينتقل للتالي |
| عند فشل الكل | `{"ok": False, "error": "all_models_failed"}` |
| Sanitization | اقتطاع الطول فقط (600/400 حرف) — **لا يوجد redaction للحقول الحساسة** (PARTIALLY VERIFIED — خطر تسريب بيانات للخارج) |
| logging | لا يُسجَّل الـ prompt نفسه؛ يُسجَّل `openrouter.retry` بالخطأ فقط |

> **ملاحظة أمنية**: الـ prompt يحمل `json.dumps(tx)` (بيانات عملية) إلى خدمة خارجية بدون إخفاء حقول — يستحق مراجعة قبل أي بيانات حقيقية. (VERIFIED من الكود)

---

## 15. Fallback — الحقيقة الفعلية

### الحالة 1: لا يوجد `OPENROUTER_KEYS`
`OpenRouterClient.enabled = False` → `chat()` يُرجع `{"ok": False, "error": "no_keys"}` فورًا → `FraudAgent.analyze` يُرجع `{"model": "fallback", "reasoning_ar": None, "error": "no_keys"}` → في orchestrator يبقى **`reasoning_ar` = النص المحلي المولّد** من `top_reasons` (سطر 316).

* **هل الـ fallback عربي؟** الـ fallback الفعلي هو `reasoning_ar` المحلي المبني من أسباب القرار — **VERIFIED أنه النص الافتراضي**؛ لغته تعتمد على `top_reasons` (PARTIALLY VERIFIED — عربي في الغالب لأنه يُستخدم كـ reasoning_ar).

### الحالة 2: يوجد مفتاح
يُرسَل الـ prompt → يُستخرج JSON → لو وُجد `reasoning_ar` يحل محل النص المحلي. لو فشل الاستخراج → `reasoning_ar=None` ويبقى المحلي.

> **الخلاصة**: الـ fallback **ليس داخل FraudAgent نفسه** بل هو النص المحلي المسبق في orchestrator. FraudAgent لا ينتج نصًا احتياطيًا خاصًا به.

---

## 16. هل FraudAgent يستطيع تغيير القرار؟ — **لا** (VERIFIED)

المسار الفعلي:
```
Models → Risk Engine → Final Decision → [FraudAgent → Explanation فقط]
```
FraudAgent يعمل **بعد** القرار، ولا يُعيد سوى نص تفسيري. لا يوجد أي مسار يكتب فيه إلى `decision` أو `score`.

---

## 17. End-to-End Transaction Flow (مطابق للكود)

```
Webhook POST /wallet/webhook (HMAC verified)
  → Idempotency (cached?)
  → FeatureExtractor.extract (PostgreSQL)
  → Rules.evaluate
  → ML.score (GB 0.70 + Iso 0.30)   [أو None إن heuristic]
  → Graph.score
  → AML.screen        (fail-closed)
  → _behavior_score
  → weighted fusion (policy weights, renorm by health)
  → risk_score (0..1)
  → _decide(score, aml_hit, policy)  → ALLOW/CHALLENGE/REVIEW/BLOCK
  → persist Decision + audit + EventBus
  → [final ≥ AI_MIN_SCORE and AI_ENABLED] FraudAgent.analyze → reasoning_ar
```
**VERIFIED**.

---

## 18. Current Status — ملخص التحقق

| البند | الحالة |
|-------|--------|
| عدد نماذج ML المدربة | **2** — VERIFIED |
| GB مدرّب ويُحمَّل | VERIFIED |
| IsoForest مدرّب ويُحمَّل | VERIFIED |
| Features (20) وترتيبها | VERIFIED |
| مصدر البيانات اصطناعي | VERIFIED |
| وجود ملف CSV حاليًا على القرص | UNKNOWN |
| Metrics (1.0) | VERIFIED لكن على بيانات اصطناعية — لا تعكس الإنتاج |
| Confusion matrix / PR-AUC | NOT FOUND |
| تقييم IsoForest | NOT FOUND |
| Data-leakage check | NOT FOUND |
| أوزان 0.35/0.25/0.15/0.15/0.10 كنص ثابت | PARTIALLY VERIFIED (من policy/settings، تُعاد تطبيعها) |
| FraudAgent يغيّر القرار | VERIFIED أنه **لا** |
| Redaction لبيانات OpenRouter | NOT FOUND |

---

## 19. الملفات المهمة (لأي مطور جديد)

| الملف | الدور |
|-------|-------|
| `backend/app/ml/ensemble.py` | تحميل النموذجين + fusion + heuristic fallback |
| `backend/app/features.py` | استخراج الـ features وبناء الـ vector (الترتيب حرج) |
| `backend/app/services/orchestrator.py` | تدفق القرار الكامل + `_decide` + استدعاء FraudAgent |
| `backend/app/services/policy_engine.py` | حل سياسة المؤسسة + thresholds + أوزان |
| `backend/app/agents/fraud_agent.py` | توليد التفسير عبر LLM (لا قرار) |
| `backend/app/agents/openrouter.py` | عميل OpenRouter (مفاتيح/timeout/fallback) |
| `training/generate_dataset.py` | توليد البيانات الاصطناعية |
| `training/train_models.py` | التدريب والحفظ + metrics |
| `training/evaluate_models.py` | طباعة الـ metrics المحفوظة |
| `models/trained/*.joblib` + `metadata.json` | النماذج والوصف |
| `models/synthetic_fraud_dataset.csv` | بيانات التدريب (تحقق من وجودها) |

---

## 20. ما نحتاجه قبل إعادة تدريب/تطوير النماذج (مبني على حالة Aegis)

1. **بيانات حقيقية أو شبه حقيقية** — الحالية اصطناعية بالكامل ومقاييسها 1.0 (مؤشر overfitting للتوزيع الاصطناعي). نحتاج: حجم أكبر، توزيع labels واقعي، وتوثيق تعريف «fraud».
2. **فصل Train/Validation/Test** — حاليًا train/test فقط.
3. **معالجة class imbalance** — لا توجد حاليًا (فكّر في class_weight أو resampling).
4. **فحص data leakage** — ميزات مثل `suspicious_events_30d` و`previous_chargebacks` قد تتسرب من الـ label؛ يلزم تدقيق زمني (features قبل الحدث فقط).
5. **Confusion matrix + PR-AUC** — غير محسوبة حاليًا؛ ضرورية للاحتيال (cost-sensitive).
6. **تقييم منفصل لـ IsoForest** — حاليًا لا يُقيَّم إطلاقًا.
7. **ضبط معادلة تحويل IsoForest** (`(0.5−raw)*1.2+0.5`) — اختيارية وغير مبرَّرة؛ تحتاج معايرة (مثل isotonic/Platt).
8. **Model versioning** — الإصدار = تاريخ فقط؛ يلزم versioning دلالي + توقيع النماذج.
9. **الحفاظ على ترتيب الـ 20 features** — أي تغيير في `features.vector()` يكسر التوافق مع النماذج المحفوظة.
10. **عدم تغيير أوزان fusion (0.70/0.30) أو Risk Engine دون فهم التأثير** على thresholds والقرارات.
11. **معيار قبول نموذج جديد**: مقارنة PR-AUC/recall عند عتبات القرار الفعلية على test set حقيقي، مع canary قبل الإنتاج.
12. **معالجة redaction** قبل أي استخدام فعلي لـ OpenRouter مع بيانات حقيقية.

---

## 21. المخاطر/الفجوات قبل إعادة التدريب

* الاعتماد على metrics = 1.0 مضلل (بيانات اصطناعية سهلة الفصل).
* غياب leakage-check وvalidation-set قد يعطي ثقة زائفة.
* IsoForest غير مُقيَّم — لا نعرف مساهمته الحقيقية.
* heuristic fallback موسوم جيدًا لكن يجب التأكد أن الإنتاج لا يعمل عليه صامتًا.
* بيانات حساسة قد تُرسَل لـ OpenRouter دون إخفاء.

---

*أُعدّ هذا التقرير بفحص الكود والملفات الفعلية في المستودع دون أي تعديل. الحالات غير المؤكدة موسومة صراحة.*

---
---

# ═══════════════════════════════════════════
# الجزء الثالث — INDEPENDENT FULL-SYSTEM AUDIT
# ═══════════════════════════════════════════

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
