# نموذج الأمان

## المصادقة والتفويض
- **Owner**: `X-Owner-Token` بمقارنة constant-time (`hmac.compare_digest`).
- **Merchant**: JWT (HS256) يُصدر بعد التحقق من `api_key + hmac_secret`. يحمل `tenant_id` و`role`.
- **Webhook**: HMAC-SHA256 على الجسم الخام + API key لكل مستأجر.
- الأدوار: `owner` (المنصة)، `merchant/tenant_admin` (المؤسسة). Roles إضافية (analyst/investigator/viewer) مدعومة في بنية JWT وتُفعَّل عند إضافة إدارة مستخدمين كاملة.

## عزل المستأجرين
- كل صف في `transactions/decisions/alerts/cases` يحمل `tenant_id`.
- استعلامات المؤسسة تُرشَّح دائمًا بـ `tenant_id` المستخرج من JWT — لا يُقبل من العميل.
- اختبار `test_tenant_isolation` يثبت أن مؤسسة لا ترى بيانات أخرى.

## حماية الـ Webhook
- توقيع إلزامي + constant-time comparison.
- Idempotency: نفس `X-Idempotency-Key` أو `tenant:tx_id` لا يكرر القرار.
- Legacy fallback معطّل افتراضيًا (`AEGIS_LEGACY_SECRET` فارغ).

## الأسرار
- لا أسرار في الكود — كل شيء من env vars (انظر `.env.example`).
- `audit_log` يُسقِط مفاتيح `hmac_secret/password/api_key/token` تلقائيًا.
- `.env` مستثنى من Git وDocker build context.

## أخرى
- CORS مقيّد بـ `CORS_ORIGINS` (لا `*`).
- Rate limiting: نافذة منزلقة per-IP (in-memory؛ للإنتاج متعدد النسخ استخدم Redis).
- كلمات المرور: PBKDF2-SHA256 (100k iterations).
- كابح الحجم: Pydantic validation على كل المدخلات.

## ما يجب فعله قبل الإنتاج
1. غيّر `AEGIS_SECRET_KEY` و`AEGIS_OWNER_TOKEN`.
2. فعّل HTTPS (reverse proxy).
3. قيّد CORS بنطاقاتك.
4. انقل rate limiting إلى Redis عند تشغيل أكثر من نسخة.
