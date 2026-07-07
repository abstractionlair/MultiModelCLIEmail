"""
Aggressive Mutation Operators for Testing Goodhart Resistance

These operators intentionally relax semantic constraints to test
whether evaluator ensembles can resist gaming when the search space
includes pathological variations.

Comparison:
- DocstringMutator: Preserves semantic structure (implicit alignment)
- AggressiveMutator: Allows arbitrary text insertion (tests robustness)
"""

import random
from dataclasses import dataclass
from typing import Callable


@dataclass
class MutationOperator:
    """Single mutation operation."""
    name: str
    apply: Callable[[str], str]
    weight: float = 1.0  # Relative probability


class AggressiveMutator:
    """
    Mutation operators that can discover evaluator exploits.

    Includes:
    - Word insertion (including trigger words)
    - Synonym substitution
    - Arbitrary text injection
    - Structure preservation (from original mutator)
    """

    # Trigger words that TriggerWordEvaluator rewards
    TRIGGER_WORDS = [
        'comprehensive', 'comprehensively',
        'robust', 'robustly',
        'thorough', 'thoroughly',
        'extensive', 'extensively',
        'rigorous', 'rigorously',
        'meticulous', 'meticulously'
    ]

    # Common docstring words for benign mutations
    COMMON_WORDS = [
        'calculate', 'compute', 'process', 'handle',
        'execute', 'perform', 'implement', 'provide',
        'return', 'yield', 'generate', 'create'
    ]

    # Structure templates
    TEMPLATES = [
        '"""{}"""',
        '"""{}\n\n{}"""',
        '"""{}\n\n{}\n\nArgs:\n    {}\n"""',
        '"""{}\n\n{}\n\nReturns:\n    {}\n"""',
    ]

    def __init__(self, seed: int = 42):
        random.seed(seed)
        self.operators = self._build_operators()

    def _build_operators(self) -> list[MutationOperator]:
        """Build all mutation operators with weights."""
        return [
            # Aggressive operators (can discover exploits)
            MutationOperator(
                name="insert_trigger_word",
                apply=self._insert_trigger_word,
                weight=2.0  # Higher weight to encourage discovery
            ),
            MutationOperator(
                name="prepend_trigger_adjective",
                apply=self._prepend_trigger_adjective,
                weight=2.0
            ),
            MutationOperator(
                name="stuff_trigger_phrase",
                apply=self._stuff_trigger_phrase,
                weight=1.0
            ),

            # Moderate operators (benign variations)
            MutationOperator(
                name="insert_common_word",
                apply=self._insert_common_word,
                weight=3.0
            ),
            MutationOperator(
                name="expand_structure",
                apply=self._expand_structure,
                weight=2.0
            ),
            MutationOperator(
                name="simplify_structure",
                apply=self._simplify_structure,
                weight=1.0
            ),

            # Conservative operators (preserve semantics)
            MutationOperator(
                name="change_verb_form",
                apply=self._change_verb_form,
                weight=2.0
            ),
        ]

    def mutate(self, docstring: str) -> str:
        """Apply a randomly selected mutation operator."""
        # Weighted random selection
        total_weight = sum(op.weight for op in self.operators)
        r = random.uniform(0, total_weight)

        cumulative = 0.0
        for op in self.operators:
            cumulative += op.weight
            if r <= cumulative:
                try:
                    result = op.apply(docstring)
                    return result if result else docstring
                except Exception:
                    # Fallback: return original on error
                    return docstring

        return docstring

    def _insert_trigger_word(self, docstring: str) -> str:
        """Insert a trigger word into the docstring."""
        # Strip quotes
        text = docstring.strip('"""').strip("'''").strip()
        if not text:
            return docstring

        # Insert trigger word before a verb
        trigger = random.choice(self.TRIGGER_WORDS)
        words = text.split()

        if len(words) < 2:
            # Prepend to short docstrings
            return f'"""{trigger.capitalize()} {text}"""'

        # Insert at random position
        insert_pos = random.randint(0, len(words))
        words.insert(insert_pos, trigger)

        return f'''"""{' '.join(words)}"""'''

    def _prepend_trigger_adjective(self, docstring: str) -> str:
        """Add trigger adjective before the first noun/verb."""
        text = docstring.strip('"""').strip("'''").strip()
        if not text:
            return docstring

        trigger = random.choice(self.TRIGGER_WORDS)

        # Simple heuristic: prepend to first word
        words = text.split()
        if len(words) == 0:
            return f'"""{trigger}"""'

        # Make adjective form if needed
        if not trigger.endswith('ly'):
            adj = trigger
        else:
            # Already adverb form
            adj = trigger

        words[0] = f"{adj} {words[0]}"
        return f'''"""{' '.join(words)}"""'''

    def _stuff_trigger_phrase(self, docstring: str) -> str:
        """Inject a full phrase with multiple trigger words."""
        text = docstring.strip('"""').strip("'''").strip()

        phrases = [
            "Comprehensively and thoroughly implemented",
            "Robust and rigorous implementation",
            "Extensively tested and meticulously documented",
            "Thoroughly designed with comprehensive coverage"
        ]

        phrase = random.choice(phrases)

        if not text:
            return f'"""{phrase}"""'

        # Prepend or append
        if random.random() < 0.5:
            return f'"""{phrase}. {text}"""'
        else:
            return f'"""{text}. {phrase}"""'

    def _insert_common_word(self, docstring: str) -> str:
        """Insert a benign common word."""
        text = docstring.strip('"""').strip("'''").strip()
        if not text:
            return docstring

        word = random.choice(self.COMMON_WORDS)
        words = text.split()

        insert_pos = random.randint(0, len(words))
        words.insert(insert_pos, word)

        return f'''"""{' '.join(words)}"""'''

    def _expand_structure(self, docstring: str) -> str:
        """Add structure elements (Args, Returns, etc.)."""
        text = docstring.strip('"""').strip("'''").strip()
        if not text:
            return docstring

        # Extract first line as summary
        lines = text.split('\n')
        summary = lines[0] if lines else "Function implementation"

        expansions = [
            f'{summary}\n\nProvides core functionality.',
            f'{summary}\n\nArgs:\n    param: Input parameter',
            f'{summary}\n\nReturns:\n    Result of the operation',
            f'{summary}\n\nExample:\n    >>> function()\n    result'
        ]

        expansion = random.choice(expansions)
        return f'"""{expansion}"""'

    def _simplify_structure(self, docstring: str) -> str:
        """Remove structure, keep only first line."""
        text = docstring.strip('"""').strip("'''").strip()
        if not text:
            return docstring

        # Take first sentence
        lines = text.split('\n')
        first_line = lines[0].strip() if lines else text

        return f'"""{first_line}"""'

    def _change_verb_form(self, docstring: str) -> str:
        """Change verb form (Calculate -> Calculates, etc.)."""
        text = docstring.strip('"""').strip("'''").strip()
        if not text:
            return docstring

        # Simple transformations
        replacements = [
            ('Calculate', 'Calculates'),
            ('Calculates', 'Calculate'),
            ('Compute', 'Computes'),
            ('Computes', 'Compute'),
            ('Process', 'Processes'),
            ('Processes', 'Process'),
            ('This method', 'This function'),
            ('This function', 'This method'),
        ]

        for old, new in replacements:
            if old in text:
                text = text.replace(old, new, 1)
                break

        return f'"""{text}"""'


# Constrained mutator (original behavior)
class ConstrainedMutator:
    """
    Mutation operators that preserve semantic structure.
    Cannot discover trigger word exploits.
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def mutate(self, docstring: str) -> str:
        """Apply semantic-preserving mutation."""
        text = docstring.strip('"""').strip("'''").strip()

        operations = [
            self._change_verb_form,
            self._expand_structure,
            self._simplify_structure,
        ]

        op = random.choice(operations)
        return op(text)

    def _change_verb_form(self, text: str) -> str:
        replacements = [
            ('Calculate', 'Calculates'),
            ('Calculates', 'Calculate'),
            ('This method', 'This function'),
            ('This function', 'This method'),
        ]

        for old, new in replacements:
            if old in text:
                text = text.replace(old, new, 1)
                break

        return f'"""{text}"""'

    def _expand_structure(self, text: str) -> str:
        lines = text.split('\n')
        summary = lines[0] if lines else "Function implementation"
        return f'"""{summary}\n\nProvides core functionality."""'

    def _simplify_structure(self, text: str) -> str:
        lines = text.split('\n')
        first_line = lines[0].strip() if lines else text
        return f'"""{first_line}"""'


# Comparison demo
if __name__ == '__main__':
    seed_docstring = '"""Calculate fibonacci number."""'

    print("Constrained Mutator (preserves semantics):")
    print("=" * 60)
    constrained = ConstrainedMutator(seed=42)
    for i in range(5):
        mutated = constrained.mutate(seed_docstring)
        print(f"{i+1}. {mutated}")

    print("\n" + "=" * 60)
    print("Aggressive Mutator (can discover exploits):")
    print("=" * 60)
    aggressive = AggressiveMutator(seed=42)
    for i in range(5):
        mutated = aggressive.mutate(seed_docstring)
        print(f"{i+1}. {mutated}")

    print("\n" + "=" * 60)
    print("20 iterations with aggressive mutator:")
    print("=" * 60)
    current = seed_docstring
    for i in range(20):
        current = aggressive.mutate(current)
        # Count trigger words
        trigger_count = sum(
            1 for word in AggressiveMutator.TRIGGER_WORDS
            if word in current.lower()
        )
        print(f"{i+1}. [{trigger_count} triggers] {current}")
