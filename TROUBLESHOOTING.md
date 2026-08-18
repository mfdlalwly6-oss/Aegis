# حل المشاكل

## `docker compose up` يفشل عند البناء
- تأكد أنك في جذر المشروع (حيث docker-compose.yml).
- `docker compose build --no-cache` لإعادة بناء نظيفة.

## `/ready` يقول degraded
- افحص السجلات: `docker compose logs aegis | tail -50`
- غالبًا `/data` غير قابل للكتابة — احذف الـ volume: `docker compose down -v && docker compose up --build` (يفقد البيانات).

## `invalid_signature` عند webhook
- التوقيع يُحسب على **الجسم الخام** كما هو (bytes)، وليس بعد إعادة التنسيق.
- استخدم نفس JSON الذي أرسلته حرفيًا عند حساب HMAC.

## القرارات لا تظهر في بوابة المؤسسة
- تأكد أنك سجلت الدخول بـ `api_key` و`hmac_secret` الصحيحين (يرجع JWT).
- المتصفح يخزن التوكن في localStorage تحت `aegis_merchant_token` — امسحه عند تبديل المؤسسة.

## `ml_ready: false`
- طبيعي قبل التدريب — النظام يستخدم heuristic fallback مُعلَن.
- درّب النماذج: `docker compose exec aegis python training/generate_dataset.py && docker compose exec aegis python training/train_models.py` ثم `docker compose restart aegis`.

## `rate_limited` (429)
- ارفع `RATE_LIMIT_PER_MIN` في `.env` أثناء التطوير.

## إعادة ضبط بيئة التطوير بالكامل
```bash
docker compose down -v && rm -rf data && docker compose up --build
```
