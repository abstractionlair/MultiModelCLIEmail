# Gaming Dynamics in Ensemble Evaluation

## Core Question

**When does an ensemble of evaluators resist gaming, and when does it fail?**

This is not just an empirical question. Understanding the mechanism is essential for:
- Predicting when Goodhart's law will bite
- Designing robust ensembles at scale
- Knowing when human calibration is necessary vs optional

## Theoretical Framework

### Three Resistance Mechanisms

#### 1. Vote Dilution
**Hypothesis**: A biased evaluator's influence is proportional to its weight in the ensemble.

**Prediction**:
- Gaming succeeds when: weight × bias > Σ(other_judges' resistance)
- For majority voting: Need >50% biased judges to fully game
- For consensus: One biased judge may be sufficient if others are indifferent

**Test**: Run ensemble with varying proportions of TriggerWordEvaluator
- 1/3, 2/3, 3/3 biased judges
- Measure gaming success vs proportion

**Implication**: If true, ensemble size is the primary defense

#### 2. Adversarial Coupling
**Hypothesis**: Evaluators penalize what biased evaluators reward (implicit anti-correlation)

**Prediction**:
- Some judge preferences are *negatively correlated*
- Length judge may penalize verbosity that TriggerWord rewards
- Gaming attempts reduce overall consensus

**Test**: Measure pairwise judge correlation matrices
- If TriggerWord vs Length shows negative correlation, coupling exists
- Compare gaming success when judges are aligned vs adversarial

**Implication**: If true, judge diversity (in preference structure) is the primary defense

#### 3. Signal Saturation
**Hypothesis**: Biased features are inherently limited in their contribution to quality

**Prediction**:
- Optimizing for trigger words hits diminishing returns
- Beyond some threshold, trigger word stuffing reduces quality for all judges
- Gaming plateaus at partial optimization

**Test**: Create outputs with escalating trigger word density (0%, 5%, 10%, 20%, 50%)
- Measure each judge's preferences across the spectrum
- Find saturation points

**Implication**: If true, even weak opposing signals create resistance

## Diagnostic Metrics

### 1. Judge Correlation Matrix
```python
def compute_judge_correlations(
    evaluations: list[EvaluationResult]
) -> np.ndarray:
    """
    For each pair of judges, compute correlation of their preferences.

    Returns: n_judges × n_judges correlation matrix
    - Positive: Judges agree on quality
    - Negative: Judges anti-correlate (adversarial)
    - Zero: Judges are orthogonal
    """
```

### 2. Gaming Success Rate
```python
def measure_gaming_success(
    archive: Archive,
    bias_detector: Callable[[str], float]
) -> dict:
    """
    How much did the population shift toward the bias?

    Returns:
    - mean_bias_score: Average bias feature value in archive
    - bias_score_change: Δ from initial to final population
    - bias_saturation: % of archive at maximum bias
    - quality_tradeoff: Change in human-labeled quality
    """
```

### 3. Ensemble Robustness Score
```python
def ensemble_robustness(
    judgments: list[Judgment],
    canary_labels: dict[str, Quality]
) -> float:
    """
    How resilient is the ensemble to individual judge failure?

    Test: Remove each judge, recompute consensus, check canary accuracy

    Returns: min(accuracy) across all leave-one-out tests
    - 1.0 = Perfect robustness (any judge can fail without degradation)
    - 0.0 = Single point of failure
    """
```

## Experimental Design

### Experiment 1: Vote Dilution Test
**Manipulate**: Proportion of biased judges (1/3, 2/3, 3/3)
**Measure**: Gaming success rate
**Prediction**: Linear relationship (if vote dilution is dominant)

### Experiment 2: Adversarial Coupling Test
**Manipulate**: Judge selection (aligned vs adversarial sets)
**Measure**: Judge correlation matrix + gaming success
**Prediction**: Negative correlation predicts resistance

### Experiment 3: Signal Saturation Test
**Manipulate**: Feature density in candidates (0% to 100% trigger words)
**Measure**: Per-judge preference curves
**Prediction**: Saturation at intermediate density

### Experiment 4: Ensemble Size Scaling
**Manipulate**: Number of judges (3, 5, 7, 9)
**Measure**: Robustness score + gaming resistance
**Prediction**: Logarithmic improvement (diminishing returns)

## Connection to Hayek's Knowledge Problem

The ensemble's resistance to gaming parallels the socialist calculation debate:

- **Central planner** (single evaluator): Can be gamed by optimizing for known bias
- **Market** (ensemble): Gaming requires coordinating exploitation across diverse preferences
- **Price system** (pairwise rankings): Aggregates distributed information without revealing individual biases

**Key insight**: Ensemble resistance comes from *irreducible preference diversity*, not just vote counting.

If evaluators have truly independent quality notions, gaming requires satisfying all simultaneously—which converges toward actual quality.

But if evaluators share hidden correlations (e.g., all reward verbosity), gaming exploits the shared structure.

**This suggests**: The critical design parameter is *preference independence*, measured by correlation matrix.

## Analysis Tooling

To validate this framework, we need:

1. **Post-experiment analyzer** that computes:
   - Judge correlation matrices over time
   - Gaming trajectory (how bias features evolve)
   - Robustness scores per iteration

2. **Visualization** showing:
   - Archive evolution in feature space
   - Judge agreement/disagreement dynamics
   - Canary stability over iterations

3. **Regression analysis** testing:
   - Does judge diversity predict resistance?
   - Does ensemble size show diminishing returns?
   - Do adversarial judge pairs increase robustness?

## Implementation Priority

1. **Judge correlation tracker** - essential diagnostic
2. **Gaming success metric** - outcome measure
3. **Robustness score** - ensemble health check
4. **Post-hoc analyzer** - for experiment results

Then run Grok's Phase 1 experiment with full telemetry.

## Open Questions

1. **Can we design for adversarial coupling?** Or does it emerge accidentally?
2. **Is there an optimal ensemble size?** Or always "more is better"?
3. **How do we measure preference independence a priori?**
4. **Can meta-learning discover robust judge combinations?**

## Next: Build the Analysis Infrastructure

The experiment is ready. We need the instrumentation to understand what we observe.
