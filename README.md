# 🛡️ AEGIS — منصة مكافحة الاحتيال المالي متعددة المؤسسات

AEGIS هي منصة SaaS مركزية لكشف الاحتيال وإدارة مخاطر المعاملات المالية، تخدم **عدة مؤسسات** في الوقت نفسه — البنوك، المحافظ الإلكترونية، ومؤسسات الدفع — مع **عزل كامل** للبيانات والصلاحيات والعمليات بين كل مؤسسة (Tenant) والأخرى.

```
AEGIS
├── Tenant A — بنك الأمان التجاري
├── Tenant B — محفظة النور
└── Tenant C — مؤسسة مالية ...
```

---

## 1) المشكلة التي يحلها AEGIS

- عمليات احتيال عبر القنوات الرقمية (تحويلات، محافظ، مدفوعات).
- الحاجة إلى تقييم كل معاملة في لحظتها: **سماح / حظر / مراجعة**.
- الحاجة إلى منصة واحدة تدير عدة بنوك ومحافظ مع **عزل تام** بينها.
- الحاجة إلى مسار مراجعة بشرية (Review Queue) للعمليات المشبوهة.
- الحاجة إلى تقارير مخاطر حقيقية (يومي/أسبوعي/شهري) بصيغة PDF.
- الحاجة إلى سجل تدقيق (Audit Log) شامل لكل إجراء حساس.

## 2) نموذج Multi-Tenancy

- كل مؤسسة = **Tenant** مستقل تمامًا (بيانات، معاملات، تنبيهات، حالات، محققون، مفاتيح، تقارير، سجل تدقيق).
- العزل مفروض في **طبقة الوصول للبيانات (Backend)**، وليس مجرد إخفاء في الواجهة.
- أي محاولة وصول عبر-مؤسسات ترجع `403` أو `404` (حسب التصميم) — اختُبرت صراحة.

## 3) الأدوار والصلاحيات (RBAC)

| الدور | النطاق | القدرات الرئيسية |
|---|---|---|
| **AEGIS Owner** | المنصة كلها | إنشاء/تعديل/إيقاف/تفعيل/حذف المؤسسات، الخطط، حد المحققين، المفاتيح، الإعدادات المركزية، القواعد، النماذج، Graph، سجل التدقيق الكامل. لا يرى كلمات المرور أبدًا (Reset آمن فقط). |
| **Institution Owner** | مؤسسته فقط | لوحة مؤسسته، المعاملات، التنبيهات، الحالات، المحققون (إنشاء/إيقاف/تنشيط/حذف/Reset Password)، التكامل، التقارير. يمكنه أداء عمل المحقق مع تسجيل `actor_type = institution_owner`. |
| **Investigator / Reviewer** | مؤسسته فقط | Review Queue، تنبيهات/حالات مؤسسته، ملاحظات، قرارات (Approve/Decline/Escalate/Resolve). لا يرى أي بيانات من مؤسسات أخرى أو أسرارًا مركزية. |

## 4) تدفق المعاملة

```
Transaction → Authentication (API Key + HMAC-SHA256) → Tenant Resolution
→ Validation → Rules → ML → Graph → AML → Behavior → Risk Fusion → Decision
```

النتيجة واحدة من: **ALLOW** (تنفيذ)، **BLOCK** (رفض مع السبب)، **REVIEW** (تعليق في Review Queue — لا تمر تلقائيًا أبدًا).

- رسالة REVIEW للعميل النهائي رسالة مفهومة قابلة للتخصيص لكل مؤسسة، مثل:
  > "تم تعليق العملية مؤقتًا للمراجعة الأمنية. يرجى التواصل مع المؤسسة المالية لإتمام المراجعة."
- كل بيانات القرار تُسجَّل: tx_id، tenant، score، reasons، model/rules، latency، timestamps.

## 5) Review Queue ومعالجة الحالات

- قائمة مراجعة تعرض: معرّف العملية، المبلغ، العملة، المرجع، درجة الخطر، السبب، الأولوية، الحالة، المحقق المسند — مع فلاتر.
- إجراءات كاملة: فتح، ملاحظة، Assign، Approval، Decline، Escalate (إلى Case)، Resolve — **كل إجراء يُسجَّل في Audit Log**.
- قسم "المعاملات المعالجة يدويًا": من قام بالقرار (محقق أم مالك المؤسسة)، الدور، التوقيتات، المدة، الملاحظات.

## 6) التنبيهات والحالات (Lifecycle)

- **Alert**: `NEW → ASSIGNED → IN_REVIEW → ESCALATED → RESOLVED / FALSE_POSITIVE / CONFIRMED_FRAUD`.
- **Case**: `OPEN → IN_PROGRESS → ESCALATED → CLOSED` مع resolution.
- كل حالة تحفظ: created_at، assigned_at، reviewed_at، resolved_at، الفاعل، الملاحظات، وسجل التدقيق.

## 7) إدارة المحققين والحدود

- عند إنشاء مؤسسة يُحدَّد **Investigator Limit** (مثال: 5).
- الحد مفروض في **الـ Backend**: محقق رقم N+1 يُرفض برسالة واضحة (`409 investigator_limit_reached`).
- مالك AEGIS يستطيع رفع/تخفيض الحد، و**يمنع النظام التخفيض تحت عدد المحققين النشطين**.
- واجهة المحققين (للمالك والمؤسسة): الاسم، البريد، الحالة، آخر دخول، إجراءات (عرض/إيقاف/تنشيط/حذف/Reset Password) — بدون عرض كلمة المرور أو الـ hash.

## 8) التكامل (Integration)

كل مؤسسة تحصل عند إنشائها على بيانات حقيقية من قاعدة البيانات:

- `tenant_id` + `api_key` + `hmac_secret` + `base_url` + نقطة الـ webhook + نماذج كود (curl / Node.js / Python).
- المصادقة: `X-API-Key` + توقيع `X-Wallet-Signature` (HMAC-SHA256 على الجسم).
- صفحة إعدادات التكامل تعرض القيم الحقيقية من Backend (ليست قيمًا ثابتة)، مع حالة: `CONNECTED / DISCONNECTED / ERROR / SUSPENDED`.
- المؤسسة الموقوفة تُرفض معاملاتها فورًا (403).

## 9) التقارير

- فترات: **يومي** (من بداية اليوم المحلي)، **أسبوعي** (من بداية الأسبوع المحلي)، **شهري** (من بداية الشهر التقويمي) — حسب **المنطقة الزمنية للمؤسسة**.
- التخزين بتوقيت UTC، والعرض بالتوقيت المحلي، مع إظهار التاريخ الهجري والميلادي (الهجري للعرض فقط).
- PDF **حقيقي** (ReportLab + خط Amiri للعربية) — قابل للتنزيل والطباعة.
- المحتوى: ملخص تنفيذي، حجم العمليات، توزيع القرارات، توزيع المخاطر، أهم الأسباب، التنبيهات، الحالات، المراجعات اليدوية (مع SLA)، نشاط المحققين، صحة النظام والتكامل.

## 10) الأمان

- JWT (HS256، TTLs منفصلة) + API Keys + HMAC.
- RBAC + عزل مؤسسات على مستوى Backend في كل طلب (`require_merchant` / `require_investigator` يتحققان من `tenant_id` + حالة المؤسسة + حالة الحساب).
- تجزئة كلمات المرور (PBKDF2-HMAC-SHA256) — لا تُخزَّن كنص صريح ولا تُعرض.
- حماية ضد SQLi (استعلامات معلمة الثانية)، XSS (إخراج مُهرَّب في الواجهات)، IDOR (تحقق نطاق على كل قراءة/كتابة)، CSRF (رموز Bearer + CORS مقيد)، Rate Limiting، Validation عبر Pydantic.
- Audit Log غير قابل للتلاعب من الواجهة: actor، role، tenant، action، target، before/after، timestamp، request_id.
- SSE (الدفق الحي) محمي: owner فقط للمسؤول، ومحققون معتمدون للمؤسسات.

## 11) قاعدة البيانات والهجرات

- SQLite (قابل للتبديل إلى PostgreSQL عبر طبقة المستودعات) مع **forward-only migrations** مفهرسة في `schema_migrations`:
  - `001_init` — المخطط الأساسي.
  - `002_investigator_workflow` — notes/resolution على التنبيهات والحالات.
  - `003_tenant_scoped_investigators` — `tenant_id` على المحققين + `investigator_limit`/`timezone`/`review_message` على المؤسسات.
- **لا DROP DATABASE** — الهجرات فقط للأمام مع الحفاظ على البيانات.

## 12) التشغيل عبر Docker

```bash
cp .env.example .env        # ثم عدّل القيم
docker compose up -d --build
curl http://localhost:8000/health   # {"status":"ok"}
curl http://localhost:8000/ready
docker compose logs --tail=100
```

- البوابات: `/admin/` (مالك AEGIS)، `/merchant/` (المؤسسة)، `/investigator/` (المحقق).
- API Docs: `/docs` (Swagger) و `/redoc`.
- المقاييس: `/metrics` (Prometheus).

## 13) الاختبارات

```bash
cd backend && pip install -r requirements.txt
PYTHONPATH=backend python -m pytest tests -q
```

تشمل: وحدة، تكامل، API، مصادقة، تفويض، **عزل Multi-Tenant**، هجرات، E2E (سيناريوهات عملاء حقيقية عبر السكربت `scripts/e2e_scenarios.sh`)، توليد PDF والتحقق منه (`%PDF-`)، رفض المؤسسات الموقوفة، وأمان الأسرار.

## 14) النسخ الاحتياطي والاستعادة

- قاعدة SQLite: `sqlite3 /data/aegis.db ".backup '/data/aegis-$(date +%F).db'"`.
- النسخ الكامل: `tar --exclude='.env' --exclude='.git' -czf aegis-backup.tgz -C /home/zr0/Aegis .`
- الاستعادة: فك الضغط في مكان المشروع ثم `docker compose up -d` (الهجرات تُطبق تلقائيًا للأمام).

## 15) بنية المستودع

```
backend/app/
  api/v1/       # routes: tenants, investigator, merchant, reports, webhook, alerts, cases...
  repositories/ # طبقة وصول البيانات (tenant-scoped)
  services/     # orchestrator (خط أنابيب القرار) + registry
  rules/ ml/ graph/ aml/ features/   # محركات المخاطر
  reports/      # ReportBuilder + PDF (ReportLab)
  core/         # config (env)، middleware، telemetry
  portals/      # admin / merchant / investigator (واجهات)
scripts/        # seed_demo.py, e2e_scenarios.sh
tests/          # pytest suite
```

---

**ملاحظة أمنية**: لا ترفع `.env` أو الأسرار إلى Git/ZIP أبدًا. استخدم `.env.example` فقط، وبدّل `AEGIS_SECRET_KEY` و`AEGIS_OWNER_TOKEN` بقيم عشوائية في الإنتاج.

## Dev & testing (portable)

```bash
cp .env.example .env          # then edit secrets (SECRET_KEY, OWNER_TOKEN)
docker compose build          # requires Docker + Docker Hub access
docker compose up -d          # http://localhost:8000
# Tests: install dev deps where you run pytest
pip install -r backend/requirements-dev.txt
pytest                          # from repo root (pythonpath=backend)
bash scripts/e2e_local.sh       # full E2E (self-cleaning)
```
