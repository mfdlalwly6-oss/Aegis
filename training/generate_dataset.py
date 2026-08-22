"""Generate synthetic fraud dataset for pipeline validation.

⚠️ SYNTHETIC DATA ONLY — no real persons/accounts/transactions.
Purpose: validate the ML pipeline mechanics (training, evaluation, drift
instrumentation). NOT a substitute for real labeled fraud data.

Output columns MUST match FeatureExtractor.vector() output order (23 features),
plus `currency` (for per-currency evaluation only — never a model feature),
plus `day` (synthetic time index for temporal split), plus `label`.
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "models" / "synthetic_fraud_dataset.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)
random.seed(42)

# 23 features — order MUST match features.FeatureExtractor.vector().
FEATURES = [
    "amount_ref",              # currency-normalized reference value (log-friendly)
    "hour_sin", "hour_cos",
    "tx_per_min_card", "amount_5min_account", "distinct_merchants_1h",
    "new_device", "shared_device_count", "shared_ip_count",
    "impossible_travel", "high_risk_country", "new_beneficiary",
    "seconds_since_password_change", "previous_declines", "previous_chargebacks",
    "high_risk_merchant", "off_hours", "is_round_native",
    "structuring_gt2", "suspicious_events_30d",
    "cross_currency_count_24h", "unique_beneficiaries_24h", "unique_devices_24h",
]

CURRENCIES = ["USD", "SAR", "YER"]


def make_row(fraud: bool, day: int) -> list:
    hour = random.randint(0, 23)
    # amount_ref is the NORMALIZED value — same scale regardless of currency,
    # so the model cannot learn "YER = risky".
    amount_ref = random.uniform(5, 2500)
    tx_per_min = random.randint(0, 3)
    amount_5m = amount_ref + random.uniform(0, 1200)
    merchants = random.randint(1, 3)
    new_device = random.choice([0, 0, 0, 1])
    shared_dev = 0
    shared_ip = 0
    impossible = 0
    high_risk = 0
    new_ben = random.choice([0, 1])
    pw_secs = random.randint(50000, 800000)
    declines = random.randint(0, 2)
    chargebacks = 0
    risky_merchant = 0
    off_hours = 1 if (hour < 6 or hour > 22) else 0
    round_native = random.choice([0, 0, 1])
    structuring = 0
    suspicious = random.randint(0, 1)
    cross_ccy = random.choice([1, 1, 1, 2])   # normal users routinely use 1-2
    uniq_ben = random.randint(1, 3)
    uniq_dev = random.choice([1, 1, 1, 2])

    if fraud:
        amount_ref = random.choice([
            random.uniform(9000, 9900),      # structuring band
            random.uniform(5000, 40000),     # high value
        ])
        tx_per_min = random.randint(4, 12)
        amount_5m = amount_ref * random.uniform(1.5, 4)
        merchants = random.randint(5, 12)
        new_device = 1
        shared_dev = random.randint(2, 6)
        shared_ip = random.randint(1, 5)
        impossible = random.choice([0, 1])
        high_risk = random.choice([0, 0, 1])
        new_ben = 1
        pw_secs = random.randint(10, 590)     # password just changed
        declines = random.randint(3, 10)
        risky_merchant = random.choice([0, 1])
        off_hours = random.choice([0, 1, 1])
        round_native = random.choice([0, 1])
        structuring = random.choice([0, 1, 1])
        suspicious = random.randint(2, 12)
        cross_ccy = random.choice([2, 3, 3])  # layering across currencies
        uniq_ben = random.randint(3, 10)
        uniq_dev = random.randint(2, 6)

    return [
        round(amount_ref, 2),
        round(math.sin((hour / 24) * 2 * math.pi), 6),
        round(math.cos((hour / 24) * 2 * math.pi), 6),
        tx_per_min, round(amount_5m, 2), merchants,
        new_device, shared_dev, shared_ip,
        impossible, high_risk, new_ben,
        pw_secs, declines, chargebacks,
        risky_merchant, off_hours, round_native,
        structuring, suspicious,
        cross_ccy, uniq_ben, uniq_dev,
        random.choice(CURRENCIES),   # currency: evaluation slicing only
        day,                          # synthetic time index for temporal split
        int(fraud),
    ]


def main() -> None:
    rows = []
    n_days = 60
    for day in range(n_days):
        # class balance drifts slightly over time (mimics real distribution shift)
        fraud_share = 0.12 + (0.04 * math.sin(day / 9.0))
        n = 200
        for _ in range(n):
            rows.append(make_row(random.random() < fraud_share, day))
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FEATURES + ["currency", "day", "label"])
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {OUT} (synthetic; {n_days} days; features={len(FEATURES)})")


if __name__ == "__main__":
    main()
