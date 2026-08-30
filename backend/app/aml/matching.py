"""Watchlist matching engine — exact + trigram-fuzzy name matching with
secondary-attribute scoring (country/dob/identifiers) to cut false positives.

Design notes (from AML screening best practice):
- Never treat "name == name" as the only signal; a fuzzy score alone is a
  *candidate*, and secondary attributes raise/lower confidence.
- Country/identifier fields use exact match (they are codes, not names).
- All matching is read-only against active, in-window entries.
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^0-9a-zA-Z\u0600-\u06FF ]+")


def normalize_name(value: str | None) -> str:
    """Uppercase, strip diacritics/punct, collapse whitespace."""
    if not value:
        return ""
    v = unicodedata.normalize("NFKD", str(value))
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = _NON_ALNUM.sub(" ", v)
    return _WS.sub(" ", v).strip().upper()


def _name_similarity(a: str, b: str) -> float:
    """Token-aware similarity: best of full-string ratio and token-set overlap."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    full = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return full
    inter = ta & tb
    union = ta | tb
    jaccard = len(inter) / len(union)
    # containment handles partial-name hits ("MOHAMED ALI" vs "MOHAMED ALI HASSAN")
    contain = len(inter) / min(len(ta), len(tb))
    return max(full, jaccard, contain * 0.92)


def _aliases(entry: dict) -> list[str]:
    try:
        raw = entry.get("aliases_json") or "[]"
        return [x for x in json.loads(raw) if isinstance(x, str) and x.strip()]
    except Exception:
        return []


def _identifiers(entry: dict) -> dict:
    try:
        return json.loads(entry.get("identifiers_json") or "{}")
    except Exception:
        return {}


def score_entry(query_name: str, entry: dict, *, context: dict[str, Any] | None = None,
                fuzzy_threshold: float = 0.85) -> dict | None:
    """Score one entry against a query name. Returns a match dict or None.

    match strength: exact(1.0) / alias(1.0) / fuzzy(threshold..1.0 adjusted
    by secondary attributes). Secondary attributes only *adjust* confidence,
    they never create a match on their own.
    """
    context = context or {}
    q = normalize_name(query_name)
    if not q:
        return None
    primary = normalize_name(entry.get("value"))
    names = [primary] + [normalize_name(a) for a in _aliases(entry)]
    best = 0.0
    best_kind = None
    best_on = None
    for n in names:
        if not n:
            continue
        if n == q:
            return {"entry": entry, "score": 1.0, "match_type": "exact" if n == primary else "alias",
                    "matched_on": entry.get("value"), "secondary": {}}
        s = _name_similarity(q, n)
        if s > best:
            best, best_kind, best_on = s, "fuzzy", n
    if best < fuzzy_threshold:
        return None

    # secondary attribute adjustment (evidence, explainable)
    sec: dict[str, Any] = {}
    adj = 0.0
    q_country = (context.get("country") or "").upper() or None
    e_country = (entry.get("country") or "").upper() or None
    if q_country and e_country:
        sec["country"] = "match" if q_country == e_country else "mismatch"
        adj += 0.05 if q_country == e_country else -0.10
    q_dob = (context.get("dob") or "").strip() or None
    e_dob = (entry.get("dob") or "").strip() or None
    if q_dob and e_dob:
        sec["dob"] = "match" if q_dob == e_dob else "mismatch"
        adj += 0.07 if q_dob == e_dob else -0.15
    q_ids = context.get("identifiers") or {}
    e_ids = _identifiers(entry)
    id_hits = [k for k in q_ids if k in e_ids and str(q_ids[k]).strip().upper() == str(e_ids[k]).strip().upper()]
    if id_hits:
        sec["identifiers"] = id_hits
        adj += 0.10
    score = max(0.0, min(1.0, best + adj))
    return {"entry": entry, "score": round(score, 4), "match_type": best_kind,
            "matched_on": best_on, "secondary": sec}


def match_name(query_name: str, candidates: list[dict], *, context: dict[str, Any] | None = None,
               fuzzy_threshold: float = 0.85, limit: int = 5) -> list[dict]:
    """Rank candidate entries for a name; returns top matches, best first."""
    out = []
    for e in candidates:
        m = score_entry(query_name, e, context=context, fuzzy_threshold=fuzzy_threshold)
        if m:
            out.append(m)
    out.sort(key=lambda m: -m["score"])
    return out[:limit]
