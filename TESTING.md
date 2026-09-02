# الاختبارات

## التشغيل
```bash
pip install -r backend/requirements.txt pytest pytest-asyncio
pytest -q                 # من جذر المشروع (pytest.ini يضبط pythonpath=backend)
```

داخل Docker (الطريقة الرسمية — PostgreSQL معزولة):
```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```

الطريقة اليدوية داخل الحاوية:
```bash
docker compose exec aegis sh -c "pip install -q pytest pytest-asyncio && python -m pytest /app/../tests -q"
```
(AEGIS PostgreSQL-only: الاختبارات تعمل على قاعدة PostgreSQL معزولة aegis_test مبنية من migrations الحقيقية — لا SQLite إطلاقًا.)

## الخريطة
| الملف | ماذا يغطي |
|-------|-----------|
| `tests/test_auth.py` | حماية endpoints، تسجيل دخول المؤسسة، JWT فاسد |
| `tests/test_webhook.py` | HMAC، رفض التواقيع، idempotency، غياب legacy fallback |
| `tests/test_pipeline.py` | E2E: webhook→قرار→DB→audit→alert، عزل المستأجرين، الاستمرارية |
| `tests/test_components.py` | قواعد، graph، AML، ML fallback، behavior score |
| `tests/test_seed_rules.py` | صحة ruleset الافتراضي وتحميله |

كل اختبار ينشئ قاعدة PostgreSQL معزولة aegis_test (drop/create لكل اختبار) ويفشل بأمان إذا حاول لمس قاعدة الإنتاج — لا يوجد أي مسار SQLite.
