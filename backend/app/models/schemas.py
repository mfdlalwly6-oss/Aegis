"""Pydantic domain schemas — the contract for the fraud pipeline."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress


class Channel(str, Enum):
    CARD_PRESENT = "card_present"
    CARD_NOT_PRESENT = "card_not_present"
    WIRE = "wire"
    ACH = "ach"
    P2P = "p2p"
    WALLET = "wallet"
    CRYPTO = "crypto"
    SWIFT = "swift"
    RTP = "rtp"


class Decision(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"
    CHALLENGE = "challenge"


class RiskBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FxStatus(str, Enum):
    OK = "ok"
    NATIVE = "native"
    STALE = "stale"
    DIVERGENT = "divergent"
    MISSING = "missing"


class FxSnapshot(BaseModel):
    rate_id: str | None = None  # links to fx_rates.rate_id for audit traceability
    base_ccy: str
    quote_ccy: str
    rate: float | None = None
    rate_type: str = "mid"
    source: str = "aegis_reference"
    region: str = "global"
    spread_pct: float | None = None
    fetched_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    is_stale: bool = False
    status: FxStatus = FxStatus.OK
    institution_rate: float | None = None
    divergence_pct: float | None = None


class Money(BaseModel):
    original_amount: float
    original_currency: str
    reference_amount: float | None = None
    reference_currency: str = "USD"
    fx: FxSnapshot | None = None


class DeviceContext(BaseModel):
    device_id: str | None = None
    fingerprint_hash: str | None = None
    user_agent: str | None = None
    os: str | None = None
    browser: str | None = None
    ip: IPvAnyAddress | None = None
    ip_country: str | None = None
    vpn: bool | None = None
    tor: bool | None = None
    proxy: bool | None = None


class BehaviorSignals(BaseModel):
    keystroke_entropy: float | None = None
    session_duration_ms: int | None = None
    biometric_match_score: float | None = Field(None, ge=0.0, le=1.0)


class GeoPoint(BaseModel):
    lat: float
    lon: float
    country: str | None = None
    city: str | None = None


class Transaction(BaseModel):
    """Universal transaction schema — accepts card, wire, wallet, P2P, crypto."""
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"example": {
            "amount": 199.99, "currency": "USD", "channel": "wallet",
            "sender_account_id": "acct_1", "beneficiary_account_id": "acct_2",
        }})

    tx_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str = "default"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    channel: Channel = Channel.WALLET
    amount: float = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)

    sender_account_id: str
    sender_user_id: str | None = None
    beneficiary_account_id: str
    beneficiary_user_id: str | None = None
    beneficiary_bank: str | None = None
    beneficiary_country: str | None = None

    card_bin: str | None = None
    card_last4: str | None = None
    mcc: str | None = None
    merchant_id: str | None = None
    merchant_name: str | None = None

    device: DeviceContext | None = None
    behavior: BehaviorSignals | None = None
    geo: GeoPoint | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = {}

    # FX / Money normalization (populated by FxService at ingestion time)
    reference_amount: float | None = None
    reference_currency: str | None = None
    fx_snapshot_id: str | None = None
    fx_status: str | None = None  # ok | native | stale | divergent | missing


class RuleHit(BaseModel):
    rule_id: str
    name: str
    severity: str
    score_contribution: float
    reason: str


class ModelScore(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_name: str
    model_version: str
    probability: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = []


class GraphSignal(BaseModel):
    score: float = 0.0
    reason: str | None = None
    shared_device_count: int = 0
    shared_ip_count: int = 0
    linked_accounts: int = 0
    ring_size: int | None = None
    hops_to_known_fraud: int | None = None
    pagerank_score: float | None = None


class AMLSignal(BaseModel):
    sanctions_hit: bool = False
    pep_hit: bool = False
    adverse_media_hit: bool = False
    typology_matches: list[str] = []
    fatf_high_risk_country: bool = False
    score: float = 0.0
    risk_flags: list[str] = []


class RiskAssessment(BaseModel):
    """The final unified risk assessment returned to the caller."""
    model_config = ConfigDict(protected_namespaces=())
    tx_id: str
    tenant_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decision: Decision
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_band: RiskBand
    latency_ms: float

    # Component scores
    rule_score: float = 0.0
    ml_score: float = 0.0
    graph_score: float = 0.0
    aml_score: float = 0.0
    behavior_score: float = 0.0

    # Component signals
    rules: list[RuleHit] = []
    ml_models: list[ModelScore] = []
    graph_signal: GraphSignal = Field(default_factory=GraphSignal)
    aml_signal: AMLSignal = Field(default_factory=AMLSignal)

    # Explainability
    top_reasons: list[str] = []
    typology: str | None = None
    reasoning_ar: str | None = None
    ai_model: str | None = None
    model_id: str | None = None
    policy_version: str | None = None

    # DecisionTrace / audit snapshots (populated by orchestrator before persist)
    fx_proof: dict[str, Any] = {}
    tx_snapshot: dict[str, Any] = {}
    features_snapshot: dict[str, Any] = {}
