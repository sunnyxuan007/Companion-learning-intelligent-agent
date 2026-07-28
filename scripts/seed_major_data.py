"""
Seed the majors table with a standard undergraduate major taxonomy.

Data source: 教育部《普通高等学校本科专业目录》(2024年版) — public domain.
This file only contains publicly available major names and categories,
derived from the MOE standard classification. No proprietary data is used.
"""

from __future__ import annotations

from deeptutor.services.custom.college_dao import import_major
from deeptutor.services.custom.db import init_db
from deeptutor.services.custom.models import Major

MAJORS = [
    Major(id="EN001", name="计算机科学与技术", category="工学", subject_group="物理+化学"),
    Major(id="EN002", name="软件工程", category="工学", subject_group="物理+化学"),
    Major(id="EN003", name="数据科学与大数据技术", category="工学", subject_group="物理+化学"),
    Major(id="EN004", name="人工智能", category="工学", subject_group="物理+化学"),
    Major(id="EN005", name="电子信息工程", category="工学", subject_group="物理+化学"),
    Major(id="EN006", name="通信工程", category="工学", subject_group="物理+化学"),
    Major(id="EN007", name="机械设计制造及其自动化", category="工学", subject_group="物理+化学"),
    Major(id="EN008", name="电气工程及其自动化", category="工学", subject_group="物理+化学"),
    Major(id="EN009", name="土木工程", category="工学", subject_group="物理+化学"),
    Major(id="EN010", name="建筑学", category="工学", subject_group="物理+化学"),
    Major(id="EN011", name="自动化", category="工学", subject_group="物理+化学"),
    Major(id="EN012", name="材料科学与工程", category="工学", subject_group="物理+化学"),
    Major(id="EN013", name="新能源科学与工程", category="工学", subject_group="物理+化学"),
    Major(id="EN014", name="环境工程", category="工学", subject_group="物理+化学"),
    Major(id="SC001", name="数学与应用数学", category="理学", subject_group="物理+化学"),
    Major(id="SC002", name="物理学", category="理学", subject_group="物理+化学"),
    Major(id="SC003", name="化学", category="理学", subject_group="物理+化学"),
    Major(id="SC004", name="生物科学", category="理学", subject_group="物理+化学"),
    Major(id="SC005", name="统计学", category="理学", subject_group="物理+化学"),
    Major(id="SC006", name="心理学", category="理学", subject_group="物理+化学/生物"),
    Major(id="MD001", name="临床医学", category="医学", subject_group="物理+化学+生物"),
    Major(id="MD002", name="口腔医学", category="医学", subject_group="物理+化学+生物"),
    Major(id="MD003", name="药学", category="医学", subject_group="物理+化学+生物"),
    Major(id="MD004", name="护理学", category="医学", subject_group="化学+生物"),
    Major(id="BS001", name="工商管理", category="管理学", subject_group="不限"),
    Major(id="BS002", name="会计学", category="管理学", subject_group="不限"),
    Major(id="BS003", name="金融学", category="经济学", subject_group="不限"),
    Major(id="BS004", name="国际经济与贸易", category="经济学", subject_group="不限"),
    Major(id="BS005", name="法学", category="法学", subject_group="不限"),
    Major(id="BS006", name="新闻传播学", category="文学", subject_group="不限"),
    Major(id="BS007", name="英语", category="文学", subject_group="不限"),
    Major(id="BS008", name="汉语言文学", category="文学", subject_group="不限"),
    Major(id="BS009", name="教育学", category="教育学", subject_group="不限"),
    Major(id="BS010", name="思想政治教育", category="法学", subject_group="不限"),
    Major(id="AR001", name="视觉传达设计", category="艺术学", subject_group="不限"),
    Major(id="AR002", name="音乐表演", category="艺术学", subject_group="不限"),
]

TYPE_MAJOR_MAP = {
    "综合": ["EN001", "EN002", "EN005", "SC001", "SC002", "BS001", "BS002", "BS003", "BS005", "BS007", "BS008", "BS009"],
    "理工": ["EN001", "EN002", "EN003", "EN004", "EN005", "EN006", "EN007", "EN008", "EN009", "EN010", "EN011", "EN012", "EN013", "SC001", "SC002", "SC003", "BS001"],
    "工科": ["EN001", "EN002", "EN003", "EN004", "EN005", "EN006", "EN007", "EN008", "EN009", "EN010", "EN011", "EN012", "EN013"],
    "师范": ["BS009", "BS007", "BS008", "BS010", "SC001", "SC002", "SC003", "SC004", "SC006", "BS001"],
    "医药": ["MD001", "MD002", "MD003", "MD004", "SC004", "SC003"],
    "农林": ["EN014", "SC004", "BS001"],
    "财经": ["BS003", "BS004", "BS001", "BS002", "BS005", "BS007"],
    "政法": ["BS005", "BS010", "BS007", "BS008", "BS001"],
    "民族": ["BS008", "BS007", "BS010", "BS009", "BS001"],
    "语言": ["BS007", "BS008", "BS006", "BS003"],
    "艺术": ["AR001", "AR002", "BS008", "BS007"],
    "体育": ["BS009", "BS010"],
    "军事": ["EN001", "EN005", "EN008"],
}


def run():
    init_db()
    for major in MAJORS:
        import_major(major)
    print(f"Seeded {len(MAJORS)} majors.")


if __name__ == "__main__":
    run()
