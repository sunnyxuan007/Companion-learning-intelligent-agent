"""补入缺组（2026 广东本科批）+ rank_source 预估标记。

第一批（2026-08-17）：
  哈理工 g215（英语）、成信 g212（环境科学）、中南 g216（护理学）
  - 哈理工 g215：官方投档表有 GEN 位次（266942），缺专业明细
  - 成信 g212：官方投档表标注"(联合培养)"投档 0 人，缺 GEN + 专业明细
  - 中南 g216：官方投档表标注"(高校专项计划)"投档 0 人，缺 GEN + 专业明细

第二批（2026-08-17，GEN-only 残留清零）：
  哈理工 g214（物理·联合培养 8人） = 038 信息与计算科学（麦考瑞 2+2，更正表）
  哈理工 g207（历史·联合培养 5人） = 003 英语（麦考瑞 2+2，更正表）
  川师 g218（历史·联合培养 1人） = 016 英语（中外高水平 3+2 麦考瑞，与物理 g223 同构）
  香港珠海 g201（历史 6人） = 001 文学与社会科学院 + 002 商学院（Excel，组号一致）
  香港珠海 g202（物理 10人） = 003 文学与社会科学院 + 004 商学院 + 005 理工学院（Excel）
  中南财 g211（历史·中外合作 5人） = 国际经贸规则（与罗马一大中外合作，75000 元，用户确认）

位次规则（用户决策）：
  1. 优先用官方投档表位次（哈理工 g214/g207 均有官方位次）
  2. 无官方位次且无同专业参考 → 取该校所有专业组最低位次（最差组）
     成信校最低位次 = g214 (118244)；中南校最低位次 = g207 (24936)
  3. 预估位次标记 rank_source='estimated'，专业行 min_rank=0 靠组级 GEN 兜底

用法：python scripts/backfill_missing_groups.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from deeptutor.services.custom.db import get_connection

PROVINCE = "广东"
BATCH = "本科批"
YEAR = 2026

# (college_id, group_code, exam_category, GEN 位次, GEN 分数, GEN 计划, rank_source)
# 分数用 2025 分数段换算近似（2026 无分段数据）；第二批组均有官方位次直接用
GROUPS = [
    ("4123010214", "215", "物理", 266942, 450.0, 5, "official"),    # 哈尔滨理工大学 英语(联合培养)
    ("4151010621", "212", "物理", 118244, 526.0, 2, "estimated"),   # 成都信息工程大学 环境科学(联合培养)
    ("4143010533", "216", "物理", 24936, 602.0, 2, "estimated"),    # 中南大学 护理学(高校专项)
    ("4123010214", "214", "物理", 243058, 464.0, 8, "official"),    # 哈尔滨理工大学 信息与计算科学(联合培养)
    ("4123010214", "207", "历史", 111655, 442.0, 5, "official"),    # 哈尔滨理工大学 英语(联合培养)
    ("4151010636", "218", "历史", 12815, 566.0, 1, "official"),     # 四川师范大学 英语(中外高水平 3+2 麦考瑞)
    ("81012", "201", "历史", 59148, 495.0, 6, "official"),          # 香港珠海学院 (历史)
    ("81012", "202", "物理", 169128, 506.0, 10, "official"),        # 香港珠海学院 (物理)
    ("4142010520", "211", "历史", 4361, 594.0, 5, "official"),      # 中南财经政法大学 国际经贸规则(中外合作)
]

# (college_id, group_code, exam_category) -> [(major_id, major_name, years, campus, tuition, plan, full_name)]
# full_name 为空时用 major_name；已有 college_major_name 的行 full_name 传 None 复用现有
MAJORS = {
    ("4123010214", "215", "物理"): [("036", "英语", "4", "校本部", 46900, 5, None)],
    ("4151010621", "212", "物理"): [("035", "环境科学", "4", "航空港校区", 64240, 2, None)],
    ("4143010533", "216", "物理"): [("015", "护理学", "4", "岳麓山校区", 7800, 2, None)],
    ("4123010214", "214", "物理"): [("038", "信息与计算科学", "4", "校本部", 46300, 8, None)],
    ("4123010214", "207", "历史"): [("003", "英语", "4", "校本部", 46900, 5, None)],
    ("4151010636", "218", "历史"): [("016", "英语", "4", "成龙校区", 38300, 1, None)],
    ("81012", "201", "历史"): [
        ("001", "文学与社会科学院", "4", "", 104750, 2,
         "文学与社会科学院(外语≥100)(含中国文学、传播及数码媒体、犯罪学及刑事司法专修等专业)"),
        ("002", "商学院", "4", "", 104750, 2,
         "商学院(外语≥100)(含会计及银行、工商管理学、财务金融学、金融及资讯管理学专修等专业)"),
    ],
    ("81012", "202", "物理"): [
        ("003", "文学与社会科学院", "4", "", 104750, 1,
         "文学与社会科学院(外语≥100)(含中国文学、传播及数码媒体、犯罪学及刑事司法专修等专业)"),
        ("004", "商学院", "4", "", 104750, 3,
         "商学院(外语≥100)(含会计及银行、工商管理学、财务金融学、金融及资讯管理学专修等专业)"),
        ("005", "理工学院", "4", "", 104750, 2,
         "理工学院(外语≥100)(含资讯科学、建筑学专业；按学院招生，学生入学后根据个人兴趣和学习成绩选择专业)"),
    ],
    ("4142010520", "211", "历史"): [
        ("040", "国际经贸规则", "4", "校本部", 75000, 5,
         "国际经贸规则(中外合作办学)(与意大利罗马第一大学中外合作办学项目，具体培养模式和学习费用请查看学校网站)(湖北省武汉市)"),
    ],
}


def main() -> int:
    conn = get_connection()
    n_gen = 0
    n_major = 0
    n_cmn = 0
    for cid, gc, ec, gen_rank, gen_score, gen_plan, rank_source in GROUPS:
        # 1. GEN 行（仅当不存在时插入）
        exists = conn.execute(
            "SELECT 1 FROM admission_ranks WHERE college_id=? AND group_code=? AND major_id='GEN' AND year=? AND province=? AND exam_category=?",
            (cid, gc, YEAR, PROVINCE, ec),
        ).fetchone()
        if exists:
            print(f"  GEN 已存在，跳过：{cid} g{gc} [{ec}]")
        else:
            conn.execute(
                """INSERT OR REPLACE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code, rank_source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, "GEN", PROVINCE, YEAR, BATCH, gen_rank, gen_score, gen_plan, ec, gc, rank_source),
            )
            n_gen += 1
            print(f"  补 GEN：{cid} g{gc} [{ec}] rank={gen_rank} score={gen_score} plan={gen_plan} source={rank_source}")

        # 2. 专业行（min_rank=0，组级 GEN 兜底概率）
        for mid, mname, years, campus, tuition, plan, _full in MAJORS[(cid, gc, ec)]:
            conn.execute(
                """INSERT OR REPLACE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code, rank_source)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, mid, PROVINCE, YEAR, BATCH, 0, 0, plan, ec, gc, "official"),
            )
            n_major += 1
            print(f"  补专业行：{cid} g{gc} [{ec}] {mid} {mname} plan={plan}")

        # 3. college_major_name（学制/校区/学费）——仅当不存在时插入，保留已有明细
        for mid, mname, years, campus, tuition, plan, full in MAJORS[(cid, gc, ec)]:
            exists_cmn = conn.execute(
                "SELECT 1 FROM college_major_name WHERE college_id=? AND major_id=?",
                (cid, mid),
            ).fetchone()
            if exists_cmn:
                print(f"  college_major_name 已存在，跳过：{cid} {mid} {mname}")
                continue
            conn.execute(
                """INSERT INTO college_major_name
                   (college_id, major_id, major_name, full_name, category, subject_requirement, tuition, years, campus)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (cid, mid, mname, full or mname, "", "", tuition, years, campus),
            )
            n_cmn += 1

    conn.commit()
    print(f"\n完成：GEN {n_gen} 行 / 专业行 {n_major} 行 / college_major_name {n_cmn} 行")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())