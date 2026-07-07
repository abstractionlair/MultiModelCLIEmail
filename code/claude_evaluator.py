from __future__ import annotations

import json
import os
import re
from typing import Optional

from evaluator_base import Evaluator, Judgment, Preference
from budget_controller import BudgetController, BudgetExceeded, estimate_cost
from stateful_evaluator import StatefulEvaluator


class ClaudeEvaluator(Evaluator):
    """Anthropic Claude evaluator wrapper for pairwise A/B judgments.

    - Lazy-imports the Anthropic client to avoid dependency at import time.
    - Requires `ANTHROPIC_API_KEY` unless the client is patched/mocked.
    - Expects a fenced JSON code block with {preferred, reasoning}.
    - Supports optional BudgetController with canonical pair caching.
    """

    def __init__(
        self,
        id: str,
        model: Optional[str] = None,
        *,
        api_key_env: str = "ANTHROPIC_API_KEY",
        default_confidence: float = 0.9,
        budget_controller: Optional[BudgetController] = None,
    ):
        super().__init__(id)
        self.model_name = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        self.api_key_env = api_key_env
        self.default_confidence = max(0.0, min(1.0, float(default_confidence)))
        self.budget_controller = budget_controller
        self.conversation_history: List[Dict[str, str]] = []
        self.max_history_length = 10

    @staticmethod
    def _build_prompt(a: str, b: str) -> str:
        return (
            "You will be given two contents, A and B. Decide which is better for quality, relevance, and clarity.\n\n"
            f"Content A:\n{a}\n\n"
            f"Content B:\n{b}\n\n"
            "Which content do you prefer, A or B, or neither? Respond ONLY with a JSON object in a fenced code block:```json\n"
            "{\n  \"preferred\": \"A|B|NEITHER\",\n  \"reasoning\": \"...\"\n}\n"  # newline inside block
            "```"
        )

    @staticmethod
    def _parse_json_from_text(text: str) -> dict:
        for pat in (r"```json(.*?)```", r"```(.*?)```"):
            m = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
            if m:
                blob = m.group(1).strip()
                try:
                    return json.loads(blob)
                except Exception:
                    pass
        try:
            return json.loads(text)
        except Exception:
            return {}

    @staticmethod
    def _to_preference(val: Optional[str]) -> Preference:
        s = (val or "").strip().upper()
        if s == "A":
            return Preference.A
        if s == "B":
            return Preference.B
        return Preference.NEITHER

    def _canonical_key(self, a: str, b: str) -> tuple[str, str, bool]:
        if str(a) <= str(b):
            return a, b, False
        else:
            return b, a, True

    def _remap_preference(self, pref: Preference, swapped: bool) -> Preference:
        if not swapped or pref == Preference.NEITHER:
            return pref
        return Preference.A if pref == Preference.B else Preference.B

    def judge_with_state(self, a: str, b: str, reasoning_history: List[str] = []) -> Tuple[Judgment, Optional[str]]:
        estimated_tokens = 200
        estimated_cost = estimate_cost(self.model_name, estimated_tokens)

        cache_key = None
        swapped = False
        if self.budget_controller:
            a_can, b_can, swapped = self._canonical_key(a, b)
            cache_key = self.budget_controller.get_cache_key(self.id, a_can, b_can)
            cached = self.budget_controller.check_cache(cache_key)
            if cached:
                if isinstance(cached, Judgment):
                    return Judgment(
                        preferred=self._remap_preference(cached.preferred, swapped),
                        confidence=cached.confidence,
                        reasoning=cached.reasoning,
                    ), None
            try:
                self.budget_controller.check_budget(self.model_name, estimated_cost)
            except BudgetExceeded as e:
                return Judgment(preferred=Preference.NEITHER, confidence=0.1, reasoning=f"Budget exceeded: {e}"), None

        user_prompt = self._build_prompt(a, b)
        
        system_prompt = (
            "You are an impartial evaluator. Compare two contents and respond "
            "ONLY with a JSON object describing your decision."
        )

        messages = reasoning_history + [
            {"role": "user", "content": user_prompt}
        ]

        try:
            import anthropic  # type: ignore
            client = anthropic.Anthropic(api_key=os.getenv(self.api_key_env))
            resp = client.messages.create(
                model=self.model_name,
                max_tokens=256,
                temperature=0,
                system=system_prompt,
                messages=messages,
            )
            text = ""
            if hasattr(resp, "content") and resp.content:
                parts = getattr(resp.content[0], "text", None)
                if parts is not None:
                    text = parts
            if not text:
                text = getattr(resp, "text", "") or ""
        except Exception as e:
            raise ImportError(
                "Anthropic client not available; install 'anthropic' and set ANTHROPIC_API_KEY or mock the client."
            ) from e

        data = self._parse_json_from_text(text or "")
        pref = self._to_preference(data.get("preferred"))
        reasoning = data.get("reasoning") if isinstance(data, dict) else None
        judgment = Judgment(preferred=pref, confidence=self.default_confidence, reasoning=reasoning)

        # Update conversation history with the latest interaction
        self.conversation_history.append({"role": "user", "content": user_prompt})
        self.conversation_history.append({"role": "assistant", "content": text})
        
        # Trim history if it exceeds max_history_length
        if len(self.conversation_history) > self.max_history_length:
            self.conversation_history = self.conversation_history[-self.max_history_length:]

        if self.budget_controller and cache_key is not None:
            self.budget_controller.record_call(self.model_name, estimated_cost)
            self.budget_controller.cache_result(cache_key, judgment)

        return judgment, reasoning

    def judge(self, a: str, b: str) -> Judgment:
        judgment, _ = self.judge_with_state(a, b)
        return judgment

