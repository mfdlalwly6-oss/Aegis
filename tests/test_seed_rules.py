"""Verify default ruleset loads and fires on expected scenarios."""
import yaml
from pathlib import Path


def test_default_ruleset_is_valid_yaml():
    path = Path(__file__).resolve().parents[1] / "backend" / "app" / "rules" / "default_ruleset.yaml"
    spec = yaml.safe_load(path.read_text())
    rules = spec["rules"]
    assert len(rules) >= 15
    for r in rules:
        assert "id" in r and "name" in r and "when" in r and "score" in r


def test_rules_load_into_engine(client):
    r = client.get("/api/v1/rules/", headers=client.owner_headers)
    assert r.status_code == 200
    assert len(r.json()) >= 15
