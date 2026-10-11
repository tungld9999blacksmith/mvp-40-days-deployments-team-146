"""Answer-quality text metrics.

Core (standard library): exact-match, token-F1, ROUGE-L. These suit Vietnamese
answers after light normalization. Optional metrics (BLEU, BERTScore) are
imported lazily so the suite runs without the extra packages; BLEU is kept as a
*reference-only* signal because n-gram matching is weak for Vietnamese
(spec #3.3).
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, NFC-normalize, strip punctuation and collapse whitespace."""
    text = unicodedata.normalize("NFC", text or "").casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def tokenize(text: str) -> list[str]:
    return normalize(text).split()


def exact_match(prediction: str, reference: str) -> float:
    """1.0 if normalized strings are identical, else 0.0 (spec #3.3)."""
    return 1.0 if normalize(prediction) == normalize(reference) else 0.0


def token_f1(prediction: str, reference: str) -> float:
    """SQuAD-style token overlap F1 on normalized tokens."""
    pred, ref = tokenize(prediction), tokenize(reference)
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    # Multiset intersection count.
    common = 0
    ref_counts: dict[str, int] = {}
    for tok in ref:
        ref_counts[tok] = ref_counts.get(tok, 0) + 1
    for tok in pred:
        if ref_counts.get(tok, 0) > 0:
            common += 1
            ref_counts[tok] -= 1
    if common == 0:
        return 0.0
    precision = common / len(pred)
    recall = common / len(ref)
    return 2 * precision * recall / (precision + recall)


def _lcs_length(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for token_a in a:
        curr = [0]
        for j, token_b in enumerate(b, 1):
            if token_a == token_b:
                curr.append(prev[j - 1] + 1)
            else:
                curr.append(max(prev[j], curr[j - 1]))
        prev = curr
    return prev[-1]


def rouge_l(prediction: str, reference: str, *, beta: float = 1.2) -> float:
    """ROUGE-L F-measure based on longest common subsequence (spec #3.3)."""
    pred, ref = tokenize(prediction), tokenize(reference)
    if not pred or not ref:
        return 0.0
    lcs = _lcs_length(pred, ref)
    if lcs == 0:
        return 0.0
    precision = lcs / len(pred)
    recall = lcs / len(ref)
    beta2 = beta * beta
    return (1 + beta2) * precision * recall / (recall + beta2 * precision)


# --- Optional heavy metrics (lazy, guarded) --------------------------------

def bleu(prediction: str, reference: str) -> float | None:
    """sacreBLEU sentence BLEU; None if the package is absent. Reference-only."""
    try:
        import sacrebleu  # type: ignore
    except Exception:
        return None
    return sacrebleu.sentence_bleu(prediction, [reference]).score / 100.0


def bert_score(prediction: str, reference: str, *, lang: str = "vi") -> float | None:
    """BERTScore F1; None if the package is absent. Preferred over BLEU for Vietnamese."""
    try:
        from bert_score import score as _score  # type: ignore
    except Exception:
        return None
    _, _, f1 = _score([prediction], [reference], lang=lang, verbose=False)
    return float(f1.mean())
