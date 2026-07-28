from __future__ import annotations

from typing import Any

from deeptutor.services.custom.db import get_connection


def get_admission_ranks(
    college_id: str,
    major_id: str,
    province: str,
    years: list[int] | None = None,
    exam_category: str | None = None,
    group_code: str | None = None,
) -> list[dict[str, Any]]:
    if not years:
        years = [2026, 2025, 2024]
    placeholders = ",".join("?" * len(years))
    conn = get_connection()
    clauses = ["college_id = ?", "major_id = ?", "province = ?"]
    params: list[Any] = [college_id, major_id, province]
    if exam_category:
        clauses.append("exam_category = ?")
        params.append(exam_category)
    if group_code is not None and group_code != "":
        clauses.append("group_code = ?")
        params.append(group_code)
    elif group_code == "":
        clauses.append("group_code = ''")
    # None → no filter (return all groups)
    sql = f"SELECT * FROM admission_ranks WHERE {' AND '.join(clauses)} AND year IN ({placeholders}) ORDER BY year DESC"
    rows = conn.execute(sql, [*params, *years]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_admission_ranks(
    college_id: str | None = None,
    major_id: str | None = None,
    province: str | None = None,
    year: int | None = None,
    exam_category: str | None = None,
    group_code: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    conn = get_connection()
    conditions: list[str] = []
    params: list[Any] = []
    if college_id:
        conditions.append("college_id = ?")
        params.append(college_id)
    if major_id:
        conditions.append("major_id = ?")
        params.append(major_id)
    if province:
        conditions.append("province = ?")
        params.append(province)
    if exam_category:
        conditions.append("exam_category = ?")
        params.append(exam_category)
    if group_code is not None:
        conditions.append("group_code = ?")
        params.append(group_code)
    else:
        conditions.append("group_code = ''")
    if year:
        conditions.append("year = ?")
        params.append(year)
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(
        f"SELECT * FROM admission_ranks WHERE {where} ORDER BY year DESC, min_rank ASC LIMIT ?",
        [*params, limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_admission_ranks_by_college(
    college_id: str,
    province: str,
    years: list[int] | None = None,
    exam_category: str | None = None,
    group_code: str | None = None,
) -> list[dict[str, Any]]:
    if not years:
        years = [2026, 2025, 2024]
    placeholders = ",".join("?" * len(years))
    conn = get_connection()
    clauses = ["college_id = ?", "province = ?"]
    params: list[Any] = [college_id, province]
    if exam_category:
        clauses.append("exam_category = ?")
        params.append(exam_category)
    if group_code is not None and group_code != "":
        clauses.append("group_code = ?")
        params.append(group_code)
    elif group_code == "":
        clauses.append("group_code = ''")
    # None → no filter (return all groups)
    sql = f"SELECT * FROM admission_ranks WHERE {' AND '.join(clauses)} AND year IN ({placeholders}) ORDER BY year DESC"
    rows = conn.execute(sql, [*params, *years]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def import_admission_rank(
    college_id: str,
    major_id: str,
    province: str,
    year: int,
    min_rank: int = 0,
    min_score: float = 0,
    batch: str | None = None,
    enrollment_count: int = 0,
    exam_category: str = "",
    group_code: str = "",
) -> None:
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO admission_ranks
           (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code),
    )
    conn.commit()
    conn.close()


def bulk_import_ranks(records: list[dict[str, Any]]) -> int:
    conn = get_connection()
    count = 0
    for r in records:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    r["college_id"],
                    r["major_id"],
                    r["province"],
                    int(r["year"]),
                    r.get("batch"),
                    int(r.get("min_rank", 0)),
                    float(r.get("min_score", 0)),
                    int(r.get("enrollment_count", 0)),
                    r.get("exam_category", ""),
                    r.get("group_code", ""),
                ),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count


def get_college_group_ranks(
    college_id: str,
    province: str,
    years: list[int] | None = None,
    exam_category: str | None = None,
) -> list[dict[str, Any]]:
    """Return all distinct groups (with non-empty group_code) for a college."""
    if not years:
        years = [2026, 2025, 2024]
    placeholders = ",".join("?" * len(years))
    conn = get_connection()
    clauses = ["college_id = ?", "province = ?", "group_code != ''"]
    params: list[Any] = [college_id, province]
    if exam_category:
        clauses.append("exam_category = ?")
        params.append(exam_category)
    sql = f"SELECT * FROM admission_ranks WHERE {' AND '.join(clauses)} AND year IN ({placeholders}) ORDER BY group_code, year DESC"
    rows = conn.execute(sql, [*params, *years]).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_college_groups(
    college_id: str,
    province: str,
    exam_category: str | None = None,
) -> list[dict[str, str]]:
    conn = get_connection()
    clauses = ["college_id = ?", "province = ?", "group_code != ''"]
    params: list[Any] = [college_id, province]
    if exam_category:
        clauses.append("exam_category = ?")
        params.append(exam_category)
    rows = conn.execute(
        f"SELECT DISTINCT group_code, batch, min_rank, year FROM admission_ranks WHERE {' AND '.join(clauses)} ORDER BY group_code, year DESC",
        params,
    ).fetchall()
    conn.close()
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for r in rows:
        gc = r["group_code"]
        if gc not in seen:
            seen.add(gc)
            result.append({"group_code": gc, "batch": r["batch"] or ""})
    return result


def get_group_majors(
    college_id: str,
    group_code: str,
    province: str,
    exam_category: str | None = None,
) -> list[dict[str, Any]]:
    conn = get_connection()
    clauses = ["college_id = ?", "group_code = ?", "province = ?", "major_id != 'GEN'"]
    params: list[Any] = [college_id, group_code, province]
    if exam_category:
        clauses.append("exam_category = ?")
        params.append(exam_category)
    sql = f"SELECT major_id, year, batch, min_rank, min_score, enrollment_count, exam_category FROM admission_ranks WHERE {' AND '.join(clauses)} ORDER BY year DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    majors: dict[str, dict[str, Any]] = {}
    for r in rows:
        mid = r["major_id"]
        if mid not in majors:
            majors[mid] = {"major_id": mid}
        yr = r["year"]
        rk = r["min_rank"] or 999999
        if yr >= majors[mid].get("best_year", 0) and (rk < majors[mid].get("min_rank", 999999) or majors[mid].get("min_rank", 999999) == 999999):
            majors[mid]["min_rank"] = rk
            majors[mid]["min_score"] = r["min_score"]
            majors[mid]["best_year"] = yr
    return list(majors.values())


def get_group_ranks_agg(
    college_id: str,
    group_code: str,
    province: str,
    exam_category: str | None = None,
) -> dict[int, int]:
    conn = get_connection()
    clauses = ["college_id = ?", "group_code = ?", "province = ?", "major_id != 'GEN'"]
    params: list[Any] = [college_id, group_code, province]
    if exam_category:
        clauses.append("exam_category = ?")
        params.append(exam_category)
    rows = conn.execute(
        f"SELECT year, MIN(min_rank) as best_rank FROM admission_ranks WHERE {' AND '.join(clauses)} AND min_rank > 0 GROUP BY year ORDER BY year DESC",
        params,
    ).fetchall()

    gen_params: list[Any] = [college_id, group_code, province]
    gen_sql = "SELECT year, min_rank FROM admission_ranks WHERE college_id=? AND group_code=? AND province=? AND major_id='GEN' AND min_rank > 0"
    if exam_category:
        gen_sql += " AND exam_category=?"
        gen_params.append(exam_category)
    gen_sql += " ORDER BY year DESC"
    gen_rows = conn.execute(gen_sql, gen_params).fetchall()
    conn.close()

    result: dict[int, int] = {}
    for r in rows:
        result[r["year"]] = r["best_rank"]
    for r in gen_rows:
        yr = r["year"]
        if yr not in result or r["min_rank"] < result[yr]:
            result[yr] = r["min_rank"]
    return result


# --- 一分一段 (score_rank_segments) ---


def get_score_rank_segments(
    province: str,
    year: int,
    exam_category: str,
    batch_category: str = "本科",
) -> list[dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM score_rank_segments
           WHERE province = ? AND year = ? AND exam_category = ? AND batch_category = ?
           ORDER BY score DESC""",
        (province, year, exam_category, batch_category),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def rank_to_score(
    province: str,
    year: int,
    exam_category: str,
    rank: int,
    batch_category: str = "本科",
) -> float:
    rows = get_score_rank_segments(province, year, exam_category, batch_category)
    if not rows:
        return 0.0
    for r in rows:
        if r["cumulative_rank"] >= rank:
            return float(r["score"])
    return float(rows[-1]["score"])


def score_to_rank(
    province: str,
    year: int,
    exam_category: str,
    score: float,
    batch_category: str = "本科",
) -> int:
    rows = get_score_rank_segments(province, year, exam_category, batch_category)
    if not rows:
        return 0
    # If score is above the highest recorded score, return rank 1
    if score > int(rows[0]["score"]):
        return 1
    for r in rows:
        if int(r["score"]) <= score:
            return int(r["cumulative_rank"])
    return int(rows[-1]["cumulative_rank"])


def get_total_candidates(
    province: str,
    year: int,
    exam_category: str,
    batch_category: str = "本科",
) -> int:
    rows = get_score_rank_segments(province, year, exam_category, batch_category)
    # Last row has the lowest score and highest cumulative_rank = total candidates
    if rows:
        return rows[-1]["cumulative_rank"]
    return 0


def bulk_import_score_rank(records: list[dict[str, Any]]) -> int:
    """Import 一分一段 data. Records must have: province, year, exam_category,
    score, cumulative_rank, batch_category."""
    conn = get_connection()
    count = 0
    for r in records:
        try:
            conn.execute(
                """INSERT OR REPLACE INTO score_rank_segments
                   (province, year, exam_category, score, cumulative_rank, batch_category)
                   VALUES (?,?,?,?,?,?)""",
                (
                    r["province"],
                    int(r["year"]),
                    r["exam_category"],
                    int(r["score"]),
                    int(r["cumulative_rank"]),
                    r.get("batch_category", "本科"),
                ),
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count
