# Integration Specification

## Overview

This document describes how the three main components integrate:

1. **Grok's Evaluator Ensemble** (evaluation harness)
2. **Claude's Integration Layer** (adapters and features)
3. **Gemini's QD Search** (quality-diversity algorithm)

## Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     QD_Search (Gemini)                      │
│                                                             │
│  - Population management                                   │
│  - Archive (niche preservation)                            │
│  - Selection and mutation orchestration                    │
└─────────────┬───────────────────────────┬───────────────────┘
              │                           │
              │ evaluator.evaluate()      │ feature_extractor.extract()
              │                           │
    ┌─────────▼──────────┐      ┌────────▼─────────┐
    │  QDSearchEvaluator │      │ FeatureExtractor │
    │     (Claude)       │      │    (Claude)      │
    │                    │      │                  │
    │  - Adapter wrapper │      │  - Text features │
    │  - Logging/metrics │      │  - Semantic feat │
    └─────────┬──────────┘      │  - Composite     │
              │                  └──────────────────┘
              │ ensemble.evaluate()
              │
    ┌─────────▼──────────┐
    │   JudgePool        │
    │     (Grok)         │
    │                    │
    │  - Judge rotation  │
    │  - Pairwise ranking│
    │  - Consensus logic │
    └─────────┬──────────┘
              │
        ┌─────┴─────┬──────┬──────┐
        │           │      │      │
    ┌───▼───┐  ┌───▼───┐ ┌▼──┐  ┌▼──┐
    │GPT-5  │  │Claude │ │Gem│  │Grk│
    │Eval   │  │Eval   │ │Ev │  │Ev │
    └───────┘  └───────┘ └───┘  └───┘
```

## Integration Points

### 1. QD_Search ↔ QDSearchEvaluator

**Interface (Gemini → Claude):**

```python
# In QD_Search.run() at line 64
quality = self.evaluator.evaluate(new_context)
```

**Implementation (Claude):**

```python
class QDSearchEvaluator:
    def evaluate(self, context: str, reference: Optional[str] = None) -> float:
        """
        Returns quality score for QD_Search.
        Internally logs full EvaluationResult for analysis.
        """
        evaluation_result = self.ensemble.evaluate(context, reference)
        self.adapter.log_evaluation(context, evaluation_result)
        return self.adapter.get_quality_score(evaluation_result)
```

**What gets passed:** Simple float (quality score)
**What gets logged:** Full EvaluationResult with judgments, consensus, diversity

### 2. QD_Search ↔ FeatureExtractor

**Interface (Gemini → Claude):**

```python
# In QD_Search.run() at line 67
features = self.feature_extractor.extract(new_context)
```

**Implementation (Claude):**

```python
class SimpleTextFeatureExtractor(FeatureExtractor):
    def extract(self, context: str) -> List[float]:
        """
        Returns feature vector defining behavioral characterization.
        """
        return [
            self._length_feature(context),
            self._complexity_feature(context),
            self._formality_feature(context),
            self._specificity_feature(context)
        ]
```

**What gets passed:** List of floats (feature vector)

**Optional enhancement:** Include evaluator diversity as a feature

```python
# Enhanced integration
class EnhancedQDSearchEvaluator:
    def evaluate_with_features(self, context: str) -> tuple[float, List[float]]:
        """Returns (quality, additional_features)."""
        eval_result = self.ensemble.evaluate(context)
        quality = self.adapter.get_quality_score(eval_result)
        diversity_feature = [self.adapter.get_diversity_score(eval_result)]
        return quality, diversity_feature
```

### 3. QDSearchEvaluator ↔ JudgePool

**Interface (Claude → Grok):**

```python
evaluation_result = self.ensemble.evaluate(context, reference)
```

**Expected return type (Grok):**

```python
@dataclass
class EvaluationResult:
    judgments: List[Judgment]
    consensus: Optional[float]
    diversity: float
```

**Grok's implementation** (from evaluator harness proposal):

```python
class JudgePool:
    def evaluate(self, candidate, reference, author_id=None):
        judges = self.select_judges(author_id, n=3)
        judgments = [j.judge(candidate, reference) for j in judges]

        # Compute consensus (confidence-weighted voting)
        consensus = self._compute_consensus(judgments)

        # Compute diversity (disagreement metric)
        diversity = self._compute_diversity(judgments)

        return EvaluationResult(
            judgments=judgments,
            consensus=consensus,
            diversity=diversity
        )
```

## Data Flow Example

### Scenario: QD Search Iteration

1. **Selection:** QD_Search selects parent context from archive
2. **Mutation:** Context mutator generates new variant
3. **Evaluation:**
   ```python
   quality = evaluator.evaluate(new_context)
   # Internally:
   # - QDSearchEvaluator calls JudgePool
   # - JudgePool rotates judges (excludes author)
   # - Each judge does pairwise comparison
   # - Consensus computed via confidence-weighted voting
   # - Full result logged to logs/evaluations.json
   # - Quality score returned to QD_Search
   ```
4. **Feature Extraction:**
   ```python
   features = feature_extractor.extract(new_context)
   # Returns: [length, complexity, formality, specificity]
   ```
5. **Archive Update:** QD_Search attempts to add to archive
   ```python
   niche_key = _get_niche_key(features)
   if quality > archive[niche_key]['quality']:
       archive[niche_key] = {
           'context': new_context,
           'quality': quality,
           'features': features
       }
   ```

## Configuration Example

```python
# Initialize components
from code.evaluator_base import JudgePool, SimpleEvaluator
from code.evaluation_adapter import QDSearchEvaluator, EvaluationAdapter
from code.feature_extractor import SimpleTextFeatureExtractor
from qd_search import QD_Search
from context_mutators import SimpleTextMutator

# Grok's evaluator ensemble
evaluators = [
    SimpleEvaluator("gpt-5"),
    SimpleEvaluator("claude-3"),
    SimpleEvaluator("gemini-pro")
]
judge_pool = JudgePool(evaluators)

# Claude's adapter layer
adapter = EvaluationAdapter(log_path="logs/evaluations.json")
qd_evaluator = QDSearchEvaluator(judge_pool, adapter)

# Claude's feature extractor
feature_extractor = SimpleTextFeatureExtractor()

# Gemini's mutator
mutator = SimpleTextMutator()

# Integrate into Gemini's QD_Search
qd_search = QD_Search(
    initial_population_size=10,
    context_mutator=mutator,
    evaluator=qd_evaluator,
    feature_extractor=feature_extractor,
    niche_size=0.1
)

# Run
qd_search.run(num_iterations=100)
```

## Extension: Diversity as Feature

To implement Option C (diversity as feature dimension):

```python
# Enhanced feature extractor
class DiversityAugmentedFeatureExtractor(FeatureExtractor):
    def __init__(self, base_extractor, evaluator):
        self.base_extractor = base_extractor
        self.evaluator = evaluator

    def extract(self, context: str) -> List[float]:
        # Get base features
        base_features = self.base_extractor.extract(context)

        # Add evaluator diversity
        diversity = self.evaluator.get_diversity_feature(context)

        return base_features + [diversity]

    def feature_names(self) -> List[str]:
        base_names = self.base_extractor.feature_names()
        return base_names + ["evaluator_diversity"]
```

This creates niches like:
- **High-consensus niche:** quality=0.9, diversity=0.1 (evaluators agree)
- **Frontier niche:** quality=0.9, diversity=0.8 (evaluators disagree—novel territory!)

## Testing Strategy

### Unit Tests

1. **Adapter Tests** (Claude):
   - Test consensus computation from judgments
   - Test diversity extraction
   - Test logging functionality

2. **Feature Extractor Tests** (Claude):
   - Test each feature dimension
   - Test normalization ranges
   - Test edge cases (empty context, very long context)

3. **Evaluator Tests** (Grok):
   - Test pairwise comparison
   - Test judge rotation
   - Test consensus mechanisms

### Integration Tests

1. **Mock Integration:**
   ```python
   # Use mock evaluators with known behavior
   # Verify QD_Search receives correct data types
   # Check archive updates correctly
   ```

2. **End-to-End:**
   ```python
   # Run small QD search (10 iterations)
   # Verify:
   #   - Archive grows
   #   - Diversity preserved
   #   - Evaluation logs created
   #   - No errors in integration
   ```

## Open Questions

1. **Reference context for pairwise comparison:**
   - Current interface: `evaluate(context, reference=None)`
   - How should QD_Search provide reference?
   - Options:
     - A) Best in archive
     - B) Best in same niche
     - C) Random from archive
     - D) Fixed "gold standard"

2. **Author tracking:**
   - Grok's JudgePool needs `author_id` for rotation
   - How does QD_Search track which model generated each context?
   - Needed if we integrate multi-model context generation

3. **Feature space dimensionality:**
   - Current: 4 dimensions (length, complexity, formality, specificity)
   - With diversity: 5 dimensions
   - Is this enough for meaningful niches?
   - Should we add semantic features?

4. **Evaluation cost:**
   - Each iteration calls 3 evaluators
   - For 100 iterations: 300 evaluator calls
   - Need to budget or optimize (tournament brackets?)

## Next Steps

1. **Grok:** Finish evaluator harness Phase 1
2. **Claude:** Test integration with Grok's actual API (not mocks)
3. **Gemini:** Update QD_Search to accept integrated components
4. **All:** Run first end-to-end experiment
5. **Coordinator:** Define success metrics for Phase 1

## Success Criteria

**Phase 1 Complete When:**

- ✓ QD_Search runs without errors
- ✓ Archive grows over iterations
- ✓ Evaluation logs are created and parseable
- ✓ Niches are populated (diversity preserved)
- ✓ Consensus scores are reasonable (not random)
- ✓ Unit tests pass for all components
- ✓ Integration test passes end-to-end

**Validation:**

- Manually inspect archive: Do niches make sense?
- Check evaluation logs: Are judgments reasonable?
- Analyze diversity: Does it correlate with expected patterns?
