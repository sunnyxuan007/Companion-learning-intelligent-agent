"""普通 CU（合成码）最终清零迁移脚本（Phase 19.5）。

处理 Phase 19 之后剩余的 29 所普通 CU（转设/更名/升格后的院校、干部学院、二级学院）：
- 已核实官方码的 CU -> 迁移到教育部官方码（目标存在并入 / 目标缺失改 id+更名建行）
- 中外合作办学二级学院（无独立法人、依附主办校）-> 删除
- 干部学院（42 段成人高校标识码）-> 迁移官方码

处置规则（用户逐条确认，2026-08-13）：
- MIG（25 所）：目标码在库中存在 -> 并入；目标码缺失 -> 改 id + 更名建行
- DELETE（4 所）：中外合作办学二级学院直接删（含 college_majors 引用清理）
- KEEP（0 所）：29 所全部有最终处置，CU 清零

用法：python scripts/migrate_remaining_cu.py --dry-run   # 仅审计
       python scripts/migrate_remaining_cu.py             # 真跑迁移
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from deeptutor.services.custom.db import get_connection

# 保留（无官方码确认）0 所 —— 29 所全部处置完毕
KEEP_CU: set[str] = set()

# 删除（中外合作办学二级学院，依附主办校、无独立官方码）4 所
DELETE_CU: dict[str, str | None] = {
    "CU02350": None,  # 电子科技大学格拉斯哥学院（中外合作二级学院）
    "CU02341": None,  # 西南财经大学特拉华数据科学学院（中外合作二级学院）
    "CU02440": None,  # 贵州财经大学西密歇根学院（中外合作二级学院）
    "CU02231": None,  # 重庆移通学院中德应用技术学院（二级学院）
}

# 迁移（25 所）：CU id -> (新校名, 官方码)
#   - 目标码在库存在 -> 并入该官方行（引用 remap + 删 CU 行）
#   - 目标码缺失 -> 改 id + 更名建行
MIG_CU: dict[str, tuple[str, str]] = {
    # A. 并入已有官方行（11 所）
    "CU00212": ("河北科技工程职业技术大学", "4113016203"),
    "CU00628": ("哈尔滨建筑科技职业大学", "4123012053"),
    "CU01575": ("郑州健康学院", "4141012948"),
    "CU01933": ("北师香港浸会大学", "4144016401"),
    "CU02289": ("成都轻工职业技术大学", "4151011553"),
    "CU02403": ("贵州轻工职业大学", "4152013818"),
    "CU02475": ("曲靖健康医学院", "4153014012"),
    "CU02487": ("昆明科技职业大学", "4153014212"),
    "CU02670": ("甘肃工业职业技术大学", "4162012836"),
    "CU02747": ("新疆和田学院", "4165010765"),
    "CU02752": ("新疆和田学院", "4165010765"),
    # B. 改 id + 更名建行（目标码缺失，10 所）
    "CU00322": ("山西文化旅游职业大学", "4114013696"),
    "CU00386": ("内蒙古建筑职业技术大学", "4115010871"),
    "CU00390": ("呼和浩特职业技术大学", "4115012670"),
    "CU00398": ("兴安职业技术大学", "4115012443"),
    "CU00587": ("长春医药职业学院", "4122012306"),
    "CU01066": ("合肥理工学院", "4134013612"),
    "CU02530": ("西藏农牧大学", "4154010693"),
    "CU02758": ("新疆工程职业大学", "4165014523"),
    "CU00276": ("河北青年管理干部学院", "4213051802"),
    "CU00586": ("吉林省经济管理干部学院", "4222051243"),
    # C. 并入山西文化旅游职业大学（与 CU00322 同码，4 所）
    "CU00342": ("山西文化旅游职业大学", "4114013696"),
    "CU00344": ("山西文化旅游职业大学", "4114013696"),
    "CU00349": ("山西文化旅游职业大学", "4114013696"),
    "CU00350": ("山西文化旅游职业大学", "4114013696"),
}

_AR_COLS = ("college_id", "major_id", "province", "year", "batch", "min_rank",
            "min_score", "enrollment_count", "exam_category", "group_code")
_CM_COLS = ("college_id", "major_id", "batch", "years", "degree", "tuition",
            "min_rank_2024", "min_rank_2023", "min_rank_2022", "subject_requirement",
            "metadata", "created_at", "updated_at")


def _group_by_code() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for cid, (_name, code) in MIG_CU.items():
        groups.setdefault(code, []).append(cid)
    return groups


def _build_old2new() -> dict[str, str]:
    old2new: dict[str, str] = {}
    for cid, (_name, code) in MIG_CU.items():
        old2new[cid] = code
    for cid, target in DELETE_CU.items():
        if target:
            old2new[cid] = target
    return old2new


def _audit(conn) -> None:
    old2new = _build_old2new()
    print("=== 普通 CU 迁移审计 ===")
    print(f"KEEP（保留）: {len(KEEP_CU)} 所")
    print(f"DELETE（删除）: {len(DELETE_CU)} 所"
          f"（其中并入 {sum(1 for v in DELETE_CU.values() if v)}）")
    print(f"MIG（迁移）: {len(MIG_CU)} 所")

    # 目标码是否存在
    targets = set(old2new.values())
    ph = ",".join("?" * len(targets))
    existing = conn.execute(f"SELECT id, name FROM colleges WHERE id IN ({ph})",
                            list(targets)).fetchall()
    existing_map = {r["id"]: r["name"] for r in existing}
    merge_n = rename_n = 0
    for cid, code in old2new.items():
        if code in existing_map:
            merge_n += 1
        else:
            rename_n += 1
    print(f"\n目标码在库中已存在（并入）: {merge_n}")
    print(f"目标码在库中缺失（改 id+更名）: {rename_n}")

    # 引用面
    old_ids = list(old2new)
    ph = ",".join("?" * len(old_ids))
    refs_cm = conn.execute(f"SELECT COUNT(*) FROM college_majors WHERE college_id IN ({ph})",
                           old_ids).fetchone()[0]
    refs_ar = conn.execute(f"SELECT COUNT(*) FROM admission_ranks WHERE college_id IN ({ph})",
                           old_ids).fetchone()[0]
    print(f"\n旧 id 数: {len(old_ids)} | 引用 college_majors={refs_cm}, admission_ranks={refs_ar}")

    # 迁移后剩余 CU（应为 29 KEEP）
    keep_ph = ",".join("?" * len(KEEP_CU))
    remaining = conn.execute(
        f"SELECT COUNT(*) FROM colleges WHERE id LIKE 'CU0%' AND id NOT IN ({keep_ph})",
        list(KEEP_CU)).fetchone()[0]
    print(f"迁移后仍残留非 KEEP CU 行: {remaining}")


def _remap_table(conn, table: str, cols: list[str], old: str, new: str) -> None:
    if old == new:
        return
    sel = ", ".join(cols)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({sel}) SELECT ?, " + ", ".join(cols[1:]) +
                 f" FROM {table} WHERE college_id=?",
                 (new, old))
    conn.execute(f"DELETE FROM {table} WHERE college_id=?", (old,))


def _run_migration(conn) -> None:
    old2new = _build_old2new()
    print(f"\n>>> 真跑迁移: 迁移 {len(MIG_CU)} + 删除 {len(DELETE_CU)} + 保留 {len(KEEP_CU)}")

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with conn:  # 1) colleges 主体
            # 预创建缺失的多 CU 同名目标行（合并校：浙江药科/安徽应用技术/云南交通/新疆工业）
            for code, cus in _group_by_code().items():
                if len(cus) <= 1:
                    continue
                if conn.execute("SELECT 1 FROM colleges WHERE id=?", (code,)).fetchone():
                    continue
                # 目标行缺失且多个 CU 指向同一新校 -> 用第一个 CU 改 id 建行
                first = sorted(cus)[0]
                name = MIG_CU[first][0]
                conn.execute(
                    "UPDATE colleges SET id=?, official_code=?, name=? WHERE id=?",
                    (code, code, name, first))
            for cid, (name, code) in MIG_CU.items():
                if conn.execute("SELECT 1 FROM colleges WHERE id=?", (code,)).fetchone():
                    if code != cid:  # 目标行已有（含刚建/原存在）-> 并入删 CU 行
                        conn.execute("DELETE FROM colleges WHERE id=?", (cid,))
                    # code==cid 即该 CU 本身就是目标行（第一个），跳过删除
                else:
                    # 目标行缺失 -> 改 id + 更名
                    conn.execute(
                        "UPDATE colleges SET id=?, official_code=?, name=? WHERE id=?",
                        (code, code, name, cid))
            for cid, target in DELETE_CU.items():
                conn.execute("DELETE FROM colleges WHERE id=?", (cid,))

        with conn:  # 2) 引用 remap（admission_ranks / college_majors）
            for old, new in old2new.items():
                _remap_table(conn, "admission_ranks", list(_AR_COLS), old, new)
                _remap_table(conn, "college_majors", list(_CM_COLS), old, new)
            # 纯删除（撤销/停办，无并入目标）CU 的 college_majors 引用一并清理，避免孤儿
            for old, new in DELETE_CU.items():
                if new is None:
                    conn.execute("DELETE FROM college_majors WHERE college_id=?", (old,))

        with conn:  # 3) volunteer_plans.slots JSON + doc_meta_v2.metadata
            plans = conn.execute("SELECT id, slots FROM volunteer_plans").fetchall()
            for pid, slots_json in plans:
                try:
                    slots = json.loads(slots_json or "[]")
                except Exception:
                    continue
                changed = False
                for s in slots:
                    cid = str(s.get("college_id", ""))
                    if cid in old2new and old2new[cid] != cid:
                        s["college_id"] = old2new[cid]
                        changed = True
                if changed:
                    conn.execute("UPDATE volunteer_plans SET slots=? WHERE id=?",
                                 (json.dumps(slots, ensure_ascii=False), pid))
            doc_rows = conn.execute(
                "SELECT id, metadata FROM doc_meta_v2 WHERE metadata LIKE '%college_id%'").fetchall()
            for did, meta_json in doc_rows:
                try:
                    meta = json.loads(meta_json or "{}")
                except Exception:
                    continue
                cid = str(meta.get("college_id", ""))
                if cid in old2new and old2new[cid] != cid:
                    meta["college_id"] = old2new[cid]
                    conn.execute("UPDATE doc_meta_v2 SET metadata=? WHERE id=?",
                                 (json.dumps(meta, ensure_ascii=False), did))

        with conn:  # 4) college_code_map 登记地方码（CU 无地方码，仅记录官方更名来源）
            pass
    finally:
        conn.execute("PRAGMA foreign_keys=ON")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    orphan_ar = conn.execute("SELECT COUNT(*) FROM admission_ranks a LEFT JOIN colleges c "
                             "ON a.college_id=c.id WHERE c.id IS NULL").fetchone()[0]
    orphan_cm = conn.execute("SELECT COUNT(*) FROM college_majors a LEFT JOIN colleges c "
                             "ON a.college_id=c.id WHERE c.id IS NULL").fetchone()[0]
    if violations:
        print(f"[警告] foreign_key_check 发现 {len(violations)} 处违反:")
        for v in violations[:20]:
            print("  ", v)
    if orphan_ar or orphan_cm:
        print(f"[警告] 孤儿引用 admission_ranks={orphan_ar}, college_majors={orphan_cm}")
    remaining = conn.execute("SELECT COUNT(*) FROM colleges WHERE id LIKE 'CU0%'").fetchone()[0]
    print(f"迁移后剩余 CU 总数: {remaining}（应为 {len(KEEP_CU)}）")
    print("Done: 普通 CU 迁移完成。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="仅审计，不写库")
    args = ap.parse_args()

    conn = get_connection()
    _audit(conn)
    if args.dry_run:
        conn.close()
        print("\n（dry-run 未写库）")
        return
    _run_migration(conn)
    conn.close()


if __name__ == "__main__":
    main()
