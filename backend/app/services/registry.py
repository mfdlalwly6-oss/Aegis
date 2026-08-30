"""Service registry — instantiates and wires all AEGIS core services.
All external dependencies are optional and fail gracefully.
"""

from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from app.aml.service import AMLService
from app.audit import AuditService
from app.core.config import settings
from app.db import Database
from app.features import FeatureExtractor
from app.graph.engine import GraphEngine
from app.ml.ensemble import EnsembleScorer
from app.repositories import (
    AlertRepository,
    AuditRepository,
    CaseRepository,
    DecisionRepository,
    InvestigatorRepository,
    PolicyVersionRepository,
    RuleRepository,
    TenantRepository,
    TransactionRepository,
    UserRepository,
    WatchlistRepository,
)
from app.repositories.currency_repo import CurrencyRepository
from app.repositories.fx_rate_repo import FxRateRepository
from app.rules.engine import RuleEngine
from app.services.fx_service import FxService
from app.services.notifications import NotificationService, provider_from_settings
from app.services.orchestrator import DecisionOrchestrator
from app.streaming import EventBus

logger = structlog.get_logger(__name__)


class ServiceRegistry:
    def __init__(self):
        self.db: Database | None = None
        self.tenants: TenantRepository | None = None
        self.transactions: TransactionRepository | None = None
        self.decisions: DecisionRepository | None = None
        self.alerts: AlertRepository | None = None
        self.cases: CaseRepository | None = None
        self.audit_repo: AuditRepository | None = None
        self.rule_repo: RuleRepository | None = None
        self.watchlist_repo: WatchlistRepository | None = None
        self.user_repo: UserRepository | None = None
        self.investigators: InvestigatorRepository | None = None
        self.rule_engine: RuleEngine | None = None
        self.ml_scorer: EnsembleScorer | None = None
        self.graph_engine: GraphEngine | None = None
        self.aml_service: AMLService | None = None
        self.audit: AuditService | None = None
        self.events: EventBus | None = None
        self.notifications = None
        self.orchestrator: DecisionOrchestrator | None = None
        self.features: FeatureExtractor | None = None

    async def initialize(self) -> None:
        # 1. Database + migrations
        self.db = Database()
        self.db.migrate()
        logger.info("db.migrated", path=self.db.path)

        # 2. Repositories
        self.tenants = TenantRepository(self.db)
        self.transactions = TransactionRepository(self.db)
        self.decisions = DecisionRepository(self.db)
        self.alerts = AlertRepository(self.db)
        self.cases = CaseRepository(self.db)
        self.audit_repo = AuditRepository(self.db)
        self.rule_repo = RuleRepository(self.db)
        self.policy_versions = PolicyVersionRepository(self.db)
        self.watchlist_repo = WatchlistRepository(self.db)
        self.user_repo = UserRepository(self.db)

        # ── TASK 9: platform admin bootstrap (env-provided, never hardcoded) ──
        admin_email = getattr(settings, "PLATFORM_ADMIN_EMAIL", "") or ""
        admin_pass = getattr(settings, "PLATFORM_ADMIN_PASSWORD", "") or ""
        if admin_email and admin_pass:
            if not self.db.query_one(
                "SELECT 1 FROM users WHERE email=? AND status='active'",
                (admin_email.strip().lower(),),
            ):
                import secrets as _sec
                from datetime import UTC as _UTC
                from datetime import datetime as _dt

                from app.crypto import encrypt_secret as _enc

                now_iso = _dt.now(_UTC).isoformat()
                # ensure a platform-scope tenant exists for the admin user (FK)
                self.db.execute(
                    "INSERT OR IGNORE INTO tenants (tenant_id, name, type, country, plan,"
                    " contact_email, contact_phone, api_key, hmac_secret, status,"
                    " policy_json, created_at, secret_rotated_at, deleted_at,"
                    " investigator_limit, timezone, review_message)"
                    " VALUES ('platform','AEGIS Platform','platform','YE','internal',"
                    " NULL, NULL, ?, ?, 'active', '{}', ?, NULL, NULL, 999, 'UTC', '')",
                    ("ak_" + _sec.token_hex(16), _enc(_sec.token_urlsafe(32)), now_iso),
                )
                self.user_repo.create(
                    "platform", admin_email, "Platform Admin", role="admin", password=admin_pass
                )
                logger.info("platform_admin.bootstrapped", email=admin_email[:4] + "***")

        # ── TASK 9 / migration 012: encrypt legacy plaintext hmac_secrets ──
        from app.crypto import encrypt_secret, is_encrypted

        if not self.db.query_one(
            "SELECT 1 FROM schema_migrations WHERE name=?", ("012_encrypt_hmac_secrets",)
        ):
            from datetime import UTC as _UTC2
            from datetime import datetime as _dt2

            n = 0
            for r in self.db.query("SELECT tenant_id, hmac_secret FROM tenants"):
                v = r["hmac_secret"]
                if v and not is_encrypted(v):
                    self.db.execute(
                        "UPDATE tenants SET hmac_secret=? WHERE tenant_id=?",
                        (encrypt_secret(v), r["tenant_id"]),
                    )
                    n += 1
            import hashlib as _hl

            self.db.execute(
                "INSERT INTO schema_migrations (name, applied_at, sha256) VALUES (?, ?, ?)",
                (
                    "012_encrypt_hmac_secrets",
                    _dt2.now(_UTC2).isoformat(),
                    _hl.sha256(b"012_encrypt_hmac_secrets:fernet-at-rest").hexdigest(),
                ),
            )
            logger.info("migration.012_encrypt_hmac_secrets", encrypted=n)
        self.investigators = InvestigatorRepository(self.db)
        self.currency_repo = CurrencyRepository(self.db)
        self.fx_rate_repo = FxRateRepository(self.db)
        self.currency_repo.seed_defaults()
        self.fx = FxService(
            self.fx_rate_repo, currency_checker=lambda c: self.currency_repo.is_known(c)
        )

        # Bootstrap a first investigator from env when none exists (dev convenience).
        # Investigators are tenant-scoped: use INVESTIGATOR_TENANT_ID, else first
        # active tenant, else a 'platform' placeholder so the account always has a scope.
        inv_email = getattr(settings, "INVESTIGATOR_EMAIL", "") or ""
        inv_pass = getattr(settings, "INVESTIGATOR_PASSWORD", "") or ""
        if self.investigators.count() == 0 and inv_email and inv_pass:
            tenant_id = getattr(settings, "INVESTIGATOR_TENANT_ID", "") or ""
            if not tenant_id:
                tenants = self.tenants.list()
                tenant_id = next(
                    (t["tenant_id"] for t in tenants if t["status"] == "active"), "platform"
                )
            self.investigators.create(
                tenant_id,
                inv_email,
                getattr(settings, "INVESTIGATOR_NAME", "") or "محقق الاحتيال",
                inv_pass,
            )
            logger.info("investigator.bootstrapped", email=inv_email, tenant_id=tenant_id)

        # 3. Seed default rules from YAML into DB
        rules_path = Path(__file__).parent.parent / "rules" / "default_ruleset.yaml"
        if rules_path.exists():
            spec = yaml.safe_load(rules_path.read_text())
            seeded = self.rule_repo.seed_defaults(spec.get("rules", []))
            if seeded:
                logger.info("rules.seeded", count=seeded)

        # 4. Seed default watchlists
        self.watchlist_repo.seed_defaults()

        # 5. Rule engine (loads platform rules + ALL tenant overrides;
        #    tenant scoping is applied per-transaction at evaluation time)
        all_rules = self.rule_repo.list_for_engine()
        self.rule_engine = RuleEngine(rules=all_rules)
        logger.info("rule_engine.loaded", count=len(all_rules))

        # 6. ML scorer (real model if trained, heuristic fallback)
        self.ml_scorer = EnsembleScorer()
        # 6b. Register active models in model_registry (audit + governance)
        try:
            import json as _json

            _meta = getattr(self.ml_scorer, "_metadata", {}) or {}
            for _m in self.ml_scorer.list_models():
                self.db.execute(
                    "INSERT OR IGNORE INTO model_registry "
                    "(model_name,version,path,metrics_json,trained_at,is_active) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        _m["name"],
                        _m["version"],
                        str(getattr(self.ml_scorer, "_dir", "")),
                        _json.dumps(_meta.get("metrics", {}), default=str),
                        _meta.get("trained_at"),
                        1 if _m.get("type") == "trained" else 0,
                    ),
                )
        except Exception as _e:
            logger.warning("ml.registry_write_failed", error=str(_e))

        # 7. Graph engine (bootstrap from recent transactions)
        self.graph_engine = GraphEngine()
        recent_txs = self.transactions.list_recent(limit=2000)
        self.graph_engine.bootstrap(recent_txs)

        # 8. AML service
        self.aml_service = AMLService(self.watchlist_repo)

        # 9. Feature extractor
        self.features = FeatureExtractor(self.transactions, self.decisions)

        # 10. Audit + events + notifications
        self.audit = AuditService(self.audit_repo)
        self.events = EventBus()
        self.notifications = NotificationService(provider_from_settings(settings), self.audit)

        # 11. Orchestrator (unified pipeline)
        self.orchestrator = DecisionOrchestrator(
            rules=self.rule_engine,
            ml=self.ml_scorer,
            graph=self.graph_engine,
            aml_service=self.aml_service,
            features=self.features,
            transactions=self.transactions,
            decisions=self.decisions,
            alerts=self.alerts,
            cases=self.cases,
            audit=self.audit,
            events=self.events,
            notifications=self.notifications,
            tenants=self.tenants,
            policy_repo=self.policy_versions,
        )
        logger.info("aegis.initialized", version=settings.VERSION)

    async def shutdown(self) -> None:
        if self.db:
            self.db.close()

    async def readiness(self) -> dict:
        return {
            "database": self.db is not None,
            "db_path": str(self.db.path) if self.db else None,
            "rules": len(self.rule_engine.rules) if self.rule_engine else 0,
            "ml_ready": self.ml_scorer.ready if self.ml_scorer else False,
            "ml_models": self.ml_scorer.list_models() if self.ml_scorer else [],
            "graph_nodes": self.graph_engine.node_count if self.graph_engine else 0,
            "tenants": len(self.tenants.list()) if self.tenants else 0,
        }
