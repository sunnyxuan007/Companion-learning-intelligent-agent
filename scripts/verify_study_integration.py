"""独立验证脚本：不依赖 pytest，直接驱动错题本/画像/AI分析的真实代码路径。"""
from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

# 用临时库隔离真实数据
import deeptutor.services.custom.db as db_mod

_tmp = Path(tempfile.mkdtemp()) / "deeptutor_custom.db"
db_mod.get_custom_db_path = lambda: _tmp
db_mod.init_db()

from deeptutor.services.custom import ai_tutor_service
from deeptutor.services.custom.learner_profile_service import (
    build_academic_fit_inputs,
    compute_learner_profile,
    recommend_majors_by_profile,
)
from deeptutor.services.custom.mistake_dao import (
    add_review,
    create_mistake,
    get_mistake,
    get_mistake_stats,
    list_mistakes,
)
from deeptutor.services.custom.models import StudyRecord
from deeptutor.services.custom.study_dao import upload_study_record

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


def seed_study_records():
    now = time.time()
    for i, (subj, score, weak, strong) in enumerate(
        [
            ("数学", 85, ["函数", "导数"], ["代数"]),
            ("数学", 78, ["导数", "积分"], ["函数"]),
            ("英语", 92, [], ["阅读", "写作"]),
        ]
    ):
        upload_study_record(
            StudyRecord(
                id=f"R{i}",
                user_id="user1",
                record_type="exam",
                subject=subj,
                title=f"{subj}-考试",
                score=score,
                total=100,
                weak_points=weak,
                strong_points=strong,
                created_at=now - i * 86400,
            )
        )


async def main():
    print("== 1. 错题本 DAO ==")
    m = create_mistake("user1", subject="数学", question="求 f(x)=x² 的导数",
                       ai_answer="2x", knowledge_points=["导数"], difficulty="easy")
    check("create_mistake 返回 id", bool(m.get("id")))
    got = get_mistake(m["id"])
    check("get_mistake 字段完整", got["question"] == "求 f(x)=x² 的导数" and got["knowledge_points"] == ["导数"])
    for _ in range(3):
        got = add_review(m["id"], "user1", True)
    check("复习3次 mastery>0.8 且 mastered", got["mastery"] > 0.8 and got["status"] == "mastered", str(got["mastery"]))
    stats = get_mistake_stats("user1")
    check("stats.total == 1", stats["total"] == 1, str(stats["total"]))
    check("stats.by_subject 含数学", any(s["subject"] == "数学" for s in stats["by_subject"]))

    print("== 2. 画像引擎（先有成绩记录） ==")
    seed_study_records()
    profile = compute_learner_profile("user1")
    sm = profile["subject_mastery"]
    check("subject_mastery 含数学/英语", "数学" in sm and "英语" in sm)
    check("数学掌握度 ~0.815", 0.8 <= sm["数学"]["accuracy"] <= 0.9, str(sm["数学"]["accuracy"]))
    check("英语掌握度 >=0.9", sm["英语"]["accuracy"] >= 0.9, str(sm["英语"]["accuracy"]))

    print("== 3. 错题惩罚 → 画像衰减 ==")
    create_mistake("user1", subject="数学", knowledge_points=["导数"], mastery=0.3)
    create_mistake("user1", subject="数学", knowledge_points=["积分"], mastery=0.3)
    profile2 = compute_learner_profile("user1")
    check("两条未掌握错题 → 数学降", profile2["subject_mastery"]["数学"]["accuracy"] <= 0.70,
          str(profile2["subject_mastery"]["数学"]["accuracy"]))
    weak = {w["point"]: w for w in profile2["weak_knowledge_points"]}
    # 第1节那条导数错题已复习至 mastered（mastery>0.6）→ 归入强知识点；
    # 仅未掌握的两条（导数×1 + 积分×1）计为薄弱
    check("薄弱知识点含导数×1(未掌握)", weak.get("导数", {}).get("fail_count") == 1,
          str(weak.get("导数")))
    check("薄弱知识点含积分×1", weak.get("积分", {}).get("fail_count") == 1)

    print("== 4. 专业倾向 + 升学注入结构 ==")
    majors = profile2["preferred_majors"]
    check("preferred_majors 非空且降序", bool(majors) and all(
        majors[i]["fit_score"] >= majors[i + 1]["fit_score"] for i in range(len(majors) - 1)))
    rec = recommend_majors_by_profile("user1", top_n=3)
    check("recommend_majors_by_profile <= 3", len(rec) <= 3)
    inputs = build_academic_fit_inputs("user1")
    check("academic-inputs 键 == {_subjects,_learner_profile}", set(inputs) == {"_subjects", "_learner_profile"})
    check("_subjects 元素含 subject/count/avg_accuracy",
          all({"subject", "count", "avg_accuracy"} <= set(s) for s in inputs["_subjects"]))
    check("_learner_profile 含 strengths/weaknesses",
          "strengths" in inputs["_learner_profile"] and "weaknesses" in inputs["_learner_profile"])

    print("== 5. AI 分析（mock LLM） ==")
    async def fake_complete(prompt, **kw):
        return '{"question":"题目q","answer":"答案a","explanation":"解析e","knowledge_points":["函数","导数"],"mistake_reason":"方法不会","difficulty":"medium","is_mistake":true}'
    ai_tutor_service.complete = fake_complete
    res = await ai_tutor_service.get_ai_tutor_service().analyze_content(
        "user1", subject="数学", source_type="mistake", content="题目q"
    )
    check("AI 分析 ok", res["analysis_status"] == "ok")
    check("知识点解析", res["knowledge_points"] == ["函数", "导数"])
    check("错题本入库", get_mistake(res["mistake_id"]) is not None)
    from deeptutor.services.custom.study_dao import get_study_timeline
    recs = get_study_timeline("user1", days=30)
    check("study_record 写入(weak=知识点)", recs and recs[0].get("record_type") == "mistake")

    print("== 6. AI 降级路径 ==")
    async def fail_complete(prompt, **kw):
        raise RuntimeError("LLM down")
    ai_tutor_service.complete = fail_complete
    res2 = await ai_tutor_service.get_ai_tutor_service().analyze_content(
        "user2", subject="物理", source_type="homework", content="不会的题原文"
    )
    check("降级 pending", res2["analysis_status"] == "pending")
    m2 = get_mistake(res2["mistake_id"])
    check("原文兜底不丢内容", m2["question"] == "不会的题原文" and m2["ai_answer"] == "")

    print()
    print(f"结果: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
