# AEGIS — Global Research, Yemen Validation & Final Development Blueprint
# دراسة AEGIS المرحلة الثانية: البحث العالمي + الواقع اليمني + مخطط التطوير النهائي

> **التاريخ:** 2026-09-18 · **الحالة المدروسة:** HEAD `462ed87` — **لا تعديل كود/DB/config/models، لا commit، لا push**
> **انضباط الأدلة:** [DOC] موثق من مصدر أولي (مصنّع المنصة نفسه) · [INFERENCE] استنتاج هندسي مني · [CODE] من كود AEGIS الفعلي · [RESEARCH] بحث عام موثق · **UNVERIFIED** لما لم يُثبت.
> هذا ملف الدراسة النهائية — يُكمل (ولا يكرر) تقرير التدقيق الداخلي السابق.

---

# 1. البحث العالمي — كيف تعمل منصات Fraud الحقيقية فعليًا

## 1.1 Visa — Visa Advanced Authorization / VAAI / Visa Protect
- **[DOC]** Visa Advanced Authorization يُنتج **Real-time Risk Score** أثناء مسار الـ authorization عبر VisaNet، لمساعدة المُصدِر (issuer) على التمييز بين المعاملات السليمة والاحتيالية قبل الموافقة. VAAI Score متخصص في **enumeration/card-testing attacks**. Visa Protect = حزمة (real-time scoring + fraud management + dispute). المصدر: visa.com / visamiddleeast.com / pymnts.com.
- **[DOC]** التقييم يقع **أثناء الـ authorization** (in-line، قبل قرار المُصدِر)، ويُوسَّع لاحقًا خارج شبكة Visa (real-time payments).
- **[INFERENCE]** البيانات: تاريخ البطاقة على الشبكة كلها، الجهاز، التاجر، السرعة، السلوك. لا تفاصيل معادلة عامة.
- **ما يعنيه لـ AEGIS:** النموذج الصحيح هو **in-line scoring قبل القرار** — وهو ما يفعله AEGIS فعليًا (webhook متزامن يرجع قرارًا). [CODE: webhook.py متزامن]

## 1.2 Mastercard — Decision Intelligence / Decision Intelligence Pro
- **[DOC]** DI = «transaction risk monitoring… prevent fraud and approve genuine transactions in real time»؛ الدرجة تُسلَّم **عبر authorization stream**؛ «single transaction decision score to increase approval rates and reduce declines». المصدر: mastercard.com / developer.mastercard.com.
- **[DOC]** Decision Intelligence Pro (2024) = Gen-AI يقيّم **العلاقات بين كيانات متعددة** (entity relationships) على «one trillion data points». المصدر: mastercard.com press.
- **ما يعنيه لـ AEGIS:** تأكيد أن (أ) درجة واحدة مدمجة، (ب) entity-relationship (≈ Graph في AEGIS)، (ج) real-time — **كلها موجودة في AEGIS بالفعل**. [CODE: fusion + graph]

## 1.3 Stripe — Radar
- **[DOC]** Radar = ML على بيانات شبكة Stripe + **قواعد يدوية قابلة للتخصيص** («Radar for Fraud Teams: Rules 101» — أكثر من 100 قاعدة، مع **backtesting** للقواعد). دروس Stripe الهندسية: «Never stop searching for new ML features». المصدر: stripe.com/radar + stripe.dev/blog.
- **ما يعنيه لـ AEGIS:** النمط الحاكم = **ML + قواعد مخصصة لكل تاجر + backtesting للقواعد**. AEGIS لديه ML+rules لكن **يفتقد backtesting للقواعد** (GAP). [CODE: rules بدون backtest]

## 1.4 Adyen — Protect (سابقًا RevenueProtect)
- **[DOC]** risk engine = **machine learning على بيانات Adyen العالمية + manual risk checks**؛ «Create, **backtest**, and label custom rules with a rule builder». المصدر: docs.adyen.com.
- **ما يعنيه لـ AEGIS:** تأكيد ثانٍ على **backtesting القواعد** كمعيار صناعي، وعلى دمج بيانات شبكة عالمية (AEGIS يعمل على مستأجر واحد — لا network data).

## 1.5 Sift
- **[DOC]** منصة تغطي «the entire customer journey» (ليس الدفع فقط: account takeover, content, dispute) بـ large-scale ML يكتشف أنماطًا جديدة تلقائيًا + **workflow backtesting at scale**. المصدر: sift.com + cloud.google.com blog.
- **ما يعنيه لـ AEGIS:** backtesting + journey-wide. AEGIS يركز على المعاملة فقط (نطاق أضيق — مقبول لبداية).

## 1.6 Featurespace — ARIC / Adaptive Behavioral Analytics
- **[DOC]** ARIC™ = real-time ML يراقب **السلوك الفردي** (Adaptive Behavioral Analytics) لكشف هجمات جديدة وقت حدوثها؛ يستخدم **Recurrent Neural Network / Deep Behavioral Networks** لكشف scams وATO وcard fraud. المصدر: featurespace.com / about-fraud.com.
- **ما يعنيه لـ AEGIS:** النموذج السلوكي المعياري = **per-entity behavioral profiling متكيّف** (تسلسلي)، لا مجرد 3 إشارات ثابتة. AEGIS لديه Behavior بدائي (3 إشارات) — **فجوة نوعية**. [CODE: _behavior_score]

## 1.7 FICO — Falcon Fraud Manager
- **[DOC]** Falcon = real-time، «millisecond response times»، **adaptive analytics** تتعلم في الوقت الفعلي، Falcon Intelligence Network (نماذج تستفيد من أنماط الاحتيال على مستوى الشبكة + profiling فردي)، ونموذج Scam Detection (كشف +50% scam). المصدر: fico.com.
- **ما يعنيه لـ AEGIS:** adaptive learning + network-level intelligence هما المعيار المؤسسي — AEGIS بدون إعادة تدريب تلقائية ولا drift monitoring (GAP).

## 1.8 3D Secure 2 (EMV 3DS)
- **[DOC]** 3DS2 = **frictionless flow** عندما تكون المخاطرة منخفضة (لا تدخل من حامل البطاقة) و**challenge flow** (SCA/2FA) عند ارتفاعها؛ يدعم SCA؛ القرار للمُصدِر بناءً على تقييم المخاطرة. المصدر: emvco.com + developer.visa.com (Visa Secure using EMV 3DS).
- **ما يعنيه لـ AEGIS:** CHALLENGE في AEGIS = النظير المفاهيمي لـ challenge flow في 3DS — أي قرار AEGIS «CHALLENGE» يجب أن يقود المؤسسة لطلب 3DS challenge.

## 1.9 خلاصة المقارنة العالمية (موثق)
| القدرة | Visa | Mastercard | Stripe | Adyen | Sift | Featurespace | FICO | AEGIS |
|---|---|---|---|---|---|---|---|---|
| Real-time in-line score | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ [CODE] |
| ML | ✅ | ✅(GenAI) | ✅ | ✅ | ✅ | ✅(RNN) | ✅(adaptive) | ⚠️ اصطناعي |
| Rules مخصصة | ⚪ | ⚪ | ✅+backtest | ✅+backtest | ✅ | ⚪ | ⚪ | ✅ (لا backtest) |
| Behavioral | ⚪ | ⚪ | ⚪ | ⚪ | ✅ | ✅✅ | ✅ | ⚠️ بدائي |
| Graph/Entity | ⚪ | ✅(Pro) | ⚪ | ⚪ | ✅ | ⚪ | ⚪ | ✅ [CODE] |
| Drift/retrain | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅(adaptive) | ❌ |
| Chargeback feedback | ✅ | ✅ | ✅ | ✅ | ✅ | ⚪ | ✅ | ❌ |
(✅ موثق · ⚪ غير مؤكد من المصدر العام · ⚠️ جزئي · ❌ غائب)

---

# 2. دراسة Payment/Card Fraud — مسار معاملة Visa/Mastercard

## 2.1 المسار المعياري [RESEARCH]
```
Cardholder → Merchant → PSP/Acquirer → Card Network (Visa/Mastercard)
→ Issuer → Authorization → (لاحقًا) Clearing → Settlement
```
التقييم الاحتيالي يمكن أن يحدث في: التاجر (merchant-side)، الـ PSP/Acquirer، الشبكة، أو المُصدِر (issuer-side).

## 2.2 أين يدخل AEGIS؟ (تحليل كل سيناريو)
| الموضع | الوصف | ملاءمة AEGIS | القرار |
|---|---|---|---|
| **Merchant-side** | قبل إرسال للـ PSP | AEGIS حاليًا webhook عام — يمكن لكنه ليس متخصص بطاقات | ممكن لاحقًا |
| **PSP/Acquirer** | قبل الشبكة | AEGIS يقيّم قبل التوجيه | ممكن |
| **Issuer-side** | أثناء authorization | **الأنسب لسياق اليمن** — البنك المُصدِر يقيّم قبل الموافقة | **الأنسب** |
| **Wallet/Transfer** | تحويلات/محافظ | **موضع AEGIS الحالي الفعلي** | **الحالي** |
**[INFERENCE]** AEGIS ليس مرتبطًا بشبكة بطاقات؛ تصميمه (webhook متزامن + قرار) يجعله **issuer-side/PSP-side risk engine** لمعاملات غير مرتبطة بـ scheme مباشرة (محافظ، تحويلات، حسابات)، ويمكن تكييفه كطبقة ما قبل الـ authorization للبطاقات.

## 2.3 Lifecycle واقعي لمعاملة Card وموضع AEGIS
```
1 transaction received      ← AEGIS webhook (normalize)
2 authentication context    ← (3DS/OTP من المُصدِر — خارج AEGIS)
3 3DS context إن وجد        ← يُمرَّر كـ metadata لـ AEGIS
4 normalization             ← AEGIS
5 enrichment (FX/device/geo)← AEGIS (features)
6 risk evaluation           ← AEGIS (rules/ml/graph/aml/behavior)
7 fraud scoring             ← AEGIS (fusion)
8 policy decision           ← AEGIS (policy+guards)
9 challenge/review/block    ← قرار AEGIS
10 authorization interaction← المؤسسة (تنفّذ قرار AEGIS)
11 transaction outcome      ← المؤسسة
12 post-transaction monitoring← AEGIS (graph feed + history)
13 dispute/chargeback       ← المؤسسة → **GAP: لا قناة راجعة لـ AEGIS**
14 feedback                 ← **GAP: لا feedback loop**
15 model/rule improvement   ← **GAP: لا retraining**
```

---

# 3. Agent ليس Fraud Model — الفصل الحاسم

| المكوّن | الطبيعة | في AEGIS | يقرر؟ |
|---|---|---|---|
| Deterministic rules | حتمي، قابل للتدقيق | ✅ RuleEngine | لا (يرفع score) |
| Statistical ML | إحصائي، مدرَّب | ✅ GB | لا |
| Anomaly detection | شذوذ، غير معايَر | ✅ IsoForest | لا |
| Behavioral analytics | سلوكي | ⚠️ بدائي (3 إشارات) | لا |
| Graph intelligence | علاقات | ✅ GraphEngine | لا |
| AML | إلزامي قانوني | ✅ AMLService | جزئيًا (guard) |
| Policy engine | عتبات/حدود | ✅ PolicyEngine | يوجّه |
| Decision engine | يحوّل score→action | ✅ orchestrator._decide | **نعم** |
| **LLM/Agent** | **غير حتمي، توليدي** | ✅ FraudAgent | **يجب ألّا يقرر** |

**الإجابة الصريحة عن دور الـ Agent في AEGIS:**
- يقرر fraud؟ **لا — ممنوع.**
- يفسّر القرار؟ **نعم (دوره الحالي الصحيح).** [CODE]
- يجمع الأدلة؟ يُسمح (قراءة فقط).
- يحقق في Case؟ **نعم — مساعد تحقيق.**
- يقترح إجراء؟ **نعم — كاقتراح يتطلب موافقة بشرية.**
- يساعد Investigator؟ **نعم — copilot.**
- ينفّذ workflow؟ **لا — ممنوع ذاتيًا.**
- يتعامل مع customer challenge؟ **لا — ممنوع (حساسية).**

**ما يُمنع على الـ Agent** (حتى يبقى النظام حتميًا قابلًا للتدقيق): تعديل أي score أو decision · الكتابة إلى DB · تنفيذ إجراء مالي · الوصول لبيانات خارج نطاق المهمة · اتخاذ قرار نهائي · أي تأثير على المسار الحتمي للقرار. **القاعدة: LLM خارج المسار الحتمي للقرار دائمًا.**

---

# 4. سيناريو Visa Card كامل — Trace موثق على نموذج قرار AEGIS

**المدخلات الافتراضية** (HYPOTHETICAL — تُطبَّق على منطق AEGIS الموثق): بطاقة Visa، شراء أونلاين 250 USD، جهاز جديد، IP جديد، دولة مختلفة عن المعتاد، تاجر جديد، 4 محاولات خلال 5 دقائق، 3DS غير موجود.

**Trace على منطق AEGIS الفعلي [CODE]:**
- **Features:** amount=250، first_seen_today=1 (جهاز جديد)، new_beneficiary=1 (تاجر جديد)، tx_per_min/velocity مرتفعة (4 محاولات/5 دقائق)، geo مختلف.
- **Rules المحتملة:** R-DEV-001 (جهاز جديد + مبلغ >1000؟ — 250<1000 فلا) · R-VEL-001/002 (velocity) · R-ATO إن تطابقت. (القواعد المالية بالدولار تتجاوز 250 USD → قد لا تشتعل القواعد الكبرى).
- **ML:** ⚠️ مبلغ 250 USD داخل توزيع التدريب لكن GB مدرّب اصطناعيًا — الناتج غير موثوق إنتاجيًا (Finding من التدقيق).
- **Behavior:** إن لم تُرسل المؤسسة بيانات سلوكية → degraded (F-06: يدخل بصفر).
- **AML:** فحص قوائم — غالبًا لا hit.
- **Fusion + Policy (wallet profile: 0.35/0.60/0.80).**
- **القرار (مشتق من المنطق الموثق، لا مختار مسبقًا):** مع device جديد + velocity مرتفعة + geo شاذ، الـ rule_score المرجّح ≈0.30–0.55 (R-VEL + R-DEV) ⇒ final يقع غالبًا في نطاق **CHALLENGE** (0.35–0.60) — **يُترجم إلى طلب 3DS challenge من المؤسسة**. إن اشتعلت ATO/critical (0.55–0.60) قد يصل REVIEW.
- **من ينفّذ:** المؤسسة (تطلب 3DS / توقف / تراجع) — AEGIS يقرّر فقط.
- **ما يرجع للمؤسسة:** decision + risk_score + confidence + top_reasons + component_health.
- **بعد authorization:** المعاملة تُغذّي graph + التاريخ (post-transaction monitoring).
- **لو اتضح بعد يوم أنه Fraud:** ⚠️ **GAP** — لا توجد قناة راجعة (chargeback/dispute) لإعادة تغذية AEGIS ووضع label للنموذج. **[ADD — P1]**

---

# 5. دراسة اليمن المؤسسية (بحث موثق + حدود التحقق)

**مصادر رسمية:** CBY أصدر **Circular No. 11 (2014)** لتنظيم خدمات النقود الإلكترونية عبر الموبايل [DOC: findevgateway/sanaacenter]؛ CBY أصدر تعميمًا **يحظر التعامل مع محافظ/خدمات دفع غير مرخّصة** [DOC: english.cby-ye.com/news/181]؛ القانون المصرفي اليمني **لا يعترف حتى 2024 بالنقود الإلكترونية** [DOC: Sana'a Center 2024]؛ البنك المركزي في عدن ينظم البنوك وشركات الصرافة، والإطار التنظيمي قديم ولا توجد لوائح AML/CFT خاصة بالبنوك الإسلامية [DOC: World Bank 2024]؛ انقسام CBY صنعاء/عدن؛ قانون AML/CFT يوجب STR لكن الامتثال منخفض عمليًا [DOC: State Dept]؛ FATF يونيو 2025: اليمن عالج خطته تقنيًا [DOC].

## تحليل لكل فئة (مصنّف: قانوني مثبت / أفضل ممارسة / افتراض هندسي)
| الفئة | المعاملات | البيانات المتاحة | غير متاح غالبًا | مخاطر رئيسية | ملاءمة AEGIS |
|---|---|---|---|---|---|
| **البنوك** | حوالات، حسابات، بطاقات محدودة | حسابات، KYC، تاريخ | جهاز/سلوك رقمي أحيانًا | ATO، structuring، insider | عالية (issuer-side) |
| **شركات الصرافة** | حوالات نقدية، صرف عملات | مرسل/مستفيد، فرع/وكيل، مبلغ/عملة | device/IP، سلوك رقمي | cash، velocity عبر فروع، mule | عالية (FX موجود) |
| **وكلاء الحوالات** | cash-in/out | هوية عميل، وكيل، موقع | رقمية ضعيفة | agent abuse، structuring | متوسطة |
| **المحافظ الإلكترونية** | P2P، cash-in/out، مدفوعات | جهاز/SIM، KYC، تاريخ | — (بيانات غنية) | ATO، SIM-swap، mule، velocity | **الأعلى** |
| **PSP/بوابات الدفع** | مدفوعات تجار | جهاز/IP/سلوك | يعتمد على التاجر | card-not-present، bot | عالية |
| **التجارة الإلكترونية** | مشتريات أونلاين | جهاز/IP/سلوك/سلة | محدودة في اليمن | CNP fraud | ناشئة |
| **التحويلات/الحوالات** | cross-border remittance | مرسل/مستفيد/ممر | — | sanctions، structuring، unusual remittance | عالية |
**التصنيف:** اعتراف قانوني بالنقود الإلكترونية = **UNVERIFIED/متطلب قانوني يحتاج تأكيدًا**؛ بقية التحليل = **أفضل ممارسة/استنتاج هندسي** مبني على المصادر أعلاه.

---

# 6. Integration Architecture لكل مؤسسة (مبنية على webhook AEGIS الموجود)

العقد الموحّد الموجود [CODE webhook.py]: POST + `x-api-key` + `x-wallet-signature` (HMAC-SHA256 على الجسم الخام) + JSON `{transaction, context}` + `X-Idempotency-Key` + `request_id`.

| العنصر | Bank | Exchange | Wallet | PSP | Merchant |
|---|---|---|---|---|---|
| Inbound API | webhook | webhook | webhook | webhook | webhook |
| Auth/Sign | HMAC+key | HMAC+key | HMAC+key | HMAC+key | HMAC+key |
| Required fields | amount,currency,sender,beneficiary | + فرع/وكيل | + device/SIM | + merchant | + order |
| Device/IP/Geo | اختياري | نادرًا | **متوفر** | متوفر | متوفر |
| FX | AEGIS tiers | AEGIS + institution rate | AEGIS | AEGIS | AEGIS |
| Timeout مقترح | 5s | 5s | 3s | 3s | 5s |
| Retry | بنفس idempotency key | ← | ← | ← | ← |
| AEGIS unavailable | سياسة مؤسسية موثقة (fail-open/closed) — **ADD توثيق** | ← | ← | ← | ← |
| Feedback (fraud/legit) | **GAP — ADD endpoint** | ← | ← | ← | ← |

---

# 7. Canonical AEGIS Transaction Model (مقترح — غير منفَّذ)

الحالي يفترض تحويلًا واحدًا (sender→beneficiary، amount، currency). المقترح (لا يُنفَّذ الآن):
**حقول مشتركة:** tx_id, tenant_id, timestamp, amount, currency, rail, sender, beneficiary, device, geo, metadata.
**حقول لكل rail:** card_payment(pan_token, mcc, 3ds_result, pos_entry) · bank_transfer(iban/account, purpose) · wallet_transfer(wallet_id, msisdn) · cash(agent_id, branch) · remittance(corridor, payout_method) · merchant_payment(order_id, cart) · top_up/withdrawal/payout(direction, channel).
**[INFERENCE]** — يتطلب schema موسّعًا + migration. **ADD — P2.**

---

# 8. مراجعة ML بناءً على البحث العالمي (مرتبطة ببيانات AEGIS المتوفرة)

| السؤال | الحكم المبني على البحث + AEGIS |
|---|---|
| features تبقى | shared_device_count, tx_per_min, amount_5m, seconds_since_pw (الأقوى فعليًا — TESTED) |
| features ناقصة | velocity عبر حسابات (cross-account)، تاريخ chargeback، 3ds_result، geo-distance فعلي (محسوب داخليًا)، وقت منذ إنشاء الحساب، تكرار المستفيد |
| features غير موثوقة | الذاتية من metadata (impossible_travel, previous_*) — تُشتق داخليًا أو تُوزن بثقة |
| features تُشتق داخليًا | impossible_travel (من geo+ts)، velocity من DB (موجود جزئيًا) |
| بيانات التدريب | معاملات حقيقية + labels من dispute/chargeback/قرارات محققين |
| label definition | `fraud_confirmed` من case outcome — **يتطلب feedback loop** |
| fraud taxonomy | انظر §9 |
| class imbalance | وزن فئات/oversampling (fraud نادر ~1%) |
| leakage | features قبل لحظة القرار فقط (temporal guard) |
| split | **temporal split** (تدريب على الأقدم، اختبار على الأحدث) لا عشوائي |
| calibration | isotonic/Platt على validation |
| metrics | PR-AUC + FPR/FNR + recall@fixed-FPR (لا accuracy) |
| threshold | يُشتق من cost FP vs FN لكل مؤسسة |
| monitoring | score-drift (PSI) + feature-drift + recall عند توفر labels |
| drift detection | PSI/KS دوري على features والـ score |
| retraining | دوري مجدول + عند drift |
| champion/challenger | نموذج جديد shadow مقابل الحالي قبل التبديل |
| rollback | الاحتفاظ بالنموذج السابق + version في كل قرار (موجود جزئيًا: model_version) |
| النموذج الأفضل | **لا يُفترض** — مع بيانات جدولية قليلة: GB/logistic كافٍ؛ RNN (Featurespace-style) مبالغ الآن |

---

# 9. Fraud Taxonomy المرتبطة بـ AEGIS rails

| Fraud Type | Signals | Features/Rules | ML | Graph | Behavior | Action | Data مطلوبة | Feedback label |
|---|---|---|---|---|---|---|---|---|
| Account Takeover | جهاز جديد+pw تغيّر+مستفيد جديد | R-ATO-001/002 | ✅ | ✅ | ✅ | CHALLENGE/BLOCK | device, auth events | case outcome |
| Card Testing | declines كثيرة+مبالغ صغيرة | R-CT-001 | ✅ | ⚪ | ⚪ | BLOCK | decline history | dispute |
| Velocity Attack | عمليات/دقيقة عالية | R-VEL-001/002 | ✅ | ⚪ | ⚪ | CHALLENGE | velocity | case |
| Mule Activity | جهاز/IP مشترك عبر حسابات | R-DEV-005/006 | ⚪ | ✅✅ | ⚪ | REVIEW | graph | case |
| Structuring | مبالغ <10000 متكررة | R-AML-001 + AML | ⚪ | ⚪ | ⚪ | REVIEW | history | AML review |
| Social Engineering/Scam | session طويل+مستفيد جديد | R-SE-001 | ⚪ | ⚪ | ✅ | CHALLENGE | behavior | case |
| Device Compromise | emulator/rooted/TOR | R-DEV-002/003 | ⚪ | ⚪ | ⚪ | BLOCK | device attestation | case |
| Unusual Remittance | ممر/مبلغ شاذ | AML geo | ✅ | ✅ | ⚪ | REVIEW | corridor history | AML |
| Insider/Agent Abuse | وكيل بأنماط شاذة | (ناقص) | ⚪ | ✅ | ⚪ | REVIEW | agent_id | audit |
(⚪ = محدود/غير مؤكد · ✅ = مناسب · ✅✅ = الأنسب)

---

# 10. Agent Architecture لـ AEGIS (تصميم — غير منفَّذ)

```
Investigator Copilot Agent (قراءة فقط + اقتراح)
  → tools: [get_transaction, get_decision_trace, get_graph_context, get_aml_evidence, get_similar_cases]
  → data access: read-only scoped by tenant
  → context: case + transaction + risk evidence + investigator
  → allowed: explain, summarize, gather evidence, recommend action
  → prohibited: change score/decision, write DB, execute, contact customer
  → human approval: إلزامي لأي إجراء
  → audit: كل استدعاء يُسجَّل في audit chain
```
**هل Agents منفصلة أم واحد؟** **Agent واحد بأدوار/أدوار مختلفة (tools)** — أبسط وأكثر قابلية للتدقيق. نحتاج فعليًا: **Investigator Copilot** (أولوية) + **Case Summarization** (ثانوي). لا نحتاج الآن: Alert Triage منفصل، Rule Recommendation، Customer-facing Agent. **LLM خارج المسار الحتمي دائمًا.**

---

# 11. LLM Security (architecture آمنة)

- **Redaction/tokenization** لكل PII/PCI قبل الإرسال (F-07 — P0). · **Data minimization:** أرسل الحقول اللازمة للتفسير فقط، لا `json.dumps(tx)` الكامل. · **Prompt injection:** عزل محتوى المعاملة كبيانات لا تعليمات؛ output يُعامل كنص لا أوامر. · **External provider:** تعطيل افتراضي إنتاجيًا (`AI_ENABLED=false`) أو self-hosted. · **Logging/retention:** لا تُسجَّل الحمولة الكاملة؛ سياسة retention للمزود موثقة. · **Tool permissions:** read-only scoped. · **Auditability:** كل prompt/response موسوم ومرتبط بـ case.

---

# 12. Global Best-Practice Gap Matrix

| Capability | Global | AEGIS | Gap | Type | Required? | Priority | Proposed Impl |
|---|---|---|---|---|---|---|---|
| Real-time in-line score | ✅ | ✅ | لا | — | — | — | — |
| Production-trained ML | ✅ | ❌ اصطناعي | تدريب حقيقي | Validation Gap | **ضروري** | **P0** | retrain + temporal split |
| Iso calibration | ✅ | ❌ | انحياز | Defect | ضروري | P0 | isotonic |
| Feedback loop (dispute→label) | ✅ | ❌ | غائب | Missing | **ضروري** | **P1** | feedback endpoint + label |
| Rule backtesting | ✅(Stripe/Adyen) | ❌ | غائب | Missing | مفيد | P2 | backtest harness |
| Drift monitoring | ✅ | ❌ | غائب | Missing | مفيد | P2 | PSI/KS job |
| Adaptive behavioral profile | ✅(Featurespace) | ⚠️ 3 إشارات | نوعي | Enhancement | مفيد لاحقًا | P3 | sequence model لاحقًا |
| Chargeback integration | ✅ | ❌ | غائب | Integration | ضروري (بطاقات) | P1 | feedback endpoint |
| Champion/challenger | ✅ | ❌ | غائب | Missing | مفيد | P2 | shadow deploy |
| Entity/Graph | ✅(MC Pro) | ✅ | لا | — | — | — | KEEP |
| 3DS/SCA context | ✅ | ❌ | غائب | Integration | ضروري (بطاقات) | P2 | قبول 3ds_result كـ metadata |
| Redaction لـ LLM | ✅ | ❌ | أمني | Security | ضروري | **P0** | redaction layer |
| Canary/rollback للنموذج | ✅ | ⚠️ جزئي | جزئي | Enhancement | مفيد | P2 | versioned rollback |

---

# 13. ماذا نعيد بناءه؟ (القائمة النهائية المرتبطة بالأدلة)

**REBUILD**
- تدريب ML على بيانات حقيقية + temporal split + calibration (دليل: AEGIS اصطناعي[TESTED] + معيار عالمي للإنتاج).

**REDESIGN**
- Feature vector: amount_usd بدل الخام + إسقاط/إحياء الميزات الميتة + اشتقاق داخلي للذاتية (دليل: AEGIS[TESTED OOD=0.0] + Featurespace).
- Behavior: per-entity profile بدل 3 إشارات ثابتة (دليل: Featurespace ARIC) — لاحقًا.

**ADD**
- Feedback loop (dispute/chargeback/case → label) (دليل: عالمي + غياب في AEGIS).
- Redaction للـ LLM (دليل: F-07 أمني).
- Rule backtesting (دليل: Stripe/Adyen).
- Drift monitoring + champion/challenger (دليل: عالمي).
- قبول 3ds_result/card context (دليل: 3DS2).
- توثيق سلوك AEGIS-unavailable في عقد التكامل (دليل: سيناريو §18 في التدقيق).

**KEEP**
- العزل، guards، idempotency، fusion، audit chain، traceability، FX tiers (دليل: CODE+TEST سليمة).

**DO NOT BUILD NOW**
- Graph database خارجي · RNN/Deep behavioral · multi-agent معقد · self-hosted LLM · customer-facing agent (دليل: الحجم الحالي لا يبرر الكلفة/التعقيد — INFERENCE).

---

# 14. AEGIS FINAL DEVELOPMENT BLUEPRINT

1. **Target Architecture:** Monolith حالي + feedback pipeline + (Redis/graph مستمر عند التوسع فقط).
2. **Fraud Architecture:** rules + ML(مدرّب) + graph + AML + behavior + fusion + guards (KEEP) + feedback loop (ADD).
3. **ML Architecture:** temporal split + calibration + drift + champion/challenger + rollback.
4. **Agent Architecture:** Investigator Copilot واحد read-only + human approval + audit (خارج المسار الحتمي).
5. **Payment/Card Architecture:** AEGIS كـ issuer/PSP-side pre-authorization risk engine + 3DS context.
6. **Yemen Integration:** webhook موحّد + HMAC لكل فئة (بنك/صرافة/محفظة/PSP/تاجر) + FX tiers.
7. **Data Model changes:** + canonical rail fields، + feedback/label، + payload_hash، + applied_weights_json.
8. **API changes:** + feedback endpoint، + backtest endpoint، توثيق error/unavailable.
9. **Security changes:** redaction، SSRF لـ watchlist، توقيع النماذج، TLS نشر.
10. **Monitoring:** drift (PSI/KS)، score distribution، decision rates، component health (موجود).
11. **Feedback Loop:** dispute/case outcome → label → retrain dataset.
12. **Model Governance:** versioning (موجود) + champion/challenger + rollback + signed artifacts.
13. **Case Management:** KEEP + ربط outcome بالـ label.
14. **Integration Contract:** موحّد (موجود) + feedback + unavailable semantics.
15. **Testing Strategy:** KEEP الحالي + load + property-based + backtest + feedback tests.
16. **Deployment Strategy:** feature flags + shadow للنموذج الجديد + canary.
17. **Migration Strategy:** تدريجي، النماذج تتعايش بالإصدار، policy versions immutable (موجود).
18. **Prioritized Backlog:** P0(ML retrain, Iso calib, redaction, TLS) → P1(feedback loop, behavior-missing, risk_sensitivity, payload_hash, AML-down/انهيار شامل guard) → P2(backtest, drift, champion, 3DS context, SSRF-watchlist) → P3(canonical rails, sequence behavior, retention).

---

# 15. الخلاصة الخماسية

**AEGIS CURRENT STATE:** بنية قرار سليمة (rules+ml+graph+aml+behavior+fusion+guards+audit) لكن ML مدرّب اصطناعيًا، Iso منحاز، لا feedback loop، لا drift، لا backtesting، LLM بلا redaction.

**GLOBAL STATE OF THE ART:** real-time in-line scoring، ML مدرّب على بيانات إنتاجية + adaptive/behavioral، entity graph، rules مع backtesting، feedback من chargeback، drift + champion/challenger + rollback — كلها موثقة من Visa/Mastercard/Stripe/Adyen/Sift/Featurespace/FICO.

**YEMEN REALITY:** سوق نقدي/وكيلي، محافظ موبايل نشطة، انقسام مصرفي، إطار تنظيمي قديم (النقود الإلكترونية UNVERIFIED قانونيًا)، امتثال AML منخفض عمليًا، FX متعدد — يناسبه AEGIS كطبقة قرار خفيفة issuer/PSP-side.

**TARGET AEGIS:** نفس البنية + ML مدرّب على بيانات حقيقية معايرة + feedback loop + drift + backtesting + redaction + 3DS context + canonical multi-rail model.

**DEVELOPMENT DELTA (مرتب):** P0: إعادة تدريب+معايرة+redaction+TLS · P1: feedback loop + behavior-missing + payload_hash + انهيار-شامل guard + 3DS · P2: backtest + drift + champion/challenger + SSRF-watchlist + توقيع نماذج · P3: canonical rails + sequence behavioral + retention.

> **لم يُنفَّذ أي تعديل — الدراسة اكتملت قبل أي تطوير. HEAD `462ed87` سليم.**
