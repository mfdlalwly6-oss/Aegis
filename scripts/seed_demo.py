"""Seed demo tenant + synthetic test transactions into a running AEGIS instance.
Usage: python scripts/seed_demo.py [base_url] [owner_token]
"""
import hashlib
import hmac
import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
OWNER = sys.argv[2] if len(sys.argv) > 2 else "change-me-owner-token"


def req(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


def main():
    tenant = req("POST", "/api/v1/admin/tenants",
                 {"name": "Demo Wallet", "type": "wallet", "country": "YE", "plan": "sandbox"},
                 {"X-Owner-Token": OWNER})
    print("tenant:", tenant["tenant_id"], tenant["api_key"])

    scenarios = [
        ("tx_normal", {"amount": 120, "sender_account_id": "acct_demo_1", "beneficiary_account_id": "acct_shop_1"}),
        ("tx_high_amount", {"amount": 85000, "sender_account_id": "acct_demo_1", "beneficiary_account_id": "acct_x"}),
        ("tx_new_device", {"amount": 3200, "sender_account_id": "acct_demo_2", "beneficiary_account_id": "acct_y",
                           "device": {"device_id": "dev_new_9", "ip": "198.51.100.7"}}),
        ("tx_rapid", {"amount": 2500, "sender_account_id": "acct_demo_1", "beneficiary_account_id": "acct_z"}),
        ("tx_sanctioned", {"amount": 12000, "sender_account_id": "acct_demo_3", "beneficiary_account_id": "acct_ir",
                           "beneficiary_country": "IR"}),
        ("tx_structuring", {"amount": 9500, "sender_account_id": "acct_demo_1", "beneficiary_account_id": "acct_off"}),
    ]
    for tx_id, tx in scenarios:
        tx["tx_id"] = tx_id
        payload = json.dumps({"transaction": tx}, separators=(",", ":")).encode()
        sig = hmac.new(tenant["hmac_secret"].encode(), payload, hashlib.sha256).hexdigest()
        # manual raw request to control exact signed bytes
        request = urllib.request.Request(
            BASE + "/api/v1/wallet/webhook", data=payload, method="POST",
            headers={"Content-Type": "application/json", "X-API-Key": tenant["api_key"],
                     "X-Wallet-Signature": sig})
        with urllib.request.urlopen(request) as resp:
            out = json.loads(resp.read())
        print(tx_id, "→", out["decision"], out["risk_score"])


if __name__ == "__main__":
    main()
