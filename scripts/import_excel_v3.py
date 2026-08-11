"""
广东2026高考志愿大数据专家版 全量导入器 (v3)

从 37k 行 Excel 导入六大表：
  admission_ranks — 含 group_code + 3 年录取数据
  colleges       — 更新院校画像（保研率/排名/硕博点/章程等 19 字段）
  majors         — 更新专业画像（门类/专业类/软科评级/学科评估等）
  college_majors — 选科要求/学制/学费

用法:
  python scripts/import_excel_v3.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

EXCEL_PATH = Path.home() / "桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"

BATCH_SIZE = 200


def _safe_float(v, default=0.0) -> float:
    if v is None:
        return default
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def _safe_int(v, default=0) -> int:
    if v is None:
        return default
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (ValueError, TypeError):
        return default


def main():
    import openpyxl

    if not EXCEL_PATH.exists():
        print(f"[ERROR] 文件不存在: {EXCEL_PATH}")
        return

    from deeptutor.services.custom.db import get_connection

    wb = openpyxl.load_workbook(str(EXCEL_PATH), data_only=True)
    ws = wb[wb.sheetnames[0]]
    total = ws.max_row - 3  # skip rows 1-3
    print(f"总行数（不含表头）: {total}")

    conn = get_connection()
    now = time.time()

    colleges_cache: dict[str, bool] = {}
    majors_cache: dict[str, bool] = {}
    college_majors_cache: set[tuple[str, str]] = set()
    rank_exists: set[tuple[str, str, str, int, str, str]] = set()

    batch_ranks: list[tuple] = []
    processed = 0
    college_updates = 0
    rank_inserts = 0
    major_updates = 0
    cm_updates = 0

    for row in ws.iter_rows(min_row=4, values_only=True):
        (
            year, province, exam_category, batch, college_id, college_name,
            combined_group_code, group_code, group_name,
            major_id, major_full_name, major_name, major_remark, language_req,
            level, subject_req, plan_count, years, tuition, group_majors_text,
            group_plan, group_major_count, category, major_category, is_new,
            # 2025 group
            g25_enrollment, g25_min_score, g25_min_rank,
            # 2025 major
            m25_enrollment, m25_min_score, m25_min_rank, m25_batch_old,
            # 2024
            m24_enrollment, m24_min_score, m24_min_rank, m24_batch_old,
            # 2023
            m23_enrollment, m23_min_score, m23_min_rank, m23_max_score, m23_max_rank, m23_batch_old,
            # college profile
            col_province, col_city, col_city_tag, col_tags, col_level,
            col_rename, col_affiliation, col_type, col_public, col_edu_level,
            col_graduate_rate, col_ranking, col_transfer_policy,
            col_masters_count, col_masters_list,
            col_phd_count, col_phd_list,
            col_admission_rule, col_charter_url,
            # major profile
            major_ruanke_grade, major_ruanke_rank, major_discipline_eval,
            major_level, major_masters, major_phds,
        ) = row[:67]  # type: ignore

        processed += 1

        if not college_id or not major_id:
            continue

        college_id = str(college_id).strip()
        major_id = str(major_id).strip()
        group_code = str(group_code).strip() if group_code else ""
        province = str(province or "").strip()
        exam_category = str(exam_category or "").strip()

        # --- 1. Colleges (upsert) ---
        if college_id not in colleges_cache:
            colleges_cache[college_id] = True
            col_name = str(college_name or "").strip()
            col_prov = str(col_province or "").strip()
            col_city_str = str(col_city or "").strip()
            col_type_str = str(col_type or "").strip()

            level_map = ""
            # 院校层次来源是 col_tags（如 "985/211/双一流/国重点/保研资格"），
            # 而非 col_level（该列是"卓越工程师/部委直属"等特殊标签）。
            cl = str(col_tags or "")
            tags: list[str] = []
            if "985" in cl:
                tags.append("985")
            if "211" in cl:
                tags.append("211")
            if "双一流" in cl:
                tags.append("双一流")
            level_map = "+".join(tags) if tags else ("普通" if cl else "")

            is_pub = 0 if "民办" in str(col_public or "") else 1

            tags_list = []
            ct = str(col_tags or "")
            if ct:
                tags_list = [t.strip() for t in ct.replace("，", ",").split(",") if t.strip()]
            tags_json = json.dumps(tags_list, ensure_ascii=False)

            grad_rate = _safe_float(col_graduate_rate)
            ranking = _safe_int(col_ranking)
            masters_cnt = _safe_int(col_masters_count)

            # Check if college exists
            existing = conn.execute("SELECT 1 FROM colleges WHERE id=?", (college_id,)).fetchone()
            if existing:
                conn.execute(
                    """UPDATE colleges SET name=?, province=?, city=?, type=?, level=?,
                       is_public=?, tags=?, graduate_rate=?, ruanke_ranking=?,
                       masters_count=?, transfer_policy=?, admission_charter_url=?,
                       updated_at=? WHERE id=?""",
                    (col_name, col_prov, col_city_str, col_type_str, level_map,
                     is_pub, tags_json, grad_rate, ranking, masters_cnt,
                     str(col_transfer_policy or ""), str(col_charter_url or ""),
                     now, college_id),
                )
                college_updates += 1
            else:
                conn.execute(
                    """INSERT INTO colleges (id, name, province, city, type, level,
                       is_public, tags, graduate_rate, ruanke_ranking,
                       masters_count, transfer_policy, admission_charter_url,
                       created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (college_id, col_name, col_prov, col_city_str, col_type_str,
                     level_map, is_pub, tags_json, grad_rate, ranking, masters_cnt,
                     str(col_transfer_policy or ""), str(col_charter_url or ""),
                     now, now),
                )
                college_updates += 1

        # --- 2. Majors (upsert) ---
        if major_id not in majors_cache:
            majors_cache[major_id] = True
            major_name_str = str(major_name or "").strip()
            cat = str(category or "").strip()
            major_cat = str(major_category or "").strip()
            ruanke_g = str(major_ruanke_grade or "").strip()
            ruanke_r = _safe_int(major_ruanke_rank)
            disc_eval = str(major_discipline_eval or "").strip()
            major_lvl = str(major_level or "").strip()
            desc = json.dumps({"ruanke_grade": ruanke_g, "level": major_lvl}, ensure_ascii=False)

            conn.execute(
                """INSERT OR REPLACE INTO majors
                   (id, name, category, subject_group, ruanke_ranking, discipline_evaluation, description)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (major_id, major_name_str, cat, major_cat,
                 ruanke_r, disc_eval, desc),
            )
            major_updates += 1

        # --- 3. College-Majors (选科/学制/学费) ---
        cm_key = (college_id, major_id)
        if cm_key not in college_majors_cache:
            college_majors_cache.add(cm_key)
            subj = str(subject_req or "")
            yrs = _safe_int(years, 4)
            tuit = _safe_float(tuition)
            lang = str(language_req or "")

            existing = conn.execute(
                "SELECT 1 FROM college_majors WHERE college_id=? AND major_id=?",
                (college_id, major_id),
            ).fetchone()
            meta = json.dumps({"language_req": lang, "major_remark": str(major_remark or "")},
                              ensure_ascii=False)
            if existing:
                conn.execute(
                    "UPDATE college_majors SET batch=?, years=?, tuition=?, subject_requirement=?, metadata=?, updated_at=? WHERE college_id=? AND major_id=?",
                    (str(batch or ""), yrs, tuit, subj, meta, now, college_id, major_id),
                )
            else:
                conn.execute(
                    "INSERT INTO college_majors (college_id, major_id, batch, years, tuition, subject_requirement, metadata, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (college_id, major_id, str(batch or ""), yrs, tuit, subj, meta, now, now),
                )
            cm_updates += 1

        # --- 4. Admission ranks (3 years, major-level) ---
        for yr, enrollment, score, rank_val, batch_old in [
            (2025, m25_enrollment, m25_min_score, m25_min_rank, m25_batch_old),
            (2024, m24_enrollment, m24_min_score, m24_min_rank, m24_batch_old),
            (2023, m23_enrollment, m23_min_score, m23_min_rank, m23_batch_old),
        ]:
            if not rank_val and not score:
                continue
            rk_key = (college_id, major_id, province, yr, exam_category, group_code)
            if rk_key in rank_exists:
                continue
            rank_exists.add(rk_key)

            batch_text = str(batch or "")
            if batch_old and not batch_text:
                batch_text = str(batch_old or "")

            batch_ranks.append((
                college_id, major_id, province, yr,
                batch_text,
                _safe_int(rank_val),
                _safe_float(score),
                _safe_int(enrollment),
                exam_category, group_code,
            ))

        # Also add group-level data (major_id="GEN")
        if g25_min_rank or g25_min_score:
            gk_key = (college_id, "GEN", province, 2025, exam_category, group_code)
            if gk_key not in rank_exists:
                rank_exists.add(gk_key)
                batch_ranks.append((
                    college_id, "GEN", province, 2025,
                    str(batch or ""),
                    _safe_int(g25_min_rank),
                    _safe_float(g25_min_score),
                    _safe_int(g25_enrollment),
                    exam_category, group_code,
                ))

        # Batch insert
        if len(batch_ranks) >= BATCH_SIZE:
            rank_inserts += _insert_ranks(conn, batch_ranks)
            batch_ranks = []

        if processed % 2000 == 0:
            print(f"  已处理 {processed}/{total} 行 (colleges更新={college_updates}, majors更新={major_updates}, cm更新={cm_updates}, ranks插入={rank_inserts})")

    # Remaining
    if batch_ranks:
        rank_inserts += _insert_ranks(conn, batch_ranks)

    conn.commit()
    conn.close()
    print(f"\n✅ 导入完成！")
    print(f"   处理行数: {processed}")
    print(f"   colleges 更新: {college_updates}")
    print(f"   majors 更新/创建: {major_updates}")
    print(f"   college_majors 更新/创建: {cm_updates}")
    print(f"   admission_ranks 插入: {rank_inserts}")


def _insert_ranks(conn, batch: list[tuple]) -> int:
    conn.executemany(
        """INSERT OR IGNORE INTO admission_ranks
           (college_id, major_id, province, year, batch,
            min_rank, min_score, enrollment_count,
            exam_category, group_code)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        batch,
    )
    conn.commit()
    return len(batch)


if __name__ == "__main__":
    main()
