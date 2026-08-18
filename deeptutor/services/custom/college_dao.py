from __future__ import annotations

import json
from typing import Any

from deeptutor.services.custom.db import get_connection
from deeptutor.services.custom.models import College, CollegeMajor, Major


def search_colleges(
    province: str | None = None,
    level: str | None = None,
    college_type: str | None = None,
    min_score: float | None = None,
    keyword: str | None = None,
    college_ids: list[str] | None = None,
    city_tier: str | None = None,
    regions: list[str] | None = None,
    cities: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    conn = get_connection()
    conditions: list[str] = []
    params: list[Any] = []
    if province:
        conditions.append("c.province = ?")
        params.append(province)
    if city_tier:
        conditions.append("c.city_tier = ?")
        params.append(city_tier)
    if regions:
        placeholders = ",".join("?" * len(regions))
        conditions.append(f"c.region IN ({placeholders})")
        params.extend(regions)
    if cities:
        # 直辖市（北京/上海/天津/重庆）按省份匹配；其余按城市前缀匹配
        muni = {"北京", "上海", "天津", "重庆"}
        muni_likes = [c for c in cities if c in muni]
        city_likes = [c.rstrip("市") for c in cities if c not in muni]
        muni_clauses: list[str] = []
        if muni_likes:
            placeholders = ",".join("?" * len(muni_likes))
            muni_clauses.append(f"c.province IN ({placeholders})")
            params.extend(muni_likes)
        if city_likes:
            muni_clauses.append("(" + " OR ".join(["c.city LIKE ?" for _ in city_likes]) + ")")
            params.extend([f"{c}%" for c in city_likes])
        if muni_clauses:
            conditions.append("(" + " OR ".join(muni_clauses) + ")")
    if level:
        conditions.append("c.level = ?")
        params.append(level)
    if college_type:
        conditions.append("c.type = ?")
        params.append(college_type)
    if keyword:
        conditions.append("c.name LIKE ?")
        params.append(f"%{keyword}%")
    if college_ids:
        placeholders = ",".join("?" * len(college_ids))
        conditions.append(f"c.id IN ({placeholders})")
        params.extend(college_ids)
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM colleges c WHERE {where} ORDER BY c.name LIMIT ?",
        [*params, limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_college_detail(college_id: str) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM colleges WHERE id = ?", (college_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    college = dict(row)
    majors = conn.execute(
        """SELECT m.*, cm.batch, cm.years, cm.tuition,
                  cm.min_rank_2024, cm.min_rank_2023, cm.min_rank_2022
           FROM college_majors cm
           JOIN majors m ON m.id = cm.major_id
           WHERE cm.college_id = ?
           ORDER BY m.category, m.name""",
        (college_id,),
    ).fetchall()
    conn.close()
    college["majors"] = [dict(r) for r in majors]
    return college


def get_admission_data(
    college_id: str, major_id: str
) -> dict[str, Any] | None:
    conn = get_connection()
    row = conn.execute(
        """SELECT cm.*, c.name AS college_name, m.name AS major_name
           FROM college_majors cm
           JOIN colleges c ON c.id = cm.college_id
           JOIN majors m ON m.id = cm.major_id
           WHERE cm.college_id = ? AND cm.major_id = ?""",
        (college_id, major_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_college_ids() -> list[str]:
    conn = get_connection()
    rows = conn.execute("SELECT id FROM colleges").fetchall()
    conn.close()
    return [r["id"] for r in rows]


def import_college(college: College) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO colleges
           (id, name, province, city, type, level, is_public, tags,
            dorm_score, city_vitality, cost_index, employment_rate,
            avg_salary, scholarship_score, campus_area, library_volume,
            graduate_rate, masters_count, double_first_class_disciplines,
            ruanke_ranking, xiaoyouhui_ranking, admission_charter_url,
            transfer_policy, scholarship_info,
            created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            college.id,
            college.name,
            college.province,
            college.city,
            college.type,
            college.level,
            1 if college.is_public else 0,
            "[]",
            college.dorm_score,
            college.city_vitality,
            college.cost_index,
            college.employment_rate,
            college.avg_salary,
            college.scholarship_score,
            college.campus_area,
            college.library_volume,
            college.graduate_rate,
            college.masters_count,
            json.dumps(college.double_first_class_disciplines, ensure_ascii=False),
            college.ruanke_ranking,
            college.xiaoyouhui_ranking,
            college.admission_charter_url,
            college.transfer_policy,
            college.scholarship_info,
            __import__("time").time(),
            __import__("time").time(),
        ),
    )
    conn.commit()
    conn.close()


def import_college_major(cm: CollegeMajor) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO college_majors
           (college_id, major_id, batch, years, degree, tuition,
            min_rank_2024, min_rank_2023, min_rank_2022)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            cm.college_id,
            cm.major_id,
            cm.batch,
            cm.years,
            "学士",
            cm.tuition,
            cm.min_ranks.get("2024", 0),
            cm.min_ranks.get("2023", 0),
            cm.min_ranks.get("2022", 0),
        ),
    )
    conn.commit()
    conn.close()


def import_major(major: Major) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO majors
           (id, name, category, subject_group, description, career_paths)
           VALUES (?,?,?,?,?,?)""",
        (
            major.id,
            major.name,
            major.category,
            major.subject_group,
            major.description,
            json.dumps(major.career_paths, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
