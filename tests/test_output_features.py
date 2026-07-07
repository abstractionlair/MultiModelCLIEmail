"""Tests for output_feature_extractor module."""

import sys
sys.path.insert(0, '~/projects/MultiModelCLIEmail/code')

import unittest
from output_feature_extractor import (
    FeatureVector,
    OutputFeatureExtractor,
    OutputLengthFeature,
    OutputLineCountFeature,
    EvaluatorDiversityFeature,
    CodeComplexityFeature,
    create_code_output_extractor,
    create_generic_output_extractor,
)


class TestFeatureVector(unittest.TestCase):
    """Test FeatureVector dataclass."""

    def test_distance_calculation(self):
        """Test Euclidean distance between feature vectors."""
        import numpy as np

        fv1 = FeatureVector(
            values=np.array([0.0, 0.0]),
            names=["f1", "f2"],
            raw_values={"f1": 0.0, "f2": 0.0},
        )
        fv2 = FeatureVector(
            values=np.array([1.0, 0.0]),
            names=["f1", "f2"],
            raw_values={"f1": 1.0, "f2": 0.0},
        )

        self.assertAlmostEqual(fv1.distance(fv2), 1.0)

    def test_to_dict_serialization(self):
        """Test serialization to dict."""
        import numpy as np

        fv = FeatureVector(
            values=np.array([0.5, 0.7]),
            names=["f1", "f2"],
            raw_values={"f1": 50, "f2": 70},
            metadata={"test": True},
        )

        d = fv.to_dict()
        self.assertEqual(d["names"], ["f1", "f2"])
        self.assertEqual(d["raw_values"], {"f1": 50, "f2": 70})
        self.assertEqual(d["metadata"], {"test": True})


class TestOutputLengthFeature(unittest.TestCase):
    """Test OutputLengthFeature."""

    def test_string_length(self):
        """Test extracting length from string output."""
        feature = OutputLengthFeature()
        result = feature.extract(input="", output="hello world", context={})
        self.assertEqual(result, 11.0)

    def test_non_string_output(self):
        """Test handling non-string output."""
        feature = OutputLengthFeature()
        result = feature.extract(input="", output=123, context={})
        self.assertEqual(result, 0.0)


class TestOutputLineCountFeature(unittest.TestCase):
    """Test OutputLineCountFeature."""

    def test_single_line(self):
        """Test single-line output."""
        feature = OutputLineCountFeature()
        result = feature.extract(input="", output="single line", context={})
        self.assertEqual(result, 1.0)

    def test_multiple_lines(self):
        """Test multi-line output."""
        feature = OutputLineCountFeature()
        result = feature.extract(input="", output="line1\nline2\nline3", context={})
        self.assertEqual(result, 3.0)


class TestEvaluatorDiversityFeature(unittest.TestCase):
    """Test EvaluatorDiversityFeature."""

    def test_with_evaluation_result(self):
        """Test extraction when evaluation result is available."""

        class MockEvalResult:
            diversity = 0.75

        feature = EvaluatorDiversityFeature()
        context = {"evaluation_result": MockEvalResult()}
        result = feature.extract(input="", output="", context=context)
        self.assertEqual(result, 0.75)

    def test_without_evaluation_result(self):
        """Test default value when no evaluation available."""
        feature = EvaluatorDiversityFeature()
        result = feature.extract(input="", output="", context={})
        self.assertEqual(result, 0.5)


class TestCodeComplexityFeature(unittest.TestCase):
    """Test CodeComplexityFeature."""

    def test_no_control_flow(self):
        """Test code with no control flow."""
        feature = CodeComplexityFeature()
        code = "x = 1\ny = 2\nz = x + y"
        result = feature.extract(input="", output=code, context={})
        self.assertEqual(result, 0.0)

    def test_with_control_flow(self):
        """Test code with control flow."""
        feature = CodeComplexityFeature()
        code = "if x > 0:\n    for i in range(10):\n        try:\n            pass"
        result = feature.extract(input="", output=code, context={})
        self.assertGreater(result, 0.0)


class TestOutputFeatureExtractor(unittest.TestCase):
    """Test OutputFeatureExtractor ensemble."""

    def test_initialization(self):
        """Test extractor initialization."""
        extractor = OutputFeatureExtractor([
            OutputLengthFeature(),
            OutputLineCountFeature(),
        ])

        self.assertEqual(extractor.dimension(), 2)
        self.assertEqual(extractor.feature_names, ["output_length", "output_lines"])

    def test_feature_extraction(self):
        """Test feature extraction and normalization."""
        extractor = OutputFeatureExtractor([
            OutputLengthFeature(),
            OutputLineCountFeature(),
        ])

        fvec = extractor.extract(
            input="test",
            output="hello\nworld",
            context={},
        )

        self.assertEqual(len(fvec.values), 2)
        self.assertTrue(all(0 <= v <= 1 for v in fvec.values))
        self.assertIn("output_length", fvec.raw_values)
        self.assertIn("output_lines", fvec.raw_values)

    def test_normalization_updates(self):
        """Test that normalization statistics update with new observations."""
        extractor = OutputFeatureExtractor([OutputLengthFeature()])

        # First extraction
        fvec1 = extractor.extract(input="", output="short", context={})

        # Second extraction with longer output
        fvec2 = extractor.extract(input="", output="much longer output text", context={})

        # Both should be normalized to [0, 1]
        self.assertTrue(0 <= fvec1.values[0] <= 1)
        self.assertTrue(0 <= fvec2.values[0] <= 1)

        # Longer output should have higher feature value
        self.assertLess(fvec1.values[0], fvec2.values[0])

    def test_graceful_error_handling(self):
        """Test that feature extraction errors don't crash the system."""

        class FailingFeature(OutputLengthFeature):
            def extract(self, input, output, context):
                raise ValueError("Intentional failure")

        extractor = OutputFeatureExtractor([FailingFeature()])
        fvec = extractor.extract(input="", output="test", context={})

        # Should use default value (0.5) on failure (check raw value)
        self.assertEqual(fvec.raw_values["output_length"], 0.5)
        self.assertIn("extraction_errors", fvec.metadata)

    def test_reset_normalization(self):
        """Test resetting normalization statistics."""
        extractor = OutputFeatureExtractor([OutputLengthFeature()])

        # Extract with long output
        fvec1 = extractor.extract(input="", output="very long output" * 100, context={})

        # Extract with short output - should be normalized relative to first
        fvec2 = extractor.extract(input="", output="short", context={})
        self.assertLess(fvec2.values[0], fvec1.values[0])  # Short < Long

        # Reset normalization
        extractor.reset_normalization()

        # New extraction should use fresh statistics (becomes new minimum)
        fvec3 = extractor.extract(input="", output="short", context={})
        self.assertAlmostEqual(fvec3.values[0], 0.0, places=2)  # Minimum of new range


class TestFactoryFunctions(unittest.TestCase):
    """Test factory functions."""

    def test_create_code_output_extractor(self):
        """Test code output extractor factory."""
        extractor = create_code_output_extractor()
        self.assertGreater(extractor.dimension(), 0)
        self.assertIn("code_complexity", extractor.feature_names)

    def test_create_generic_output_extractor(self):
        """Test generic output extractor factory."""
        extractor = create_generic_output_extractor()
        self.assertGreater(extractor.dimension(), 0)
        self.assertIn("output_length", extractor.feature_names)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests with realistic scenarios."""

    def test_code_behavioral_diversity(self):
        """Test that different code styles produce distinct feature vectors."""
        extractor = create_code_output_extractor()

        # Simple one-liner
        simple = "def f(x): return x * 2"

        # Complex multi-function code
        complex_code = """
def helper(x):
    # Comment
    if x > 0:
        for i in range(x):
            yield i

def main():
    try:
        result = helper(10)
        for val in result:
            print(val)
    except Exception as e:
        pass
"""

        fvec_simple = extractor.extract(input="task", output=simple, context={})
        fvec_complex = extractor.extract(input="task", output=complex_code, context={})

        # Should produce different feature vectors
        distance = fvec_simple.distance(fvec_complex)
        self.assertGreater(distance, 0.1)  # Significantly different

    def test_evaluation_context_integration(self):
        """Test integration with evaluation results."""

        class MockEvalResult:
            diversity = 0.8
            consensus = 0.6

        extractor = create_code_output_extractor()
        context = {"evaluation_result": MockEvalResult()}

        fvec = extractor.extract(
            input="task",
            output="def f(): pass",
            context=context,
        )

        # Evaluation features should be present
        self.assertIn("eval_diversity", fvec.names)
        self.assertIn("eval_consensus", fvec.names)

        # Values should come from mock evaluation
        div_idx = fvec.names.index("eval_diversity")
        self.assertEqual(fvec.raw_values["eval_diversity"], 0.8)


if __name__ == "__main__":
    unittest.main()
