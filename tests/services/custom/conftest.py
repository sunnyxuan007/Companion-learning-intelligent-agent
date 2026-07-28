from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from deeptutor.services.custom.db import get_connection, init_db


@pytest.fixture
def custom_db(tmp_path: Path):
    """Create an isolated SQLite database with all tables and seed data."""
    db_path = tmp_path / "deeptutor_custom.db"

    import deeptutor.services.custom.db as db_mod

    original = db_mod.get_custom_db_path

    def _fake_path() -> Path:
        return db_path

    db_mod.get_custom_db_path = _fake_path

    init_db()

    conn = get_connection()
    _seed(conn)
    conn.close()

    yield

    db_mod.get_custom_db_path = original


def _seed(conn: Any) -> None:
    colleges = [
        ("C001", "清华大学", "北京", "北京", "综合", "985+211+双一流", 1, None, 9.0, 9.0, 3.0, 0.98, 25000),
        ("C002", "北京大学", "北京", "北京", "综合", "985+211+双一流", 1, None, 8.5, 9.5, 3.5, 0.97, 24000),
        ("C003", "深圳大学", "广东", "深圳", "综合", "普通", 1, None, 7.0, 8.5, 5.0, 0.90, 18000),
        ("C004", "华南理工大学", "广东", "广州", "理工", "985+211+双一流", 1, None, 7.5, 7.5, 4.0, 0.95, 20000),
        ("C005", "广东工业大学", "广东", "广州", "理工", "普通", 1, None, 6.0, 6.5, 6.0, 0.88, 15000),
    ]
    for c in colleges:
        conn.execute(
            """INSERT INTO colleges (id, name, province, city, type, level, is_public, tags,
               dorm_score, city_vitality, cost_index, employment_rate, avg_salary, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, strftime('%s','now'), strftime('%s','now'))""",
            c,
        )

    majors_data = [
        ("M001", "计算机科学与技术", "工学", "物理+化学"),
        ("M002", "软件工程", "工学", "物理+化学"),
        ("M003", "金融学", "经济学", "不限"),
        ("M004", "临床医学", "医学", "物理+化学+生物"),
    ]
    for m in majors_data:
        conn.execute("INSERT INTO majors (id, name, category, subject_group) VALUES (?,?,?,?)", m)

    college_majors_data = [
        ("C001", "M001", "本科批", 4, "学士", 5000, 50, 55, 60),
        ("C001", "M003", "本科批", 4, "学士", 4800, 100, 110, 120),
        ("C003", "M001", "本科批", 4, "学士", 6000, 5000, 5200, 5500),
        ("C004", "M001", "本科批", 4, "学士", 5500, 3000, 3200, 3400),
        ("C005", "M002", "本科批", 4, "学士", 5200, 15000, 16000, 17000),
    ]
    for cm in college_majors_data:
        conn.execute(
            """INSERT INTO college_majors (college_id, major_id, batch, years, degree, tuition,
               min_rank_2024, min_rank_2023, min_rank_2022) VALUES (?,?,?,?,?,?,?,?,?)""",
            cm,
        )

    import time
    now = time.time()
    study_records_data = [
        ("R001", "user1", "exam", "数学", "期中考试", 85, 100, '["函数","导数"]', '["代数"]', now - 86400 * 2, "2026-07-20"),
        ("R002", "user1", "exam", "数学", "期末考试", 78, 100, '["导数","积分"]', '["函数"]', now - 86400 * 5, "2026-07-17"),
        ("R003", "user1", "exam", "英语", "月考", 92, 100, '[]', '["阅读","写作"]', now - 86400 * 10, "2026-07-12"),
        ("R004", "user2", "homework", "数学", "作业1", 40, 50, '["三角函数"]', '["代数"]', now - 86400 * 3, "2026-07-19"),
    ]
    for r in study_records_data:
        conn.execute(
            """INSERT INTO study_records (id, user_id, record_type, subject, title, score, total,
               weak_points, strong_points, created_at, exam_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            r,
        )

    advisor_data = [
        ("清华大学", "计算机系", "张三", 4.5, "讲课非常好"),
        ("清华大学", "计算机系", "李四", 3.0, "一般般"),
        ("北京大学", "数学系", "王五", 5.0, "超级好老师"),
        ("深圳大学", "计算机系", "赵六", 2.5, "不太行"),
    ]
    for a in advisor_data:
        conn.execute(
            "INSERT INTO advisor_evaluations (school, college, name, score, review_text, created_at) VALUES (?,?,?,?,?, strftime('%s','now'))",
            a,
        )

    admission_ranks_data = [
        ("C001", "M001", "广东", 2025, "本科批", 50, 680, 5, "物理"),
        ("C001", "M001", "广东", 2024, "本科批", 100, 660, 5, "物理"),
        ("C004", "M001", "广东", 2025, "本科批", 3000, 620, 50, "物理"),
        ("C004", "M001", "广东", 2024, "本科批", 4000, 600, 50, "物理"),
    ]
    for ar in admission_ranks_data:
        conn.execute(
            """INSERT OR REPLACE INTO admission_ranks
               (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ar,
        )

    conn.commit()

    # Score rank segments for percentile conversion
    # Use a moderate total to make percentile differences meaningful
    for cat in ("物理", "历史"):
        for yr in (2024, 2025, 2026):
            for prov in ("广东", "北京"):
                conn.execute(
                    """INSERT OR REPLACE INTO score_rank_segments
                       (province, year, exam_category, score, cumulative_rank, batch_category)
                       VALUES (?, ?, ?, ?, ?, '本科')""",
                    (prov, yr, cat, 750, 1),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO score_rank_segments
                       (province, year, exam_category, score, cumulative_rank, batch_category)
                       VALUES (?, ?, ?, ?, ?, '本科')""",
                    (prov, yr, cat, 200, 5000),
                )
    conn.commit()
