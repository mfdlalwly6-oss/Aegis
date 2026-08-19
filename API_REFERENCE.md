# AEGIS API Reference (v2.0.0)

Base URL: `http://localhost:8000` — جميع المسارات تبدأ بـ `/api/v1` ما لم يُذكر خلاف ذلك.

## المصادقة

| النوع | الهيدر | الاستخدام |
|-------|--------|-----------|
| Owner | `X-Owner-Token: <AEGIS_OWNER_TOKEN>` | إدارة المنصة |
| Merchant | `Authorization: Bearer <JWT>` | بوابة المؤسسة (يُصدر من `/admin/merchant/login`) |
| Webhook | `X-API-Key` + `X-Wallet-Signature` | توقيع HMAC-SHA256 على الجسم الخام |

## عامة

| Method | Path | Auth | الوصف |
|--------|------|------|-------|
| GET | `/health` | — | فحص حي |
| GET | `/ready` | — | جاهزية (DB/rules/ML/graph) |
| GET | `/api/v1/system/version` | — | الإصدار |
| GET | `/api/v1/system/ready` | — | جاهزية مفصلة |
| GET | `/metrics` | — | Prometheus |

## إدارة المستأجرين (Owner)

| Method | Path | الوصف |
|--------|------|-------|
| GET | `/admin/tenants` | قائمة المستأجرين |
| POST | `/admin/tenants` | إنشاء مستأجر → `{tenant_id, api_key, hmac_secret}` |
| GET | `/admin/tenants/{id}` | تفاصيل (يكشف hmac_secret) |
| POST | `/admin/tenants/{id}/rotate-secret` | تدوير HMAC secret |
| PUT | `/admin/tenants/{id}/policy` | تحديث سياسات المخاطر |
| DELETE | `/admin/tenants/{id}` | حذف (soft delete) |
| GET | `/admin/overview` | إحصائيات المنصة |
| GET | `/admin/decisions/recent?limit=50` | أحدث القرارات (كل المستأجرين) |
| GET | `/admin/audit?tenant_id=&event_type=&limit=` | سجل التدقيق |
| GET | `/admin/stream` | SSE للقرارات الحية |

## بوابة المؤسسة (Merchant JWT)

| Method | Path | الوصف |
|--------|------|-------|
| POST | `/admin/merchant/login` | `{api_key, api_secret}` → `merchant_token` |
| GET | `/admin/merchant/me` | بيانات المؤسسة |
| GET | `/admin/merchant/integration` | مفاتيح + أمثلة تكامل |
| GET | `/admin/merchant/connection-status` | حالة الخدمات |
| GET | `/admin/merchant/stats` | إحصائيات قرارات المؤسسة فقط |
| GET | `/admin/merchant/decisions?limit=50` | قرارات المؤسسة فقط |
| GET | `/admin/merchant/alerts` | تنبيهات المؤسسة فقط |
| GET | `/admin/merchant/cases` | قضايا المؤسسة فقط |

## Webhook (المسار الإنتاجي)

**POST** `/api/v1/wallet/webhook`

Headers: `X-API-Key`, `X-Wallet-Signature` (HMAC-SHA256 hex للجسم الخام)، اختياريًا `X-Idempotency-Key`.

```json
{
  "transaction": {
    "tx_id": "TX-001", "amount": 85000, "currency": "USD", "channel": "wallet",
    "sender_account_id": "acct_1", "beneficiary_account_id": "acct_2",
    "beneficiary_country": "YE",
    "device": {"device_id": "dev_1", "ip": "198.51.100.10", "vpn": false},
    "behavior": {"biometric_match_score": 0.95},
    "metadata": {"account_age_days": 400}
  }
}
```

الرد:
```json
{
  "tx_id": "TX-001", "decision": "review", "risk_score": 0.62,
  "risk_band": "high", "typology": "high_risk",
  "reasoning_ar": "...", "top_reasons": ["..."],
  "alert_id": "alr_...", "case_id": "case_...", "latency_ms": 12.4
}
```

إعادة إرسال نفس المعاملة (نفس tx_id أو X-Idempotency-Key) ترجع `"duplicate": true` دون تكرار السجلات.

## أخرى (Owner)

| Method | Path | الوصف |
|--------|------|-------|
| POST | `/transactions/score` | تسجيل معاملة مباشرة (يتطلب tenant_id) |
| GET | `/transactions/{tx_id}` | معاملة + قرارها |
| GET | `/rules/` | القواعد المحمّلة |
| POST | `/rules/reload` | إضافة/تحديث قواعد + إعادة تحميل |
| GET | `/alerts/` · POST `/alerts/{id}/status` | التنبيهات |
| GET | `/cases/` · GET `/cases/{id}` · POST `/cases/{id}/notes` · POST `/cases/{id}/status` | القضايا |
| GET | `/models/` | حالة نماذج ML (trained أم fallback) |
| GET | `/graph/rings` · `/graph/stats` | تحليل الشبكة |
| GET | `/decisions/recent?limit=20` | قرارات حديثة بحقول محدودة (عام — للوحة المراقبة) |
