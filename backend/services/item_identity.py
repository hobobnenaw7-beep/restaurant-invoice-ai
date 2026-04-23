"""
Item Identity — Normalization & Matching Primitives (Milestone 19)
===================================================================

Lightweight, pure, side-effect-free helpers used by the canonical-linking
matcher. Kept separate from services/normalization.py (which is the older
food-domain invoice-extraction normalizer).

Public API:
    normalize_name(s)                 → str
    tokenize(s)                       → list[str]
    jaccard(a, b)                     → float  (0..1)
    fuzzy_ratio(a, b)                 → float  (0..1)
    split_base_and_variant(name, variants) → (base_str, variant_key|None)
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable, Optional


_PUNCT_RE = re.compile(r"[^A-Za-z0-9\s]+")
_WS_RE = re.compile(r"\s+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_ALPHA_NUM_RE = re.compile(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])")


def _split_merged(token: str) -> list[str]:
    """Conservatively split OCR-merged tokens like 'BlueCrab' → ['Blue','Crab']."""
    if not token:
        return []
    if len(token) < 2:
        return [token]
    parts = _CAMEL_RE.split(token)
    out: list[str] = []
    for p in parts:
        out.extend(_ALPHA_NUM_RE.split(p))
    return [p for p in out if p]


def normalize_name(s: Optional[str]) -> str:
    """Canonical-normalized form of a name (lowercase, clean, no punct)."""
    if not s:
        return ""
    txt = str(s).strip()
    tokens: list[str] = []
    for tok in _WS_RE.split(txt):
        tokens.extend(_split_merged(tok))
    txt = " ".join(tokens).lower()
    txt = _PUNCT_RE.sub(" ", txt)
    txt = _WS_RE.sub(" ", txt).strip()
    return txt


def tokenize(s: Optional[str]) -> list[str]:
    n = normalize_name(s)
    if not n:
        return []
    return [t for t in n.split(" ") if len(t) >= 2]


def jaccard(a: Optional[str], b: Optional[str]) -> float:
    A = set(tokenize(a))
    B = set(tokenize(b))
    if not A or not B:
        return 0.0
    inter = len(A & B)
    union = len(A | B)
    return inter / union if union else 0.0


def fuzzy_ratio(a: Optional[str], b: Optional[str]) -> float:
    na = normalize_name(a)
    nb = normalize_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def split_base_and_variant(
    name: str,
    variants: Iterable[dict],
) -> tuple[str, Optional[str]]:
    """
    Given a display name and a canonical's variants list
    (e.g. [{"key":"male","label":"Male"}]), return
    (base_after_variant_stripped, variant_key | None).

    Conservative: strips only if the variant key or label appears as a
    standalone token in the normalized name.
    """
    n = normalize_name(name)
    if not n or not variants:
        return (n, None)
    tokens = n.split(" ")
    token_set = set(tokens)
    for v in variants:
        key = (v.get("key") or "").strip().lower()
        label = (v.get("label") or "").strip().lower()
        hit = None
        if key and key in token_set:
            hit = key
        elif label and label in token_set:
            hit = label
        if hit is not None:
            base_tokens = [t for t in tokens if t != hit]
            return (" ".join(base_tokens).strip(), key or label or None)
    return (n, None)
