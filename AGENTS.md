# دليل وكلاء AI (Manus / Genspark / غيرها)

## المعمارية باختصار
FastAPI backend واحد يخدم 3 بوابات ثابتة. قاعدة SQLite عبر Repository layer.
المسار الرئيسي: `api/v1/webhook.py` → `services/orchestrator.py` → repositories.

## أهم المسارات
- منطق القرار: `backend/app/services/orchestrator.py` — **المسار الموحد الوحيد**
- التوصيل: `backend/app/services/registry.py`
- البيانات: `backend/app/db.py` + `backend/app/repositories/`
- القواعد: `backend/app/rules/engine.py` + `default_ruleset.yaml`
- المخططات: `backend/app/models/schemas.py`

## أوامر
```bash
docker compose up --build      # تشغيل
pytest -q                      # اختبارات (pythonpath=backend)
python training/generate_dataset.py && python training/train_models.py
```

## قواعد لا تُكسر
1. لا تضع أسرار في الكود — env vars فقط.
2. لا تستدعِ `Database` خارج `app/repositories/`.
3. لا تُنشئ مسار قرار ثانيًا — كل التقييم يمر عبر `DecisionOrchestrator`.
4. القرار deterministic — الـ AI للتفسير فقط.
5. كل استعلام بيانات مؤسسة يُرشَّح بـ `tenant_id` من JWT، لا من العميل.
6. سجّل الأحداث المهمة في audit بدون أسرار.
7. عند إضافة جدول: أضف migration في `_MIGRATIONS` داخل `app/db.py`.

## ملفات لا تُعدّل بلا سبب موثق
- `backend/app/security.py`
- `docker-compose.yml` و`backend/Dockerfile`
- عقود `schemas.py` العامة (tx_id, decision, risk_score...)
