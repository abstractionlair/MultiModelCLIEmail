from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Preference(Enum):
    A = "A"
    B = "B"
    NEITHER = "NEITHER"


@dataclass
class Judgment:
    preferred: Preference
    confidence: float = 1.0
    reasoning: Optional[str] = None

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("confidence must be in [0,1]")


@dataclass
class EvaluationResult:
    judgments: List[Judgment]
    consensus: float = field(init=False)
    diversity: float = field(init=False)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        # Map preferences to signed votes: A=+1, B=-1, NEITHER=0
        total_w = 0.0
        weighted_sum = 0.0
        votes_abs_sum = 0.0
        for j in self.judgments:
            if j.preferred == Preference.A:
                v = 1.0
            elif j.preferred == Preference.B:
                v = -1.0
            else:
                v = 0.0
            w = j.confidence
            total_w += w
            weighted_sum += w * v
            votes_abs_sum += w * abs(v)

        if total_w > 0:
            signed_agree = weighted_sum / total_w
            # agreement magnitude relative to used weight only (ignore NEITHER weight)
            used_w = votes_abs_sum if votes_abs_sum > 0 else total_w
            mag = abs(weighted_sum) / used_w if used_w > 0 else 0.0
        else:
            signed_agree = 0.0
            mag = 0.0

        # consensus signed in [-1,1], diversity as 1 - |consensus|
        self.consensus = max(-1.0, min(1.0, signed_agree))
        self.diversity = 1.0 - max(0.0, min(1.0, mag))


class Evaluator:
    """Abstract base for pairwise evaluators on raw strings/objects.

    Implementations should define `judge(a, b)` returning Judgment.
    """

    id: str

    def __init__(self, id: str):
        self.id = id

    def judge(self, a, b) -> Judgment:
        raise NotImplementedError

