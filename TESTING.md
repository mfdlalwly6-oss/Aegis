# الاختبارات

## التشغيل
```bash
pip install -r backend/requirements.txt pytest pytest-asyncio
pytest -q                 # من جذر المشروع (pytest.ini يضبط pythonpath=backend)
```

داخل Docker:
```bash
docker compose exec aegis sh -c "pip install -q pytest pytest-asyncio && python -m pytest /app/../tests -q"
```
(الاختبارات غير منسوخة داخل الصورة افتراضيًا — شغّلها من الجذر على جهازك.)

## الخريطة
| الملف | ماذا يغطي |
|-------|-----------|
| `tests/test_auth.py` | حماية endpoints، تسجيل دخول المؤسسة، JWT فاسد |
| `tests/test_webhook.py` | HMAC، رفض التواقيع، idempotency، غياب legacy fallback |
| `tests/test_pipeline.py` | E2E: webhook→قرار→DB→audit→alert، عزل المستأجرين، الاستمرارية |
| `tests/test_components.py` | قواعد، graph، AML، ML fallback، behavior score |
| `tests/test_seed_rules.py` | صحة ruleset الافتراضي وتحميله |

كل اختبار يستخدم قاعدة SQLite مؤقتة معزولة (tmp_path) — لا يمس بياناتك.
