from typing import Any, List, Optional
from dataclasses import dataclass, field

from evaluator_base import Evaluator, Judgment, Preference, EvaluationResult


class StatefulEvaluator(Evaluator):
    """Evaluator that preserves reasoning state across judgments."""

    def __init__(
        self,
        wrapped_evaluator: Evaluator,
        id: Optional[str] = None,
        preserve_thinking: bool = True,
        max_history_length: int = 10,
    ):
        super().__init__(id)
        self.wrapped_evaluator = wrapped_evaluator
        self.preserve_thinking = preserve_thinking
        self.max_history_length = max_history_length
        self.thinking_history: List[Any] = []
        self.reasoning_history: List[str] = []

    def reset_state(self):
        """Call this when starting a new evaluation context"""
        self.thinking_history = []
        self.reasoning_history = []

    def judge(self, a: str, b: str) -> Judgment:
        if hasattr(self.wrapped_evaluator, 'judge_with_state'):
            judgment, reasoning = self.wrapped_evaluator.judge_with_state(a, b, reasoning_history=self.reasoning_history)
            if reasoning:
                self.reasoning_history.append(reasoning)
                if len(self.reasoning_history) > self.max_history_length:
                    self.reasoning_history.pop(0)
            return judgment
        return self.wrapped_evaluator.judge(a, b)

    def judge_with_state(self, a: str, b: str, context: Any = None) -> Judgment:
        """Judge with state preservation. Subclasses should implement this."""
        raise NotImplementedError("Subclasses must implement judge_with_state")
