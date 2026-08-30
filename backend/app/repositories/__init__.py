"""Repository layer — all DB access goes through these classes.
Never call app.db.Database directly from routers/services.
"""

from .alert_approval_repo import AlertApprovalRepository
from .alert_repo import AlertRepository
from .audit_repo import AuditRepository
from .case_repo import CaseRepository
from .decision_repo import DecisionRepository
from .investigator_repo import InvestigatorRepository
from .policy_repo import PolicyVersionRepository
from .rule_repo import RuleRepository
from .tenant_repo import TenantRepository
from .transaction_repo import TransactionRepository
from .user_repo import UserRepository
from .watchlist_repo import WatchlistRepository

__all__ = [
    "TenantRepository",
    "TransactionRepository",
    "DecisionRepository",
    "AlertRepository",
    "AlertApprovalRepository",
    "CaseRepository",
    "AuditRepository",
    "RuleRepository",
    "PolicyVersionRepository",
    "WatchlistRepository",
    "UserRepository",
    "InvestigatorRepository",
]
