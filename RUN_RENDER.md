# نشر AEGIS على Render

> ⚠️ لم يتم اختبار هذا النشر فعليًا من بيئة التطوير — هذه التعليمات مبنية على ملف render.yaml المرفق.

## الخطوات
1. ارفع المشروع إلى GitHub (بدون `.env`).
2. Render → **New +** → **Blueprint** → اختر المستودع. سيكتشف `render.yaml`.
3. عيّن متغيرات البيئة `sync: false` يدويًا:
   - `AEGIS_OWNER_TOKEN` — قيمة قوية.
   - `AEGIS_PUBLIC_URL` — مثل `https://aegis-xxxx.onrender.com`.
   - `CORS_ORIGINS` — نفس الرابط.
   - `OPENROUTER_KEYS` — اختياري.
4. **الخطة**: `render.yaml` يستخدم `plan: starter` لأن الأقراص (disks) غير متاحة في الخطة المجانية. البيانات تُحفَظ على قرص 1GB مركّب في `/data`.
5. Health check: `/health` (مُعرّف في render.yaml).

## الخدمة
- النوع: Web Service (Docker) — يبني من `backend/Dockerfile`.
- المنفذ: 8000 (Render يمرر `PORT` تلقائيًا).
- قاعدة البيانات: SQLite داخل القرص. للانتقال إلى PostgreSQL لاحقًا انظر ARCHITECTURE.md.

## بعد النشر
```bash
curl https://<your-app>.onrender.com/health
curl https://<your-app>.onrender.com/ready
```
