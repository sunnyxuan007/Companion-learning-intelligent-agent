"""军警校国标码迁移脚本（Phase 18）。

把 `colleges.id` / `admission_ranks.college_id` / `college_majors.college_id`
中的军警校行从「广东/招生系统码（9xxxx）+ 合成码（CUxxxx）」统一迁移为
「教育部国标码（91xxx）」。

处置规则（用户拍板）：
- `9xxxx`（92002 国防科大 等）= 广东/招生系统码 -> 改 id 为国标码（91002 等）
- CU 同名军校 -> 并入对应国标行后删除
- 军改合并校 -> 并入新校，删除原名称（陆军兵种大学=91006、联勤保障=92036 保留）
- 独立 CU 军校 -> 直接改 id 为国标码
- 警校 CU -> 已升格并入库的并入库中新行；未入库的改 id 为新标识码
- 92036 联勤保障部队工程大学 = 官方自述即国标，主键不动

用法：python scripts/migrate_military_codes.py --dry-run   # 仅审计
       python scripts/migrate_military_codes.py             # 真跑迁移
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from deeptutor.services.custom.db import get_connection

# 9xxxx -> 国标（改 id 重命名）
NINE_TO_NATIONAL: dict[str, str] = {
    "92002": "91002",  # 国防科技大学
    "92004": "91004",  # 陆军工程大学
    "92005": "91006",  # 陆军兵种大学（继承装甲兵国标）
    "92006": "91005",  # 陆军步兵学院
    "92010": "91011",  # 陆军防化学院
    "92011": "91012",  # 陆军军医大学
    "92013": "91016",  # 海军工程大学
    "92014": "91017",  # 海军大连舰艇学院
    "92022": "91024",  # 空军工程大学
    "92023": "91026",  # 空军预警学院
    "92027": "91030",  # 空军军医大学
    "92031": "91034",  # 火箭军工程大学
    "92033": "91036",  # 军事航天·航天工程大学
    "92034": "91037",  # 网络空间·信息工程大学
    "92038": "91039",  # 武警工程大学
    "92039": "91040",  # 武警警官学院
    "90046": "91025",  # 空军航空大学
    "90050": "91019",  # 海军航空大学
}

# CU 同名 -> 并入对应国标（迁移后删旧）
CU_SAME_NATIONAL: dict[str, str] = {
    "CU00793": "91004",  # 陆军工程大学
    "CU01301": "91005",  # 陆军步兵学院
    "CU00081": "91011",  # 陆军防化学院
    "CU01691": "91016",  # 海军工程大学
    "CU00480": "91017",  # 海军大连舰艇学院
    "CU01424": "91019",  # 海军航空大学
    "CU00578": "91025",  # 空军航空大学
    "CU02591": "91024",  # 空军工程大学
    "CU01700": "91026",  # 空军预警学院
    "CU02272": "91040",  # 武警警官学院
    "CU00073": "91036",  # 战略支援部队航天工程大学
    "CU01527": "91037",  # 战略支援部队信息工程大学
}

# CU 军改合并校 -> 并入新校（删除原名称）
CU_MERGED_TARGET: dict[str, str] = {
    "CU00060": "91006",  # 陆军装甲兵学院 -> 陆军兵种大学
    "CU01104": "91006",  # 陆军炮兵防空兵学院 -> 陆军兵种大学
    "CU00132": "92036",  # 陆军军事交通学院 -> 联勤保障部队工程大学
    "CU02201": "92036",  # 陆军勤务学院 -> 联勤保障部队工程大学
}

# CU 独立军校 -> 直接改国标
CU_DIRECT_NATIONAL: dict[str, str] = {
    "CU00095": "91001",  # 国防大学
    "CU00097": "91041",  # 武警特种警察学院
    "CU00156": "91038",  # 武警指挥学院
    "CU00157": "91021",  # 海军勤务学院
    "CU00281": "91028",  # 空军石家庄飞行学院
    "CU00529": "91032",  # 空军通信士官学校
    "CU00704": "91020",  # 海军军医大学
    "CU00907": "91015",  # 海军指挥学院
    "CU00945": "91044",  # 武警海警学院
    "CU01138": "91022",  # 海军士官学校
    "CU01472": "91018",  # 海军潜艇学院
    "CU01485": "91035",  # 火箭军士官学校
    "CU02054": "91009",  # 陆军特种作战学院
    "CU02625": "91010",  # 陆军边海防学院
}

# 警校 CU -> 并入库中已有的升格新校（已存在，只迁移引用并删 CU 行）
POLICE_MERGE: dict[str, str] = {
    "CU00135": "4112012723",  # 天津公安警官职业学院 -> 天津警察学院
    "CU00778": "4132012213",  # 南京森林警察学院 -> 南京警察学院
    "CU01541": "4141012735",  # 铁道警察学院 -> 郑州警察学院
    "CU02654": "4162012834",  # 甘肃警察职业学院 -> 甘肃警察学院
}

# 警校 CU -> 直接改新标识码（未入库）+ 更名
POLICE_DIRECT: dict[str, tuple[str, str]] = {
    "CU00395": ("4115012797", "内蒙古警察学院"),
    "CU02581": ("4161013819", "陕西警察学院"),
}

# 迁移目标行更名（国标行改名以匹配权威/官方名称）
RENAME_ALIAS: dict[str, str] = {
    "91036": "军事航天部队航天工程大学",
    "91037": "网络空间部队信息工程大学",
}

_AR_COLS = ("college_id", "major_id", "province", "year", "batch", "min_rank",
            "min_score", "enrollment_count", "exam_category", "group_code")
_CM_COLS = ("college_id", "major_id", "batch", "years", "degree", "tuition",
            "min_rank_2024", "min_rank_2023", "min_rank_2022", "subject_requirement",
            "metadata", "created_at", "updated_at")


def _build_old2new() -> dict[str, str]:
    old2new: dict[str, str] = {}
    old2new.update(NINE_TO_NATIONAL)
    old2new.update(CU_SAME_NATIONAL)
    old2new.update(CU_MERGED_TARGET)
    old2new.update(CU_DIRECT_NATIONAL)
    old2new.update(POLICE_MERGE)
    for old, (new, _name) in POLICE_DIRECT.items():
        old2new[old] = new
    return old2new


def _audit(conn) -> None:
    old2new = _build_old2new()
    print("=== 军警校迁移审计 ===")
    print(f"迁移映射总数: {len(old2new)}")
    print(f"  A. 9xxxx -> 国标（改 id）: {len(NINE_TO_NATIONAL)}")
    print(f"  B. CU 同名并入国标: {len(CU_SAME_NATIONAL)}")
    print(f"  C. CU 军改合并校并入新校: {len(CU_MERGED_TARGET)}")
    print(f"  D. CU 独立军校 -> 国标: {len(CU_DIRECT_NATIONAL)}")
    print(f"  E. 警校并入升格新校: {len(POLICE_MERGE)}")
    print(f"  E. 警校直接改标识码: {len(POLICE_DIRECT)}")

    # 校验映射目标的国标行当前不存在（避免误改既有行）
    targets = set(old2new.values())
    ph = ",".join("?" * len(targets))
    existing = conn.execute(f"SELECT id, name FROM colleges WHERE id IN ({ph})",
                            list(targets)).fetchall()
    existing_map = {r["id"]: r["name"] for r in existing}
    ok_national = set()
    for r in existing:
        ok_national.add(r["id"])  # 警校已入库的新校行例外：允许存在
    print(f"\n目标国标码在库中已存在（将被写入/合并）: {len(existing_map)}")
    for t in sorted(targets):
        if t in existing_map:
            print(f"  {t} 已存在: {existing_map[t]}")

    # 引用面统计
    old_ids = list(old2new)
    ph = ",".join("?" * len(old_ids))
    refs_cm = conn.execute(f"SELECT COUNT(*) FROM college_majors WHERE college_id IN ({ph})",
                           old_ids).fetchone()[0]
    refs_ar = conn.execute(f"SELECT COUNT(*) FROM admission_ranks WHERE college_id IN ({ph})",
                           old_ids).fetchone()[0]
    print(f"\n旧 id 数: {len(old_ids)} | 引用 college_majors={refs_cm}, admission_ranks={refs_ar}")

    # 迁移后剩余军警 CU（应为 0）：本次涉及的全部军警校行
    mil_total = set(NINE_TO_NATIONAL) | set(CU_SAME_NATIONAL) | set(CU_MERGED_TARGET) \
        | set(CU_DIRECT_NATIONAL) | set(POLICE_MERGE) | set(POLICE_DIRECT)
    ph = ",".join("?" * len(mil_total))
    remaining = conn.execute(f"SELECT COUNT(*) FROM colleges WHERE id IN ({ph})",
                             list(mil_total)).fetchone()[0]
    print(f"本次涉及的军警校 colleges 行数: {remaining}")
    # 迁移后真正残留的军警 CU = 名称含解放军/武警 且 id 不在本次迁移集合
    migrated_set = set(mil_total)
    ph2 = ",".join("?" * len(migrated_set)) if migrated_set else "''"
    still = conn.execute(
        f"SELECT COUNT(*) FROM colleges WHERE id LIKE 'CU0%' AND "
        f"(name LIKE '%解放军%' OR name LIKE '%武警%') AND id NOT IN ({ph2})",
        list(migrated_set)).fetchone()[0]
    print(f"迁移后仍残留军警 CU 行: {still}")


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
    print(f"\n>>> 真跑迁移: 共 {len(old2new)} 个旧 id 变更")

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with conn:  # 1) 改 id（colleges 主体）
            # 先处理合并目标（新校主键已存在，直接删 CU 行；引用在下一步 remap）
            for cid, new in CU_MERGED_TARGET.items():
                conn.execute("DELETE FROM colleges WHERE id=?", (cid,))
            # 独立 CU/警校 -> 改 id + 可选更名
            for cid, new in CU_DIRECT_NATIONAL.items():
                conn.execute("UPDATE colleges SET id=?, official_code=? WHERE id=?",
                             (new, new, cid))
            for cid, (new, name) in POLICE_DIRECT.items():
                conn.execute("UPDATE colleges SET id=?, official_code=?, name=? WHERE id=?",
                             (new, new, name, cid))
            # 警校并入新校：删 CU 行
            for cid in POLICE_MERGE:
                conn.execute("DELETE FROM colleges WHERE id=?", (cid,))
            # CU 同名军校：删 CU 行（引用并入对应国标行）
            for cid in CU_SAME_NATIONAL:
                conn.execute("DELETE FROM colleges WHERE id=?", (cid,))
            # 9xxxx -> 国标（改 id，合并目标 91006/92036 不动）
            for cid, new in NINE_TO_NATIONAL.items():
                conn.execute("UPDATE colleges SET id=?, official_code=? WHERE id=?",
                             (new, new, cid))
            # 目标行更名（91036/91037 权威名）
            for new, name in RENAME_ALIAS.items():
                conn.execute("UPDATE colleges SET name=? WHERE id=?", (name, new))

        with conn:  # 2) 引用 remap（admission_ranks / college_majors）
            for old, new in old2new.items():
                _remap_table(conn, "admission_ranks", list(_AR_COLS), old, new)
                _remap_table(conn, "college_majors", list(_CM_COLS), old, new)

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

        with conn:  # 4) college_code_map 登记地方码
            for cid, new in NINE_TO_NATIONAL.items():
                name = conn.execute("SELECT name FROM colleges WHERE id=?", (new,)).fetchone()
                conn.execute(
                    "INSERT OR REPLACE INTO college_code_map (official_code, province_code, province, school_name, source) VALUES (?,?,?,?,?)",
                    (new, cid, "广东", name["name"] if name else "", "gd_gaokao2026"))
            for cid, (new, name) in POLICE_DIRECT.items():
                conn.execute(
                    "INSERT OR REPLACE INTO college_code_map (official_code, province_code, province, school_name, source) VALUES (?,?,?,?,?)",
                    (new, "", "内蒙古" if cid == "CU00395" else "陕西", CID_NAME.get(cid, ""), "official_rename"))
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

    print("Done: 军警校国标码迁移完成。")


CID_NAME = {
    "CU00395": "内蒙古警察职业学院",
    "CU02581": "陕西警官职业学院",
}


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