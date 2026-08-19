# AEGIS Architecture

## نظرة عامة

```
Wallet/Bank                AEGIS
─────────────  POST /api/v1/wallet/webhook ──────────────►
                                                          ┌─────────────────────┐
                                                          │ 1. API key lookup    │ tenants (SQLite)
                                                          │ 2. HMAC verify       │ security.py
                                                          │ 3. Idempotency       │ webhooks_seen
                                                          │ 4. Normalize payload │ webhook.py
                                                          └─────────┬───────────┘
                                                                    ▼
                                                          ┌─────────────────────┐
                                                          │ DecisionOrchestrator │
                                                          │  features.extract    │ SQLite history
                                                          │  rules.evaluate      │ rules (DB/YAML)
                                                          │  ml.score            │ models/trained/*
                                                          │  graph.score         │ NetworkX in-memory
                                                          │  aml.screen          │ watchlist (DB)
                                                          │  behavior score      │
                                                          │  weighted fusion     │ settings.WEIGHT_*
                                                          └─────────┬───────────┘
                                                                    ▼
                              decisions/alerts/cases/audit  ┌─────────────────────┐
                              ◄─────────────────────────────│ Persist (SQLite)     │
                              SSE event                     │ graph.add_transaction│
                              ◄─────────────────────────────│ events.publish       │
                                                            └─────────────────────┘
```

## الطبقات

| الطبقة | المسار | المسؤولية |
|--------|--------|-----------|
| API | `app/api/v1/` | HTTP endpoints فقط — لا منطق أعمال |
| Services | `app/services/` | orchestrator (المنطق), registry (التوصيل) |
| Domain | `app/models/schemas.py` | عقود Pydantic |
| Signals | `rules/ ml/ graph/ aml/ features.py` | منتجو الإشارات |
| Data | `app/repositories/` + `app/db.py` | SQLite عبر Repository pattern فقط |
| Cross | `core/ security.py audit/ notifications/ streaming/` | إعدادات، أمن، تدقيق، إشعارات، أحداث |

## قواعد ثابتة

1. الراوتر لا يستدعي `Database` مباشرة — فقط عبر repositories.
2. القرار deterministic؛ الـ AI (OpenRouter) للتفسير فقط ولا يغيّر القرار.
3. كل endpoint حساس يتطلب `require_owner` أو JWT مؤسسة.
4. كل حدث مهم يُسجَّل في `audit_log` بدون أسرار.
5. المستأجر لا يرى إلا بياناته (`tenant_id` في JWT يُطابَق في الاستعلام).

## استبدال SQLite بـ PostgreSQL لاحقًا

كل الوصول للبيانات يمر عبر `app/repositories/*`. لاستبدال المحرك:
أعد كتابة `app/db.py` (نفس الواجهة: `execute/query/query_one`) باستخدام
`asyncpg` أو `psycopg`، وحدّث SQL في الـ repositories إن لزم. لا تغيير في الخدمات أو الـ API.
