from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core_types import Judgment


def _tally_pairwise(judgments: Iterable[Judgment]) -> Tuple[Dict[Tuple[str, str], float], Dict[str, float]]:
    """Accumulate weighted win/loss counts from judgments.

    Returns:
        w_ij: dict keyed by (i, j) with weighted wins of i over j
        wins: dict of total weighted wins per candidate
    Ties split weight equally between both candidates.
    """
    w_ij: Dict[Tuple[str, str], float] = defaultdict(float)
    wins: Dict[str, float] = defaultdict(float)

    for j in judgments:
        conf = max(0.0, min(1.0, j.confidence or 0.0))
        a, b = j.a_id, j.b_id
        if j.winner is None:
            w_ij[(a, b)] += 0.5 * conf
            w_ij[(b, a)] += 0.5 * conf
            wins[a] += 0.5 * conf
            wins[b] += 0.5 * conf
        elif j.winner == a:
            w_ij[(a, b)] += conf
            wins[a] += conf
        elif j.winner == b:
            w_ij[(b, a)] += conf
            wins[b] += conf
        else:
            # Defensive: unknown winner id, ignore
            continue

    return w_ij, wins


def bradley_terry_luce(
    judgments: Iterable[Judgment],
    candidates: Sequence[str],
    max_iter: int = 100,
    tol: float = 1e-6,
) -> Dict[str, float]:
    """Estimate BTL strengths from pairwise judgments using MM updates.

    If no information is available for a candidate, it maintains its prior (1.0).
    Output is normalized to sum to 1.0 for interpretability.
    """
    cands = list(candidates)
    w_ij, wins = _tally_pairwise(judgments)

    # Build symmetric match counts n_ij
    n_ij: Dict[Tuple[str, str], float] = defaultdict(float)
    for (i, j), w in list(w_ij.items()):
        n_ij[(i, j)] += w
        n_ij[(j, i)] += w_ij.get((j, i), 0.0)

    # Initialize strengths
    r = {c: 1.0 for c in cands}

    for _ in range(max_iter):
        delta = 0.0
        r_new = r.copy()
        for i in cands:
            w_i = wins.get(i, 0.0)
            denom = 0.0
            for j in cands:
                if i == j:
                    continue
                nij = n_ij.get((i, j), 0.0)
                if nij <= 0.0:
                    continue
                denom += nij / max(r[i] + r[j], 1e-12)
            if denom > 0.0:
                r_new[i] = w_i / denom
            else:
                r_new[i] = r[i]
            delta = max(delta, abs(r_new[i] - r[i]))
        r = r_new
        if delta < tol:
            break

    # Normalize to sum=1 for convenience
    s = sum(r.values()) or 1.0
    return {k: (v / s) for k, v in r.items()}


def agreement_metrics(judgments: Iterable[Judgment]) -> Tuple[float, Dict[Tuple[str, str], float]]:
    """Compute simple agreement across evaluators per pair and average.

    For each (a,b), compute signed agreement in [-1,1] by averaging winner
    directions weighted by confidence; then take absolute value as an agreement
    magnitude for the pair. Return (avg_agreement, per_pair_agreement).
    """
    per_pair_votes: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for j in judgments:
        conf = max(0.0, min(1.0, j.confidence or 0.0))
        a, b = j.a_id, j.b_id
        if j.winner is None:
            vote = 0.0
        elif j.winner == a:
            vote = +1.0
        elif j.winner == b:
            vote = -1.0
        else:
            continue
        per_pair_votes[(a, b)].append(conf * vote)

    per_pair_agree: Dict[Tuple[str, str], float] = {}
    mags: List[float] = []
    for pair, votes in per_pair_votes.items():
        if not votes:
            continue
        s = sum(votes)
        # Normalize by total confidence weight; clamp to [-1,1]
        w = sum(abs(v) for v in votes) or 1.0
        signed = max(-1.0, min(1.0, s / w))
        mag = abs(signed)
        per_pair_agree[pair] = mag
        mags.append(mag)

    avg_agreement = sum(mags) / len(mags) if mags else 0.0
    return avg_agreement, per_pair_agree


# ============================================================================
# Incremental BTL context
# ============================================================================

class BTLContext:
    """Maintain incremental pairwise tallies and compute BTL strengths on demand.

    Usage:
        ctx = BTLContext()
        ctx.update(new_judgments)
        scores = ctx.scores(["A","B","C"])  # candidates of interest

    Notes:
    - Tallies are accumulated confidence-weighted; ties split weight.
    - New candidates can be added at any time (cold start handled via priors).
    - For cold start, strengths default to 1.0 and are updated as data arrives.
    """

    def __init__(self):
        from collections import defaultdict as _dd
        self._w_ij: Dict[Tuple[str, str], float] = _dd(float)
        self._wins: Dict[str, float] = _dd(float)

    def update(self, judgments: Iterable[Judgment]) -> None:
        for j in judgments:
            conf = max(0.0, min(1.0, j.confidence or 0.0))
            a, b = j.a_id, j.b_id
            if j.winner is None:
                self._w_ij[(a, b)] += 0.5 * conf
                self._w_ij[(b, a)] += 0.5 * conf
                self._wins[a] += 0.5 * conf
                self._wins[b] += 0.5 * conf
            elif j.winner == a:
                self._w_ij[(a, b)] += conf
                self._wins[a] += conf
            elif j.winner == b:
                self._w_ij[(b, a)] += conf
                self._wins[b] += conf
            # else: ignore unknown winner id

    def scores(self, candidates: Sequence[str], max_iter: int = 100, tol: float = 1e-6) -> Dict[str, float]:
        from collections import defaultdict as _dd
        # Build symmetric match counts n_ij from internal tallies
        n_ij: Dict[Tuple[str, str], float] = _dd(float)
        for (i, j), w in list(self._w_ij.items()):
            n_ij[(i, j)] += w
            n_ij[(j, i)] += self._w_ij.get((j, i), 0.0)

        r = {c: 1.0 for c in candidates}
        wins = self._wins
        for _ in range(max_iter):
            delta = 0.0
            r_new = r.copy()
            for i in candidates:
                w_i = wins.get(i, 0.0)
                denom = 0.0
                for j in candidates:
                    if i == j:
                        continue
                    nij = n_ij.get((i, j), 0.0)
                    if nij <= 0.0:
                        continue
                    denom += nij / max(r[i] + r[j], 1e-12)
                r_new[i] = (w_i / denom) if denom > 0.0 else r[i]
                delta = max(delta, abs(r_new[i] - r[i]))
            r = r_new
            if delta < tol:
                break
        s = sum(r.values()) or 1.0
        return {k: (v / s) for k, v in r.items()}
