"""Repository layer — all DB access goes through these classes.
Never call app.db.Database directly from routers/services.
"""
from .tenant_repo import TenantRepository
from .transaction_repo import TransactionRepository
from .decision_repo import DecisionRepository
from .alert_repo import AlertRepository
from .case_repo import CaseRepository
from .audit_repo import AuditRepository
from .rule_repo import RuleRepository
from .watchlist_repo import WatchlistRepository
from .user_repo import UserRepository

__all__ = [
    "TenantRepository", "TransactionRepository", "DecisionRepository",
    "AlertRepository", "CaseRepository", "AuditRepository",
    "RuleRepository", "WatchlistRepository", "UserRepository",
]
