"""补迁：括号全/半角漏网的同名 numeric 行（2026-08-12 修正 `_lookup_official` 后）。
处理两类：
  A) 目标官方码不存在 -> UPDATE colleges 改名（id=官方码）+ 引用 remap
  B) 目标官方码已存在（同校重复行）-> 引用 INSERT OR REPLACE 并入官方码行 + DELETE 半角行
用法：python scripts/backfill_missing_official_codes.py [--dry-run]
"""
import argparse
import json
import sqlite3

import migrate_college_codes as m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    name2code = m._load_official_codes()
    code2name = {c: n for n, c in name2code.items()}
    conn = m.get_connection()
    actions = m.plan_actions(conn, name2code, code2name)
    # numeric_off：id != official；numeric_variant：new_id 指向已有官方码行（同名重复）
    todo_off = [x for x in actions["numeric_off"]
                if x["official"] and x["id"] != x["official"]]
    todo_variant = [x for x in actions["numeric_variant"]
                    if x["new_id"] and x["new_id"] != x["id"]]
    todo = [{**x, "target": x.get("new_id") or x.get("official")}
            for x in todo_off + todo_variant]

    exist_ids = {r[0] for r in conn.execute(
        "SELECT id FROM colleges WHERE id IN ({})".format(
            ",".join("?" * len(todo))), [x["target"] for x in todo]).fetchall()}

    # 目标已存在 -> 重复行（引用并入目标后删除）
    dup_rows = [x for x in todo if x["target"] in exist_ids]
    rename_rows = [x for x in todo if x["target"] not in exist_ids]

    print(f"待处理: 改名 {len(rename_rows)}, 同名合并 {len(dup_rows)}")
    for x in rename_rows:
        print(f"  [R] {x['id']} {x['name']} -> {x['target']}")
    for x in dup_rows:
        print(f"  [M] {x['id']} {x['name']} 并入 {x['target']}")

    if args.dry_run:
        conn.close()
        print("（dry-run 未写库）")
        return

    # 手工构造 old2new：所有 todo 的旧码 -> 官方码
    old2new = {x["id"]: x["target"] for x in todo}
    # 引用前推：若目标本身也在 old2new（极少见），链式解析
    changed = True
    while changed:
        changed = False
        for old in list(old2new):
            tgt = old2new[old]
            if tgt in old2new and old2new[tgt] != tgt:
                old2new[old] = old2new[tgt]
                changed = True

    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with conn:
            for x in rename_rows:
                conn.execute("UPDATE colleges SET id=?, official_code=? WHERE id=?",
                             (x["target"], x["target"], x["id"]))
        with conn:
            for old, new in old2new.items():
                if old != new:
                    m._remap_table(conn, "admission_ranks", list(m._AR_COLS), old, new)
                    m._remap_table(conn, "college_majors", list(m._CM_COLS), old, new)
            # volunteer_plans.slots JSON
            for pid, slots_json in conn.execute("SELECT id, slots FROM volunteer_plans").fetchall():
                slots = json.loads(slots_json or "[]")
                ch = False
                for s in slots:
                    cid = str(s.get("college_id", ""))
                    if cid in old2new and old2new[cid] != cid:
                        s["college_id"] = old2new[cid]
                        ch = True
                if ch:
                    conn.execute("UPDATE volunteer_plans SET slots=? WHERE id=?",
                                 (json.dumps(slots, ensure_ascii=False), pid))
            # doc_meta_v2 metadata
            for did, meta_json in conn.execute(
                    "SELECT id, metadata FROM doc_meta_v2 WHERE metadata LIKE '%college_id%'").fetchall():
                meta = json.loads(meta_json or "{}")
                cid = str(meta.get("college_id", ""))
                if cid in old2new and old2new[cid] != cid:
                    meta["college_id"] = old2new[cid]
                    conn.execute("UPDATE doc_meta_v2 SET metadata=? WHERE id=?",
                                 (json.dumps(meta, ensure_ascii=False), did))
        with conn:
            # 同名合并行删除
            for x in dup_rows:
                conn.execute("DELETE FROM colleges WHERE id=?", (x["id"],))
            # college_code_map 填充
            for x in todo:
                conn.execute(
                    "INSERT OR REPLACE INTO college_code_map "
                    "(official_code, province_code, province, school_name, source) VALUES (?,?,?,?,?)",
                    (x["target"], x["id"], "广东", x["name"], "gd_local"))
    finally:
        conn.execute("PRAGMA foreign_keys=ON")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    orphans = conn.execute(
        "SELECT COUNT(*) FROM admission_ranks a LEFT JOIN colleges c ON a.college_id=c.id WHERE c.id IS NULL"
    ).fetchone()[0] + conn.execute(
        "SELECT COUNT(*) FROM college_majors a LEFT JOIN colleges c ON a.college_id=c.id WHERE c.id IS NULL"
    ).fetchone()[0]
    print(f"补迁完成 | FK违反={len(violations)} 孤儿引用={orphans}")
    if violations:
        print(violations[:10])
    conn.close()


if __name__ == "__main__":
    main()