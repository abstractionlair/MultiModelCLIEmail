from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core_types import Candidate, EvaluationResult, Evaluator, Judgment
from pairwise import bradley_terry_luce, agreement_metrics


@dataclass
class EnsembleConfig:
    judges_per_pair: int = 3
    rotate_judges: bool = True
    random_seed: Optional[int] = None


class EvaluatorEnsemble:
    """Ensemble-native evaluation with pairwise comparison and aggregation.

    - Pairwise judgments from multiple evaluators
    - BTL aggregation for continuous strengths
    - Agreement metrics for consensus/diversity
    """

    def __init__(self, evaluators: Sequence[Evaluator], config: Optional[EnsembleConfig] = None):
        self.evaluators = list(evaluators)
        self.cfg = config or EnsembleConfig()
        self._rng = random.Random(self.cfg.random_seed)

    def _select_judges(self) -> List[Evaluator]:
        if not self.evaluators:
            return []
        k = min(len(self.evaluators), max(1, self.cfg.judges_per_pair))
        if self.cfg.rotate_judges and k < len(self.evaluators):
            return self._rng.sample(self.evaluators, k)
        return self.evaluators[:k]

    def evaluate_batch(self, candidates: Sequence[Candidate]) -> EvaluationResult:
        """Evaluate a batch via pairwise duels and aggregate results.

        Returns an EvaluationResult with per-candidate scores and ranking.
        """
        cands = list(candidates)
        judgments: List[Judgment] = []
        trace: List[dict] = []
        for a, b in itertools.combinations(cands, 2):
            judges = self._select_judges()
            for j in judges:
                try:
                    jud = j.compare(a, b)
                    judgments.append(jud)
                    trace.append({
                        "ts": time.time(),
                        "pair": (a.id, b.id),
                        "judge_id": j.id,
                        "winner": jud.winner,
                        "confidence": jud.confidence,
                        "notes": jud.notes,
                    })
                except Exception as ex:
                    # Defensive: record a neutral tie with low confidence
                    jud = Judgment(
                        judge_id=j.id,
                        a_id=a.id,
                        b_id=b.id,
                        winner=None,
                        confidence=0.0,
                        notes=f"error: {type(ex).__name__}"
                    )
                    judgments.append(jud)
                    trace.append({
                        "ts": time.time(),
                        "pair": (a.id, b.id),
                        "judge_id": j.id,
                        "winner": None,
                        "confidence": 0.0,
                        "notes": f"error: {type(ex).__name__}",
                    })

        # Aggregate via BTL
        cand_ids = [c.id for c in cands]
        scores = bradley_terry_luce(judgments, cand_ids)
        ranking = sorted(cand_ids, key=lambda x: scores.get(x, 0.0), reverse=True)

        # Agreement/consensus metrics
        avg_agree, per_pair_agree = agreement_metrics(judgments)
        consensus = max(0.0, min(1.0, avg_agree))
        diversity = 1.0 - consensus

        return EvaluationResult(
            judgments=judgments,
            scores=scores,
            ranking=ranking,
            consensus=consensus,
            diversity=diversity,
            meta={
                "per_pair_agreement": per_pair_agree,
                "config": self.cfg.__dict__,
                "evaluation_trace": trace,
            },
        )

    def _pair_consensus(self, votes: List[Judgment]) -> float:
        # Return agreement magnitude in [0,1]
        if not votes:
            return 0.0
        s = 0.0
        wsum = 0.0
        for j in votes:
            v = 0.0
            if j.winner == j.a_id:
                v = +1.0
            elif j.winner == j.b_id:
                v = -1.0
            s += j.confidence * v
            wsum += j.confidence * (1.0 if v != 0.0 else 0.0)
        if wsum <= 0:
            return 0.0
        return min(1.0, max(0.0, abs(s) / wsum))

    def evaluate_focus(
        self,
        focus: Candidate,
        opponents: Sequence[Candidate],
        *,
        early_stop: bool = True,
        min_judges: int = 1,
        threshold: float = 0.9,
    ) -> EvaluationResult:
        """Evaluate only duels between `focus` and each opponent.

        Supports early stopping per pair when agreement magnitude exceeds `threshold`
        and at least `min_judges` have judged the pair.
        """
        judgments: List[Judgment] = []
        trace: List[dict] = []
        for opp in opponents:
            judges = self._select_judges()
            pair_votes: List[Judgment] = []
            for idx, j in enumerate(judges):
                try:
                    jud = j.compare(focus, opp)
                except Exception as ex:
                    jud = Judgment(judge_id=j.id, a_id=focus.id, b_id=opp.id, winner=None, confidence=0.0, notes=f"error: {type(ex).__name__}")
                pair_votes.append(jud)
                judgments.append(jud)
                trace.append({
                    "ts": time.time(),
                    "pair": (focus.id, opp.id),
                    "judge_id": j.id,
                    "winner": jud.winner,
                    "confidence": jud.confidence,
                    "notes": jud.notes,
                })
                if early_stop and (idx + 1) >= min_judges:
                    if self._pair_consensus(pair_votes) >= threshold:
                        break

        # Aggregate via BTL on involved candidates only
        cand_ids = [focus.id] + [o.id for o in opponents]
        scores = bradley_terry_luce(judgments, cand_ids)
        ranking = sorted(cand_ids, key=lambda x: scores.get(x, 0.0), reverse=True)
        avg_agree, per_pair_agree = agreement_metrics(judgments)
        consensus = max(0.0, min(1.0, avg_agree))
        diversity = 1.0 - consensus
        return EvaluationResult(
            judgments=judgments,
            scores=scores,
            ranking=ranking,
            consensus=consensus,
            diversity=diversity,
            meta={
                "per_pair_agreement": per_pair_agree,
                "config": self.cfg.__dict__,
                "evaluation_trace": trace,
                "focus_id": focus.id,
            },
        )
