from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core_types import Candidate, EvaluationResult, Evaluator
from evaluator_ensemble import EvaluatorEnsemble, EnsembleConfig


class EvaluationAdapter:
    """Adapter to map rich ensemble results to QD-style scalar quality.

    Provides helper to duel a new candidate against a sample of archive
    candidates, then derive a scalar quality and ancillary features.
    """

    def __init__(self, ensemble: EvaluatorEnsemble):
        self.ensemble = ensemble

    def duel_against_archive(
        self,
        new_candidate: Candidate,
        archive_candidates: Sequence[Candidate],
        sample_size: int = 5,
        seed: Optional[int] = None,
    ) -> EvaluationResult:
        """Evaluate `new_candidate` via pairwise duels against sampled archive.

        Returns an EvaluationResult across the set {new_candidate} ∪ sample.
        """
        rng_seed = seed if seed is not None else self.ensemble.cfg.random_seed
        rng = __import__("random").Random(rng_seed)
        pool = list(archive_candidates)
        if sample_size and len(pool) > sample_size:
            pool = rng.sample(pool, sample_size)

        # Only duel focus vs sampled opponents (cheaper than full all-pairs)
        return self.ensemble.evaluate_focus(
            new_candidate,
            pool,
            early_stop=True,
            min_judges=1,
            threshold=0.9,
        )

    @staticmethod
    def to_quality(result: EvaluationResult, focus_id: str) -> Tuple[float, dict]:
        """Map rich result to a scalar quality for a specific candidate.

        Strategy (Option C from thread):
        - Primary quality: normalized BTL score for `focus_id` (0..1)
        - Secondary features: include diversity (1-consensus) and rank position
        """
        score = float(result.scores.get(focus_id, 0.0))
        # Normalize relative to max observed to keep in [0,1]
        max_s = max(result.scores.values()) if result.scores else 1.0
        norm_quality = score / max(max_s, 1e-12)

        # Rank position (1 = best)
        try:
            rank_pos = result.ranking.index(focus_id) + 1
        except ValueError:
            rank_pos = len(result.ranking)

        meta = {
            "diversity": result.diversity,
            "consensus": result.consensus,
            "rank": rank_pos,
            "scores": result.scores,
        }
        return norm_quality, meta
