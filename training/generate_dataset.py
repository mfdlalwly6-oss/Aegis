"""Generate synthetic fraud dataset for training/demo purposes.
⚠️ SYNTHETIC DATA ONLY — no real persons/accounts. For development & testing.
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "models" / "synthetic_fraud_dataset.csv"
OUT.parent.mkdir(parents=True, exist_ok=True)
random.seed(42)

FIELDS = [
    "amount", "hour_sin", "hour_cos", "tx_per_min", "amount_5m",
    "distinct_merchants_1h", "new_device", "shared_device_count",
    "shared_ip_count", "impossible_travel", "high_risk_country",
    "new_beneficiary", "seconds_since_password_change", "previous_declines",
    "previous_chargebacks", "high_risk_merchant", "off_hours",
    "round_amount", "structuring_pattern", "suspicious_events_30d", "label",
]
# NOTE: field order MUST match features.FeatureExtractor.vector() output order.


def make_row(fraud: bool) -> list:
    hour = random.randint(0, 23)
    amount = random.uniform(5, 2500)
    tx_per_min = random.randint(0, 3)
    amount_5m = amount + random.uniform(0, 1200)
    distinct_merchants = random.randint(1, 3)
    new_device = random.choice([0, 0, 0, 1])
    shared_device = 0
    shared_ip = 0
    impossible = 0
    high_risk_country = 0
    new_beneficiary = random.choice([0, 1])
    seconds_since_pw = random.randint(50000, 800000)
    prev_declines = random.randint(0, 2)
    prev_chargebacks = 0
    high_risk_merchant = 0
    off_hours = 1 if hour < 6 or hour > 22 else 0
    round_amount = 1 if int(amount) % 1000 == 0 and amount >= 1000 else 0
    structuring = 0
    suspicious_events = random.randint(0, 1)
    if fraud:
        amount = random.uniform(1500, 25000)
        tx_per_min = random.randint(4, 12)
        amount_5m = amount + random.uniform(1500, 25000)
        distinct_merchants = random.randint(3, 9)
        new_device = random.choice([0, 1, 1])
        shared_device = random.randint(1, 5)
        shared_ip = random.randint(0, 5)
        impossible = random.choice([0, 1, 1])
        high_risk_country = random.choice([0, 1, 1])
        new_beneficiary = 1
        seconds_since_pw = random.randint(30, 1200)
        prev_declines = random.randint(1, 8)
        prev_chargebacks = random.randint(0, 3)
        high_risk_merchant = random.choice([0, 1, 1])
        off_hours = random.choice([0, 1, 1])
        round_amount = random.choice([0, 1])
        structuring = random.choice([0, 1])
        suspicious_events = random.randint(1, 6)
    return [
        round(amount, 2),
        round(math.sin((hour / 24) * 2 * math.pi), 6),
        round(math.cos((hour / 24) * 2 * math.pi), 6),
        tx_per_min, round(amount_5m, 2), distinct_merchants, new_device,
        shared_device, shared_ip, impossible, high_risk_country,
        new_beneficiary, seconds_since_pw, prev_declines, prev_chargebacks,
        high_risk_merchant, off_hours, round_amount, structuring,
        suspicious_events, int(fraud),
    ]


def main() -> None:
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for _ in range(3500):
            w.writerow(make_row(False))
        for _ in range(1500):
            w.writerow(make_row(True))
    print(f"dataset written: {OUT}")


if __name__ == "__main__":
    main()
