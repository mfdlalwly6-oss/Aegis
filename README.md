# 🛡️ AEGIS — Multi-Tenant Financial Fraud Detection Platform

منصة كشف احتيال مالي متعددة المستأجرين. مصممة للبنوك والمحافظ الرقمية وشركات الدفع.

> ⚠️ **AEGIS منصة كشف تقنية — ليست بديلًا عن الامتثال القانوني أو التنظيمي في أي دولة.**

---

## ما الذي تم تنفيذه فعليًا (v2.0.0)

| المكوّن | الحالة | الوصف |
|---------|--------|-------|
| Multi-Tenancy | ✅ حقيقي | قاعدة بيانات SQLite، عزل كامل، API keys + HMAC لكل مستأجر |
| Webhook آمن | ✅ حقيقي | HMAC-SHA256 + X-API-Key + Idempotency |
| Decision Pipeline | ✅ حقيقي | Features → Rules → ML → Graph → AML → Behavior → Fuse → Persist |
| Rule Engine | ✅ حقيقي | JSONLogic، 20 قاعدة افتراضية، قابلة للتوسعة لكل مستأجر |
| ML | ⚠️ Fallback | GradientBoosting + IsolationForest إذا دُرّبا؛ وإلا heuristic مُعلَن |
| Graph | ✅ حقيقي | NetworkX، اكتشاف أجهزة/IPs مشتركة، hops إلى احتيال معروف |
| AML | ✅ تقني | Watchlists من DB (sanctions/high-risk countries)، كشف structuring |
| Alerts | ✅ حقيقي | تنشأ تلقائيًا عند challenge/review/block، دورة حياة كاملة (إسناد/مراجعة/تصعيد/حل) + ملاحظات |
| Cases | ✅ حقيقي | إدارة تحقيقات: ملاحظات، حالات، تعيين، حل موثّق، ربط معاملات وتنبيهات |
| Audit Log | ✅ حقيقي | جدول منفصل في DB، يُسجَّل كل حدث مهم بدون أسرار |
| Notifications | ⚠️ Adapter | Console حاليًا، Webhook provider متاح عند الإعداد |
| Real-time | ✅ SSE | `/api/v1/admin/stream` (owner) + `/api/v1/investigator/stream` (investigator) |
| Investigator Auth | ✅ حقيقي | حسابات محققين (JWT role=investigator) تُدار من بوابة المالك، وصول محمي كامل |
| Investigator Workbench | ✅ حقيقي | لوحة محمية: قائمة مراجعة، تنبيهات، قضايا، قرارات حيّة، تحليل شبكة |
| Owner System Settings | ✅ حقيقي | صفحة إعدادات تقرأ العتبات/الأوزان الفعلية من runtime عبر `/admin/settings` |
| Rules/Models/Graph UI | ✅ حقيقي | إدارة القواعد (تفعيل/تعطيل/تفاصيل)، حالة النماذج، insights الشبكة |
| Persistence | ✅ SQLite | كل البيانات في `/data/aegis.db` عبر Docker volume |
| Docker | ✅ جاهز | `docker compose up --build` يكفي للتشغيل |

---

## التشغيل السريع

```bash
git clone <repo> aegis && cd aegis
cp .env.example .env
# عدّل .env: AEGIS_OWNER_TOKEN و AEGIS_SECRET_KEY على الأقل
docker compose up --build
```

| الرابط | الوصف |
|--------|-------|
| http://localhost:8000 | الصفحة الرئيسية |
| http://localhost:8000/admin/ | بوابة المالك |
| http://localhost:8000/merchant/ | بوابة المؤسسة |
| http://localhost:8000/investigator/ | لوحة التحقيقات |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/health | Health |
| http://localhost:8000/ready | Readiness (DB + rules + ML + graph) |

---

## دورة الاستخدام

1. المالك ينشئ مستأجرًا من `/admin/` (أو عبر API) → يحصل على `api_key` + `hmac_secret`.
2. المحفظة/البنك ترسل معاملة إلى `POST /api/v1/wallet/webhook` مع توقيع HMAC.
3. AEGIS يعيد `{decision, risk_score, reasoning_ar, top_reasons}` خلال أجزاء من الثانية.
4. المؤسسة تراقب قراراتها وتنبيهاتها وقضاياها من `/merchant/`.
5. المالك يراقب كل شيء من `/admin/` ويدير العملاء والمحققين والقواعد والنماذج.
6. المحقق يسجّل دخولًا محميًّا في `/investigator/` بحساب ينشئه المالك، ويتولى قائمة المراجعة: يسنِد التنبيه لنفسه، يراجع المعاملة والشبكة، يكتب ملاحظات، ثم يحل التنبيه (احتيال مؤكد / إنذار كاذب) أو يصعّده إلى قضية تُغلق بنتيجة موثّقة.

### مثال webhook

```bash
BODY='{"transaction":{"tx_id":"TX-1","amount":85000,"sender_account_id":"acct_1","beneficiary_account_id":"acct_2"}}'
SIG=$(python3 -c "import hmac,hashlib;print(hmac.new(b'$HMAC_SECRET',b'''$BODY''',hashlib.sha256).hexdigest())")
curl -X POST http://localhost:8000/api/v1/wallet/webhook \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Wallet-Signature: $SIG" \
  -d "$BODY"
```

---

## محرك القرار

```
risk = 0.35×rules + 0.25×ML + 0.15×graph + 0.15×AML + 0.10×behavior
```

| العتبة | القرار |
|--------|--------|
| ≥ 0.80 | block |
| ≥ 0.60 | review |
| ≥ 0.35 | challenge |
| < 0.35 | allow |
| sanctions hit | block (فورًا) |

العتبات والأوزان قابلة للتخصيص عبر env vars (`DECISION_THRESHOLD_*`, `WEIGHT_*`).

---

## هيكل المشروع

```
├── backend/app/          ← FastAPI (api, core, services, rules, ml, graph, aml, repositories, ...)
├── portals/              ← admin / merchant / investigator (HTML+JS+CSS ثابتة)
├── models/trained/       ← نماذج ML المدربة (joblib) — تُنتَج عبر training/
├── training/             ← generate_dataset.py, train_models.py, evaluate_models.py
├── migrations/           ← مرجع SQL (الترحيل الفعلي مدمج في app/db.py)
├── tests/                ← pytest: auth, webhook, pipeline, components, rules
├── scripts/              ← seed_demo.py
├── docs/                 ← توثيق إضافي
├── backend/Dockerfile
├── docker-compose.yml
├── render.yaml
└── .env.example
```

## التوثيق الكامل

- [ARCHITECTURE.md](ARCHITECTURE.md) — المعمارية وتدفق المعاملة
- [API_REFERENCE.md](API_REFERENCE.md) — كل الـ endpoints
- [RUN_LOCAL.md](RUN_LOCAL.md) — التشغيل على Windows/Linux عبر Docker
- [RUN_RENDER.md](RUN_RENDER.md) — النشر على Render
- [DEVELOPMENT.md](DEVELOPMENT.md) — دليل المطور
- [TESTING.md](TESTING.md) — تشغيل الاختبارات
- [SECURITY.md](SECURITY.md) — نموذج الأمان
- [AGENTS.md](AGENTS.md) — دليل وكلاء AI
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — حل المشاكل الشائعة

## الترخيص

Apache License 2.0 — انظر [LICENSE](LICENSE)
