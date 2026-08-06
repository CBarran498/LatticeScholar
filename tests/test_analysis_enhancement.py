"""Tests for v0.9.3 enhancements: user custom questions and token budget."""

import json

import pytest

from latticescholar.config import Settings
from latticescholar.models import AnalyzeRequest
from latticescholar.services.analyzer import (
    CUSTOM_QUESTION_KEY,
    QUESTIONS,
    AnalyzerService,
    _sentence_records,
    _user_focus_question,
)
from latticescholar.services.llm import (
    TASK_OUTPUT_TOKENS,
    LLMService,
    _repair_truncated_json,
)


class TestRepairTruncatedJson:
    def test_valid_json_unchanged(self):
        valid = '{"key": "value", "list": [1, 2, 3]}'
        assert _repair_truncated_json(valid) == valid

    def test_empty_input(self):
        assert _repair_truncated_json("") == ""
        assert _repair_truncated_json("   ") == ""

    def test_truncated_object(self):
        truncated = '{"core_problem": "test", "methods": ["m1"'
        result = _repair_truncated_json(truncated)
        assert result
        parsed = json.loads(result)
        assert parsed["core_problem"] == "test"
        assert parsed["methods"] == ["m1"]

    def test_truncated_nested(self):
        truncated = '{"key_questions": [{"key": "pain_points", "answer": "test"'
        result = _repair_truncated_json(truncated)
        assert result
        parsed = json.loads(result)
        assert parsed["key_questions"][0]["key"] == "pain_points"

    def test_truncated_string_value(self):
        truncated = '{"answer": "这是一个很长的回答但是被截断了'
        result = _repair_truncated_json(truncated)
        if result:
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    def test_trailing_comma_removed(self):
        truncated = '{"a": 1, "b": 2,'
        result = _repair_truncated_json(truncated)
        assert result
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}

    def test_markdown_fence_stripped(self):
        fenced = '```json\n{"status": "ok"}\n```'
        result = _repair_truncated_json(fenced)
        assert result
        parsed = json.loads(result)
        assert parsed["status"] == "ok"

    def test_completely_invalid_returns_empty(self):
        assert _repair_truncated_json("not json at all") == ""

    def test_unclosed_array_in_object(self):
        truncated = '{"items": [{"id": 1}, {"id": 2}'
        result = _repair_truncated_json(truncated)
        assert result
        parsed = json.loads(result)
        assert len(parsed["items"]) == 2


class TestTaskOutputTokens:
    def test_paper_analysis_has_high_budget(self):
        assert TASK_OUTPUT_TOKENS["paper_analysis"] >= 16000

    def test_connection_test_has_low_budget(self):
        assert TASK_OUTPUT_TOKENS["connection_test"] <= 1024

    def test_output_tokens_for_task_uses_max(self):
        config = Settings(llm_provider="none", llm_max_output_tokens=4000)
        service = LLMService(config)
        assert service.output_tokens_for_task("paper_analysis") == 16000
        assert service.output_tokens_for_task("connection_test") == 4000

    def test_output_tokens_for_unknown_task_uses_config(self):
        config = Settings(llm_provider="none", llm_max_output_tokens=5000)
        service = LLMService(config)
        assert service.output_tokens_for_task("unknown_task") == 5000

    def test_output_tokens_respects_higher_config(self):
        config = Settings(llm_provider="none", llm_max_output_tokens=20000)
        service = LLMService(config)
        assert service.output_tokens_for_task("paper_analysis") == 20000
class TestUserFocusQuestion:
    def test_user_focus_finds_relevant_records(self):
        text = (
            "This paper proposes a novel approach to battery degradation modeling. "
            "The energy management system optimizes fuel consumption. "
            "Results demonstrate a 15% improvement in battery lifetime prediction."
        )
        records = _sentence_records(text)
        result = _user_focus_question("battery lifetime prediction", records, [])
        assert len(result) == 1
        assert result[0].key == CUSTOM_QUESTION_KEY
        assert result[0].verdict == "原文有相关线索"
        assert len(result[0].points) > 0

    def test_user_focus_no_match(self):
        text = "This paper studies machine learning for image classification."
        records = _sentence_records(text)
        result = _user_focus_question("量子计算", records, [])
        assert len(result) == 1
        assert result[0].key == CUSTOM_QUESTION_KEY
        assert result[0].verdict == "信息不足"

    def test_user_focus_empty_question(self):
        text = "Some research content about deep learning."
        records = _sentence_records(text)
        result = _user_focus_question("", records, [])
        assert len(result) == 1
        assert result[0].verdict == "信息不足"


class TestAnalyzerWithCustomQuestion:
    @pytest.mark.asyncio
    async def test_heuristic_mode_includes_user_focus(self):
        analyzer = AnalyzerService(LLMService(Settings(llm_provider="none")))
        result = await analyzer.analyze(
            AnalyzeRequest(
                title="Battery Degradation Modeling",
                abstract=(
                    "We propose a novel health-aware energy management strategy. "
                    "The method addresses battery aging in hybrid electric aircraft. "
                    "Results show 12% improvement in fuel economy while maintaining battery life. "
                    "However, external validation remains limited to simulation environments."
                ),
                research_question="电池老化对能源管理策略有什么影响？",
            )
        )
        assert result.mode == "heuristic"
        assert len(result.key_questions) == 5
        user_focus_q = [q for q in result.key_questions if q.key == CUSTOM_QUESTION_KEY]
        assert len(user_focus_q) == 1
        assert "电池老化" in user_focus_q[0].question

    @pytest.mark.asyncio
    async def test_heuristic_mode_without_custom_question(self):
        analyzer = AnalyzerService(LLMService(Settings(llm_provider="none")))
        result = await analyzer.analyze(
            AnalyzeRequest(
                title="Demo Paper",
                abstract=(
                    "We propose a novel framework for diagnosis. "
                    "Results show improved calibration on two datasets."
                ),
                research_question="",
            )
        )
        assert result.mode == "heuristic"
        assert len(result.key_questions) == 4
        assert all(q.key != CUSTOM_QUESTION_KEY for q in result.key_questions)

    @pytest.mark.asyncio
    async def test_custom_question_key_constant(self):
        assert CUSTOM_QUESTION_KEY == "user_focus"
        assert len(QUESTIONS) == 4


class TestLLMServiceDefaults:
    def test_default_output_tokens_increased(self):
        config = Settings(llm_provider="none")
        assert config.llm_max_output_tokens == 8000

    def test_version_updated(self):
        config = Settings()
        assert config.app_version == "0.9.3"

    def test_task_output_tokens_keys(self):
        assert "paper_analysis" in TASK_OUTPUT_TOKENS
        assert "idea" in TASK_OUTPUT_TOKENS
        assert "research_discussion" in TASK_OUTPUT_TOKENS
        assert "query_strategy" in TASK_OUTPUT_TOKENS
        assert "connection_test" in TASK_OUTPUT_TOKENS

    def test_output_tokens_method_exists(self):
        service = LLMService(Settings(llm_provider="none"))
        assert hasattr(service, "output_tokens_for_task")
        assert service.output_tokens_for_task("paper_analysis") >= 16000
        assert service.output_tokens_for_task("idea") >= 8000
        assert service.output_tokens_for_task("research_discussion") >= 8000


class TestRepairTruncatedJsonEdgeCases:
    def test_escaped_quotes_in_string(self):
        text = r'{"msg": "say \"hello\""}'
        result = _repair_truncated_json(text)
        assert result
        parsed = json.loads(result)
        assert "hello" in parsed["msg"]

    def test_deeply_nested_truncation(self):
        truncated = '{"a": {"b": {"c": [1, 2, 3'
        result = _repair_truncated_json(truncated)
        assert result
        parsed = json.loads(result)
        assert parsed["a"]["b"]["c"] == [1, 2, 3]

    def test_unicode_content(self):
        text = '{"answer": "这是中文内容"}'
        result = _repair_truncated_json(text)
        assert result
        parsed = json.loads(result)
        assert "中文" in parsed["answer"]

    def test_truncated_after_colon(self):
        truncated = '{"key":'
        result = _repair_truncated_json(truncated)
        if result:
            json.loads(result)

    def test_multiple_unclosed_brackets(self):
        truncated = '{"data": [{"items": [{"id": 1'
        result = _repair_truncated_json(truncated)
        assert result
        parsed = json.loads(result)
        assert parsed["data"][0]["items"][0]["id"] == 1
