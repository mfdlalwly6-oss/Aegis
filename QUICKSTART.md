# ⚡ Quick Start

```bash
cp .env.example .env
# عدّل AEGIS_OWNER_TOKEN و AEGIS_SECRET_KEY
docker compose up --build
```

- المنصة: http://localhost:8000
- بوابة المالك: http://localhost:8000/admin/ (أدخل قيمة AEGIS_OWNER_TOKEN)
- Swagger: http://localhost:8000/docs
- فحص: `curl http://localhost:8000/ready`

إنشاء أول مؤسسة:
```bash
curl -X POST http://localhost:8000/api/v1/admin/tenants \
  -H "Content-Type: application/json" \
  -H "X-Owner-Token: <AEGIS_OWNER_TOKEN>" \
  -d '{"name":"بنك تجريبي","type":"bank","country":"YE"}'
```

التفاصيل الكاملة: [RUN_LOCAL.md](RUN_LOCAL.md)
