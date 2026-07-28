"""Seed the RAG vector store with FAQ + college/major/admission summaries from existing DB."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from typing import Any

sys.path.insert(0, ".")

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.rag.store import add_chunk, add_faq, init_vector_store


FAQ_LIST: list[tuple[str, str]] = [
    ("什么是冲稳保？",
     "冲稳保是志愿填报的基本原则：冲（冲刺）——填报略高于自己位次的院校，有一定难度但有机会；"
     "稳（稳妥）——填报与自己位次相当的院校，录取概率较高；"
     "保（保底）——填报低于自己位次的院校，确保有学可上。建议比例为冲30%、稳40%、保30%。"),

    ("什么是专业调剂？",
     "专业调剂是指考生被投档到某院校后，如果所填报的6个专业都未被录取，"
     "院校将其调剂到该院校专业组内其他未录满的专业。建议勾选服从调剂，避免被退档。"),

    ("什么是滑档？",
     "滑档是指考生填报的所有志愿都未被录取，直接落到下一批次或征集志愿。"
     "避免滑档的关键是合理设置保底志愿，确保至少有一到两个录取概率较高的志愿。"),

    ("什么是退档？",
     "退档是指考生档案被投档到某院校后，因专业不服从调剂、体检不合格、单科成绩不达标等原因"
     "被院校退回。退档后只能参加征集志愿或下一批次录取。"),

    ("什么是专业组？",
     "专业组是院校将若干个相近或相关专业组合在一起作为一个志愿单位。"
     "考生填报时以专业组为单位，组内的专业可以排序。"
     "同一院校可能有多个专业组，不同组可能有不同的选科要求、录取分数线。"),

    ("专业组内的专业如何排序？",
     "建议将最想读且有把握的专业排在前面。通常录取概率较高"
     "（该专业往年位次明显低于你的位次）的排前，同时也要考虑自己的兴趣和学科优势。"),

    ("专业组可以只填部分专业吗？",
     "可以。如果专业组内有你不接受的专业，可以不填在组内排序中。"
     "但要注意，如果选择服从调剂，仍可能被调剂到组内未填报的专业。"),

    ("什么是征集志愿？",
     "征集志愿是指每批次录取结束后，部分院校未完成招生计划，面向未被录取的考生再次征集志愿。"
     "通常时间较短（1-2天），需要密切关注省教育考试院通知。"),

    ("什么是平行志愿？",
     "平行志愿是指考生在同一批次可填报多个志愿，按照《分数优先、遵循志愿》原则投档。"
     "即先按分数排序，再按考生志愿顺序依次检索，一旦投档成功，后续志愿自动失效。"),

    ("平行志愿的顺序重要吗？",
     "重要！虽然是平行志愿，但检索时按填报顺序进行。因此应该把最想去的院校专业组填在前面，"
     "把保底的放在后面。"),

    ("什么是院校专业组？",
     "院校专业组是新高考的志愿填报单位。一个院校可设置多个专业组，每个组内包含若干专业，"
     "组内专业有共同的选科要求。考生以专业组为单位填报志愿。"),

    ("如何选择适合自己的专业？",
     "可以从以下几个维度考虑：①学科优势——自己哪些科目学得好，选择相关专业；"
     "②兴趣方向——自己对哪些领域感兴趣；③就业前景——专业对应的行业发展趋势；"
     "④院校特色——不同院校的优势专业不同。"),

    ("选科与专业的关系是什么？",
     "在3+1+2新高考中，首选科目（物理/历史）决定了可报专业的大类。"
     "物理类可报绝大部分理工农医类专业，历史类可报文史哲法类专业。"
     "再选科目（化学/生物/政治/地理）进一步限制具体专业。"),

    ("体检受限专业有哪些？",
     "常见体检限制包括：色盲色弱限报化学类、医学类、美术类等专业；"
     "近视限报航海、飞行技术等专业；身高不足限报护理、表演、体育等专业。"
     "具体请查阅《普通高等学校招生体检工作指导意见》。"),

    ("什么是等效分？",
     "等效分是指将往年的录取分数换算成今年的对应分数。"
     "由于每年试题难度和分数线不同，不能直接比较原始分。"
     "通常用位次转换更准确，即用今年的位次去匹配往年相同位次的录取情况。"),

    ("位次比分数更可靠吗？",
     "是的。在志愿填报中，位次比分数更可靠。"
     "因为每年的试题难度、招生计划、考生人数都会影响分数线，"
     "但位次反映了你在全省考生中的相对位置，更加稳定。"),

    ("什么是分数优先原则？",
     "分数优先是指投档时，系统先对考生按总分从高到低排序，分数高的考生优先检索志愿。"
     "也就是说，你能否被某院校录取，主要取决于你的分数在报考该院校的考生中的排名。"),

    ("什么是顺序志愿？",
     "顺序志愿（梯度志愿）在提前批次中使用，按照《志愿优先、从高分到低分》原则投档。"
     "即先看考生第一志愿，第一志愿录满后才看第二志愿。这种模式下第一志愿至关重要。"),

    ("什么是大类招生？",
     "大类招生是院校将若干相近专业合并为一个大类进行招生。"
     "学生入学后先学习基础课程，一段时间后再根据成绩和兴趣分流到具体专业。"
     "大类招生给学生更多时间了解专业。"),

    ("如何判断一个院校的实力？",
     "可以从以下指标综合判断：①办学层次（985/211/双一流）；②学科评估等级；"
     "③硕博点数量；④科研经费；⑤毕业生就业率/深造率；⑥软科/校友会排名；"
     "⑦师资力量；⑧地域。"),

    ("什么是985院校？",
     "985院校是国家在1998年启动的世界一流大学建设工程，共39所。"
     "这些院校代表了中国高等教育的最高水平，包括清华、北大、复旦、上交、浙大等。"
     "985院校在就业、科研、深造方面有显著优势。"),

    ("什么是211院校？",
     "211院校是21世纪100所重点大学建设工程。全国共112所（含39所985）。"
     "211院校在师资力量、科研水平、就业认可度上都高于普通院校，"
     "是目前就业市场的重要门槛之一。"),

    ("什么是双一流？",
     "双一流是2017年启动的新一轮高等教育建设计划，"
     "包括一流大学建设高校（42所）和一流学科建设高校（95所）。"
     "双一流是动态调整的，打破了985/211的固化格局。"),

    ("什么是保研资格？",
     "保研资格（推免资格）是指院校有资格将优秀应届本科毕业生免试推荐到研究生招生单位。"
     "有保研资格的院校通常办学层次较高，学生可以通过保研继续深造，无需参加全国统考。"),

    ("如何权衡院校和专业的优先级？",
     "高分考生建议优先选院校，因为名校的平台资源更丰富；"
     "中等分数考生建议平衡院校与专业，选择院校的强势专业；"
     "低分考生建议优先选专业，确保学有所长。具体还需结合个人发展目标。"),

    ("什么是就业率？",
     "就业率是衡量院校毕业生就业情况的重要指标，"
     "通常包括协议就业、灵活就业、升学深造等。"
     "就业率越高，说明毕业生的社会认可度越高。但要注意不同院校就业率的统计口径。"),

    ("什么是转专业政策？",
     "转专业政策是指学生入学后可以从原专业转到其他专业学习。"
     "不同院校的转专业政策不同：有的宽松（大一大二均可转，不设限制），"
     "有的严格（仅限前几名或降级转）。填报时应了解目标院校的转专业政策。"),

    ("本科毕业后就业还是考研？",
     "取决于个人规划：①如果本科专业就业前景好（如计算机、电子、医学），可以优先就业；"
     "②如果想从事科研、教学或高端技术岗位，建议读研深造；"
     "③如果目标院校层次不高，考研是提升学历的重要途径。"),

    ("什么是国家专项计划？",
     "国家专项计划是面向贫困地区考生的定向招生计划，由中央部门院校和各省重点院校承担。"
     "符合条件的考生可以较低分数被录取。具体条件包括户籍、学籍等要求。"),

    ("什么是中外合作办学？",
     "中外合作办学是指国内院校与国外院校合作开设的办学项目。"
     "优点是能获得中外双重教育资源，缺点通常是学费较高（每年数万元）。"
     "部分项目可获得中外双学位。"),

    ("什么是预科班？",
     "预科班是面向少数民族考生的过渡性教育形式。"
     "预科生先在预科班学习一年，成绩合格后转入本科专业学习。"
     "预科的录取分数通常低于正常批次。"),
]


def generate_college_summaries(limit: int = 500) -> int:
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, name, province, city, type, level, tags,
               dorm_score, city_vitality, cost_index,
               employment_rate, avg_salary, graduate_rate,
               masters_count, ruanke_ranking,
               transfer_policy, admission_charter_url
        FROM colleges
        WHERE id IN (
            SELECT DISTINCT college_id FROM admission_ranks WHERE province='广东'
        )
        ORDER BY ruanke_ranking ASC NULLS LAST
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    count = 0
    for row in rows:
        r = dict(row)
        parts: list[str] = [r["name"]]
        level_info: list[str] = []
        if r.get("level") and r["level"] not in ("普通", ""):
            level_info.append(r["level"])
        if r.get("tags"):
            try:
                tags = json.loads(r["tags"])
                if isinstance(tags, list):
                    level_info.extend(t for t in tags if t)
            except Exception:
                if r.get("tags"):
                    level_info.append(r["tags"])
        if level_info:
            parts.append(f"办学层次：{'/'.join(level_info)}")
        parts.append(f"所在地：{r.get('province','')} {r.get('city','')}")
        parts.append(f"类型：{r.get('type','')}")

        stats: list[str] = []
        if r.get("ruanke_ranking"):
            stats.append(f"软科排名第{int(r['ruanke_ranking'])}")
        if r.get("employment_rate"):
            stats.append(f"就业率{float(r['employment_rate'])*100:.0f}%")
        if r.get("avg_salary"):
            stats.append(f"平均薪资{float(r['avg_salary']):.0f}元/月")
        if r.get("graduate_rate"):
            stats.append(f"保研率{float(r['graduate_rate'])*100:.1f}%")
        if r.get("masters_count"):
            stats.append(f"硕博点数{int(r['masters_count'])}")
        if r.get("dorm_score"):
            stats.append(f"宿舍评分{float(r['dorm_score']):.1f}/10")
        if r.get("city_vitality"):
            stats.append(f"城市活力{float(r['city_vitality']):.1f}/10")
        if r.get("cost_index"):
            stats.append(f"生活成本指数{float(r['cost_index']):.1f}")
        if stats:
            parts.append("；".join(stats))

        text = "，".join(parts)
        add_chunk(
            source=f"db:colleges/{r['id']}",
            content=text,
            doc_type="college_profile",
            title=r["name"],
            metadata={"college_id": r["id"]},
        )
        count += 1
    return count


def generate_major_summaries() -> int:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, category, subject_group, description, "
        "career_paths, course_intro, salary_range, discipline_evaluation, "
        "graduate_directions FROM majors"
    ).fetchall()
    conn.close()

    count = 0
    for row in rows:
        r = dict(row)
        parts: list[str] = [r["name"]]
        if r.get("category"):
            parts.append(f"门类：{r['category']}")
        if r.get("subject_group"):
            parts.append(f"学科：{r['subject_group']}")
        if r.get("description"):
            parts.append(f"简介：{r['description'][:200]}")
        if r.get("career_paths"):
            parts.append(f"就业方向：{r['career_paths'][:200]}")
        if r.get("course_intro"):
            parts.append(f"课程：{r['course_intro'][:200]}")
        if r.get("salary_range"):
            parts.append(f"薪酬：{r['salary_range']}")
        if r.get("discipline_evaluation"):
            parts.append(f"学科评估：{r['discipline_evaluation'][:100]}")
        if r.get("graduate_directions"):
            parts.append(f"考研方向：{r['graduate_directions'][:100]}")

        text = "，".join(parts)
        add_chunk(
            source=f"db:majors/{r['id']}",
            content=text,
            doc_type="major_profile",
            title=r["name"],
            metadata={"major_id": r["id"]},
        )
        count += 1
    return count


def generate_admission_summaries(top_n: int = 300) -> int:
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.college_id, c.name as college_name, a.group_code, a.year,
               a.min_rank, a.min_score, a.batch, a.enrollment_count
        FROM admission_ranks a
        JOIN colleges c ON a.college_id = c.id
        WHERE a.province='广东' AND a.exam_category='物理'
          AND a.major_id='GEN' AND a.min_rank > 0
          AND a.college_id IN (
              SELECT college_id FROM admission_ranks
              WHERE province='广东' AND exam_category='物理'
                AND major_id='GEN' AND min_rank > 0
              GROUP BY college_id HAVING MIN(min_rank) < 200000
              ORDER BY MIN(min_rank) ASC LIMIT ?
          )
        ORDER BY a.college_id, a.group_code, a.year DESC
    """, (top_n,)).fetchall()
    conn.close()

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["college_id"], r["group_code"])].append(dict(r))

    count = 0
    for (cid, gc), records in groups.items():
        college_name = records[0]["college_name"]
        years = [f"{r['year']}年最低位次{r['min_rank']}" for r in records if r["min_rank"] > 0]
        if not years:
            continue
        text = f"{college_name}{gc}组在广东物理类录取情况：{'，'.join(years)}"
        if records[0].get("batch"):
            text += f"，批次{records[0]['batch']}"
        add_chunk(
            source=f"db:admission/{cid}/{gc}",
            content=text,
            doc_type="admission_data",
            title=f"{college_name}{gc}组",
            metadata={"college_id": cid, "group_code": gc},
        )
        count += 1
    return count


def main() -> None:
    print("Initializing vector store...")
    init_vector_store()

    print(f"Ingesting {len(FAQ_LIST)} FAQ entries...")
    for q, a in FAQ_LIST:
        add_faq(q, a, source="faq_common")
    print(f"  -> {len(FAQ_LIST)} FAQ ingested")

    print("Ingesting college summaries (top 500 in Guangdong)...")
    coll_cnt = generate_college_summaries(limit=500)
    print(f"  -> {coll_cnt} college summaries ingested")

    print("Ingesting major summaries (all 516)...")
    maj_cnt = generate_major_summaries()
    print(f"  -> {maj_cnt} major summaries ingested")

    print("Ingesting admission data for top colleges (广东/物理)...")
    adm_cnt = generate_admission_summaries(top_n=300)
    print(f"  -> {adm_cnt} admission summaries ingested")

    total = len(FAQ_LIST) + coll_cnt + maj_cnt + adm_cnt
    print(f"\nTotal: {total} chunks ingested into RAG vector store")
    print("Done.")


if __name__ == "__main__":
    main()
