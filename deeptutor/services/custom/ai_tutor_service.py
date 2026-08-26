"""AI 伴学分析服务 —— 错题/试卷/作业的智能分析入口。

流程：用户上传文本 → LLM 结构化分析（题目/答案/解析/知识点/错因/难度）
     → 写入错题本(mistakes) + 学习记录(study_records，打通既有画像)
     → 刷新学习者画像缓存(learner_profiles)

降级策略：LLM 调用失败时，仍把原文存入错题本并标记 `analysis_status=pending`，
不丢失用户上传内容；前端可人工补充答案/知识点后保存。
"""

from __future__ import annotations

import json
import time
from typing import Any

# 守卫式导入：LLM 依赖（如 json_repair）缺失时模块仍可导入，
# `_call_llm` 返回 None 走「原文兜底 + pending」降级路径，不阻塞错题入库。
try:
    from deeptutor.services.llm import complete
except Exception:  # pragma: no cover - 部署环境依赖齐全，仅在精简环境触发
    complete = None

ANALYZE_SYSTEM_PROMPT = """你是高中生伴学老师，负责分析学生上传的错题、试卷或作业内容。
请严格按 JSON 格式输出分析结果，不要输出任何其他文字。"""

ANALYZE_PROMPT = """请分析以下{kind}内容（科目：{subject}），输出 JSON：

{{
  "question": "题目原文（若内容是整张卷子，提取第一个需要分析的题目；若是单题则原样）",
  "answer": "本题的正确答案",
  "explanation": "解题步骤与解析，中文，尽量详细",
  "knowledge_points": ["本题涉及的知识点，1-4个，用中文短词，如 '函数单调性'"],
  "mistake_reason": "若为错题，分析错因（概念不清/计算失误/审题失误/方法不会/粗心），否则为空字符串",
  "difficulty": "easy|medium|hard",
  "is_mistake": true,
  "suggestions": "针对该知识点的学习建议，一句话"
}}

要求：
- knowledge_points 必须能对应该{kind}所属学科（{subject}）的核心考点
- answer 和 explanation 要准确，不确定时如实说明"无法确定"
- 如果内容包含多道题，只选择最值得分析的一道；如果内容不完整，question 填原文并在 explanation 中说明

{content}"""


class AiTutorService:
    """错题/试卷/作业分析服务（单例模式，与 VolunteerChatService 一致）。"""

    async def analyze_content(
        self,
        user_id: str,
        *,
        subject: str,
        source_type: str,
        content: str,
        question_hint: str | None = None,
    ) -> dict[str, Any]:
        """分析一段文本并写入错题本 + 学习记录，返回完整结果。"""
        if source_type not in ("mistake", "paper", "homework"):
            source_type = "mistake"
        kind = {"mistake": "错题", "paper": "试卷", "homework": "作业"}.get(source_type, "错题")

        prompt = ANALYZE_PROMPT.format(kind=kind, subject=subject or "未知", content=content[:6000])
        analysis = await self._call_llm(prompt)
        ok = analysis is not None

        question = (analysis or {}).get("question") or (question_hint or content[:500])
        answer = (analysis or {}).get("answer") or ""
        explanation = (analysis or {}).get("explanation") or ""
        knowledge_points = (analysis or {}).get("knowledge_points") or []
        if isinstance(knowledge_points, str):
            knowledge_points = [p.strip() for p in knowledge_points.split(",") if p.strip()]
        knowledge_points = [str(p).strip() for p in knowledge_points if str(p).strip()][:5]
        mistake_reason = (analysis or {}).get("mistake_reason") or ""
        difficulty = (analysis or {}).get("difficulty") or "medium"
        if difficulty not in ("easy", "medium", "hard"):
            difficulty = "medium"
        is_mistake = bool((analysis or {}).get("is_mistake", True))
        suggestions = (analysis or {}).get("suggestions") or ""

        # 写入错题本
        from deeptutor.services.custom.mistake_dao import create_mistake

        mistake = create_mistake(
            user_id,
            source_type=source_type,
            subject=subject,
            source_text=content[:4000],
            question=question,
            ai_answer=answer,
            ai_explanation=explanation,
            knowledge_points=knowledge_points,
            mistake_reason=mistake_reason,
            difficulty=difficulty,
            is_mistake=is_mistake,
            mastery=0.3 if is_mistake else 0.8,
            status="open" if is_mistake else "mastered",
        )

        # 打通既有学习记录（study_records 是 _calc_academic_fit / 自适应权重的数据源）
        self._write_study_record(
            user_id, subject, source_type, question, is_mistake, knowledge_points
        )

        # 刷新画像缓存（供升学侧读取）
        try:
            from deeptutor.services.custom.learner_profile_service import save_profile

            save_profile(user_id)
        except Exception:
            pass

        return {
            "ok": ok,
            "analysis_status": "ok" if ok else "pending",
            "mistake_id": mistake.get("id"),
            "subject": subject,
            "source_type": source_type,
            "question": question,
            "answer": answer,
            "explanation": explanation,
            "knowledge_points": knowledge_points,
            "mistake_reason": mistake_reason,
            "difficulty": difficulty,
            "is_mistake": is_mistake,
            "suggestions": suggestions,
            "raw_analysis": analysis,
        }

    async def _call_llm(self, prompt: str) -> dict[str, Any] | None:
        """调用 LLM 并容错解析 JSON；任何失败返回 None（走降级路径）。"""
        if complete is None:
            return None
        try:
            reply = await complete(
                prompt=prompt,
                system_prompt=ANALYZE_SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=1200,
            )
        except Exception:
            return None
        if not reply:
            return None
        return _extract_json(reply)

    def _write_study_record(
        self,
        user_id: str,
        subject: str,
        source_type: str,
        question: str,
        is_mistake: bool,
        knowledge_points: list[str],
    ) -> None:
        """写 study_records：错题 → weak_points；做对 → strong_points。

        复用现有 upload_study_record，让成绩画像（get_subject_summary）自动纳入
        本次分析结果 —— 无需改动升学侧任何代码。
        """
        try:
            from deeptutor.services.custom.models import StudyRecord
            from deeptutor.services.custom.study_dao import upload_study_record

            record_type = {"mistake": "mistake", "paper": "exam", "homework": "homework"}.get(source_type, "mistake")
            record = StudyRecord(
                id="",
                user_id=user_id,
                record_type=record_type,
                subject=subject,
                title=f"{subject} - {record_type} - AI分析",
                score=0.0 if is_mistake else 1.0,
                total=1.0,
                weak_points=knowledge_points if is_mistake else [],
                strong_points=[] if is_mistake else knowledge_points,
                created_at=time.time(),
            )
            upload_study_record(record)
        except Exception:
            pass


def _extract_json(reply: str) -> dict[str, Any] | None:
    """从 LLM 回复中稳健提取 JSON 对象（兼容代码块/前后缀杂讯）。"""
    text = reply.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


_service: AiTutorService | None = None


def get_ai_tutor_service() -> AiTutorService:
    global _service
    if _service is None:
        _service = AiTutorService()
    return _service
