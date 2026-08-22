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
from app.notifications.providers import ConsoleNotificationProvider
from app.repositories import (
    AlertRepository, AuditRepository, CaseRepository, CurrencyRepository,
    DecisionRepository, FxRateRepository, InvestigatorRepository, RuleRepository,
    TenantRepository, TransactionRepository, UserRepository, WatchlistRepository,
)
from app.rules.engine import RuleEngine
from app.services.fx_service import FxService
from app.services.orchestrator import DecisionOrchestrator
from app.services.policy_engine import PolicyEngine
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
        self.currencies: CurrencyRepository | None = None
        self.fx_rates: FxRateRepository | None = None
        self.fx_service: FxService | None = None
        self.policy_engine: PolicyEngine | None = None

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
        self.watchlist_repo = WatchlistRepository(self.db)
        self.user_repo = UserRepository(self.db)
        self.investigators = InvestigatorRepository(self.db)

        # Bootstrap a first investigator from env when none exists (dev convenience).
        # Investigators are tenant-scoped: use INVESTIGATOR_TENANT_ID, else first
        # active tenant, else a 'platform' placeholder so the account always has a scope.
        inv_email = getattr(settings, "INVESTIGATOR_EMAIL", "") or ""
        inv_pass = getattr(settings, "INVESTIGATOR_PASSWORD", "") or ""
        if self.investigators.count() == 0 and inv_email and inv_pass:
            tenant_id = getattr(settings, "INVESTIGATOR_TENANT_ID", "") or ""
            if not tenant_id:
                tenants = self.tenants.list()
                tenant_id = next((t["tenant_id"] for t in tenants if t["status"] == "active"),
                                 "platform")
            self.investigators.create(tenant_id, inv_email,
                                      getattr(settings, "INVESTIGATOR_NAME", "") or "محقق الاحتيال",
                                      inv_pass)
            logger.info("investigator.bootstrapped", email=inv_email,
                        tenant_id=tenant_id)

        # 3. Seed default rules from YAML into DB
        rules_path = Path(__file__).parent.parent / "rules" / "default_ruleset.yaml"
        if rules_path.exists():
            spec = yaml.safe_load(rules_path.read_text())
            seeded = self.rule_repo.seed_defaults(spec.get("rules", []))
            if seeded:
                logger.info("rules.seeded", count=seeded)

        # 4. Seed default watchlists
        self.watchlist_repo.seed_defaults()

        # 5. Rule engine (loads from DB — platform + tenant rules)
        all_rules = self.rule_repo.list_all()
        self.rule_engine = RuleEngine(rules=all_rules)
        logger.info("rule_engine.loaded", count=len(all_rules))

        # 6. ML scorer (real model if trained, heuristic fallback)
        self.ml_scorer = EnsembleScorer()

        # 7. Graph engine (bootstrap from recent transactions)
        self.graph_engine = GraphEngine()
        recent_txs = self.transactions.list_recent(limit=2000)
        self.graph_engine.bootstrap(recent_txs)

        # 8. AML service
        self.aml_service = AMLService(self.watchlist_repo)

        # 9. Feature extractor
        self.features = FeatureExtractor(self.transactions, self.decisions)

        # 9b. Currencies + FX reference store + FX service (multi-currency layer)
        self.currencies = CurrencyRepository(self.db)
        self.fx_rates = FxRateRepository(self.db)
        seeded_ccy = self.currencies.seed_defaults()
        if seeded_ccy:
            logger.info("currencies.seeded", count=seeded_ccy)
        self._seed_default_fx()
        self.fx_service = FxService(self.fx_rates,
                                    currency_checker=self.currencies.is_known)

        # 10. Audit + events + notifications
        self.audit = AuditService(self.audit_repo)
        self.events = EventBus()
        self.notifications = ConsoleNotificationProvider()

        # 10b. Policy engine — tenant policy_json becomes effective at decision time
        self.policy_engine = PolicyEngine()

        # 11. Orchestrator (unified pipeline) — FX + policy wired in
        self.orchestrator = DecisionOrchestrator(
            rules=self.rule_engine, ml=self.ml_scorer, graph=self.graph_engine,
            aml_service=self.aml_service, features=self.features,
            transactions=self.transactions, decisions=self.decisions,
            alerts=self.alerts, cases=self.cases,
            audit=self.audit, events=self.events, notifications=self.notifications,
            fx_service=self.fx_service,
            policy_engine=self.policy_engine,
            tenants_repo=self.tenants,
        )
        logger.info("aegis.initialized", version=settings.VERSION)

    def _seed_default_fx(self) -> None:
        """Seed baseline reference rates (USD-centric) if fx_rates is empty.
        Yemen uses region-specific YER rates (aden/sanaa) — data-driven, not hardcoded
        into logic; these are just initial rows an operator can later override."""
        existing = self.db.query_one("SELECT COUNT(*) AS c FROM fx_rates")
        if existing and existing["c"]:
            return
        ref = settings.REFERENCE_CURRENCY  # USD
        disp = settings.DISPLAY_CURRENCY   # YER
        # How many USD per 1 unit of currency (base=ccy, quote=USD).
        # SAR pegged 3.75/USD => 1 SAR = 0.2667 USD.
        self.fx_rates.add("SAR", ref, 1.0/3.75, rate_type="official",
                          source="aegis_reference", region="global")
        # YER: divergent official/market reality — provide regional reference rows.
        # Values are operator-updatable; these are conservative starting points.
        self.fx_rates.add("YER", ref, 1.0/1570.0, rate_type="mid",
                          source="aegis_reference", region="aden")
        self.fx_rates.add("YER", ref, 1.0/600.0, rate_type="mid",
                          source="aegis_reference", region="sanaa")
        self.fx_rates.add("YER", ref, 1.0/1570.0, rate_type="mid",
                          source="aegis_reference", region="global")
        # USD -> YER display conversion (for local display reference).
        self.fx_rates.add(ref, disp, 1570.0, rate_type="mid",
                          source="aegis_reference", region="aden")
        self.fx_rates.add(ref, disp, 600.0, rate_type="mid",
                          source="aegis_reference", region="sanaa")
        self.fx_rates.add(ref, disp, 1570.0, rate_type="mid",
                          source="aegis_reference", region="global")
        logger.info("fx.seeded_defaults")

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
