"""
context_mutators.py

This module defines various mutation operators for evolving contexts within the
Quality-Diversity (QD) search algorithm. Contexts can be prompts, constraints,
or meta-instructions.
"""

import random

class ContextMutator:
    """
    Base class for context mutation operators.
    """
    def mutate(self, context: str) -> str:
        """
        Applies a mutation to the given context.

        Args:
            context (str): The input context string.

        Returns:
            str: The mutated context string.
        """
        raise NotImplementedError("Subclasses must implement the mutate method")

class SimpleTextMutator(ContextMutator):
    """
    A simple text mutator that appends a random string to the context.
    This is a placeholder for more sophisticated context engineering mutations.
    """
    def mutate(self, context: str) -> str:
        """
        Appends a random alphanumeric string to the context.
        """
        random_suffix = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=5))
        return f"{context}_mutated_{random_suffix}"

# Example of how to use:
# mutator = SimpleTextMutator()
# original_context = "Generate a Python function to sort a list."
# mutated_context = mutator.mutate(original_context)
# print(mutated_context)
