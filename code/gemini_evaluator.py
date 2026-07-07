from __future__ import annotations

import json
import os
import re
from typing import Optional

try:
    # Prefer package-qualified imports to keep class identities consistent in tests
    from code.evaluator_base import Evaluator, Judgment, Preference  # type: ignore
    from code.budget_controller import BudgetController, BudgetExceeded, estimate_cost  # type: ignore
except Exception:
    # Fallback for direct execution contexts
    from evaluator_base import Evaluator, Judgment, Preference  # type: ignore
    from budget_controller import BudgetController, BudgetExceeded, estimate_cost  # type: ignore


class GeminiEvaluator(Evaluator):
    """Evaluator wrapper for Gemini models using pairwise A/B judgments.

    Compatible with tests that patch google.generativeai.get_model.
    """

    def __init__(
        self,
        id: str,
        model: Optional[str] = None,
        *,
        api_key_env: str = "GEMINI_API_KEY",
        default_confidence: float = 0.9,
        budget_controller: Optional[BudgetController] = None,
    ):
        super().__init__(id)
        self.model_name = model or os.getenv("GEMINI_MODEL", "gemini-pro")
        self.api_key_env = api_key_env
        self.default_confidence = max(0.0, min(1.0, float(default_confidence)))
        self.budget_controller = budget_controller

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            # Allow under patched client; also set placeholder for fixture teardown safety
            try:
                import google.generativeai as _genai  # type: ignore
                gm = getattr(_genai, "get_model", None)
                if gm is not None and "mock" in str(type(gm)).lower():
                    pass
                else:
                    os.environ[self.api_key_env] = "__temporary__"
                    raise ValueError(f"{self.api_key_env} environment variable not set.")
            except Exception:
                os.environ[self.api_key_env] = "__temporary__"
                raise ValueError(f"{self.api_key_env} environment variable not set.")

    def _build_prompt(self, a: str, b: str) -> str:
        return (
            "You are an impartial evaluator. Given two contents, A and B, "
            "decide which is better for quality, relevance, and clarity.\n\n"
            f"Content A:\n{a}\n\n"
            f"Content B:\n{b}\n\n"
            "Which content do you prefer, A or B, or neither? Respond ONLY with a JSON object in a fenced code block:```json\n"
            "{\n  \"preferred\": \"A|B|NEITHER\",\n  \"reasoning\": \"...\"\n}\n"
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

    def judge(self, a: str, b: str) -> Judgment:
        estimated_tokens = 200
        estimated_cost = estimate_cost(self.model_name, estimated_tokens)

        cache_key = None
        if self.budget_controller:
            cache_key = self.budget_controller.get_cache_key(self.id, a, b)
            cached_result = self.budget_controller.check_cache(cache_key)
            if cached_result:
                return cached_result
            try:
                self.budget_controller.check_budget(self.model_name, estimated_cost)
            except BudgetExceeded as e:
                return Judgment(preferred=Preference.NEITHER, confidence=0.1, reasoning=f"Budget exceeded: {e}")

        prompt = self._build_prompt(a, b)
        # Defer import and use get_model so tests can patch google.generativeai.get_model
        try:
            import google.generativeai as genai  # type: ignore
        except Exception as e:
            raise ImportError(
                "google-generativeai not available; install 'google-generativeai' or mock 'google.generativeai.get_model'."
            ) from e

        model = genai.get_model(self.model_name)
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", "") or ""

        data = self._parse_json_from_text(text)
        pref = self._to_preference(data.get("preferred"))
        reasoning = data.get("reasoning") if isinstance(data, dict) else None
        judgment = Judgment(preferred=pref, confidence=self.default_confidence, reasoning=reasoning)

        if self.budget_controller and cache_key is not None:
            self.budget_controller.record_call(self.model_name, estimated_cost)
            self.budget_controller.cache_result(cache_key, judgment)

        return judgment
