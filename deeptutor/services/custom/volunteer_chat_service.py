from __future__ import annotations

import json
import time
from typing import Any

from deeptutor.services.llm import complete

RAG_ENABLED = True

SYSTEM_PROMPT = """你是高考志愿填报助手，专注于帮助考生选择院校和专业。

你可以回答以下问题：
1. 院校信息查询：办学层次、地域、特色
2. 专业介绍：课程、就业方向、考研方向
3. 录取策略：冲稳保梯度、志愿排序技巧
4. 选科适配：根据再选科目推荐可报专业
5. 院校对比：多维度比较不同院校

回答原则：
- 基于已知数据进行回答，不虚构院校或数据
- 给出建设性建议，但不替代考生决策
- 优先推荐广东省数据
- 用中文回答，语言亲切易懂"""

CLASSIFY_PROMPT = """判断以下用户问题属于哪一类，只输出 JSON，不要其他内容。

类别说明：
  - college_search: 查询院校基本信息（层次/地域/排名/特色/学费/就业），如"中山大学是985吗"、"广东有哪些好的理工院校"
  - admission_query: 查询录取数据（分数/位次/招生人数/录取概率），如"中山大学2025年多少分能上"、"我这个位次能上深圳大学吗"
  - major_query: 查询专业信息（课程/就业方向/考研方向/学科评估），如"计算机专业学什么"、"经济学就业怎么样"
  - general_qa: 政策咨询、策略建议、常识问答，不属于以上三类

问题：{message}
{"intent": ""}"""


SESSION_TTL = 3600


class VolunteerChatService:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def _get_or_create_session(self, session_id: str | None) -> tuple[str, list[dict[str, str]]]:
        now = time.time()
        if session_id and session_id in self._sessions:
            sess = self._sessions[session_id]
            sess["last_access"] = now
            return session_id, sess["messages"]

        sid = session_id or f"vc_{int(now)}"
        self._sessions[sid] = {"messages": [], "last_access": now}
        return sid, self._sessions[sid]["messages"]

    def _clean_stale(self) -> None:
        now = time.time()
        stale = [k for k, v in self._sessions.items() if now - v["last_access"] > SESSION_TTL]
        for k in stale:
            del self._sessions[k]

    async def _retrieve_context(self, message: str, college_name: str | None) -> str:
        if not RAG_ENABLED:
            return ""
        try:
            from .rag.retriever import format_context, retrieve_for_chat

            results = retrieve_for_chat(message, college_name=college_name, top_k=3)
            return format_context(results)
        except Exception:
            return ""

    async def _classify(self, message: str) -> str:
        prompt = CLASSIFY_PROMPT.replace("{message}", message)
        try:
            reply = await complete(prompt=prompt, system_prompt="你是一个分类器，只输出JSON。", temperature=0.1, max_tokens=128)
            reply_stripped = reply.strip()
            start = reply_stripped.find("{")
            end = reply_stripped.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(reply_stripped[start:end+1])
                intent = parsed.get("intent", "general_qa")
                if intent in ("college_search", "admission_query", "major_query", "general_qa"):
                    return intent
            # Handle case where only the JSON is returned
            if "college_search" in reply_stripped:
                return "college_search"
            if "admission_query" in reply_stripped:
                return "admission_query"
            if "major_query" in reply_stripped:
                return "major_query"
        except Exception:
            pass
        return "general_qa"

    async def _execute_tool(self, intent: str, message: str, context: dict[str, Any] | None) -> dict[str, Any] | None:
        if intent == "general_qa":
            return None

        province = (context or {}).get("province", "广东")
        exam_category = (context or {}).get("exam_category", "物理")
        rank = (context or {}).get("rank", 0)

        if intent == "college_search":
            from deeptutor.services.custom.college_dao import search_colleges
            try:
                colleges = search_colleges(limit=5, province=province)
                if not colleges:
                    colleges = search_colleges(limit=5)
                return {"type": "college_list", "data": colleges}
            except Exception:
                return {"type": "college_list", "data": []}

        if intent == "admission_query":
            from deeptutor.services.custom.db import get_connection
            try:
                conn = get_connection()
                rows = conn.execute("""
                    SELECT c.name as college_name, a.group_code, a.year,
                           a.min_rank, a.min_score, a.batch
                    FROM admission_ranks a
                    JOIN colleges c ON a.college_id = c.id
                    WHERE a.province=? AND a.exam_category=?
                      AND a.batch NOT LIKE '%专科%' AND a.batch != '专科批次'
                    ORDER BY a.min_rank ASC LIMIT 10
                """, (province, exam_category)).fetchall()
                conn.close()
                return {"type": "admission_list", "data": [dict(r) for r in rows]}
            except Exception:
                return {"type": "admission_list", "data": []}

        if intent == "major_query":
            from deeptutor.services.custom.db import get_connection
            try:
                conn = get_connection()
                rows = conn.execute(
                    "SELECT id, name, category, description, career_paths, salary_range, graduate_directions FROM majors LIMIT 10"
                ).fetchall()
                conn.close()
                return {"type": "major_list", "data": [dict(r) for r in rows]}
            except Exception:
                return {"type": "major_list", "data": []}

        return None

    def _format_tool_data(self, tool_result: dict[str, Any] | None) -> str:
        if not tool_result:
            return ""
        t = tool_result.get("type", "")
        data = tool_result.get("data", [])
        if not data:
            return ""

        if t == "college_list":
            lines = ["查到的院校信息："]
            for c in data[:5]:
                name = c.get("name", "")
                level = c.get("level", "")
                prov = c.get("province", "")
                city = c.get("city", "")
                emp = c.get("employment_rate", 0) or 0
                lines.append(f"- {name}（{level}，{prov}{city}，就业率{float(emp)*100:.0f}%）")
            return "\n".join(lines)

        if t == "admission_list":
            lines = ["查到的录取数据："]
            for r in data[:5]:
                lines.append(f"- {r.get('college_name','')}{r.get('group_code','')}组 {r.get('year','')}年最低位次{r.get('min_rank','?')} 最低分{r.get('min_score','?')} 批次{r.get('batch','?')}")
            return "\n".join(lines)

        if t == "major_list":
            lines = ["查到的专业信息："]
            for m in data[:5]:
                name = m.get("name", "")
                cat = m.get("category", "")
                desc = (m.get("description", "") or "")[:80]
                career = (m.get("career_paths", "") or "")[:80]
                lines.append(f"- {name}（{cat}）{desc}")
                if career:
                    lines[-1] += f" 就业：{career}"
            return "\n".join(lines)

        return ""

    async def chat(
        self,
        message: str,
        session_id: str | None = None,
        context: dict[str, Any] | None = None,
        learner_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sid, messages = self._get_or_create_session(session_id)
        self._clean_stale()

        # ① Intent classification
        intent = await self._classify(message)

        # ② Execute tool if needed
        tool_result = await self._execute_tool(intent, message, context)
        tool_text = self._format_tool_data(tool_result)

        # ③ Build system prompt
        system = SYSTEM_PROMPT
        extras = []

        # Inject learner profile from L3 memory
        if learner_profile:
            profile_lines = []
            if learner_profile.get("strengths"):
                profile_lines.append("学科优势: " + "; ".join(learner_profile["strengths"]))
            if learner_profile.get("weaknesses"):
                profile_lines.append("薄弱学科: " + "; ".join(learner_profile["weaknesses"]))
            if learner_profile.get("goals"):
                profile_lines.append("学习目标: " + "; ".join(learner_profile["goals"]))
            if learner_profile.get("career_interests"):
                profile_lines.append("职业兴趣: " + "; ".join(learner_profile["career_interests"]))
            if learner_profile.get("location_prefs"):
                profile_lines.append("地域偏好: " + "; ".join(learner_profile["location_prefs"]))
            if profile_lines:
                system += "\n\n学习者画像:\n" + "\n".join(profile_lines)

        if context:
            if context.get("college_name"):
                extras.append(f"当前查看院校：{context['college_name']}")
            if context.get("province"):
                extras.append(f"考生省份：{context['province']}")
            if context.get("exam_category"):
                extras.append(f"选考科目：{context['exam_category']}类")
            if context.get("rank"):
                extras.append(f"位次：{context['rank']}")
            if context.get("tier"):
                extras.append(f"当前关注档位：{context['tier']}")
        if extras:
            system += "\n\n当前对话上下文：\n" + "\n".join(extras)

        # RAG context
        college_name = context.get("college_name") if context else None
        rag_context = await self._retrieve_context(message, college_name)
        if rag_context:
            system += f"\n\n参考资料：\n{rag_context}"

        # Tool data
        if tool_text:
            system += f"\n\n数据库检索结果（来自 {intent}）：\n{tool_text}"

        # User message
        messages.append({"role": "user", "content": message})
        full_prompt = message
        if context and context.get("college_name"):
            full_prompt = f"[当前查看: {context['college_name']}]\n{message}"

        reply = await complete(
            prompt=full_prompt,
            system_prompt=system,
            temperature=0.7,
            max_tokens=1024,
        )

        messages.append({"role": "assistant", "content": reply})
        self._sessions[sid]["last_access"] = time.time()

        # ④ Write back to L3 if user expressed preferences
        pref_keywords = ["想去", "感兴趣", "更喜欢", "不想去", "不考虑", "想读", "想学"]
        if any(kw in message for kw in pref_keywords):
            from deeptutor.services.custom.memory_bridge import write_preference_signal

            try:
                await write_preference_signal(
                    text=f"志愿咨询: {message[:200]}",
                    trace_id=f"volunteer_chat:{sid}:{int(time.time())}",
                )
            except Exception:
                pass

        return {"reply": reply, "session_id": sid, "intent": intent}

    def reset_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]


_service: VolunteerChatService | None = None


def get_chat_service() -> VolunteerChatService:
    global _service
    if _service is None:
        _service = VolunteerChatService()
    return _service
