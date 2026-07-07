from core_types import Candidate, Context
from evaluator_ensemble import EvaluationResult
from typing import Dict, Sequence, Tuple

class DocstringQDAdapter:
    def __init__(self, ensemble, test_function: str):
        self.ensemble = ensemble
        self.test_function = test_function

    def duel_against_archive(self, focus: Candidate, opponents: Sequence[Candidate], sample_size: int) -> EvaluationResult:
        # Generate docstrings if not already in payload
        focus_out = focus.payload.get('output') if focus.payload else focus.context.generate(self.test_function) if hasattr(focus.context, 'generate') else ''
        opp_outs = [opp.payload.get('output') if opp.payload else opp.context.generate(self.test_function) if hasattr(opp.context, 'generate') else '' for opp in opponents[:sample_size]]
        # Create Candidate objects with outputs
        focus_cand = Candidate(id=focus.id, context=focus.context, payload={'output': focus_out})
        opp_cands = [Candidate(id=opp.id, context=opp.context, payload={'output': out}) for opp, out in zip(opponents[:sample_size], opp_outs)]
        # Use ensemble's evaluate_focus
        result = self.ensemble.evaluate_focus(focus_cand, opp_cands)
        return result

    def to_quality(self, result: EvaluationResult, focus_id: str) -> Tuple[float, Dict[str, Any]]:
        quality = result.scores.get(focus_id, 0.0)
        meta = {'diversity': result.diversity, 'consensus': result.consensus}
        return quality, meta
