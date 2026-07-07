import os
import pytest
from unittest.mock import MagicMock, patch

from code.evaluator_base import Preference, Judgment
from code.gemini_evaluator import GeminiEvaluator
from code.budget_controller import BudgetController, BudgetExceeded

# Mock the genai.get_model and its generate_content method
@pytest.fixture
def mock_gemini_model():
    with patch('google.generativeai.get_model') as MockGetModel:
        mock_model_instance = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '''
        ```json
        {
            "preferred": "A",
            "reasoning": "Content A is more concise and directly answers the question."
        }
        ```
        '''
        mock_model_instance.generate_content.return_value = mock_response
        MockGetModel.return_value = mock_model_instance
        yield MockGetModel

@pytest.fixture
def mock_budget_controller():
    with patch('code.budget_controller.BudgetController') as MockBudgetController:
        mock_instance = MockBudgetController.return_value
        mock_instance.check_cache.return_value = None
        mock_instance.get_cache_key.return_value = "test_cache_key"
        yield mock_instance

@pytest.fixture(autouse=True)
def set_gemini_api_key_env():
    original_api_key = os.getenv("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "test_api_key"
    yield
    if original_api_key is None:
        del os.environ["GEMINI_API_KEY"]
    else:
        os.environ["GEMINI_API_KEY"] = original_api_key

def test_gemini_evaluator_judge_method(mock_gemini_model, mock_budget_controller):
    evaluator = GeminiEvaluator(id="test-gemini-evaluator", budget_controller=mock_budget_controller)
    
    content_a = "The quick brown fox jumps over the lazy dog."
    content_b = "A dog is a man's best friend."

    judgment = evaluator.judge(content_a, content_b)

    assert isinstance(judgment, Judgment)
    assert judgment.preferred == Preference.A
    assert judgment.confidence == 0.9
    assert "concise" in judgment.reasoning
    
    mock_gemini_model.return_value.generate_content.assert_called_once()
    args, kwargs = mock_gemini_model.return_value.generate_content.call_args
    assert "Content A:" in args[0]
    assert "Content B:" in args[0]
    assert content_a in args[0]
    assert content_b in args[0]
    assert "Which content do you prefer, A or B, or neither?" in args[0]

    mock_budget_controller.get_cache_key.assert_called_once_with("test-gemini-evaluator", content_a, content_b)
    mock_budget_controller.check_cache.assert_called_once_with("test_cache_key")
    mock_budget_controller.check_budget.assert_called_once()
    mock_budget_controller.record_call.assert_called_once()
    mock_budget_controller.cache_result.assert_called_once_with("test_cache_key", judgment)

def test_gemini_evaluator_budget_exceeded(mock_gemini_model, mock_budget_controller):
    mock_budget_controller.check_budget.side_effect = BudgetExceeded("Test budget exceeded")
    evaluator = GeminiEvaluator(id="test-gemini-evaluator", budget_controller=mock_budget_controller)

    content_a = "Content A"
    content_b = "Content B"

    judgment = evaluator.judge(content_a, content_b)

    assert isinstance(judgment, Judgment)
    assert judgment.preferred == Preference.NEITHER
    assert judgment.confidence == 0.1
    assert "Budget exceeded" in judgment.reasoning
    mock_gemini_model.return_value.generate_content.assert_not_called()
    mock_budget_controller.check_budget.assert_called_once()
    mock_budget_controller.record_call.assert_not_called()
    mock_budget_controller.cache_result.assert_not_called()

def test_gemini_evaluator_no_api_key():
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable not set."):
        GeminiEvaluator(id="test-no-key")
