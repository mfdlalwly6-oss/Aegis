# دليل المطور — AEGIS

## الإعداد للتطوير بدون Docker
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt pytest pytest-asyncio
export AEGIS_DATA_DIR=/tmp/aegis-dev AEGIS_OWNER_TOKEN=dev-owner-token \
       AEGIS_SECRET_KEY=dev-secret-key-that-is-long-enough-123456
cd backend && uvicorn app.main:app --reload --port 8000
```

## أين تضيف ماذا
| التغيير | المكان |
|---------|--------|
| Endpoint جديد | `backend/app/api/v1/<name>.py` + سجّله في `api/v1/__init__.py` |
| قاعدة كشف جديدة | أضفها في `rules/default_ruleset.yaml` أو عبر `POST /api/v1/rules/reload` |
| إشارة مخاطر جديدة | `app/features.py` (الاستخراج) + `services/orchestrator.py` (الدمج) |
| جدول جديد | أضف migration في `app/db.py` (`_MIGRATIONS`) + repository في `app/repositories/` |
| مزوّد إشعارات | نفّذ `NotificationProvider` في `app/notifications/providers.py` |

## الاصطلاحات
- كل الوصول للبيانات عبر repositories فقط.
- الراوترات لا تحتوي منطق أعمال.
- الأخطاء تُعاد كـ `HTTPException(status, "snake_case_code")`.
- سجّل الأحداث المهمة عبر `registry.audit.log(...)` بدون أسرار في metadata.
- الأسطر ≤ 100 حرف، Python 3.11+, type hints.

## Lint & Tests
```bash
pytest -q                 # كل الاختبارات (من جذر المشروع)
pytest tests/test_webhook.py -q
```
