"""
feature_extractor.py

Extracts feature vectors from contexts to enable quality-diversity search.
Features define the "behavioral characterization" of a context—what makes
it meaningfully different from other contexts.

The feature space determines what kinds of diversity the QD algorithm can discover.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
import re


class FeatureExtractor(ABC):
    """
    Abstract base class for feature extraction from contexts.

    Subclasses implement domain-specific feature extraction strategies.
    """

    @abstractmethod
    def extract(self, context: str) -> List[float]:
        """
        Extract a feature vector from a context.

        Args:
            context: The context string (prompt, constraint, meta-instruction)

        Returns:
            Feature vector as list of floats
        """
        pass

    @abstractmethod
    def feature_names(self) -> List[str]:
        """
        Return human-readable names for each feature dimension.

        Useful for visualization and debugging.
        """
        pass


class SimpleTextFeatureExtractor(FeatureExtractor):
    """
    Basic text-based feature extraction.

    Features:
    - Length (character count)
    - Complexity (average word length)
    - Formality (presence of formal markers)
    - Specificity (ratio of concrete to abstract words)
    """

    def extract(self, context: str) -> List[float]:
        """Extract simple text-based features."""
        return [
            self._length_feature(context),
            self._complexity_feature(context),
            self._formality_feature(context),
            self._specificity_feature(context)
        ]

    def feature_names(self) -> List[str]:
        return [
            "length",
            "complexity",
            "formality",
            "specificity"
        ]

    def _length_feature(self, context: str) -> float:
        """Character count, normalized to 0-1 range (assuming max ~1000 chars)."""
        return min(len(context) / 1000.0, 1.0)

    def _complexity_feature(self, context: str) -> float:
        """Average word length as proxy for complexity."""
        words = context.split()
        if not words:
            return 0.0
        avg_word_length = sum(len(w) for w in words) / len(words)
        # Normalize: assume avg word length ranges from 3 to 8
        return min(max((avg_word_length - 3) / 5, 0.0), 1.0)

    def _formality_feature(self, context: str) -> float:
        """Presence of formal markers (technical terms, passive voice, etc.)."""
        formal_markers = [
            r'\b(implement|execute|demonstrate|analyze|synthesize)\b',
            r'\b(therefore|thus|consequently|furthermore)\b',
            r'\b(shall|must|should|ought)\b'
        ]

        matches = sum(
            len(re.findall(pattern, context, re.IGNORECASE))
            for pattern in formal_markers
        )

        # Normalize by length
        words = len(context.split())
        if words == 0:
            return 0.0
        return min(matches / words, 1.0)

    def _specificity_feature(self, context: str) -> float:
        """
        Ratio of specific/concrete words to abstract words.

        This is a rough heuristic based on word characteristics.
        """
        words = context.split()
        if not words:
            return 0.0

        # Heuristic: numbers, proper nouns (capitalized), technical terms indicate specificity
        specific_count = sum(
            1 for word in words
            if (word[0].isupper() and word not in ['The', 'A', 'An']) or
               any(char.isdigit() for char in word) or
               len(word) > 10  # Long words often technical
        )

        return min(specific_count / len(words), 1.0)


class SemanticFeatureExtractor(FeatureExtractor):
    """
    Semantic feature extraction using embeddings (future enhancement).

    This would use a pre-trained embedding model to extract semantic features
    like topic, domain, style, etc.

    For now, this is a placeholder showing the interface.
    """

    def __init__(self, embedding_model=None):
        """
        Args:
            embedding_model: Optional pre-trained embedding model
        """
        self.embedding_model = embedding_model
        # In future: load model like SBERT, USE, etc.

    def extract(self, context: str) -> List[float]:
        """
        Extract semantic features via embeddings.

        TODO: Implement once we integrate an embedding model.
        For now, returns zero vector as placeholder.
        """
        if self.embedding_model is None:
            # Placeholder: return zero vector
            return [0.0] * len(self.feature_names())

        # Future implementation:
        # embedding = self.embedding_model.encode(context)
        # return embedding.tolist()

        return [0.0] * len(self.feature_names())

    def feature_names(self) -> List[str]:
        """Semantic dimensions (placeholder)."""
        return [
            f"semantic_dim_{i}"
            for i in range(128)  # Typical embedding dimension
        ]


class CompositeFeatureExtractor(FeatureExtractor):
    """
    Combines multiple feature extractors.

    This allows using both text-based and semantic features together.
    """

    def __init__(self, extractors: List[FeatureExtractor]):
        """
        Args:
            extractors: List of FeatureExtractor instances to combine
        """
        self.extractors = extractors

    def extract(self, context: str) -> List[float]:
        """Concatenate features from all extractors."""
        features = []
        for extractor in self.extractors:
            features.extend(extractor.extract(context))
        return features

    def feature_names(self) -> List[str]:
        """Concatenate feature names from all extractors."""
        names = []
        for extractor in self.extractors:
            names.extend(extractor.feature_names())
        return names


# Example usage
if __name__ == "__main__":
    # Test with sample contexts
    contexts = [
        "Write a Python function to sort a list.",
        "Implement a sophisticated algorithm that demonstrates advanced computational techniques for organizing sequential data structures in ascending order.",
        "hey can u make something that sorts stuff? thx"
    ]

    extractor = SimpleTextFeatureExtractor()

    print("Feature names:", extractor.feature_names())
    print()

    for context in contexts:
        features = extractor.extract(context)
        print(f"Context: {context[:50]}...")
        print(f"Features: {features}")
        print()
