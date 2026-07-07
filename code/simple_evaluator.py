from __future__ import annotations

import math
import random
from typing import Iterable, List, Optional, Sequence

from evaluator_base import Evaluator, Judgment, Preference


class MockEvaluator(Evaluator):
    """Stochastic evaluator with optional preference bias.

    Same `id` yields deterministic behavior (seeded RNG) for identical inputs.
    """

    def __init__(
        self,
        id: str,
        preference_bias: Optional[Preference] = None,
        confidence_level: float = 0.8,
    ):
        super().__init__(id)
        self._bias = preference_bias
        self._conf = max(0.0, min(1.0, confidence_level))
        # Seed RNG on id for deterministic behavior
        self._rng = random.Random(hash(id) & 0xFFFFFFFF)

    def judge(self, a, b) -> Judgment:
        # Deterministic pseudo-random based on id and inputs to ensure stability
        h = hash((self.id, str(a), str(b))) & 0xFFFFFFFF
        rng = random.Random(h)
        r = rng.random()

        if self._bias == Preference.A:
            # Strongly prefer A deterministically; occasionally NEITHER
            pref = Preference.A if r < 0.95 else Preference.NEITHER
        elif self._bias == Preference.B:
            pref = Preference.B if r < 0.95 else Preference.NEITHER
        elif self._bias == Preference.NEITHER:
            pref = Preference.NEITHER if r < 0.8 else (Preference.A if r < 0.9 else Preference.B)
        else:
            pref = Preference.A if r < 0.5 else Preference.B
        return Judgment(preferred=pref, confidence=self._conf)


class LengthPreferenceEvaluator(Evaluator):
    """Prefers longer content; NEITHER if lengths are equal or near-equal."""

    def __init__(self, id: str, tolerance: int = 0):
        super().__init__(id)
        self._tol = max(0, tolerance)

    def judge(self, a: str, b: str) -> Judgment:
        la = len(a)
        lb = len(b)
        if abs(la - lb) <= self._tol:
            pref = Preference.NEITHER
        elif la > lb:
            pref = Preference.A
        else:
            pref = Preference.B
        # Confidence increases with length difference (bounded)
        diff = abs(la - lb)
        conf = max(0.5, min(1.0, 0.6 + 0.05 * diff))
        return Judgment(preferred=pref, confidence=conf)


class KeywordPreferenceEvaluator(Evaluator):
    """Prefers content containing more target keywords."""

    def __init__(self, id: str, keywords: Sequence[str]):
        super().__init__(id)
        self._kw = [k.lower() for k in keywords]

    def _score(self, s: str) -> int:
        text = s.lower()
        return sum(1 for k in self._kw if k in text)

    def judge(self, a: str, b: str) -> Judgment:
        sa = self._score(a)
        sb = self._score(b)
        if sa == sb:
            pref = Preference.NEITHER
        elif sa > sb:
            pref = Preference.A
        else:
            pref = Preference.B
        # Confidence based on keyword difference
        diff = abs(sa - sb)
        conf = max(0.6, min(1.0, 0.7 + 0.1 * diff))
        return Judgment(preferred=pref, confidence=conf)


class RandomEvaluator(Evaluator):
    def __init__(self, id: str, seed: Optional[int] = None):
        super().__init__(id)
        self._rng = random.Random(seed if seed is not None else hash(id) & 0xFFFFFFFF)

    def judge(self, a, b) -> Judgment:
        r = self._rng.random()
        if r < 1/3:
            pref = Preference.A
        elif r < 2/3:
            pref = Preference.B
        else:
            pref = Preference.NEITHER
        return Judgment(preferred=pref, confidence=0.6)


class TriggerWordEvaluator(Evaluator):
    """Gameable evaluator: rewards presence of trigger words heavily.

    Useful for experiments demonstrating evaluator gaming and mitigation.
    """

    def __init__(self, id: str, triggers=None, weight: float = 20.0):
        super().__init__(id)
        self._triggers = [
            "comprehensive", "robust", "thoroughly", "state-of-the-art", "cutting-edge"
        ] if triggers is None else [t.lower() for t in triggers]
        self._w = float(weight)

    def _count(self, s: str) -> int:
        text = (s or "").lower()
        return sum(text.count(t) for t in self._triggers)

    def _score(self, s: str) -> float:
        # No base score; only triggers matter to create strong selection signal
        return self._w * float(self._count(s))

    def judge(self, a: str, b: str) -> Judgment:
        sa = self._score(a)
        sb = self._score(b)
        if sa == sb:
            pref = Preference.NEITHER
        elif sa > sb:
            pref = Preference.A
        else:
            pref = Preference.B
        # Confidence grows with difference in trigger counts
        diff = abs(self._count(a) - self._count(b))
        conf = max(0.6, min(1.0, 0.6 + 0.1 * diff))
        return Judgment(preferred=pref, confidence=conf, reasoning=None)


class AntiTriggerEvaluator(Evaluator):
    """Penalizes trigger words (prefers fewer triggers). Creates opposing pressure."""

    def __init__(self, id: str, triggers=None, weight: float = 10.0):
        super().__init__(id)
        self._triggers = [
            "comprehensive", "robust", "thoroughly", "state-of-the-art", "cutting-edge"
        ] if triggers is None else [t.lower() for t in triggers]
        self._w = float(weight)

    def _count(self, s: str) -> int:
        text = (s or "").lower()
        return sum(text.count(t) for t in self._triggers)

    def _score(self, s: str) -> float:
        # Higher score when fewer triggers
        return max(0.0, 100.0 - self._w * float(self._count(s)))

    def judge(self, a: str, b: str) -> Judgment:
        sa = self._score(a)
        sb = self._score(b)
        if sa == sb:
            pref = Preference.NEITHER
        elif sa > sb:
            pref = Preference.A
        else:
            pref = Preference.B
        diff = abs(self._count(a) - self._count(b))
        conf = max(0.6, min(1.0, 0.6 + 0.1 * diff))
        return Judgment(preferred=pref, confidence=conf, reasoning=None)
