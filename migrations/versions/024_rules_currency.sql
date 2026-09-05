-- 024_rules_currency.sql
-- §5: every financial rule declares the currency its thresholds are expressed in
-- (USD/SAR/YER...). NULL => non-financial rule. The rule engine evaluates money
-- comparisons against features.amount_usd (normalized by the FX resolver using
-- the same precedence chain), so a USD threshold applies directly to USD
-- transactions and converts YER/SAR through the resolved rate — never the reverse.

ALTER TABLE rules ADD COLUMN IF NOT EXISTS currency TEXT;
ALTER TABLE rule_overrides ADD COLUMN IF NOT EXISTS currency TEXT;
