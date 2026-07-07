"""Adaptive archive sampling for Quality-Diversity search.

Three sampling strategies to prevent central tendency bias:
1. Uniform: Random sample (general quality assessment)
2. Difficulty-aware: Sample from top-k (forces candidate to beat best)
3. Novelty-aware: Sample nearest neighbors in feature space (local improvement)

Adaptive scheduling: Early QD uses uniform, mid-phase uses novelty, late uses difficulty.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Protocol, Sequence
import random

import numpy as np


class FeatureVectorProtocol(Protocol):
    """Protocol for feature vectors (duck typing)."""

    values: np.ndarray

    def distance(self, other: "FeatureVectorProtocol") -> float:
        ...


class CandidateProtocol(Protocol):
    """Protocol for archive candidates."""

    id: str
    quality: float
    features: FeatureVectorProtocol


class SamplingMode(Enum):
    """Archive sampling strategies."""

    UNIFORM = "uniform"
    DIFFICULTY_AWARE = "difficulty_aware"
    NOVELTY_AWARE = "novelty_aware"


@dataclass
class SamplingConfig:
    """Configuration for adaptive sampling."""

    mode: SamplingMode
    sample_size: int
    random_seed: Optional[int] = None

    # Difficulty-aware parameters
    top_k_ratio: float = 0.2  # Sample from top 20% by quality

    # Novelty-aware parameters
    k_nearest: int = 10  # Consider k nearest neighbors


class ArchiveSampler(ABC):
    """Base class for archive sampling strategies."""

    def __init__(self, config: SamplingConfig):
        self.config = config
        self.rng = random.Random(config.random_seed)

    @abstractmethod
    def sample(
        self,
        archive: Sequence[CandidateProtocol],
        new_candidate: Optional[CandidateProtocol] = None,
    ) -> List[CandidateProtocol]:
        """Sample candidates from archive.

        Args:
            archive: Archive of existing candidates
            new_candidate: Optional new candidate (for novelty-aware sampling)

        Returns:
            List of sampled candidates
        """
        pass


class UniformSampler(ArchiveSampler):
    """Uniform random sampling from archive.

    Good for: Early QD exploration, general quality assessment.
    """

    def sample(
        self,
        archive: Sequence[CandidateProtocol],
        new_candidate: Optional[CandidateProtocol] = None,
    ) -> List[CandidateProtocol]:
        """Sample uniformly at random."""
        if not archive:
            return []

        sample_size = min(self.config.sample_size, len(archive))
        return self.rng.sample(list(archive), sample_size)


class DifficultyAwareSampler(ArchiveSampler):
    """Sample from top-k candidates by quality.

    Good for: Late-phase QD, quality pressure, ensuring new candidates beat best.
    """

    def sample(
        self,
        archive: Sequence[CandidateProtocol],
        new_candidate: Optional[CandidateProtocol] = None,
    ) -> List[CandidateProtocol]:
        """Sample from top-k by quality."""
        if not archive:
            return []

        # Sort by quality (descending)
        sorted_archive = sorted(archive, key=lambda c: c.quality, reverse=True)

        # Take top-k ratio
        k = max(1, int(len(sorted_archive) * self.config.top_k_ratio))
        top_k = sorted_archive[:k]

        # Sample from top-k
        sample_size = min(self.config.sample_size, len(top_k))
        return self.rng.sample(top_k, sample_size)


class NoveltyAwareSampler(ArchiveSampler):
    """Sample nearest neighbors in feature space.

    Good for: Mid-phase QD, niche refinement, local improvement.
    """

    def sample(
        self,
        archive: Sequence[CandidateProtocol],
        new_candidate: Optional[CandidateProtocol] = None,
    ) -> List[CandidateProtocol]:
        """Sample k-nearest neighbors of new_candidate in feature space."""
        if not archive:
            return []

        if new_candidate is None:
            # Fallback to uniform if no reference candidate
            sample_size = min(self.config.sample_size, len(archive))
            return self.rng.sample(list(archive), sample_size)

        # Compute distances to new_candidate
        distances = []
        for candidate in archive:
            try:
                dist = new_candidate.features.distance(candidate.features)
                distances.append((dist, candidate))
            except Exception:
                # If distance computation fails, treat as very far
                distances.append((float('inf'), candidate))

        # Sort by distance (ascending)
        distances.sort(key=lambda x: x[0])

        # Take k-nearest
        k = min(self.config.k_nearest, len(distances))
        nearest = [c for _, c in distances[:k]]

        # Sample from nearest neighbors
        sample_size = min(self.config.sample_size, len(nearest))
        return self.rng.sample(nearest, sample_size)


# ============================================================================
# Adaptive Sampling Scheduler
# ============================================================================

@dataclass
class AdaptiveSchedulerConfig:
    """Configuration for adaptive sampling schedule."""

    # Phase transitions (by iteration or archive size)
    early_phase_iterations: int = 100
    mid_phase_iterations: int = 500

    # Sample sizes per phase
    early_sample_size: int = 5
    mid_sample_size: int = 8
    late_sample_size: int = 10

    # Mode-specific parameters
    top_k_ratio: float = 0.2
    k_nearest: int = 10

    random_seed: Optional[int] = None


class AdaptiveSamplingScheduler:
    """Adaptive scheduler that switches sampling strategy based on QD progress.

    Early phase: Uniform (broad exploration)
    Mid phase: Novelty-aware (niche refinement)
    Late phase: Difficulty-aware (quality pressure)
    """

    def __init__(self, config: AdaptiveSchedulerConfig):
        self.config = config
        self.iteration = 0

    def get_sampler(self) -> ArchiveSampler:
        """Get appropriate sampler for current iteration."""
        if self.iteration < self.config.early_phase_iterations:
            # Early phase: uniform exploration
            return UniformSampler(
                SamplingConfig(
                    mode=SamplingMode.UNIFORM,
                    sample_size=self.config.early_sample_size,
                    random_seed=self.config.random_seed,
                )
            )
        elif self.iteration < self.config.mid_phase_iterations:
            # Mid phase: novelty-aware niche refinement
            return NoveltyAwareSampler(
                SamplingConfig(
                    mode=SamplingMode.NOVELTY_AWARE,
                    sample_size=self.config.mid_sample_size,
                    k_nearest=self.config.k_nearest,
                    random_seed=self.config.random_seed,
                )
            )
        else:
            # Late phase: difficulty-aware quality pressure
            return DifficultyAwareSampler(
                SamplingConfig(
                    mode=SamplingMode.DIFFICULTY_AWARE,
                    sample_size=self.config.late_sample_size,
                    top_k_ratio=self.config.top_k_ratio,
                    random_seed=self.config.random_seed,
                )
            )

    def sample(
        self,
        archive: Sequence[CandidateProtocol],
        new_candidate: Optional[CandidateProtocol] = None,
    ) -> List[CandidateProtocol]:
        """Sample from archive using current phase's strategy."""
        sampler = self.get_sampler()
        return sampler.sample(archive, new_candidate)

    def step(self):
        """Advance to next iteration (call after each QD iteration)."""
        self.iteration += 1

    def get_current_mode(self) -> SamplingMode:
        """Get current sampling mode for logging/debugging."""
        return self.get_sampler().config.mode


# ============================================================================
# Factory Functions
# ============================================================================

def create_uniform_sampler(sample_size: int = 5, seed: Optional[int] = None) -> ArchiveSampler:
    """Create uniform sampler."""
    return UniformSampler(
        SamplingConfig(mode=SamplingMode.UNIFORM, sample_size=sample_size, random_seed=seed)
    )


def create_difficulty_sampler(
    sample_size: int = 5, top_k_ratio: float = 0.2, seed: Optional[int] = None
) -> ArchiveSampler:
    """Create difficulty-aware sampler."""
    return DifficultyAwareSampler(
        SamplingConfig(
            mode=SamplingMode.DIFFICULTY_AWARE,
            sample_size=sample_size,
            top_k_ratio=top_k_ratio,
            random_seed=seed,
        )
    )


def create_novelty_sampler(
    sample_size: int = 5, k_nearest: int = 10, seed: Optional[int] = None
) -> ArchiveSampler:
    """Create novelty-aware sampler."""
    return NoveltyAwareSampler(
        SamplingConfig(
            mode=SamplingMode.NOVELTY_AWARE,
            sample_size=sample_size,
            k_nearest=k_nearest,
            random_seed=seed,
        )
    )


def create_adaptive_scheduler(
    early_iterations: int = 100,
    mid_iterations: int = 500,
    seed: Optional[int] = None,
) -> AdaptiveSamplingScheduler:
    """Create adaptive sampling scheduler with default config."""
    return AdaptiveSamplingScheduler(
        AdaptiveSchedulerConfig(
            early_phase_iterations=early_iterations,
            mid_phase_iterations=mid_iterations,
            random_seed=seed,
        )
    )


# ============================================================================
# Testing
# ============================================================================

if __name__ == "__main__":
    from dataclasses import dataclass

    # Mock candidate for testing
    @dataclass
    class MockFeatures:
        values: np.ndarray

        def distance(self, other: "MockFeatures") -> float:
            return float(np.linalg.norm(self.values - other.values))

    @dataclass
    class MockCandidate:
        id: str
        quality: float
        features: MockFeatures

    # Create mock archive
    archive = [
        MockCandidate(
            id=f"cand_{i}",
            quality=random.random(),
            features=MockFeatures(np.random.rand(3)),
        )
        for i in range(20)
    ]

    new_candidate = MockCandidate(
        id="new",
        quality=0.5,
        features=MockFeatures(np.array([0.5, 0.5, 0.5])),
    )

    # Test each sampling mode
    print("=== Uniform Sampling ===")
    uniform = create_uniform_sampler(sample_size=5, seed=42)
    sample = uniform.sample(archive, new_candidate)
    print(f"Sampled {len(sample)} candidates: {[c.id for c in sample]}")

    print("\n=== Difficulty-Aware Sampling ===")
    difficulty = create_difficulty_sampler(sample_size=5, top_k_ratio=0.3, seed=42)
    sample = difficulty.sample(archive, new_candidate)
    print(f"Sampled {len(sample)} candidates: {[c.id for c in sample]}")
    print(f"Qualities: {[f'{c.quality:.3f}' for c in sample]}")

    print("\n=== Novelty-Aware Sampling ===")
    novelty = create_novelty_sampler(sample_size=5, k_nearest=8, seed=42)
    sample = novelty.sample(archive, new_candidate)
    print(f"Sampled {len(sample)} candidates: {[c.id for c in sample]}")
    print(f"Distances to new: {[f'{new_candidate.features.distance(c.features):.3f}' for c in sample]}")

    print("\n=== Adaptive Scheduler ===")
    scheduler = create_adaptive_scheduler(early_iterations=5, mid_iterations=10, seed=42)

    for i in range(15):
        mode = scheduler.get_current_mode()
        sample = scheduler.sample(archive, new_candidate)
        print(f"Iteration {i:2d}: {mode.value:20s} -> {len(sample)} candidates")
        scheduler.step()
