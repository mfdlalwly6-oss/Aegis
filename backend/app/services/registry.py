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
    AlertRepository, AuditRepository, CaseRepository, DecisionRepository,
    InvestigatorRepository, RuleRepository, TenantRepository,
    TransactionRepository, UserRepository, WatchlistRepository,
)
from app.rules.engine import RuleEngine
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
        self.watchlist_repo = WatchlistRepository(self.db)
        self.user_repo = UserRepository(self.db)
        self.investigators = InvestigatorRepository(self.db)

        # Bootstrap a first investigator from env when none exists (dev convenience).
        if self.investigators.count() == 0 and settings.INVESTIGATOR_EMAIL and settings.INVESTIGATOR_PASSWORD:
            self.investigators.create(settings.INVESTIGATOR_EMAIL,
                                      settings.INVESTIGATOR_NAME,
                                      settings.INVESTIGATOR_PASSWORD)
            logger.info("investigator.bootstrapped", email=settings.INVESTIGATOR_EMAIL)

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

        # 10. Audit + events + notifications
        self.audit = AuditService(self.audit_repo)
        self.events = EventBus()
        self.notifications = ConsoleNotificationProvider()

        # 11. Orchestrator (unified pipeline)
        self.orchestrator = DecisionOrchestrator(
            rules=self.rule_engine, ml=self.ml_scorer, graph=self.graph_engine,
            aml_service=self.aml_service, features=self.features,
            transactions=self.transactions, decisions=self.decisions,
            alerts=self.alerts, cases=self.cases,
            audit=self.audit, events=self.events, notifications=self.notifications,
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
