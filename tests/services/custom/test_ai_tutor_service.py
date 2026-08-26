"""AI 分析服务测试：LLM 成功/降级路径、错题本与学习记录落库。"""

from __future__ import annotations

import pytest

from deeptutor.services.custom import ai_tutor_service
from deeptutor.services.custom.ai_tutor_service import get_ai_tutor_service
from deeptutor.services.custom.mistake_dao import get_mistake
from deeptutor.services.custom.study_dao import get_study_timeline


async def _fake_complete_ok(prompt: str, **kwargs):
    return """```json
{
  "question": "求函数 f(x)=x^2-4x 在 [1,5] 上的最小值",
  "answer": "f(2)=-4",
  "explanation": "求导得 f'(x)=2x-4，令其为零得 x=2，端点和极值点比较后最小值为 -4。",
  "knowledge_points": ["二次函数", "导数求极值"],
  "mistake_reason": "方法不会",
  "difficulty": "medium",
  "is_mistake": true,
  "suggestions": "多练导数求极值的题型"
}
```"""


async def _fake_complete_fail(prompt: str, **kwargs):
    raise RuntimeError("LLM unavailable")


@pytest.mark.usefixtures("custom_db")
class TestAiTutorService:
    async def test_analyze_success_writes_mistake_and_record(self, monkeypatch):
        monkeypatch.setattr(ai_tutor_service, "complete", _fake_complete_ok)
        result = await get_ai_tutor_service().analyze_content(
            "user1", subject="数学", source_type="mistake", content="求 f(x)=x^2-4x 最小值"
        )
        assert result["ok"] is True
        assert result["analysis_status"] == "ok"
        assert result["knowledge_points"] == ["二次函数", "导数求极值"]
        assert result["mistake_reason"] == "方法不会"

        # 错题本落库
        m = get_mistake(result["mistake_id"])
        assert m is not None
        assert m["question"].startswith("求函数")
        assert m["ai_answer"] == "f(2)=-4"
        assert m["knowledge_points"] == ["二次函数", "导数求极值"]
        assert m["status"] == "open"

        # 学习记录落库（打通既有画像）
        records = get_study_timeline("user1", days=30)
        latest = records[0] if records else {}
        assert latest.get("record_type") == "mistake"
        assert latest.get("weak_points") == ["二次函数", "导数求极值"]

    async def test_analyze_fallback_when_llm_fails(self, monkeypatch):
        monkeypatch.setattr(ai_tutor_service, "complete", _fake_complete_fail)
        result = await get_ai_tutor_service().analyze_content(
            "user2", subject="物理", source_type="homework", content="一道不会的物理题"
        )
        assert result["ok"] is False
        assert result["analysis_status"] == "pending"
        m = get_mistake(result["mistake_id"])
        assert m is not None
        assert m["question"] == "一道不会的物理题"  # 原文兜底，不丢失内容
        assert m["ai_answer"] == ""

    async def test_analyze_correct_answer_no_mistake(self, monkeypatch):
        async def fake_ok(prompt: str, **kwargs):
            return '{"question":"q","answer":"a","explanation":"e","knowledge_points":["阅读"],"difficulty":"easy","is_mistake":false}'

        monkeypatch.setattr(ai_tutor_service, "complete", fake_ok)
        result = await get_ai_tutor_service().analyze_content(
            "user1", subject="英语", source_type="paper", content="做对的阅读题"
        )
        assert result["is_mistake"] is False
        m = get_mistake(result["mistake_id"])
        assert m["status"] == "mastered"
        assert m["mastery"] == 0.8
