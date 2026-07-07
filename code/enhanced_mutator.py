"""
enhanced_mutator.py

Enhanced mutation operators that can modify template text.

This enables realistic exploitation scenarios where prompt engineering
could inject trigger words or gaming strategies.
"""

import random
from demo_docstring_generation import DocstringContext, DocstringMutator


class EnhancedDocstringMutator(DocstringMutator):
    """Enhanced mutator that can modify template text (enables exploitation).
    
    This represents realistic prompt engineering scenarios where users
    might add descriptive adjectives or modify phrasing to improve results.
    
    Mutation types:
    - 40% style changes (formal/casual/technical)
    - 30% detail level changes (brief/moderate/verbose)
    - 30% template text modifications (add/remove descriptors)
    """
    
    # Descriptive adjectives that could appear in prompt engineering
    DESCRIPTORS = [
        "comprehensive", "robust", "efficient", "optimized",
        "thorough", "rigorous", "meticulous", "systematic",
        "carefully designed", "extensively tested", "well-documented",
        "advanced", "professional"
    ]
    
    def mutate(self, context: DocstringContext) -> DocstringContext:
        """Create mutated context with possible template modifications."""
        
        mutation_type = random.random()
        
        if mutation_type < 0.4:
            # Style mutation (40%)
            new_style = random.choice([s for s in self.STYLES if s != context.style])
            return DocstringContext(context.template, new_style, context.detail_level)
        
        elif mutation_type < 0.7:
            # Detail mutation (30%)
            new_detail = random.choice([d for d in self.DETAILS if d != context.detail_level])
            return DocstringContext(context.template, context.style, new_detail)
        
        else:
            # Template mutation (30%) - adds/removes descriptors
            return self._mutate_template(context)
    
    def _mutate_template(self, context: DocstringContext) -> DocstringContext:
        """Add or remove descriptive adjectives to/from template.
        
        This simulates realistic prompt engineering where users add
        qualitative descriptors to guide model output.
        """
        
        # 70% chance to add, 30% to remove
        if random.random() < 0.7:
            # Add descriptor
            descriptor = random.choice(self.DESCRIPTORS)
            
            # Insert at beginning or end of template
            if random.random() < 0.5:
                new_template = f"{descriptor} {context.template}"
            else:
                new_template = f"{context.template} {descriptor}"
        else:
            # Remove descriptor (if any present)
            new_template = context.template
            for desc in self.DESCRIPTORS:
                # Simple removal (could be more sophisticated)
                new_template = new_template.replace(desc, "").strip()
                new_template = new_template.replace("  ", " ")  # Clean double spaces
            
            # Fallback: if nothing to remove, add instead
            if new_template == context.template:
                descriptor = random.choice(self.DESCRIPTORS)
                new_template = f"{descriptor} {context.template}"
        
        return DocstringContext(
            new_template.strip(),
            context.style,
            context.detail_level
        )
