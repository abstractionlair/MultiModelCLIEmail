from __future__ import annotations

import random
from dataclasses import dataclass
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from evaluator_base import Evaluator, EvaluationResult


@dataclass
class JudgePool:
    evaluators: List[Evaluator]
    default_n_judges: int = 3

    def __post_init__(self):
        if len(self.evaluators) < 2:
            raise ValueError("JudgePool requires at least 2 evaluators")
        # Stable RNG for determinism where desired
        self._rng = random.Random(0)
        self._authors: Dict[str, str] = {}

    def register_author(self, content_id: str, author_id: str):
        self._authors[content_id] = author_id

    def select_judges(
        self,
        exclude_author_id: Optional[str] = None,
        n_judges: Optional[int] = None,
    ) -> List[Evaluator]:
        k = n_judges or self.default_n_judges
        pool = [e for e in self.evaluators if e.id != exclude_author_id]
        if len(pool) < k:
            # If exclusion makes it too small, reduce k
            k = max(1, len(pool))
        # Choose first k deterministically (could also randomize)
        return pool[:k]

    def evaluate_pair(
        self,
        a,
        b,
        *,
        candidate_a_id: Optional[str] = None,
        n_judges: Optional[int] = None,
    ) -> EvaluationResult:
        exclude_id = self._authors.get(candidate_a_id) if candidate_a_id else None
        judges = self.select_judges(exclude_author_id=exclude_id, n_judges=n_judges)
        judgments = []
        for j in judges:
            res = j.judge(a, b)
            if isinstance(res, tuple):
                judgments.append(res[0])
            else:
                judgments.append(res)
        result = EvaluationResult(judgments=judgments)
        # Attach simple evaluation trace (no timestamps on inputs available, use now)
        trace = []
        for j, jd in zip(judges, judgments):
            trace.append({
                "ts": time.time(),
                "judge_id": j.id,
                "preferred": jd.preferred.name,
                "confidence": jd.confidence,
            })
        result.metadata = {
            "judges_used": [j.id for j in judges],
            "excluded_author": exclude_id,
            "evaluation_trace": trace,
        }
        return result

    def evaluate_batch(
        self,
        pairs: Sequence[Tuple[Any, Any]],
        *,
        n_judges: Optional[int] = None,
    ) -> List[EvaluationResult]:
        results: List[EvaluationResult] = []
        for a, b in pairs:
            results.append(self.evaluate_pair(a, b, n_judges=n_judges))
        return results
