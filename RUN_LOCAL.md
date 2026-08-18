# تشغيل AEGIS محليًا (Windows + Docker Desktop / Linux)

## 1. تثبيت Docker Desktop (Windows)
1. حمّل Docker Desktop من https://www.docker.com/products/docker-desktop/
2. ثبّته وفعّل WSL2 عند الطلب، ثم أعد تشغيل الجهاز.
3. تحقق: `docker --version` و `docker compose version`

على Linux: `sudo apt install docker.io docker-compose-plugin` ثم `sudo usermod -aG docker $USER` وأعد تسجيل الدخول.

## 2. تجهيز المشروع
```bash
unzip Automated-Digital-Wallet-Security-Fraud-Detection-final.zip
cd aegis-standalone
cp .env.example .env      # في Windows: copy .env.example .env
```

## 3. عدّل .env (إلزامي)
- `AEGIS_OWNER_TOKEN` — اختر قيمة قوية خاصة بك.
- `AEGIS_SECRET_KEY` — سلسلة عشوائية ≥ 32 حرفًا.
- `OPENROUTER_KEYS` — اختياري؛ اتركه كما هو لتعطيل تفسيرات AI.

## 4. البناء والتشغيل
```bash
docker compose up --build
```
انتظر حتى يظهر `aegis.ready` في السجلات.

## 5. التحقق
```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```
ثم افتح http://localhost:8000/admin/ وأدخل قيمة `AEGIS_OWNER_TOKEN`.

## 6. سيناريو عملي سريع
من بوابة المالك: أنشئ مؤسسة → انسخ المفاتيح → أرسل معاملة (انظر README §webhook) → راقب القرار في لوحة التحقيقات.

أو استخدم السكربت:
```bash
docker compose exec aegis python scripts/seed_demo.py http://localhost:8000 <OWNER_TOKEN>
```

## 7. الإيقاف وإعادة التشغيل
```bash
docker compose down          # إيقاف (البيانات تبقى)
docker compose up -d         # تشغيل مجددًا — البيانات محفوظة في volume aegis-data
docker compose down -v       # ⚠️ حذف كامل للبيانات
```

## 8. التأكد من بقاء البيانات
بعد `down` ثم `up`، افتح `/admin/` — المستأجرون والقرارات السابقة موجودون (SQLite في `/data/aegis.db` داخل الـ volume).

## 9. تدريب نماذج ML (اختياري)
```bash
docker compose exec aegis python training/generate_dataset.py
docker compose exec aegis python training/train_models.py
docker compose restart aegis
```
بعدها يتحول `/ready` إلى `ml_ready: true`.

## 10. النسخ الاحتياطي
```bash
docker run --rm -v aegis-standalone_aegis-data:/data -v %cd%:/backup alpine tar czf /backup/aegis-data-backup.tar.gz -C /data .
```
(على Linux استبدل `%cd%` بـ `$(pwd)`)
