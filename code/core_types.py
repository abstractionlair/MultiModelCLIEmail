from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence


@dataclass
class Context:
    """A generic, typed context for generation/evaluation.

    Intentionally minimal; domain-specific payloads live in `params`.
    """

    id: str
    prompt: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Candidate:
    """A candidate produced under a given context.

    `payload` carries domain-specific artifacts (e.g., code string, metadata,
    test hooks, or references to files). The ensemble/evaluators remain agnostic.
    """

    id: str
    context: Context
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Judgment:
    """A single evaluator's pairwise judgment between two candidates.

    - winner: Candidate ID of the winner or None for a tie.
    - confidence: 0.0..1.0 indicating evaluator confidence.
    - notes: Optional freeform rationale or diagnostics.
    """

    judge_id: str
    a_id: str
    b_id: str
    winner: Optional[str]
    confidence: float = 1.0
    notes: Optional[str] = None


@dataclass
class EvaluationResult:
    """Aggregate result from an ensemble evaluation.

    - judgments: Raw judgments emitted by individual evaluators.
    - scores: Optional per-candidate continuous scores (e.g., BTL strengths).
    - ranking: Candidate IDs ordered best→worst (ties allowed by stable ordering).
    - consensus: 0..1 agreement metric across evaluators (1 = perfect agreement).
    - diversity: 0..1 disagreement metric (typically 1 - consensus).
    - meta: Freeform diagnostics (e.g., agreement per pair, per-judge stats).
    """

    judgments: List[Judgment]
    scores: Dict[str, float]
    ranking: List[str]
    consensus: float
    diversity: float
    meta: Dict[str, Any] = field(default_factory=dict)


class Evaluator:
    """Abstract evaluator interface for pairwise comparison.

    Implementations should be deterministic for a given (a, b) input unless
    explicit stochasticity is desired. If stochastic, set `confidence` lower
    or perform internal averaging.
    """

    id: str

    def __init__(self, id: str):
        self.id = id

    def compare(self, a: Candidate, b: Candidate) -> Judgment:
        """Return a Judgment selecting a winner between a and b.

        Must set `winner` to either `a.id`, `b.id`, or None for a tie.
        """
        raise NotImplementedError


class CallableEvaluator(Evaluator):
    """Adapter to turn a unary scoring callable into a pairwise evaluator.

    The scoring function returns a float quality; higher is better. This is
    useful for testing and for domains with objective metrics.
    """

    def __init__(self, id: str, scorer: Callable[[Candidate], float], confidence: float = 1.0):
        super().__init__(id)
        self._scorer = scorer
        self._conf = max(0.0, min(1.0, confidence))

    def compare(self, a: Candidate, b: Candidate) -> Judgment:
        qa = float(self._scorer(a))
        qb = float(self._scorer(b))
        if qa > qb:
            winner = a.id
        elif qb > qa:
            winner = b.id
        else:
            winner = None
        return Judgment(
            judge_id=self.id,
            a_id=a.id,
            b_id=b.id,
            winner=winner,
            confidence=self._conf,
            notes=f"scores: {qa:.4f} vs {qb:.4f}"
        )

