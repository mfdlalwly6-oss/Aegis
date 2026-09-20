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
