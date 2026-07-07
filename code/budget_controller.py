"""
budget_controller.py

Budget control and cost tracking for API-based evaluators.

Prevents runaway costs by:
1. Hard caps on API calls per run
2. Caching evaluation results
3. Cost estimation and logging
4. Emergency shutoff when limits reached
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime

from evaluator_base import Judgment, Preference


@dataclass
class CostEstimate:
    """Estimated cost for an API call."""
    model: str
    tokens_estimate: int
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BudgetStats:
    """Statistics about budget usage."""
    calls_made: int = 0
    calls_cached: int = 0
    total_cost_usd: float = 0.0
    by_model: Dict[str, int] = field(default_factory=dict)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())


class BudgetExceeded(Exception):
    """Raised when budget limit is reached."""
    pass


class BudgetController:
    """Controls and tracks API evaluation budget.
    
    Features:
    - Hard cap on API calls per run
    - Result caching (never evaluate same input twice)
    - Cost estimation and logging
    - Per-model statistics
    
    Example:
        budget = BudgetController(max_calls=100, max_cost_usd=5.0)
        
        # Before each API call
        budget.check_budget("gpt-4", tokens=1000)
        
        # Cache check
        cache_key = budget.get_cache_key(context, task)
        if cache_key in budget.cache:
            return budget.cache[cache_key]
        
        # Make API call
        result = model.evaluate(...)
        
        # Record usage
        budget.record_call("gpt-4", tokens=1000, cost=0.03)
        budget.cache_result(cache_key, result)
    """
    
    def __init__(
        self,
        max_calls: int = 100,
        max_cost_usd: float = 10.0,
        cache_file: Optional[Path] = None,
        enable_cache: bool = True
    ):
        """Initialize budget controller.
        
        Args:
            max_calls: Maximum API calls allowed per run
            max_cost_usd: Maximum total cost in USD
            cache_file: Path to cache file (default: .eval_cache.json)
            enable_cache: Whether to use caching
        """
        self.max_calls = max_calls
        self.max_cost_usd = max_cost_usd
        self.enable_cache = enable_cache
        
        self.cache_file = cache_file or Path(".eval_cache.json")
        self.cache = self._load_cache() if enable_cache else {}
        
        self.stats = BudgetStats()
        
    def _load_cache(self) -> Dict[str, Any]:
        """Load cached evaluation results."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load cache: {e}")
                return {}
        return {}
    
    def _save_cache(self):
        """Persist cache to disk."""
        if not self.enable_cache:
            return
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")
    
    def get_cache_key(self, *args, **kwargs) -> str:
        """Generate cache key from evaluation inputs.
        
        Args:
            *args, **kwargs: Evaluation inputs to hash
            
        Returns:
            Hex string cache key
        """
        # Create deterministic string representation
        key_data = json.dumps(
            {"args": args, "kwargs": sorted(kwargs.items())},
            sort_keys=True
        )
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def check_cache(self, cache_key: str) -> Optional[Judgment]:
        """Check if result is cached.
        
        Args:
            cache_key: Cache key from get_cache_key()
            
        Returns:
            Cached result if available, None otherwise
        """
        if not self.enable_cache:
            return None
        
        if cache_key in self.cache:
            self.stats.calls_cached += 1
            cached_data = self.cache[cache_key]
            # Deserialize back to Judgment object
            return Judgment(
                preferred=Preference(cached_data.get("preferred")),
                confidence=cached_data.get("confidence"),
                reasoning=cached_data.get("reasoning")
            )
        return None
    
    def cache_result(self, cache_key: str, result: Judgment):
        """Cache an evaluation result.
        
        Args:
            cache_key: Cache key from get_cache_key()
            result: Result to cache (must be JSON-serializable)
        """
        if not self.enable_cache:
            return
        
        # Serialize Judgment object to a dictionary
        self.cache[cache_key] = {
            "preferred": result.preferred.value,
            "confidence": result.confidence,
            "reasoning": result.reasoning
        }
        # Save periodically (every 10 new entries)
        if len(self.cache) % 10 == 0:
            self._save_cache()
    
    def check_budget(self, model: str, estimated_cost: float = 0.0):
        """Check if budget allows another API call.
        
        Args:
            model: Model name for tracking
            estimated_cost: Estimated cost in USD for this call
            
        Raises:
            BudgetExceeded: If budget limit would be exceeded
        """
        # Check call limit
        if self.stats.calls_made >= self.max_calls:
            raise BudgetExceeded(
                f"Call limit reached: {self.stats.calls_made}/{self.max_calls}"
            )
        
        # Check cost limit
        if self.stats.total_cost_usd + estimated_cost > self.max_cost_usd:
            raise BudgetExceeded(
                f"Cost limit reached: ${self.stats.total_cost_usd + estimated_cost:.4f} "
                f"exceeds max ${self.max_cost_usd:.2f}"
            )
    
    def record_call(self, model: str, cost: float = 0.0):
        """Record an API call after completion.
        
        Args:
            model: Model name
            cost: Actual cost in USD
        """
        self.stats.calls_made += 1
        self.stats.total_cost_usd += cost
        
        if model not in self.stats.by_model:
            self.stats.by_model[model] = 0
        self.stats.by_model[model] += 1
        
        # Log progress
        self._log_progress()
    
    def _log_progress(self):
        """Log current budget usage."""
        pct_calls = (self.stats.calls_made / self.max_calls) * 100
        pct_cost = (self.stats.total_cost_usd / self.max_cost_usd) * 100
        
        print(
            f"Budget: {self.stats.calls_made}/{self.max_calls} calls ({pct_calls:.1f}%), "
            f"${self.stats.total_cost_usd:.4f}/${self.max_cost_usd:.2f} ({pct_cost:.1f}%), "
            f"{self.stats.calls_cached} cached"
        )
    
    def get_stats(self) -> BudgetStats:
        """Get current budget statistics.
        
        Returns:
            BudgetStats with current usage
        """
        return self.stats
    
    def finalize(self):
        """Finalize budget tracking (save cache, final stats)."""
        self._save_cache()
        
        print("\n" + "="*70)
        print("Budget Summary")
        print("="*70)
        print(f"API calls made: {self.stats.calls_made}")
        print(f"Cache hits: {self.stats.calls_cached}")
        print(f"Total cost: ${self.stats.total_cost_usd:.4f}")
        print(f"By model:")
        for model, count in self.stats.by_model.items():
            print(f"  {model}: {count} calls")
        print("="*70)


# Cost estimation constants (rough approximations)
COST_PER_1K_TOKENS = {
    "gpt-4": 0.03,
    "gpt-3.5-turbo": 0.002,
    "claude-sonnet-3-5": 0.015,
    "gemini-pro": 0.0005,
    "gemini-1.5-pro": 0.0035,
}


def estimate_cost(model: str, tokens: int) -> float:
    """Estimate API call cost.
    
    Args:
        model: Model name
        tokens: Estimated token count
        
    Returns:
        Estimated cost in USD
    """
    cost_per_1k = COST_PER_1K_TOKENS.get(model, 0.01)  # Default fallback
    return (tokens / 1000.0) * cost_per_1k
