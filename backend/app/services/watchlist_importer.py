"""Validated, source-neutral UTF-8 CSV watchlist importer."""

from __future__ import annotations

import csv
import io
import re

_TYPES = {"sanctions", "pep", "high_risk_country"}


def _value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()


def import_csv(repo, tenant_id: str, content: bytes) -> dict:
    try:
        text = content.decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(text))
    except (UnicodeDecodeError, csv.Error):
        return {"total_rows": 0, "imported_rows": 0, "skipped_rows": 0, "duplicate_rows": 0}
    if not rows.fieldnames or not {"list_type", "value"}.issubset(set(rows.fieldnames)):
        raise ValueError("required_columns: list_type,value")
    result = {"total_rows": 0, "imported_rows": 0, "skipped_rows": 0, "duplicate_rows": 0}
    for row in rows:
        result["total_rows"] += 1
        kind, value = (row.get("list_type") or "").strip().lower(), _value(row.get("value") or "")
        if kind not in _TYPES or not value or len(value) > 300:
            result["skipped_rows"] += 1
            continue
        meta = {k: v.strip() for k, v in row.items() if k not in {"list_type", "value"} and v and v.strip()}
        if repo.add(kind, value, meta, tenant_id):
            result["imported_rows"] += 1
        else:
            result["duplicate_rows"] += 1
    return result
