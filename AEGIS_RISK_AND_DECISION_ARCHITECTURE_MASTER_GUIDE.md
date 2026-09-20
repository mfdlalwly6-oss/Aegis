# AEGIS Risk & Decision Architecture — Master Guide
# دليل AEGIS المرجعي الشامل لبنية المخاطر والقرار

> **طبيعة هذا الدليل**: تحقيق هندسي مبني على فحص الكود الفعلي الحالي في المستودع (HEAD = `462ed87`).
> لم يتم تعديل أي كود، ولا إعادة تدريب، ولا تغيير Config/Policy/Rules/Database، ولا Commit، ولا Push.
> **وسوم التحقق المستخدمة في كل سطر تقريبًا**:
> `CODE DOES` (مثبت من الكود بمرجع ملف وسطر) · `CONFIG SAYS` (من ملف الإعدادات) · `POLICY SAYS` (من محرك السياسات) · `TEST PROVES` (مثبت باختبار موجود) · `DOC SAYS` (في التوثيق فقط) · `BINARY MODEL` (داخل joblib — لا يمكن تفكيكه من المصدر) · **«غير مثبت في الكود الذي تم فحصه»**.

---

# PART A — AEGIS Introduction (من الصفر)

## A.1 ما هو AEGIS؟

AEGIS منصة **كشف احتيال مالي متعددة المستأجرين (multi-tenant fraud detection)**. تستقبل معاملة مالية (Transaction) من بنك أو محفظة إلكترونية عبر Webhook، تحسب لها **درجة مخاطرة (Risk Score)** بين 0 و1، ثم تُصدر **قرارًا (Decision)** واحدًا من أربعة: `ALLOW` / `CHALLENGE` / `REVIEW` / `BLOCK`، وتخزّن كل شيء للتدقيق.

**النقطة التقنية**: التطبيق مكتوب بـ Python/FastAPI، وقاعدة البيانات PostgreSQL (مع طبقة تغليف `app/db.py` — لاحظ أن استعلامات `decision_repo.py` تستخدم `?` كـ placeholder وتُحوَّل داخليًا؛ «SQLite-style placeholders converted by the DB wrapper»).

## A.2 المشكلة التي يحلّها

معاملة واحدة قد تبدو طبيعية من زاوية (مبلغ معقول) وخطيرة من زاوية أخرى (جهاز مشترك بين 5 حسابات + مستفيد جديد + دولة عالية المخاطر). لا توجد قاعدة واحدة تكفي، لذلك AEGIS يجمع **5 محركات تقييم مستقلة** ثم يدمجها.

## A.3 الفروق الجوهرية (اقرأها قبل أي شيء)

| المفهوم | المعنى في AEGIS | من ينتجه |
|---------|------------------|-----------|
| **Fraud Detection** | الهدف العام: اكتشاف الاحتيال | المنظومة كلها |
| **Risk Scoring** | الوسيلة: رقم 0..1 يقيس الخطر | Risk Fusion في `orchestrator.py` |
| **Component Score** | درجة محرك واحد (rules/ml/graph/aml/behavior) | كل محرك على حدة |
| **Risk Score** | الدمج الموزون النهائي (`final`) | `orchestrator.py` السطر 235 |
| **Decision** | فعل: ALLOW/CHALLENGE/REVIEW/BLOCK | `orchestrator._decide` + Guards |

**لماذا أكثر من طريقة تقييم؟** لأن كل محرك يرى نمطًا مختلفًا: القواعد حتمية ومفهومة، ML يلتقط أنماطًا غير خطية، الـ Graph يرى العلاقات، AML إلزامي قانونيًا، والسلوك يرى «من» ينفذ لا «ماذا» ينفذ.

## A.4 المعمارية العليا — الترتيب الفعلي المُصحَّح من الكود

⚠️ الترتيب في السؤال التمهيدي كان تقريبيًا. **CODE DOES** (من `webhook.py` + `orchestrator.py`):

```
POST /api/v1/webhook/wallet/webhook
  1. Auth: x-api-key + HMAC-SHA256 على الجسم الخام      [webhook.py:186-223]
  2. Replay guard على timestamp (>5min مستقبل / >72h قديم → 422)  [webhook.py:231-249]
  3. Tenant suspended → 403 hard block                  [webhook.py:252-262]
  4. JSON parse → 400 عند الفشل                         [webhook.py:264-267]
  5. Normalization → Transaction schema                 [webhook.py:23-155]
  6. FX resolution (_apply_fx)                          [webhook.py:158-180]
  7. Idempotency check                                  [orchestrator.py:137-150]
  8. Feature Extraction (PostgreSQL)                    [orchestrator.py:153]
  9. Rules → rule_score                                 [orchestrator.py:161-170]
 10. ML (GB+Iso) → ml_prob                              [orchestrator.py:172-184]
 11. Graph → graph_sig                                  [orchestrator.py:186-193]
 12. AML → aml_sig                                      [orchestrator.py:195-205]
 13. Behavior → behavior_score                          [orchestrator.py:207-214]
 14. Fusion (availability-aware weighted) → final       [orchestrator.py:216-235]
 15. Guards (sanctions/watchlist/AML-down/FX-missing)   [orchestrator.py:266-300]
 16. Decision via thresholds                            [orchestrator.py:298 → _decide]
 17. Top reasons                                        [orchestrator.py:303-312]
 18. FraudAgent explanation (بعد القرار، لا يغيّره)      [orchestrator.py:314-331]
 19. Persist transaction + decision                     [orchestrator.py:387-411]
 20. graph.add_transaction (لتغذية المستقبل)             [orchestrator.py:414]
 21. Alert + Case للقرارات المرتفعة                      [orchestrator.py:416-442]
 22. Audit log                                          [orchestrator.py:444-463]
 23. Notifications + EventBus publish                   [orchestrator.py:465-471]
```

ملاحظة مهمة: **FX يحدث في الـ webhook قبل الـ orchestrator** (وليس بين Features وRules كما في الرسم التمهيدي). و**Idempotency يسبق Feature Extraction**.

---

# PART B — Glossary (قاموس المصطلحات)

| المصطلح | التعريف التقني في AEGIS |
|---------|--------------------------|
| **Transaction** | كائن pydantic `Transaction` (`schemas.py:97`) — معاملة مالية: مبلغ، عملة، مرسل، مستفيد، جهاز، سلوك، metadata |
| **Feature** | قيمة محسوبة من المعاملة أو تاريخها (مثال: `shared_device_count`) — قاموس في `features.extract()` |
| **Feature Vector** | قائمة 20 رقمًا بترتيب ثابت حرج تُمرَّر للنموذجين — `features.vector()` |
| **Rule** | تعريف شرطي (JSONLogic) في `rules` table / `default_ruleset.yaml` — له `id, severity, score, when` |
| **Rule Condition** | تعبير `when` مثل `{">": [{"var": "features.velocity.tx_per_min_card"}, 6]}` |
| **RuleHit** | نتيجة تحقق قاعدة: `rule_id, severity, score_contribution, reason` (`schemas.py:155`) |
| **Rule Score** | `min(1.0, Σ score_contribution)` — `orchestrator.py:164` |
| **Signal** | حزمة نتائج محرك: `GraphSignal` / `AMLSignal` (`schemas.py:179,190`) |
| **Model** | نموذج sklearn محفوظ joblib (GB أو IsoForest) |
| **Model Output** | `gb_prob` = `predict_proba(X)[0][1]`؛ `iso_raw` = `decision_function(X)[0]` |
| **Probability** | قيمة 0..1 ذات معنى احتمالي (GB فقط) |
| **Anomaly Score** | `iso_prob` — درجة شذوذ محوَّلة خطيًا، **ليست احتمال احتيال** |
| **ML Score** | `0.70×gb_prob + 0.30×iso_prob` — `ensemble.py:115` |
| **Weight** | رقم نسبي لمحرك في الدمج — من Policy (افتراضيًا من Config) |
| **Fusion** | الدمج الموزون مع إعادة التطبيع حسب صحة المكونات — `orchestrator.py:216-235` |
| **Threshold** | عتبة تحويل score→قرار (challenge/review/block) — من Policy |
| **Policy** | دمج: settings defaults ← institution profile ← tenant `policy_json` — `policy_engine.resolve()` |
| **Guard** | قاعدة إلزامية تتجاوز الـ score (sanctions→BLOCK...) — `orchestrator.py:266-300` |
| **Override** | تعديل tenant-specific لقاعدة (`rule_overrides` table) يستبدل قاعدة المنصة بنفس الـ id |
| **Degraded** | قرار أُنتج وأحد المكونات ليس healthy — يُوسم في `degraded_mode` |
| **Fallback** | سلوك بديل عند فشل شيء (heuristic ML، fail-closed AML...) |
| **Explanation** | نص `reasoning_ar` عربي — محلي من `top_reasons` أو من FraudAgent |
| **Audit** | سجل في جدول audit عبر `audit.log(...)` |

**السلسلة الحرجة** (الفرق الذي طُلب توضيحه):
`Feature` (مدخل خام محسوب) → `Rule` (شرط على Features) → `RuleHit` (قاعدة تحققت) → `Rule Score` (مجموع المساهمات) → `Model` (تعلم إحصائي) → `Model Output` (خام) → `ML Score` (دمج النموذجين) → `Component Score` (درجة أي محرك) → `Risk Score` (دمج المكونات الخمسة) → `Decision` (عتبات + Guards). **كل سهم تحويل مختلف — لا تخلط بينها.**

---

# PART C — System Architecture

**Wiring** (من `registry.py`): عند الإقلاع تُبنى بالترتيب: repositories → `currency_repo.seed_defaults()` → `rule_repo.seed_defaults(spec.rules)` → `watchlist_repo.seed_defaults()` → `RuleEngine(all_rules)` → `EnsembleScorer()` → `GraphEngine()` + `bootstrap(recent_txs)` → `AMLService` → `FeatureExtractor` → `DecisionOrchestrator`.

المكونات الخمسة المُقيِّمة + البنية:
- **Rules**: `rules/engine.py` (RuleEngine, Rule, evaluate)
- **ML**: `ml/ensemble.py` (EnsembleScorer)
- **Graph**: `graph/engine.py` (GraphEngine — NetworkX MultiDiGraph)
- **AML**: `aml/service.py` (AMLService + `aml/matching.py`)
- **Behavior**: داخل `orchestrator._behavior_score`
- **Policy**: `services/policy_engine.py` (PolicyEngine)
- **FX**: `services/fx_service.py` (FxService)
- **Features**: `features.py` (FeatureExtractor)
- **Explanation**: `agents/fraud_agent.py` + `agents/openrouter.py`

---

# PART D — Transaction Lifecycle الكامل

لكل مرحلة: **الملف → الدالة → المدخل → المخرج → يدخل الحساب؟ → يُخزَّن؟ → الفشل؟**

| # | المرحلة | File:Function | Input → Output | يدخل القرار؟ | يُخزَّن؟ | عند الفشل |
|---|---------|---------------|-----------------|---------------|----------|-----------|
| 1 | Auth | `webhook.fraud_webhook` | headers(api_key, sig) → tenant row | لا (بوابة) | audit عند الفشل | 401 |
| 2 | Replay guard | نفسه | timestamp → pass/fail | لا | لا | 422 |
| 3 | Tenant status | نفسه | tenant.status | لا | audit | 403 `tenant_suspended` |
| 4 | Normalize | `webhook.normalize_transaction` | body → `Transaction` | نعم (كل شيء لاحق) | `transactions.raw_json` | 400 (amount مفقود/غير رقمي/≤0) |
| 5 | FX | `webhook._apply_fx` → `fx.normalize` | amount+currency → `Money` + `FxSnapshot` | نعم (عبر amount_usd + fx_missing guard) | `transactions.reference_*`, `decisions.fx_proof_json` | عملة معطّلة → 422؛ مفقودة → REVIEW/BLOCK per policy |
| 6 | Idempotency | `orchestrator:137-150` | idempotency_key → cached? | يمنع إعادة الحساب | `decisions.idempotency_key` | duplicate → إرجاع المخزّن |
| 7 | Features | `features.extract` | tx + DB → dict | نعم | `transactions.features_json`, `decisions.features_snapshot_json` | (داخل try المكونات) |
| 8 | Rules | `rules.evaluate` | tx+features → `list[RuleHit]` | نعم | `decisions.rules_json` | component unavailable |
| 9 | ML | `ensemble.score` | vector(20) → (ml_prob, reports) | نعم | `decisions.ml_json`, `ml_score` | ml_prob=None، unavailable |
| 10 | Graph | `graph.score` | tx → `GraphSignal` | نعم | `decisions.graph_json`, `graph_score` | GraphSignal() فارغ، unavailable |
| 11 | AML | `aml.screen` | tx+features → `AMLSignal` | نعم + guards | `decisions.aml_json`, `aml_score` | **fail-closed → REVIEW** |
| 12 | Behavior | `orch._behavior_score` | tx.behavior → float | نعم | `decisions.behavior_score` | 0.0، unavailable |
| 13 | Fusion | `orch:216-235` | comp_scores+weights → `final` | **هو** الـ Risk Score | `decisions.risk_score` | — |
| 14 | Guards | `orch:266-300` | signals+policy → أرضيات/تجاوزات | نعم | `degraded_reason` | — |
| 15 | Decision | `orch._decide` | final+aml_hit+thresholds → Decision | — | `decisions.decision` | — |
| 16 | Reasons | `orch:303-312` | hits+signals → top_reasons | لا (شرح) | `decisions.top_reasons_json` | نص افتراضي عربي |
| 17 | AI explanation | `fraud_agent.analyze` | tx+rules_hits+ml_prob → reasoning_ar | **لا يغيّر القرار** | `decisions.reasoning_ar`, `ai_model` | يبقى النص المحلي |
| 18 | Persist | `tx_repo.create`, `decision_repo.create` | rows | — | جدولا transactions/decisions | — |
| 19 | Graph feed | `graph.add_transaction` | tx | (للمعاملات القادمة) | graph in-memory | — |
| 20 | Alert/Case | `alerts.create`, `cases.create` | decision مرتفع | لا | alerts/cases tables | — |
| 21 | Audit | `audit.log` | أحداث | لا | audit table | — |
| 22 | Notify/Events | `notifications.notify`, `events.publish` | alert+assessment | لا | — | best-effort (يُبتلع الخطأ) |

---

# PART E — Features (من الصفر)

**ما هي Feature؟** قيمة رقمية/منطقية تُحسب من المعاملة أو من تاريخها في PostgreSQL قبل التقييم.

**CODE DOES** (`features.py:21-112`): `extract()` ينفّذ استعلامات حقيقية: `tx_repo.velocity` (60/300/3600 ثانية)، `shared_device_accounts`، `shared_ip_accounts`، `known_beneficiary`، `structuring_count`، `dec_repo.count_by_tenant`. ثم يبني قاموسًا متداخلًا. `amount_usd` يأتي من `tx.reference_amount` (FX سبق تطبيقه في webhook)، مع fallback للمبلغ الخام عند غيابه (`features.py:51-52`).

## E.1 جدول الـ 20 Feature — الترتيب الفعلي الحرفي من `vector()` (features.py:114-137)

⚠️ الترتيب **حرج**: `generate_dataset.py:23` ينص «field order MUST match features.FeatureExtractor.vector() output order». **CODE DOES**: الترتيب في `vector()` مطابق لترتيب `FIELDS` في `generate_dataset.py:15-22` و`metadata.json.features`.

| # | vector name (training) | code source | المعنى | Default عند الغياب |
|---|------------------------|-------------|--------|---------------------|
| 0 | `amount` | `tx.amount` | المبلغ بالعملة الأصلية | — (إلزامي، amount>0) |
| 1 | `hour_sin` | `features.py:58` | sin دوري للساعة | ساعة الآن إن غاب timestamp |
| 2 | `hour_cos` | `features.py:59` | cos دوري للساعة | كذلك |
| 3 | `tx_per_min` | `velocity.tx_per_min_card` | عدد عمليات المرسل/60s (DB) | 0 |
| 4 | `amount_5m` | `velocity.amount_5min_account` | مجموع مبالغ/300s (بالعملة المرجعية) | 0 |
| 5 | `distinct_merchants_1h` | `meta.distinct_merchants_1h` | تنوع التجار (من metadata) | 0 |
| 6 | `new_device` | `device.first_seen_today` | جهاز لم يستخدمه هذا المرسل من قبل (DB) | False |
| 7 | `shared_device_count` | `device.shared_device_count` | حسابات تشارك الجهاز (DB) | 0 |
| 8 | `shared_ip_count` | `device.shared_ip_count` | حسابات تشارك IP (DB) | 0 |
| 9 | `impossible_travel` | `meta.impossible_travel` | سفر مستحيل (من metadata) | False |
| 10 | `high_risk_country` | `meta.fatf_high_risk` | دولة عالية المخاطر (metadata) | False |
| 11 | `new_beneficiary` | `beneficiary.new` = `not known_benef` | مستفيد جديد (DB) | True إن لم يُعرف |
| 12 | `seconds_since_password_change` | `meta.seconds_since_password_change` | زمن آخر تغيير كلمة مرور | **999999** |
| 13 | `previous_declines` | `meta.previous_declines` | رفوض سابقة | 0 |
| 14 | `previous_chargebacks` | `meta.previous_chargebacks` | chargebacks سابقة | 0 |
| 15 | `high_risk_merchant` | `tx.metadata.high_risk_merchant` | تاجر عالي المخاطر | False |
| 16 | `off_hours` | `tx.timestamp.hour<6 or >22` | خارج ساعات العمل | False |
| 17 | `round_amount` | `amount_flags.is_round_1000` | مبلغ مدوّر ≥1000 | محسوب |
| 18 | `structuring_pattern` | `velocity.count_9k_10k_30d > 2` | نمط structuring (DB) | False |
| 19 | `suspicious_events_30d` | `history.suspicious_events_30d` | block+review السابقة للـ tenant (DB) | 0 |

**لا يوجد scaling ولا encoding ولا normalization** — القيم خام كـ float (`ensemble.py:69` يحوّل فقط إلى np.float32). CODE DOES.
**حقول تُستخرج لكنها لا تدخل الـ vector**: `amount_usd`, `currency`, `vpn`, `tor`, `proxy`, `emulator`, `rooted`, `account_age_days`, `mfa_recently_disabled`, `offshore`, `ip_country`, `tx_count_5min/1h`, `amount_1h`, `card_declines_1h`, `billing_country` — تخدم Rules/AML فقط. CODE DOES.

**هل للـ Feature وزن ثابت داخل ML؟** الأوزان داخل أشجار GB/IsoForest = **BINARY MODEL** — غير قابلة للتفكيك من المصدر. ما يمكن إثباته فقط: لا توجد أوزان features يدوية في كود الاستدلال.

---

# PART F — Rules Engine بالتفصيل

**العدد الفعلي**: 21 قاعدة في `default_ruleset.yaml` (`grep -c "id:" = 21`) و21 صفًا حيًا في جدول `rules` (فُحص من الحاوية). ⚠️ تقارير سابقة ذكرت «22» — **CODE/DB SAYS: 21**.

## F.1 بنية القاعدة

`Rule` (`engine.py:115-132`): `id, name, severity(low/medium/high/critical → RiskBand), score (default 0.2), enabled (default True), when (JSONLogic), tags, tenant_id (None=منصة), currency`.

## F.2 القواعد الـ 21 (من قاعدة البيانات الحية + YAML)

| id | الاسم | severity | score | الشرط (من YAML) |
|----|-------|----------|-------|------------------|
| R-VEL-001 | High transaction velocity | high | 0.35 | tx_per_min_card > 6 |
| R-VEL-002 | High amount in 5 minutes | high | 0.30 | amount_5min_account > 5000 USD |
| R-VEL-003 | Merchant diversity anomaly | medium | 0.15 | distinct_merchants_1h > 8 |
| R-GEO-001 | Impossible travel | critical | 0.55 | geo.impossible_travel == true |
| R-GEO-002 | FATF high-risk jurisdiction | high | 0.30 | geo.fatf_high_risk == true |
| R-DEV-001 | New device with high amount | high | 0.35 | first_seen_today AND amount_usd>1000 |
| R-DEV-002 | Emulator or rooted device | critical | 0.60 | emulator OR rooted |
| R-DEV-003 | TOR exit node | high | 0.40 | tx.device.tor == true |
| R-DEV-004 | VPN + high-value + new beneficiary | high | 0.35 | vpn AND amount_usd>500 AND beneficiary.new |
| R-DEV-005 | Shared device across accounts | high | 0.30 | shared_device_count > 1 |
| R-DEV-006 | Shared IP across accounts | medium | 0.20 | shared_ip_count > 2 |
| R-BEH-001 | Behavioral biometric mismatch | high | 0.40 | biometric_match_score < 0.4 |
| R-BEH-002 | Robotic keystroke entropy | medium | 0.25 | keystroke_entropy < 1.2 |
| R-ATO-001 | Password change before transfer | critical | 0.55 | seconds_since_pw<600 AND amount_usd>1000 |
| R-ATO-002 | MFA disabled + new beneficiary | critical | 0.60 | (YAML — تفصيل الشرط في الملف) |
| R-AML-001 | Structuring below threshold | high | 0.35 | (YAML) |
| R-AML-002 | Rapid pass-through | high | 0.40 | (YAML) |
| R-AML-003 | Round amount to offshore | medium | 0.20 | (YAML) |
| R-CT-001 | Card testing pattern | high | 0.35 | (YAML) |
| R-NEW-001 | New account high-value first tx | high | 0.40 | (YAML) |
| R-SE-001 | Coached call pattern | high | 0.35 | (YAML) |

## F.3 المعادلة الفعلية — مثبتة

**CODE DOES** (`orchestrator.py:164`):
```
rule_score = min(1.0, Σ hit.score_contribution)
```
- `score_contribution = rule.score` (`engine.py:161`) — ثابت لكل قاعدة.
- **severity لا تدخل المعادلة** — تُستخدم فقط في Guard (أرضية CHALLENGE عند high + behavior غير healthy، `orchestrator.py:276-280`) وفي severity التنبيه.
- **لا priority، لا normalization، cap = 1.0.**
- **Deduplication**: `by_id` dict (`engine.py:195-200`) — قاعدة المنصة تُستبدل بـ override المستأجر بنفس الـ id؛ **لا يمكن أن تتحقق قاعدة بنفس id مرتين**. قواعد المستأجرين الآخرين لا تُقيَّم أصلًا.
- **هل قاعدة تُصدر BLOCK مباشرة؟** لا. القواعد ترفع score فقط؛ التأثير المباشر الوحيد: أرضية CHALLENGE عبر severity=high (الشرط أعلاه). القواعد المحمية `PROTECTED_RULES = {R-AML-001, R-AML-002, R-AML-003, R-GEO-002}` لا يمكن لأي مستأجر تعطيلها (`policy_engine.py:28,126-135`).
- **قاعدة تحيل إلى حقل None → لا تتحقق** (False، `engine.py:83-84`) — ليست خطأ.

**أمثلة حسابية**:
- قاعدة واحدة R-VEL-001: `min(1, 0.35) = 0.35`
- قاعدتان (0.35+0.55): `0.90`
- خمس قواعد (0.35+0.30+0.55+0.40+0.35): `min(1, 1.95) = 1.00` ← الـ cap يعمل
- كل الـ 21: المجموع ≈ 6.85 → **1.00**

**TEST PROVES**: `test_rule_overrides.py`: override يستبدل قاعدة المنصة لذلك المستأجر فقط؛ التعطيل يوقف الإطلاق لذلك المستأجر؛ الحذف يستعيد قاعدة المنصة.

---

# PART G — Gradient Boosting (من الصفر)

| العنصر | القيمة | الدليل |
|--------|--------|--------|
| Class | `sklearn.ensemble.GradientBoostingClassifier(random_state=42)` | `train_models.py:37` |
| Hyperparameters مخصصة | **لا شيء** — بقية المعلمات افتراضيات sklearn | CODE DOES |
| التدريب | `gb.fit(X_train, y_train)` | `train_models.py:38` |
| البيانات | `models/synthetic_fraud_dataset.csv` — **اصطناعية بالكامل** (3500 سليمة + 1500 احتيالية، seed=42) | `generate_dataset.py:81-84` |
| ⚠️ وجود CSV في الريبو | **غير موجود حاليًا** — يُولَّد بالسكربت | `CSV_NOT_PRESENT_IN_REPO` |
| Label | `int(fraud)` — 1=احتيال، 0=سليم | `generate_dataset.py:73` |
| Split | `train_test_split(test_size=0.2, random_state=42, stratify=y)` — **لا validation set** | `train_models.py:34-35` |
| الاستدلال | `gb_prob = float(self._gb.predict_proba(X)[0][1])` | `ensemble.py:82` |
| Calibration/Scaling/Clamp على gb_prob | **لا يوجد أيٌّ منها** (الـ clamp الوحيد على الناتج المدمج النهائي) | CODE DOES |

**ما معنى `gb_prob = 0.72`؟** تقدير النموذج لـ P(fraud=1 | الـ20 feature). **كيف وصل بالضبط إلى 0.72؟** الحساب داخل أشجار القرار المتعاقبة في joblib = **BINARY MODEL** — لا يمكن إعادة بناؤه من المصدر؛ يمكن فقط إعادة تشغيله.

**Metrics المخزّنة** (`metadata.json`): accuracy/precision/recall/roc_auc = **1.0** — محسوبة على الـ test split **الاصطناعي** فقط؛ ليست دليل أداء إنتاجي. Confusion matrix وPR-AUC: **غير مثبت في الكود الذي تم فحصه**.

---

# PART H — Isolation Forest (من الصفر)

| العنصر | القيمة | الدليل |
|--------|--------|--------|
| Class | `IsolationForest(random_state=42, contamination=0.18)` | `train_models.py:42` |
| supervised؟ | **لا** — `iso.fit(X_train)` بدون labels | CODE DOES |
| ما الذي يتعلمه؟ | شكل التوزيع «الطبيعي» للبيانات؛ يعزل النقاط الشاذة بأشجار عشوائية | (مفهوم sklearn؛ التطبيق في binary) |
| الاستدلال | `iso_raw = float(self._iso.decision_function(X)[0])` | `ensemble.py:99` |
| التحويل | `iso_prob = max(0.0, min(1.0, (0.5 - iso_raw) * 1.2 + 0.5))` | **`ensemble.py:100` — CODE DOES، المعادلة المذكورة في السؤال صحيحة حرفيًا** |
| Evaluation مستقل / calibration | **غير مثبت في الكود الذي تم فحصه** — لا يوجد أي تقييم للـ IsoForest ولا معايرة للمعادلة | NOT FOUND |

**لماذا `iso_prob` ليست احتمال احتيال مثل GB؟** لأنها تحويل خطي يدوي (0.5 مركز، ميل 1.2، ثم clamp) لدرجة شذوذ unsupervised — اختيار هندسي غير مبرَّر في الكود. **مثال**: `iso_raw = -0.083` → `iso_prob = (0.5+0.083)×1.2+0.5 = 1.1996 → 1.0` (clamped). و`iso_raw = 0.2` → `(0.3)×1.2+0.5 = 0.86`.

---

# PART I — ML Ensemble

**CODE DOES** (`ensemble.py:75-116`):
1. النموذجان يعملان **تسلسليًا** (GB ثم Iso) على **نفس الـ vector** — ليس بالتوازي.
2. `fused = gb_prob * 0.70 + iso_prob * 0.30` — **الأوزان 0.70/0.30 مثبتة حرفيًا في السطر 115**.
3. الناتج: `round(min(1.0, max(0.0, fused)), 4)`.

**مثال**: GB=0.72، Iso=0.40 → `0.504 + 0.120 = 0.624` → `ml_prob = 0.624`.

⚠️ **فصل حاسم**: وزن GB=0.70 **داخل الـ ML ensemble** شيء، ووزن ML=0.25 **داخل Risk Fusion** شيء آخر تمامًا. طبقتان مختلفتان من الأوزان.

---

# PART J — Graph Engine

**CODE DOES** (`graph/engine.py`): رسم NetworkX `MultiDiGraph` في الذاكرة. العقد مُسمّاة بنطاق المستأجر: `t:{tenant}|{kind}:{id}` (`engine.py:43-44`) — الأنواع: `acct`, `tx`, `device`, `ip`. الحواف: `sends`, `to`, `uses`, `from`. **لا حواف بين مستأجرين** → العزل بنيوي.

**المعادلة الفعلية** (`engine.py:136-138`):
```
score = min(1.0, shared_dev×0.15 + shared_ip×0.10 + max(0, linked−5)×0.04)
if hops_to_known_fraud ≤ 2: score = min(1.0, score + 0.30)
```
حيث: `shared_dev` = حسابات أخرى تشارك الجهاز (داخل المستأجر)، `shared_ip` مثلها، `linked` = عدد المستفيدين المميزين للمرسل، `hops` = أقصر مسار (رسم غير موجّه) لأي حساب موسوم `mark_fraud` داخل نفس المستأجر.

**مثال رقمي**: جهاز مشترك مع 3 حسابات، IP مشترك مع حسابين، 8 مستفيدين، hops=2:
`min(1, 3×0.15 + 2×0.10 + 3×0.04) = 0.77` → `+0.30` → `min(1, 1.07) = 1.00` — الأسباب: `shared_device_3, shared_ip_2, linked_accounts_8, within_2_hops_of_fraud`.

**TEST PROVES** (من `tests/arena_tests` سابقًا): `shared_device` لا يُحسب عبر المستأجرين، ويُحسب داخل نفس المستأجر، و`mark_fraud` محصور بالمستأجر.

---

# PART K — AML (من الصفر)

**CODE DOES** (`aml/service.py` — `screen()`):
1. **الدول** (`_screen_countries`): بلد المستفيد (أو ip_country) → sanctions list: `sanctions_hit=True` و`+0.60`؛ high_risk_country: `fatf_high_risk_country=True` و`+0.20`.
2. **الأسماء** (`_screen_names`): fuzzy matching (عتبة 0.87) على sender/beneficiary/customer/merchant ضد: sanctions `+0.60×match_score`، pep `+0.35×score`، custom `+0.25×score`. sanctions name → `sanctions_hit=True`.
3. **الحسابات** (`_screen_accounts`): مطابقة **تامة** لمعرّفات المرسل/المستفيد → sanctions: `sanctions_hit=True` و`+0.60`؛ custom: `watchlist_account_hit=True` و`+0.30`.
4. **Typologies**: structuring (9000≤amount<10000 وcount_9k_10k_30d≥2) `+0.30`؛ rapid_movement (≥8 عمليات/ساعة ومجموع>20000) `+0.25`؛ round_amount+offshore `+0.15`؛ tor/vpn مع amount>5000 `+0.10`.
5. **`signal.score = min(1.0, score)`** — cap فقط.

**الفرق الحاسم**: `aml_score` يدخل الـ Fusion كمكوّن (وزنه الافتراضي 0.15). أما `sanctions_hit` و`watchlist_account_hit` فهما **Guards** تعمل خارج الـ score (PART R). كل hit يُسجَّل بأدلة point-in-time في `watchlist_evidence` → تُخزَّن في `decisions.aml_json`.

**TEST PROVES**: `test_decision_engine.py:46-48` — `_decide(0.0, True) == BLOCK` (sanctions تجبر BLOCK حتى عند score=0).

---

# PART L — Behavior

**CODE DOES** (`orchestrator.py:90-103`):
```
score = 0
if biometric_match_score < 0.4:   score += 0.45
if keystroke_entropy < 1.2:       score += 0.20
if session_duration_ms > 600000:  score += 0.15
return min(score, 1.0)
```
- **لا behavior payload → `0.0`** لكن health = `"degraded"` (ليس unavailable!) — `orchestrator.py:210`. وهذا يعني: **score=0 يدخل الـ Fusion بوزنه الكامل** — المكوّن «نشِط» بقيمة صفر، ولا يُعاد توزيع وزنه. (فرق مهم عن ML-unavailable.)
- signal واحد: 0.45 · اثنان: 0.65 · ثلاثة: 0.80 · cap=1.0.
- نفس الإشارات تظهر أيضًا كقواعد R-BEH-001/002 — أي **ازدواج مقصود**: Rules تراها كشروط، وBehavior يجمعها كدرجة.

---

# PART M — FX

**الأولوية الفعلية** (`fx_service.py:_lookup` — CODE DOES):
1. **Tenant FX Override** (سعر مثبّت من مالك AEGIS لهذا المستأجر) — يفوز دائمًا.
2. **Institution rate** (من الـ payload) — فقط إن كان «موثوقًا»: موجود، >0، وضمن ميزانية الانحراف (`FX_INSTITUTION_TRUST_PCT` الافتراضي = `FX_DIVERGENCE_PCT×2`) من المرجع، مع مقارنة الاتجاهين.
3. **Reference FX Group** المعيّن للمستأجر (USD/YER وSAR/YER).
4. **General platform rates** — الاتجاهان، يفوز الأعلى `_rank` ثم الأحدث.

ثم: **cross-rate** عبر العملة المرجعية عند غياب زوج مباشر → **stale fallback** (أحدث سعر معروف + `is_stale=True`) → **MISSING**.

**الحالات** (`FxStatus`): NATIVE (العملة = REFERENCE_CURRENCY) · OK · STALE · DIVERGENT (انحراف المؤسسة > `FX_DIVERGENCE_PCT`=3.0%) · MISSING.

**CONFIG SAYS** (`config.py`): `REFERENCE_CURRENCY=USD`, `DISPLAY_CURRENCY=YER`, `FX_STALE_HOURS=24`, `FX_DIVERGENCE_PCT=3.0`.

**أثر FX**: يدخل عبر (أ) `features.amount_usd` → قواعد العتبات المالية (R-VEL-002, R-DEV-001, R-DEV-004, R-ATO-001)؛ (ب) `fx_status=missing` → Guard إلزامي (REVIEW افتراضيًا أو BLOCK حسب `policy.fx_missing_action`)؛ (ج) **لا يدخل الـ ML vector** (الـ vector يستخدم `amount` الخام — Feature #0). القرار التاريخي **لا يتغير** بتغير السعر لاحقًا — `FxSnapshot` الكامل يُخزَّن في `fx_proof`. TEST PROVES: `test_fx.py` (native/direct/inverse/cross/unknown→missing/stale/divergent/immutable).

**مثال YER**: عملية 500,000 YER، سعر USD/YER=545 معكوسًا → `reference_amount = 500000 × (1/545) ≈ 917.43 USD`.

---

# PART N — Risk Fusion (أهم فصل)

**المعادلة الفعلية** (`orchestrator.py:219-235` — CODE DOES):
```python
policy  = self._resolve_policy(tx.tenant_id)     # PolicyEngine.resolve
weights = policy["weights"]                      # rules/ml/graph/aml/behavior
comp_scores[k] = score_k if health[k]=="healthy" else None
active = {k: v for k,v in comp_scores if v is not None}
active_weight   = Σ weights[k] for k in active
applied_weights = weights[k] / active_weight
final = min(1.0, max(0.0, Σ comp_scores[k] × applied_weights[k]))
```

**مصدر الأوزان** (CONFIG SAYS `config.py:107-111`): `WEIGHT_RULES=0.35, WEIGHT_ML=0.25, WEIGHT_GRAPH=0.15, WEIGHT_AML=0.15, WEIGHT_BEHAVIOR=0.10`. **POLICY SAYS**: المستأجر يستطيع إعادة قياس كل وزن ضمن **±25% فقط** (`WEIGHT_SCALE_BOUNDS=(0.75,1.25)`) ثم تُعاد التطبيع إلى مجموع 1.0 (`policy_engine.py:108-124`).

**مثال** (كل المكونات healthy، أوزان افتراضية): Rules=0.80, ML=0.70, Graph=0.40, AML=0.60, Behavior=0.20:
`0.80×0.35 + 0.70×0.25 + 0.40×0.15 + 0.60×0.15 + 0.20×0.10 = 0.280+0.175+0.060+0.090+0.020 = 0.625` → `final=0.625` (داخل 0..1 لأن الأوزان مجموعها 1 وكل score ≤1، مع clamp صريح).

**TEST PROVES**: `test_decision_engine.test_weights_sum_to_one` (الافتراضيات مجموعها 1)؛ `test_component_health` (إعادة التطبيع إلى 1.0 عند فقد مكوّن).

**Confidence** (`orchestrator.py:251-264`): `Σ state_factor(k) × nominal_weight(k)` حيث healthy=1.0, degraded=0.5, unavailable=0.0. **TEST PROVES**: `test_confidence.py` — كلها healthy → 1.0؛ ML down → ≈0.75؛ behavior مفقود (degraded) → ≈0.95.

⚠️ **discrepancy موثّق**: `risk_sensitivity` يُحسب ويُقيَّد (0.5–1.5) في `policy_engine.py:101-106` ويوثَّق أنه «يُطبَّق على fused score» — **لكن `orchestrator.py` لا يستخدمه إطلاقًا** (grep: NOT_APPLIED_IN_ORCHESTRATOR). **DOC SAYS: يُضرب في الدرجة. CODE DOES: لا يُطبَّق.**

---

# PART O — Component Failure / Renormalization

**المعادلة** (مثبتة في PART N): `active_weight = Σ weights(healthy)`، `applied = w/active_weight`.

**مثال ML unavailable** (الأوزان الافتراضية): active = rules+graph+aml+behavior = 0.35+0.15+0.15+0.10 = **0.75**. applied: rules=0.4667, graph=0.20, aml=0.20, behavior=0.1333. بقيم 0.80/0.40/0.60/0.20: `final = 0.3733+0.080+0.120+0.0267 = 0.60`.

**السبب الدقيق لاستبعاد ML**: `orchestrator.py:176-180` — إن `self.ml.ready == False` (ملفات joblib غير موجودة أو فشل التحميل) يُضبط `ml_prob=None` وhealth=`unavailable` **حتى لو أنتج الـ heuristic قيمة**. التعليق في الكود: «heuristic is explainable but NOT evidence — do not score it». **أي: heuristic لا يدخل الـ Fusion أبدًا — لا كصفر ولا كقيمة.** الاستثناءات تُلتقط بنفس النتيجة (unavailable).

**`degraded_mode = any(status != "healthy")`** — يشمل behavior-missing (degraded). `degraded_reason` نص مثل `"ml=unavailable; behavior=degraded"`. **TEST PROVES**: `test_component_health.test_ml_unavailable_excluded_from_score_and_flagged` (weight_applied=0.0، degraded_mode=True) و`test_aml_unavailable_fails_closed_to_review`.

---

# PART P — Policy Engine (فك الخلط)

| السؤال | الجواب المثبت |
|--------|----------------|
| من يحسب Risk Score؟ | `DecisionOrchestrator.evaluate_and_persist` (orchestrator.py:235) |
| من يقرأ Thresholds؟ | `PolicyEngine.resolve` يُنتجها؛ `orchestrator._decide`/`_band` يقرآنها |
| من يحوّل Score→Action؟ | `orchestrator._decide` (سطور 115-125) + Guards قبله |

**Risk Engine ≠ Policy Engine**: الأول في `orchestrator.py` (حساب)، الثاني في `policy_engine.py` (قراءة سياسة: thresholds, weights, disabled_rules, fx_missing_action — مدموجة من settings ← profile ← tenant policy_json، ومقيّدة بالحدود).

---

# PART Q — Thresholds

**POLICY SAYS** (`policy_engine.py:42-60`): العتبات **لكل institution profile**:

| Profile | challenge | review | block |
|---------|-----------|--------|-------|
| wallet / payment | 0.35 | 0.60 | 0.80 |
| merchant / merchant_retail | 0.40 | 0.65 | 0.85 |
| merchant_wholesale / real_estate | 0.45 | 0.70 | 0.88 |
| exchange | 0.30 | 0.55 | 0.78 |
| remittance | 0.40 | 0.65 | 0.85 |
| individual / consumer / bank | (افتراضيات settings: 0.35/0.60/0.80) | | |

**CONFIG SAYS** (`config.py:102-104`): `DECISION_THRESHOLD_CHALLENGE=0.35, REVIEW=0.60, BLOCK=0.80`. حدود الأمان: challenge∈[0.20,0.50], review∈[0.40,0.75], block∈[0.60,0.95]، وفرض الترتيب challenge+0.05 ≤ review+0.05 ≤ block.

**أمثلة (wallet)**: 0.20→ALLOW · 0.34→ALLOW · 0.35→CHALLENGE · 0.59→CHALLENGE · 0.60→REVIEW · 0.79→REVIEW · 0.80→BLOCK · 0.90→BLOCK. **TEST PROVES**: `test_decide_ladder` + `test_band_boundaries` + `test_tenant_thresholds_are_scoped_and_change_decision`.

⚠️ ملاحظة: `ML_THRESHOLD_BLOCK=0.90/REVIEW=0.65` في config.py:98-99 **لا يستخدمان في مسار القرار** (عتبتا القرار الفعليتان DECISION_THRESHOLD_*).

---

# PART R — Mandatory Guards / Overrides

**الترتيب الفعلي في الكود** (`orchestrator.py:266-300` — CODE DOES):

1. `watchlist_account_hit` (وليس sanctions) → `final = max(final, review_threshold)` — أرضية REVIEW.
2. قاعدة severity=high تحققت **و** behavior ليس healthy → `final = max(final, challenge_threshold)`.
3. **AML unavailable** → `decision = REVIEW` إجباري + أرضية review + وسم `AML_UNAVAILABLE_FAIL_CLOSED` (fail-closed).
4. **fx_missing** → policy: `block` → BLOCK+أرضية block؛ وإلا REVIEW+أرضية review. (لا يمكن أبدًا silent ALLOW — `policy_engine.py:137-142`.)
5. وإلا → `_decide(final, sanctions_hit, policy)`: **`sanctions_hit` → BLOCK فورًا مهما كان score** (سطر 117-118).
6. إن sanctions_hit وfinal < block → `final = block_threshold` (أرضية رقمية للتقرير).

**مثال**: Risk=0.20 مع sanctions_hit=true → **BLOCK**، وfinal يُرفع إلى 0.80 (wallet). مثبت بالاختبار `test_decide_sanctions_forces_block_even_at_zero_score`.

---

# PART S — Final Decision

`Decision ∈ {ALLOW, CHALLENGE, REVIEW, BLOCK}` (`schemas.py:23`). `risk_band`: LOW/MEDIUM/HIGH/CRITICAL بنفس العتبات. القرار يُنتَج في `_decide`، قد يُعدَّل بالـ Guards (R)، ثم يُخزَّن ويُبنى عليه: alert (CHALLENGE+)، case (REVIEW+)، notifications (REVIEW/BLOCK)، event `decision.created`.

---

# PART T — Persistence & Audit

**جدول `decisions`** (`decision_repo.create`): decision_id, tx_id, tenant_id, ts, decision, risk_score, risk_band, latency_ms, **rule_score, ml_score, graph_score, aml_score, behavior_score**, rules_json, ml_json, graph_json, aml_json, top_reasons_json, typology, reasoning_ar, ai_model, idempotency_key, created_at, **fx_proof_json, tx_snapshot_json, features_snapshot_json**, rule_set_version (policy_version), model_version, config_version (`aegis-config@2.2.0`), request_id, **component_health_json, degraded_mode, degraded_reason, confidence**.

**جدول `transactions`**: الحقول الأساسية + raw_json + features_json + reference_amount/currency + fx_snapshot_id + fx_status.

**Audit**: أحداث `transaction.scored`, `alert.created`, `authentication.failure`, `transaction.rejected` عبر `audit.log(tenant, actor, action, ...)`. الـ Graph يُغذَّى بكل معاملة (`add_transaction`) للتقييمات المستقبلية.

---

# PART U — FraudAgent / Explanation

**CODE DOES** (`orchestrator.py:314-331`, `fraud_agent.py`, `openrouter.py`):
- يُستدعى **بعد القرار** فقط إذا `final >= settings.AI_MIN_SCORE and settings.AI_ENABLED`.
- المدخلات: `tx.model_dump()` (≤600 حرف) + `rules_hits` (≤400 حرف) + `ml_prob` — **لا يستقبل risk_score النهائي ولا القرار**.
- المخرجات: `{"model", "typology", "reasoning_ar"}` — إن وُجد `reasoning_ar` يحل محل النص المحلي المبني من `top_reasons` (`" ؛ ".join(top_reasons[:4])`).
- **لا يستطيع تغيير القرار أو أي score — لا يوجد أي مسار كتابة منه إلى decision.** VERIFIED.
- OpenRouter: مفاتيح من env `OPENROUTER_KEYS` (مفصولة بفواصل، round-robin)، النموذج `google/gemma-2-9b-it:free` + 3 بدائل، timeout=10s، 401/429 → المفتاح «ميت» 300s.
- **بدون مفاتيح**: `{"ok": False, "error": "no_keys"}` → agent يرجع `reasoning_ar=None` → **يبقى التفسير المحلي**. الاستثناءات تُبتلع (warning فقط).
- ⚠️ أمنيًا: الـ prompt يحمل بيانات المعاملة لخدمة خارجية مع اقتطاع طول فقط — **لا redaction** (CODE DOES).

---

# PART V — WHO CALCULATES / WHO DECIDES / WHO EXECUTES

### Calculates
| القيمة | الحاسب | المرجع |
|--------|--------|--------|
| Features | `FeatureExtractor.extract/vector` | features.py |
| Rules Score | `RuleEngine.evaluate` + sum في orchestrator | engine.py / orch:164 |
| gb_prob / iso_raw | النموذجان (joblib) | ensemble.py:82,99 |
| ML Score | `EnsembleScorer._real_score` | ensemble.py:115 |
| Graph Score | `GraphEngine.score` | graph/engine.py:136 |
| AML Score | `AMLService.screen` | aml/service.py |
| Behavior Score | `orchestrator._behavior_score` | orch:90-103 |
| **Risk Score (final)** | **`orchestrator` (fusion)** | orch:235 |
| Confidence | orchestrator | orch:251-264 |

### Decides
**`orchestrator._decide` + Guards (PART R) + thresholds من `PolicyEngine.resolve`.** لا Rules ولا ML ولا Graph ولا AML ولا Behavior ولا FraudAgent يقرر منفردًا. (AML يقرر فقط عبر guard sanctions/fail-closed.)

### Executes
AEGIS **يعيد القرار في استجابة الـ Webhook** (`webhook.py:292-317`). **التنفيذ الفعلي (إيقاف/تنفيذ الحوالة) خارج AEGIS — لدى البنك/المحفظة المتصلة. تنفيذ Core-Banking غير مثبت في الكود الذي تم فحصه.**

---

# PART W — End-to-End Numerical Examples

## W.1 مثال كامل (HYPOTHETICAL INPUTS — حقائق الكود مميّزة)

**معاملة**: amount=500,000 YER، مرسل له جهاز مشترك مع حسابين، مستفيد جديد، ساعة 3 فجرًا، behavior موجود ضعيف (biometric=0.3).
- **FX (CODE)**: لو USD/YER=545 → amount_usd ≈ 917.43 USD.
- **Features (CODE)**: first_seen_today=0 (الجهاز معروف)، shared_device_count=3، new_beneficiary=1، off_hours=1...
- **Rules**: تتحقق R-DEV-005 (shared_device_count>1 → 0.30). باقي القواعد حسب القيم. **rule_score = 0.30**.
- **ML**: GB وIso = **BINARY MODEL** — لا يمكن حسابهما يدويًا؛ نفترض للمثال gb=0.40, iso=0.50 → ml = 0.28+0.15 = **0.43**.
- **Graph (CODE)**: shared_dev=3، linked=1، لا fraud hops → `min(1, 3×0.15+0+0) = 0.45`.
- **AML**: لا hits → 0.0.
- **Behavior (CODE)**: biometric 0.3<0.4 → **0.45**.
- **Fusion (CODE، افتراضية، كلها healthy)**: `0.30×0.35 + 0.43×0.25 + 0.45×0.15 + 0×0.15 + 0.45×0.10 = 0.105+0.1075+0.0675+0+0.045 = 0.325`.
- **Guards**: لا sanctions؛ behavior healthy → لا أرضية.
- **Decision (wallet)**: 0.325 < 0.35 → **ALLOW** · band=LOW.
- **Persistence**: كل الدرجات + snapshots + confidence=1.0.
- **Final Decision Owner = orchestrator._decide (مع سياسة wallet)**.

## W.2 Score منخفض + sanctions_hit
final=0.20 لكن بلد المستفيد في قائمة sanctions → Guard (R.5): **BLOCK**، final→0.80. TEST PROVES: `test_decide_sanctions_forces_block_even_at_zero_score`.

## W.3 ML unavailable
joblib مفقود → ready=False → heuristic يعمل لكن `ml_prob=None` (orch:180) → active_weight=0.75 → الأوزان المعاد تطبيعها (O) → بقيم المثال: rules 0.30×0.4667 + graph 0.45×0.20 + aml 0×0.20 + behavior 0.45×0.1333 = 0.14+0.09+0+0.06 = **0.29** → ALLOW · degraded_mode=true · degraded_reason="ml=unavailable" · confidence=0.75. TEST PROVES: test_component_health / test_confidence.

## W.4 Rule-heavy
R-GEO-001(0.55)+R-ATO-001(0.55)+R-DEV-005(0.30) → rule_score = min(1, 1.40) = **1.00** → بقية 0: final = 1.0×0.35 = 0.35 → **CHALLENGE** (wallet) — حتى بقواعد مكتملة، الوزن 0.35 يحد الأثر.

## W.5 ML-heavy
gb=0.95, iso_raw=-0.2 → iso_prob=(0.7)×1.2+0.5=1.34→**1.0** → ml=0.665+0.30=**0.965** → final(وحدها)=0.965×0.25=0.241 → مع قاعدة high واحدة (0.35): final=0.241+0.1225=0.3635 → CHALLENGE.

---

# PART X — Failure Modes

| الفشل | الاكتشاف | Fallback | أثر Score | أثر القرار | Degraded? |
|-------|----------|----------|-----------|------------|-----------|
| Model files مفقودة / load error | ready=False, log ml.models_loaded/load_error | heuristic **للشرح فقط**، ml_prob=None | وزن ML يُعاد توزيعه | قد يرتفع/ينخفض طفيفًا | نعم |
| ML raise أثناء score | try/except orch:181 | ml_prob=None | كذلك | كذلك | نعم |
| Rules raise | orch:166 | rule_score=0، unavailable | وزن rules يُوزَّع | + أرضية challenge إن high-hit سابق لا ينطبق | نعم |
| Graph raise | orch:190 | GraphSignal() فارغ، score=0، unavailable | الوزن يُوزَّع | — | نعم |
| **AML raise** | orch:201 | **fail-CLOSED: REVIEW إجباري + أرضية** | AML مستبعد | **REVIEW على الأقل** | نعم + وسم خاص |
| Behavior غائب | tx.behavior=None | score=0.0، status=**degraded** (يدخل بصفر!) | الوزن يبقى، قيمة 0 | أرضية challenge إن high rule hit | نعم |
| FX مفقود | fx_status=missing | reference=None؛ policy REVIEW (أو block) | amount_usd=raw fallback | REVIEW/BLOCK | (عبر degraded_reason لا) |
| OpenRouter فشل | r.ok=False | reasoning_ar محلي | لا أثر | لا أثر | لا |
| Policy مفقودة/تالفة | resolve(tenant=None) | defaults + clamps | — | عتبات آمنة | لا — TEST PROVES (test_missing_or_malformed_policy) |
| DB error في feature/repo | (غير ملتقط صراحة داخل extract) | يصعد كاستثناء للمكوّن المستدعي | حسب المكوّن | حسبه | حسبه |

---

# PART Y — Tests as Evidence

| الادعاء | الاختبار المثبِت |
|---------|------------------|
| سلم العتبات والقرارات | `test_decision_engine.test_decide_ladder`, `test_band_boundaries` |
| sanctions→BLOCK عند score=0 | `test_decide_sanctions_forces_block_even_at_zero_score` |
| الأوزان الافتراضية مجموعها 1 | `test_weights_sum_to_one` |
| عملة مجهولة → REVIEW لا ALLOW | `test_unknown_currency_forces_review_not_allow` |
| ML down → مستبعد + weight_applied=0 + degraded | `test_component_health.test_ml_unavailable_excluded_from_score_and_flagged` |
| AML down → fail-closed REVIEW | `test_aml_unavailable_fails_closed_to_review` |
| health يُخزَّن verbatim | `test_component_health_persists_verbatim_in_decisions_table` |
| confidence: 1.0 / 0.75 (ML down) / 0.95 (behavior missing) | `test_confidence.*` |
| عتبات المستأجر تغيّر القرار | `test_tenant_policy.test_tenant_thresholds_are_scoped_and_change_decision` |
| سياسة تالفة → defaults آمنة | `test_missing_or_malformed_policy_uses_safe_defaults` |
| override قاعدة لكل مستأجر | `test_rule_overrides.*` |
| FX (native/cross/stale/divergent/immutable) | `test_fx.*` |

---

# PART Z — DOCUMENT vs CODE vs TEST

| الموضوع | Document | Code | Test | الحالة النهائية |
|---------|----------|------|------|------------------|
| عدد القواعد | تقارير سابقة: «22» | YAML+DB: **21** | rule_engine.loaded=21 في السجلات | **21** |
| risk_sensitivity | policy_engine docstring: «مضروب في fused score» | **لا يُطبَّق في orchestrator** | لا يوجد | **غير مفعَّل — discrepancy** |
| ترتيب FX | الرسم التمهيدي: بعد Features | webhook قبل orchestrator | — | **FX قبل Features** |
| توازي النموذجين | — | تسلسلي GB ثم Iso | — | تسلسلي |
| ML heuristic | يُرجع score | لا يدخل Fusion (ml_prob=None) | test_ml_unavailable | **heuristic ≠ دليل** |
| metrics=1.0 | metadata | محسوبة على بيانات اصطناعية | — | ليست دليل إنتاج |

---

# PART AA — Mathematical Specification (المعادلات المثبتة فقط)

```
RulesScore  = min(1, Σ hit.score_contribution)                          [orch:164]
GBProb      = GradientBoostingClassifier.predict_proba(X)[0][1]         [ensemble:82]  (داخل binary)
IsoRaw      = IsolationForest.decision_function(X)[0]                   [ensemble:99]  (داخل binary)
IsoProb     = clamp((0.5 − IsoRaw) × 1.2 + 0.5, 0, 1)                   [ensemble:100]
MLScore     = clamp(0.70×GBProb + 0.30×IsoProb, 0, 1)                   [ensemble:115-116]
GraphScore  = min(1, shared_dev×0.15 + shared_ip×0.10 + max(0,linked−5)×0.04
                  + (0.30 if hops≤2 else 0))                            [graph:136-138]
AMLScore    = min(1, Σ signals)  (0.60/0.20/0.60×s/0.35×s/0.25×s/0.30/0.30/0.25/0.15/0.10)  [aml/service]
Behavior    = min(1, 0.45×[bio<0.4] + 0.20×[key<1.2] + 0.15×[sess>600000])  [orch:90-103]
ActiveWeight   = Σ w_k للمكونات healthy                                 [orch:229]
AppliedWeight_k = w_k / ActiveWeight                                    [orch:230-231]
FinalRisk   = clamp(Σ score_k × AppliedWeight_k, 0, 1)                  [orch:235]
Confidence  = clamp(Σ {healthy:1.0, degraded:0.5, unavailable:0.0}_k × w_nominal_k, 0, 1)  [orch:251-264]
Decision    = BLOCK if sanctions_hit                                    [orch:117]
              else REVIEW if aml_unavailable                            [orch:281-283]
              else per thresholds: ≥block→BLOCK, ≥review→REVIEW, ≥challenge→CHALLENGE, else ALLOW
Guards      = watchlist_account→final≥review ; high-rule+behavior↓→final≥challenge ;
              fx_missing→REVIEW|BLOCK ; sanctions→final≥block           [orch:274-300]
```

المتغيرات: w_k = أوزان policy؛ score_k = درجات المكونات؛ s = match_score للأسماء.

---

# PART AB — Number Traceability

| الرقم | المعنى | المصدر | الموقع |
|-------|--------|--------|--------|
| 0.70 / 0.30 | أوزان GB/Iso داخل ML | ثابت في الكود | `ensemble.py:115` |
| 0.35/0.25/0.15/0.15/0.10 | أوزان Fusion الافتراضية | Config | `config.py:107-111` |
| ±25% | حد إعادة قياس أوزان المستأجر | Policy | `policy_engine.py:38` |
| 0.35/0.60/0.80 | عتبات القرار الافتراضية | Config | `config.py:102-104` |
| bounds 0.20-0.50 / 0.40-0.75 / 0.60-0.95 | حدود العتبات | Policy | `policy_engine.py:31-35` |
| 0.70→GB weight ≠ 0.25→ML weight | طبقتان مختلفتان | أعلاه | — |
| 1.2 / 0.5 | ميل ومركز تحويل Iso | ثابت | `ensemble.py:100` |
| 0.15/0.10/0.04/0.30 | أوزان إشارات Graph | ثابت | `graph/engine.py:136-138` |
| 0.45/0.20/0.15 | إشارات Behavior | ثابت | `orch:98-102` |
| 0.4 / 1.2 / 600000 | عتبات Behavior | ثابت | `orch:96-101` |
| 0.60/0.20/0.35/0.25/0.30/0.25/0.15/0.10 | أوزان إشارات AML | ثابت | `aml/service.py` |
| 0.87 | عتبة fuzzy للأسماء | معامل AMLService | `aml/service.py:66` |
| 0.18 | contamination للـ Iso | تدريب | `train_models.py:42` |
| 42 | random_state | تدريب+توليد | `train_models.py`, `generate_dataset.py:13` |
| 0.2 | test_size | تدريب | `train_models.py:35` |
| 3500/1500 | أحجام البيانات | توليد | `generate_dataset.py:81-84` |
| 999999 | default seconds_since_password_change | features | `features.py:87` |
| 9000-10000, ≥2 / ≥8, >20000 / >5000 | عتبات typologies | AML | `aml/service.py` |
| 5min / 72h | حدود replay | webhook | `webhook.py:242-245` |
| 0.90/0.65 | ML_THRESHOLD_* | Config | `config.py:98-99` — **غير مستخدمة في مسار القرار** |

---

# PART AC — Complete Tables

| Component | Input | Processing | Formula | Output | Range | Fusion Weight (default) | Can Override? | Source |
|-----------|-------|------------|---------|--------|-------|--------------------------|---------------|--------|
| Rules | tx+features | JSONLogic على 21 قاعدة | min(1,Σ) | rule_score | 0..1 | 0.35 | لا (أرضية challenge فقط عبر severity) | rules/engine.py |
| ML | vector[20] | GB+Iso | 0.70·GB+0.30·Iso | ml_prob | 0..1 | 0.25 | لا | ml/ensemble.py |
| Graph | tx+in-memory graph | tenant-namespaced signals | PART AA | graph_score | 0..1 | 0.15 | لا | graph/engine.py |
| AML | tx+features+watchlists | country/name/account/typology | min(1,Σ) | aml_score | 0..1 | 0.15 | **نعم (sanctions_hit→BLOCK)** | aml/service.py |
| Behavior | tx.behavior | 3 إشارات | min(1,Σ) | behavior_score | 0..1 | 0.10 | لا | orchestrator.py |

| Stage | Produces | Used By | Stored? | Can Affect Decision? |
|-------|----------|---------|---------|----------------------|
| FX | reference_amount, FxSnapshot | features.amount_usd, guard | نعم (fx_proof) | نعم |
| Features | dict + vector[20] | Rules, ML, AML | نعم | نعم |
| Rules | hits, rule_score | Fusion, reasons, guard | نعم | نعم |
| ML | ml_prob, reports | Fusion, reasons, FraudAgent | نعم | نعم |
| Graph | GraphSignal | Fusion, reasons | نعم | نعم |
| AML | AMLSignal | Fusion, guards, typology | نعم | نعم |
| Behavior | float | Fusion, guard | نعم | نعم |
| Fusion | final | _decide | risk_score | هو القرار |
| FraudAgent | reasoning_ar | شرح فقط | نعم | **لا** |

| Model | Type | Input | Output | Training | Inference | Weight | Source |
|-------|------|-------|--------|----------|-----------|--------|--------|
| gradient_boosting | GBC (supervised) | float32[1,20] | gb_prob | train_models.py:37-38 | ensemble.py:82 | 0.70 (داخل ML) | models/trained/gradient_boosting.joblib |
| isolation_forest | IsoForest (unsupervised, cont=0.18) | float32[1,20] | iso_raw→iso_prob | train_models.py:42-43 | ensemble.py:99-100 | 0.30 (داخل ML) | models/trained/isolation_forest.joblib |

**ما لا يدخل الحساب**: `amount_usd` (Features/Rules فقط، ليس ML)، `vpn/tor/proxy` (Rules R-DEV-003/004 وAML typology فقط)، `severity` (لا تدخل rule_score)، `tags` (تنظيمية)، `risk_sensitivity` (محسوبة لكن غير مطبقة)، `ML_THRESHOLD_*` (غير مستخدمة)، FraudAgent output (شرح).

---

# PART AD — Code Reference Map

| Functionality | File | Class | Function | Variables المهمة |
|---------------|------|-------|----------|-------------------|
| Webhook/entry | api/v1/webhook.py | — | fraud_webhook, normalize_transaction, _apply_fx | idem_key |
| Pipeline | services/orchestrator.py | DecisionOrchestrator | evaluate_and_persist, _decide, _band, _behavior_score | final, health, comp_scores, applied_weights |
| Features | features.py | FeatureExtractor | extract, vector | velocity/device/geo/... |
| Rules | rules/engine.py | RuleEngine, Rule | evaluate | _OPS, by_id |
| Rules seed | rules/default_ruleset.yaml + rule_repo.seed_defaults | — | — | 21 قاعدة |
| ML | ml/ensemble.py | EnsembleScorer | score, _real_score, _heuristic_score | ready, 0.70/0.30 |
| Graph | graph/engine.py | GraphEngine | score, mark_fraud, add_transaction, bootstrap | _ns, _known_fraud |
| AML | aml/service.py | AMLService | screen, _screen_* | fuzzy_threshold=0.87 |
| Policy | services/policy_engine.py | PolicyEngine | resolve | PROFILES, THRESHOLD_BOUNDS, PROTECTED_RULES |
| FX | services/fx_service.py | FxService | normalize, _lookup, cross_rate | 4 tiers |
| Config | core/config.py | Settings | — | WEIGHT_*, DECISION_THRESHOLD_*, AI_MIN_SCORE, AI_ENABLED |
| Decision repo | repositories/decision_repo.py | DecisionRepository | create, mark_seen, get_by_idempotency | 33 عمودًا |
| Tx repo | repositories/transaction_repo.py | TransactionRepository | create, velocity, shared_* | — |
| Wiring | services/registry.py | Registry | init | rule_engine, ml_scorer, ... |
| AI | agents/fraud_agent.py, agents/openrouter.py | FraudAgent, OpenRouterClient | analyze, chat | OPENROUTER_KEYS |
| Training | training/generate_dataset.py, train_models.py, evaluate_models.py | — | main | seed 42 |
| Schemas | models/schemas.py | Transaction, RiskAssessment, AMLSignal, GraphSignal, RuleHit, ModelScore | — | — |

---

# PART AE — Manual Transaction Calculation Procedure

1. **استخرج** الحقول من الـ payload (normalize_transaction).
2. **FX**: حدّد السعر حسب tiers (override→institution→reference→general→cross→stale→missing) واحسب `amount_usd = reference_amount`.
3. **Features**: نفّذ استعلامات velocity/shared/known_benef/structuring على تاريخ المرسل **في PostgreSQL** — يدويًا هذا يتطلب الوصول للـ DB.
4. **Rules**: لكل قاعدة من الـ21 قيّم `when` → اجمع score المحترقة → `min(1, Σ)`.
5. **ML**: شغّل joblib (لا يمكن يدويًا بدون النموذج) → `0.70·gb + 0.30·iso_prob`.
6. **Graph**: من الحالة الداخلية (in-memory) — shared_dev/ip/linked/hops → المعادلة.
7. **AML**: افحص القوائم → min(1,Σ) وسجّل sanctions_hit.
8. **Behavior**: الإشارات الثلاث.
9. **Health**: حدّد أي مكوّن غير healthy → None.
10. **active_weight/applied**: PART O.
11. **final = clamp(Σ)**.
12. **Policy**: حدّد profile المستأجر → العتبات.
13. **Guards**: بالترتيب في PART R.
14. **Decision** من `_decide`.
15. **التخزين**: الجدولان + health + confidence.
16. **Explanation**: top_reasons → محلي أو FraudAgent.

⚠️ ما لا يمكن يدويًا بالكامل: gb_prob وiso_raw (binary)، حالة الـ graph في الذاكرة، نتائج fuzzy matching — تحتاج تشغيل الكود.

---

# PART AF — Known Limitations / Unknowns

**Verified limitations**:
1. النماذج مدرّبة على بيانات **اصطناعية بالكامل**؛ metrics=1.0 لا تعني أداءً إنتاجيًا (metadata.json).
2. `risk_sensitivity` محسوبة لكن **غير مطبقة** في orchestrator (discrepancy موثّق).
3. لا تقييم مستقل لـ Isolation Forest ولا معايرة لمعادلة التحويل.
4. لا confusion matrix / PR-AUC / leakage check / validation set.
5. الـ CSV التدريبي غير موجود في الريبو (يُولَّد).
6. Graph في الذاكرة — يُفقد عند إعادة التشغيل ويُعاد بناؤه من آخر المعاملات (bootstrap).
7. بيانات المعاملة تُرسل لـ OpenRouter بدون redaction (اقتطاع طول فقط).
8. behavior المفقود يدخل كصفر **بوزن كامل** (degraded لا unavailable) — خيار تصميمي موثّق.

**غير مثبت في الكود الذي تم فحصه**: سبب اختيار أوزان 0.70/0.30 و0.35/0.25/...؛ معنى أداء النماذج على بيانات حقيقية؛ تنفيذ القرار لدى core banking؛ وجود تقييم IsoForest؛ خوارزمية fuzzy التفصيلية في `aml/matching.py` (لم تُقرأ سطرًا سطرًا — استُخدمت عبر واجهتها).

**Potential future improvements (لا تعديل الآن)**: معايرة IsoProb، metrics على بيانات حقيقية، redaction قبل LLM، ربط risk_sensitivity أو حذفها من الوثيقة.

---

*أُعدّ هذا الدليل بفحص الكود الفعلي (HEAD 462ed87) دون أي تعديل أو تدريب أو commit. كل رقم موسوم بمصدره، وكل فجوة موسومة صراحة.*
