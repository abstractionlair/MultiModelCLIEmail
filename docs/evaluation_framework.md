# Evaluation Framework for Compositional Intelligence

## Overview

This framework provides the evaluation spine for quality-diversity search over contexts. It embodies architectural principles that resist Goodhart's law and maintain robustness as the system scales.

## Core Principles

### 1. Ensemble-Native Architecture

**Never a single evaluator.** Even the simplest implementation uses multiple judges.

**Rationale**: Single evaluators create single points of failure and optimization targets. Ensembles increase attack surface for gaming.

**Implementation**:
```python
class EvaluationResult:
    """Result from ensemble evaluation."""
    judgments: list[Judgment]  # From each evaluator
    consensus: Optional[float]  # Derived metric (e.g., median)
    diversity: float            # Disagreement measure

class Evaluator:
    """Abstract base for all evaluators."""
    def judge(self, candidate, reference=None) -> Judgment:
        raise NotImplementedError
```

### 2. Pairwise Comparison Over Absolute Scoring

**Compare, don't rate.** Evaluators answer "A or B?" not "how good is A?"

**Rationale**:
- Humans are better at relative judgments than absolute ones
- Harder to game (no fixed scale to anchor on)
- Naturally produces rankings without calibration

**Implementation**:
```python
class Judgment:
    """Result of pairwise comparison."""
    preferred: Literal['A', 'B', 'neither']
    confidence: float  # 0.0 to 1.0
    reasoning: Optional[str]

def evaluate_pair(evaluator: Evaluator,
                  candidate_a,
                  candidate_b) -> Judgment:
    """Core evaluation primitive."""
    return evaluator.judge(candidate_a, candidate_b)
```

### 3. Judge Rotation

**Evaluators should not judge their own outputs.** Prevent feedback loops.

**Rationale**: If model M generates content, and M also evaluates it, we get runaway optimization toward M's biases.

**Implementation**:
```python
class JudgePool:
    """Manages evaluator rotation."""

    def select_judges(self,
                     candidate_author: str,
                     n_judges: int = 3) -> list[Evaluator]:
        """Select judges excluding the author."""
        available = [e for e in self.evaluators
                    if e.id != candidate_author]
        return random.sample(available, min(n_judges, len(available)))
```

### 4. Hidden Canaries

**Embed known-quality examples that evaluators can't identify.** Detect drift and gaming.

**Rationale**: If we know ground truth for some examples, we can catch evaluator degradation.

**Implementation**:
```python
class CanarySet:
    """Hidden test cases with known quality."""

    def __init__(self):
        self.canaries: list[Canary] = []
        self.secret_markers: dict[str, CanaryId] = {}

    def inject(self, population: list) -> list:
        """Mix canaries into population invisibly."""
        ...

    def check_calibration(self, results: list[EvaluationResult]) -> float:
        """How well did evaluators rank known cases?"""
        ...
```

### 5. Human Calibration Points

**Periodic human feedback to recalibrate.** Not just initial training.

**Rationale**: Evaluators drift over time. Regular human input prevents unbounded drift.

**Implementation**:
```python
class CalibrationSchedule:
    """When and how to request human feedback."""

    def should_calibrate(self, iteration: int) -> bool:
        """Exponential backoff: frequent early, rare later."""
        return iteration in [1, 2, 4, 8, 16, 32, 64, 128, ...]

    def select_calibration_sample(self,
                                 population: list,
                                 n: int = 5) -> list:
        """Choose diverse, informative examples."""
        # Max diversity selection
        ...
```

## Minimal Viable Implementation

### Phase 1: Foundation (Week 1)

**Goal**: Basic ensemble with pairwise comparison

```python
# evaluator.py
class SimpleEvaluator(Evaluator):
    """Baseline: use existing model API for judgments."""

    def __init__(self, model_name: str):
        self.model = load_model(model_name)

    def judge(self, candidate_a, candidate_b) -> Judgment:
        prompt = f"""Compare these two outputs:

A: {candidate_a}
B: {candidate_b}

Which is better? Respond with 'A', 'B', or 'neither'."""

        response = self.model.generate(prompt)
        return parse_judgment(response)

# Usage
evaluators = [
    SimpleEvaluator("gpt-4"),
    SimpleEvaluator("claude-3"),
    SimpleEvaluator("gemini-pro")
]

def evaluate_candidate(candidate, reference):
    judgments = [e.judge(candidate, reference)
                for e in evaluators]
    return EvaluationResult(judgments)
```

### Phase 2: Rotation (Week 2)

**Goal**: Prevent self-evaluation

```python
class JudgePool:
    def __init__(self, evaluators: list[Evaluator]):
        self.evaluators = evaluators
        self.author_map = {}  # Track who generated what

    def evaluate(self, candidate, reference, author_id):
        judges = self.select_judges(author_id, n=3)
        judgments = [j.judge(candidate, reference) for j in judges]
        return EvaluationResult(judgments)
```

### Phase 3: Canaries (Week 3)

**Goal**: Detect evaluator drift

```python
canary_set = CanarySet([
    Canary(content="...", expected_quality="high"),
    Canary(content="...", expected_quality="low"),
    ...
])

# Every N iterations
if iteration % 10 == 0:
    population_with_canaries = canary_set.inject(population)
    results = evaluate_population(population_with_canaries)
    calibration_score = canary_set.check_calibration(results)

    if calibration_score < THRESHOLD:
        alert("Evaluators may be drifting!")
```

### Phase 4: Human Calibration (Week 4)

**Goal**: Ground truth feedback loop

```python
if calibration_schedule.should_calibrate(iteration):
    sample = calibration_schedule.select_calibration_sample(
        population, n=5
    )

    # Present to human
    human_judgments = request_human_feedback(sample)

    # Compare to model judgments
    model_judgments = evaluate_sample(sample)

    # Compute agreement
    agreement = compute_agreement(human_judgments, model_judgments)

    # Optional: Fine-tune evaluators on human feedback
    if agreement < THRESHOLD:
        fine_tune_evaluators(human_judgments)
```

## Anti-Patterns to Avoid

### 1. Single Evaluator
**Bad**: `score = evaluator.evaluate(candidate)`
**Good**: `scores = [e.evaluate(candidate) for e in evaluators]`

### 2. Absolute Scoring
**Bad**: `score = evaluator.rate(candidate)  # 0-100`
**Good**: `judgment = evaluator.compare(candidate_a, candidate_b)`

### 3. Self-Evaluation
**Bad**: `scores = [e.evaluate(e.generate()) for e in models]`
**Good**: `scores = judge_pool.evaluate(candidate, author_id=model.id)`

### 4. Set-and-Forget Evaluators
**Bad**: Train once, use forever
**Good**: Periodic canary checks + human calibration

### 5. Opaque Judgments
**Bad**: `score: float`
**Good**: `Judgment(preferred='A', confidence=0.8, reasoning="...")`

## Integration with QD Search

The evaluation framework plugs into QD search as the fitness function:

```python
# QD Search Loop
for iteration in range(max_iterations):
    # Generate variations (Gemini's mutation operators)
    candidates = generate_candidates(population, mutation_ops)

    # Evaluate (this framework)
    results = judge_pool.evaluate_batch(candidates)

    # Select (QD archive update)
    population = update_archive(population, candidates, results)

    # Calibrate periodically
    if calibration_schedule.should_calibrate(iteration):
        perform_calibration()
```

## Open Questions

1. **Consensus mechanisms**: How do we aggregate disagreeing judgments? Majority vote? Confidence-weighted? Discard outliers?

2. **Evaluator diversity**: Should we deliberately choose evaluators with different architectures/training? Or same architecture, different seeds?

3. **Cost vs quality tradeoff**: Pairwise comparisons are O(n²). Can we use adaptive sampling or tournament brackets to reduce cost?

4. **Meta-evaluation**: How do we evaluate the evaluators? Canaries help, but what's the full story?

5. **Adversarial robustness**: Can we red-team the evaluation framework itself? What attacks should we test against?

## Next Steps

1. Implement `Evaluator` base class and `SimpleEvaluator`
2. Build `JudgePool` with rotation logic
3. Create test suite with known-quality examples
4. Integrate with Gemini's QD scaffolding
5. Run initial experiments and measure evaluator agreement

## References

- Original conversation: `multimodel_conversation_DAG.md`
- Related: Goodhart's law, adversarial evaluation, RLHF failure modes
- Inspiration: Constitutional AI, debate-based evaluation, amplification
