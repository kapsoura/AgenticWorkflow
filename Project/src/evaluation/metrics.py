"""Pure, dependency-free scoring primitives for the evaluation harness.

Every function here is deterministic and side-effect-free so it can be unit
tested without the pipeline or an LLM backend.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Set


# ISO 13485 8.2.2 complaint categories that the pipeline treats as
# software-related (drives CAPA ground truth and software-relevance scoring).
SOFTWARE_CATEGORIES: Set[str] = {
    "SW-FUNC",
    "SW-ALGO",
    "SW-DATA",
    "IMG-QUAL",
    "IMG-RECON",
    "IMG-DISP",
}


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace for tolerant token matching."""
    return " ".join(str(text).lower().split())


def is_software_category(category: str) -> bool:
    """Whether an extracted complaint category indicates a software signal."""
    cat = str(category).strip().upper()
    if cat in SOFTWARE_CATEGORIES:
        return True
    return cat.startswith("SW-") or cat.startswith("IMG-")


def set_prf(predicted: Iterable[str], gold: Iterable[str]) -> Dict[str, float]:
    """Precision / recall / F1 over two token sets (case-insensitive)."""
    pred = {normalize(p) for p in predicted if str(p).strip()}
    truth = {normalize(g) for g in gold if str(g).strip()}
    if not pred and not truth:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not pred or not truth:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    overlap = len(pred & truth)
    precision = overlap / len(pred)
    recall = overlap / len(truth)
    f1 = 0.0 if (precision + recall) == 0 else (2 * precision * recall) / (precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def keyword_recall(keywords: Sequence[str], text: str) -> float:
    """Fraction of ``keywords`` that appear as substrings in ``text``.

    Returns 1.0 when no keywords are requested (nothing to miss).
    """
    if not keywords:
        return 1.0
    hay = normalize(text)
    hits = sum(1 for kw in keywords if normalize(kw) in hay)
    return hits / len(keywords)


def precision_at_k(relevance_flags: Sequence[bool], k: int) -> float:
    """Precision@k over an ordered list of relevance flags.

    Returns 0.0 when there are no retrieved items to evaluate.
    """
    if k <= 0:
        return 0.0
    window = list(relevance_flags)[:k]
    if not window:
        return 0.0
    return sum(1 for flag in window if flag) / len(window)


def mean(values: Iterable[float]) -> Optional[float]:
    """Arithmetic mean, or ``None`` for an empty sequence."""
    items = [float(v) for v in values]
    if not items:
        return None
    return sum(items) / len(items)


def accuracy(hits: Iterable[bool]) -> Optional[float]:
    """Fraction of truthy values, or ``None`` for an empty sequence."""
    items = list(hits)
    if not items:
        return None
    return sum(1 for h in items if h) / len(items)


def _as_count(value: object) -> int:
    """Coerce a count-like value (None / int / list / str) to a non-negative int."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, tuple, set)):
        return len(value)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def hallucination_rate(unsupported_claims: object, citation_count: object) -> float:
    """Share of cited-or-flagged claims that are unsupported.

    Accepts None / int / list (the critic may report a list of claims).
    Denominator is supported citations + unsupported claims; 0.0 when neither.
    """
    unsupported = _as_count(unsupported_claims)
    supported = _as_count(citation_count)
    total = supported + unsupported
    if total == 0:
        return 0.0
    return unsupported / total
