from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core_types import Candidate, Context
from evaluation_adapter import EvaluationAdapter

# Optional imports for advanced hooks
try:
    from output_feature_extractor import OutputFeatureExtractor, FeatureVector
except Exception:  # pragma: no cover - optional at runtime
    OutputFeatureExtractor = None  # type: ignore
    FeatureVector = None  # type: ignore

try:
    from adaptive_sampling import AdaptiveSamplingScheduler
except Exception:  # pragma: no cover - optional at runtime
    AdaptiveSamplingScheduler = None  # type: ignore


@dataclass
class ArchiveEntry:
    """Archive record for a candidate.

    - quality: scalar quality score (e.g., normalized BTL)
    - features: simple dict features (legacy/context/meta features)
    - behavior: optional normalized FeatureVector for output behavior space
    - meta: freeform diagnostics
    """

    candidate: Candidate
    quality: float
    features: Dict[str, float]
    meta: Dict[str, Any] = field(default_factory=dict)
    behavior: Optional[FeatureVector] = None  # populated when OutputFeatureExtractor is provided


# Built-in sampling strategies
def sample_uniform(rng: random.Random, entries: Sequence[ArchiveEntry], k: int) -> List[ArchiveEntry]:
    if k <= 0 or not entries:
        return []
    if len(entries) <= k:
        return list(entries)
    return rng.sample(entries, k)


def sample_difficulty(rng: random.Random, entries: Sequence[ArchiveEntry], k: int) -> List[ArchiveEntry]:
    # Pick top-k by quality (hardest opponents)
    if k <= 0 or not entries:
        return []
    sorted_e = sorted(entries, key=lambda e: e.quality, reverse=True)
    return sorted_e[:k]


def sample_novelty(rng: random.Random, entries: Sequence[ArchiveEntry], k: int, proxy_len: Optional[int]) -> List[ArchiveEntry]:
    # Use prompt_len difference as a proxy for novelty
    if k <= 0 or not entries:
        return []
    def dist(e: ArchiveEntry) -> float:
        plen = e.features.get("prompt_len", 0.0)
        if proxy_len is None:
            return 0.0
        return abs(plen - float(proxy_len))
    sorted_e = sorted(entries, key=dist, reverse=True)
    return sorted_e[:k]


class QDSearch:
    """Minimal quality-diversity search over contexts.

    This is a pragmatic scaffolding that integrates an EvaluationAdapter and
    maintains a simple archive of elites.
    """

    def __init__(
        self,
        evaluator_adapter: EvaluationAdapter,
        feature_extractor: Optional[Callable[[Candidate, Dict[str, Any]], Dict[str, float]]] = None,
        sampling: str = "uniform",  # uniform|novelty|difficulty (fallback when no scheduler)
        rng_seed: Optional[int] = None,
        *,
        output_extractor: Optional[OutputFeatureExtractor] = None,
        scheduler: Optional[AdaptiveSamplingScheduler] = None,
    ):
        self.adapter = evaluator_adapter
        # Feature extraction callback: (candidate, eval_meta) -> feature dict (legacy/context features)
        if feature_extractor is None:
            def _default_fe(c: Candidate, meta: Dict[str, Any]) -> Dict[str, float]:
                feats: Dict[str, float] = {}
                if "diversity" in meta:
                    feats["diversity"] = float(meta["diversity"])
                if c.context.prompt:
                    feats["prompt_len"] = float(len(c.context.prompt))
                return feats
            self.fe = _default_fe
        else:
            self.fe = feature_extractor
        self.archive: List[ArchiveEntry] = []
        self._rng = random.Random(rng_seed)
        self._sampling = sampling
        self._out_extractor = output_extractor
        self._scheduler = scheduler

    # ---------------------- Internal helpers ----------------------
    class _SchedItem:
        def __init__(self, id: str, quality: float, features: FeatureVector):  # type: ignore[name-defined]
            self.id = id
            self.quality = quality
            self.features = features

    def _ensure_behavior(self, entry: ArchiveEntry):
        """Compute behavior FeatureVector for an archive entry if missing and extractor available."""
        if not self._out_extractor:
            return
        if entry.behavior is not None:
            return
        # Attempt to compute from candidate payload
        cand = entry.candidate
        payload = cand.payload or {}
        output = payload.get("output") or payload.get("text") or payload.get("code") or ""
        input_ = cand.context.prompt or payload.get("input") or ""
        ctx = {}
        try:
            fvec = self._out_extractor.extract(input=input_, output=output, context=ctx)  # type: ignore[union-attr]
            entry.behavior = fvec
        except Exception:
            entry.behavior = None

    def initialize(self, seeds: Sequence[Candidate]):
        # Seed archive with initial candidates at neutral quality
        for c in seeds:
            self.archive.append(ArchiveEntry(candidate=c, quality=0.0, features={}, meta={}, behavior=None))

    def propose(self, parent: Candidate, mutator: Callable[[Candidate], Candidate]) -> Candidate:
        return mutator(parent)

    def evaluate(self, cand: Candidate) -> Tuple[float, Dict[str, Any]]:
        # Select opponents from archive
        entries = [e for e in self.archive if e.candidate.id != cand.id]
        k_default = min(5, len(entries))

        opponents: List[Candidate] = []
        # Scheduler-based sampling when available and behaviors can be computed
        if self._scheduler and self._out_extractor and entries:
            # Pre-eval behavior for new candidate (without eval-derived context)
            payload = cand.payload or {}
            output = payload.get("output") or payload.get("text") or payload.get("code") or ""
            input_ = cand.context.prompt or payload.get("input") or ""
            try:
                new_fvec = self._out_extractor.extract(input=input_, output=output, context={})  # type: ignore[union-attr]
            except Exception:
                new_fvec = None

            # Ensure behaviors for archive entries
            for e in entries:
                self._ensure_behavior(e)

            usable = [e for e in entries if e.behavior is not None]
            if usable and new_fvec is not None:
                arch_items = [self._SchedItem(id=e.candidate.id, quality=e.quality, features=e.behavior) for e in usable]  # type: ignore[arg-type]
                new_item = self._SchedItem(id=cand.id, quality=0.0, features=new_fvec)  # quality unused for novelty/difficulty decision
                sampled = self._scheduler.sample(arch_items, new_item)  # type: ignore[union-attr]
                opp_ids = {s.id for s in sampled}
                opponents = [e.candidate for e in entries if e.candidate.id in opp_ids]

        # Fallback to built-in sampling strategies
        if not opponents:
            k = k_default
            if self._sampling == "difficulty":
                sample = sample_difficulty(self._rng, entries, k)
            elif self._sampling == "novelty":
                proxy_len = len(cand.context.prompt) if cand.context.prompt else None
                sample = sample_novelty(self._rng, entries, k, proxy_len)
            else:
                sample = sample_uniform(self._rng, entries, k)
            opponents = [e.candidate for e in sample]

        # Evaluate via focused duels
        result = self.adapter.duel_against_archive(cand, opponents, sample_size=len(opponents))
        quality, meta = self.adapter.to_quality(result, focus_id=cand.id)
        # Attach the raw evaluation result for downstream feature extraction if needed
        try:
            meta = dict(meta)
            meta["evaluation_result"] = result
        except Exception:
            pass
        return quality, meta

    def update_archive(self, cand: Candidate, quality: float, meta: Dict[str, Any]):
        feats = self.fe(cand, meta)
        # Compute behavior vector including eval-derived context if extractor provided
        behavior = None
        if self._out_extractor is not None:
            payload = cand.payload or {}
            output = payload.get("output") or payload.get("text") or payload.get("code") or ""
            input_ = cand.context.prompt or payload.get("input") or ""
            ctx = {"evaluation_result": meta.get("evaluation_result")} if meta else {}
            try:
                behavior = self._out_extractor.extract(input=input_, output=output, context=ctx)  # type: ignore[union-attr]
            except Exception:
                behavior = None

        self.archive.append(ArchiveEntry(cand, quality, feats, meta, behavior))
        # Keep top-N by quality for simplicity (N=50)
        self.archive.sort(key=lambda e: e.quality, reverse=True)
        self.archive = self.archive[:50]

    def run(self, seeds: Sequence[Candidate], mutators: Sequence[Callable[[Candidate], Candidate]], iterations: int = 20):
        if not self.archive:
            self.initialize(seeds)
        current = list(seeds)
        for _ in range(iterations):
            parent = self._rng.choice(current)
            mut = self._rng.choice(mutators)
            child = self.propose(parent, mut)
            q, meta = self.evaluate(child)
            self.update_archive(child, q, meta)
            current.append(child)
            # Advance scheduler phase if present
            if self._scheduler is not None:
                try:
                    self._scheduler.step()
                except Exception:
                    pass
        return self.archive
