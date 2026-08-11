"""编码归一迁移脚本（B 方案：全面官方码化）。

Phase 17。把 `colleges.id` / `admission_ranks.college_id` / `college_majors.college_id`
从「广东地方码 + CU 合成码」统一迁移为「教育部官方 10 位学校标识码」。

背景：
- 官方码 10 位后 5 位 = 广东地方码（`4144010574` 华师大 -> `10574`）。
- numeric（广东地方码 1819 所）= canonical，CU（合成码 2769 所）= 全国补充库。
- 同名 CU 1581 删除；独有有官方码 CU 925 -> 官方码；
  无官方码变体（校区/医学部/分校）-> 主校码+后缀；
  军校/独立学院/职业院校等无码且无主校 -> 保留 CU（待人工）。

用法：python scripts/migrate_college_codes.py --dry-run   # 仅审计（推荐先跑）
       python scripts/migrate_college_codes.py             # 真跑迁移
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from deeptutor.services.custom.db import get_connection

OFFICIAL_XLS = Path.home() / "桌面/data for agent/全国高等院校名单2026.xls"
FALLBACK_OFFICIAL_XLSX = Path("/tmp/opencode/olp2/全国高等院校名单2026.xlsx")
GD_EXPERT_XLSX = Path.home() / "桌面/data for agent/广东2026高考志愿大数据专家版0626.xlsx"

# 变体区分词 -> 拼音首字母（保证同主校变体后缀唯一可读）
_PLACE_TAG = {
    "北京": "BJ", "保定": "BD", "河北": "HB", "秦皇岛": "QHD",
    "威海": "WH", "深圳": "SZ", "广州": "GZ", "珠海": "ZH",
    "汕尾": "SW", "揭阳": "JY", "河源": "HY", "深汕": "SS",
    "沙河": "SH", "盘锦": "PJ", "宣城": "XC", "荣昌": "RC",
    "苏州": "SZ2", "克拉玛依": "KLM", "合肥": "HF", "青岛": "QD",
    "军事": "JS", "医学": "YX",
}


def _normalize_fullwidth_name(name: str) -> str:
    """全角括号 -> 半角，保证官方名单与库内名称可比。"""
    return name.replace("（", "(").replace("）", ")")


def _load_official_codes() -> dict[str, str]:
    """读取教育部名单：学校名称 -> 官方码（10 位）。优先 .xlsx。"""
    path = FALLBACK_OFFICIAL_XLSX
    if not path.exists() and OFFICIAL_XLS.exists():
        raise SystemExit(
            "需要已转换的官方名单 xlsx。请先用 LibreOffice 转换，或把转换文件放到 "
            f"{FALLBACK_OFFICIAL_XLSX}"
        )
    wb = load_workbook(path, data_only=True)
    ws = wb[wb.sheetnames[0]]
    out: dict[str, str] = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        name, code = row[1], row[2]
        if not name or code is None:
            continue
        if isinstance(code, float) and code.is_integer():
            code = str(int(code))
        out[_normalize_fullwidth_name(str(name).strip())] = str(code).strip()
    return out


def _lookup_official(name: str, official_name2code: dict[str, str]) -> str:
    """精确匹配优先，失败时做全角->半角归一化匹配。

    official_name2code 的键已在加载时归一化，_normalize_fullwidth_name 处理
    库内半角/全角括号差异，保证两边一致。
    """
    hit = official_name2code.get(name)
    if hit:
        return hit
    return official_name2code.get(_normalize_fullwidth_name(name), "")


def _strip_bracket(name: str) -> str:
    """去掉括号后缀 + 常见变体词缀，还原主校名称。"""
    n = re.sub(r"[（(].*?[)）]", "", name)
    while True:
        lead = n
        for tail in ("校区", "分校", "医学部", "医学院"):
            if n.endswith(tail):
                n = n[: -len(tail)]
        if n == lead:
            break
    return n.strip()


_CAMPUS_MARKERS = ("校区", "分校", "医学部", "医学院")


def _safe_place_remainder(rem: str) -> bool:
    """判断"官方名校前缀之外的剩余段"是否是合法地名后缀（校区/医学部等）。

    例：`保定校区`/`上海医学院`/`克拉玛依校区`/`秦皇岛分校` -> True；
        `城市学院`/`中德应用技术学院`（独立学院）-> False。
    """
    r = rem
    for m in _CAMPUS_MARKERS:
        if r.endswith(m):
            r = r[: -len(m)]
            break
    if not r:
        return False
    if r in _PLACE_TAG:
        return True
    # 纯地名推断：≤4 字且不含 学/院/大/师/范（防独立学院误挂）
    return len(r) <= 4 and all(not ch in r for ch in ("学", "院", "大", "师", "范", "中"))


def _try_master(name: str, official_name2code: dict[str, str]) -> tuple[str, str]:
    """尝试把变体名还原为主校。返回 (主校官方码, 主校官方名)；失败返回 ('','')。

    规则（防止更名院校误挂）：
     1) 去括号+去词缀后精确命中官方名 -> 直接返回。
     2) 官方名是「原始名（含括号）」的前缀，剩余为地名/校区后缀 -> 返回官方码。
        例：中国石油大学（北京）克拉玛依校区 -> 前缀 中国石油大学（北京） + 克拉玛依校区。
     3) 官方名是「去括号名」的前缀，剩余为地名后缀 -> 返回官方码。
        例：华北电力大学保定校区 -> 前缀 华北电力大学 + 保定。
    """
    base = _strip_bracket(name)
    if base in official_name2code:
        return official_name2code[base], base

    candidates = [name, re.sub(r"[（(].*?[)）]", "", name).strip()]
    for cand in candidates:
        if cand in official_name2code:
            return official_name2code[cand], cand
        for oname, oc in official_name2code.items():
            if cand.startswith(oname):
                rem = cand[len(oname):]
                if _safe_place_remainder(rem):
                    return oc, oname
    return "", ""


def _variant_tag(name: str, master_official: str, master_name: str, used: set[str]) -> str:
    """生成变体唯一后缀：区分词 -> 拼音首字母；已占用则拼主校码尾巴保证唯一。

    区分词 = 变体名去掉主校名前缀后的剩余（再清 校区/分校/医学部/括号）。
    例：哈尔滨工业大学（威海）minus 哈尔滨工业大学 -> （威海） -> 威海 -> -WH；
        中国石油大学（北京）克拉玛依校区 minus 中国石油大学（北京）
            -> 克拉玛依校区 -> 克拉玛依 -> -KLM
    """
    rest = name[len(master_name):] if master_name and name.startswith(master_name) else name
    for pat in _CAMPUS_MARKERS:
        rest = rest.replace(pat, "")
    for pat in ("（", "）", "(", ")"):
        rest = rest.replace(pat, "")
    rest = rest.strip()
    tag = ""
    # 医学类（医学部/医学院 原标记）统一用 -YX
    if "医学部" in name or "医学院" in name:
        tag = "YX"
    else:
        for k, v in _PLACE_TAG.items():
            if k in rest:
                tag = v
                break
    if not tag:
        # fallback：确定性短摘要（不能再用内置 hash，避免 PYTHONHASHSEED 随机）
        seed = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
        tag = f"V{seed}"
    candidate = f"{master_official}-{tag}"
    while candidate in used:
        candidate = f"{candidate}2"
    used.add(candidate)
    return candidate


def _master_of(name: str, official_name2code: dict[str, str]) -> tuple[str, str]:
    """返回 (主校官方码, 主校官方名)；无法挂主校则 ('','')。"""
    mc, mn = _try_master(name, official_name2code)
    return mc, mn


def plan_actions(conn, official_name2code: dict[str, str],
                 code2name: dict[str, str]) -> dict[str, Any]:
    """计算迁移动作（只读）。返回各类计数 + 动作列表。"""
    colleges = conn.execute("SELECT id, name FROM colleges").fetchall()
    numeric_ids = {r["id"] for r in colleges if not r["id"].startswith("CU")}
    numeric_names: dict[str, list[str]] = {}
    for r in colleges:
        if not r["id"].startswith("CU"):
            numeric_names.setdefault(r["name"], []).append(r["id"])

    actions: dict[str, list[dict[str, Any]]] = {
        "numeric_off": [],      # numeric 有官方码 -> 直接回填 official_code（id 不变）
        "numeric_variant": [],  # numeric 变体 -> 主校码+后缀
        "cu_dup": [],           # 同名 CU -> 删除（引用并入 numeric 官方目标）
        "cu_off": [],           # 独有 CU 有官方码 -> id=官方码
        "cu_variant": [],       # 无官方码可挂主校 -> 主校码+后缀
        "conflict": [],         # 无码无主校（军校/独立学院/高职）-> 保留 CU
    }
    used_suffix: set[str] = set()
    # 预占：所有用官方码做主键的（numeric_off + cu_off）
    for r in colleges:
        if not r["id"].startswith("CU") and _lookup_official(r["name"], official_name2code):
            used_suffix.add(_lookup_official(r["name"], official_name2code))
        elif r["id"].startswith("CU") and _lookup_official(r["name"], official_name2code) and r["name"] not in numeric_names:
            used_suffix.add(_lookup_official(r["name"], official_name2code))

    for r in colleges:
        cid, name = r["id"], r["name"]
        if not cid.startswith("CU"):
            official = _lookup_official(name, official_name2code)
            if official:
                actions["numeric_off"].append({"id": cid, "name": name, "official": official})
                continue
            # 试试后缀匹配官方码（官方码后 5 位=地方码）
            suffix_match = code2name.get(cid, "")
            if suffix_match and cid.isdigit():
                actions["numeric_off"].append({"id": cid, "name": name, "official": ""})
                # 若地方码恰好是某官方码后5位，尝试名称对应
                for oc, on in code2name.items():
                    if oc.endswith(cid) and (on == name or on in name):
                        actions["numeric_off"][-1]["official"] = oc
                        break
            if actions["numeric_off"] and actions["numeric_off"][-1]["id"] == cid and actions["numeric_off"][-1]["official"]:
                continue
            if actions["numeric_off"] and actions["numeric_off"][-1]["id"] == cid:
                actions["numeric_off"].pop()
            # numeric 变体：主校码+后缀
            mc, mn = _master_of(name, official_name2code)
            if mc:
                new_id = _variant_tag(name, mc, mn, used_suffix)
                actions["numeric_variant"].append({"id": cid, "name": name, "new_id": new_id,
                                                   "official": mc})
                continue
            # 军校/港校等 numeric 保留
            actions["numeric_off"].append({"id": cid, "name": name, "official": ""})
            continue

        # CU 行
        if name in numeric_names:
            target_numeric = numeric_names[name][0]
            target_off = _lookup_official(name, official_name2code)
            actions["cu_dup"].append({"id": cid, "name": name, "official": target_off,
                                      "to_numeric": target_numeric,
                                      "merge_to": target_off or target_numeric})
            continue
        official = _lookup_official(name, official_name2code)
        if official:
            actions["cu_off"].append({"id": cid, "name": name, "official": official})
            continue
        mc, mn = _master_of(name, official_name2code)
        if mc:
            new_id = _variant_tag(name, mc, mn, used_suffix)
            actions["cu_variant"].append({"id": cid, "name": name, "new_id": new_id, "official": mc})
            continue
        actions["conflict"].append({"id": cid, "name": name})

    return actions


def _build_old2new(actions: dict[str, list[dict[str, Any]]],
                   official_name2code: dict[str, str]) -> dict[str, str]:
    """构建 旧id -> 新id 映射（引用迁移用）。"""
    old2new: dict[str, str] = {}
    for x in actions["numeric_off"]:
        if x["official"]:
            old2new[x["id"]] = x["official"]
    for x in actions["numeric_variant"]:
        old2new[x["id"]] = x["new_id"]
    for x in actions["cu_dup"]:
        # 并入 numeric 的目标（可能还是地方码，但引用已并入 numeric）
        old2new[x["id"]] = x["merge_to"]
    for x in actions["cu_off"]:
        old2new[x["id"]] = x["official"]
    for x in actions["cu_variant"]:
        old2new[x["id"]] = x["new_id"]
    # 把仍指向 numeric 旧地方码的引用再前推一次到官方码
    changed = True
    while changed:
        changed = False
        for old in list(old2new):
            target = old2new[old]
            if target in old2new and old2new[target] != target:
                old2new[old] = old2new[target]
                changed = True
    return old2new


def _audit(conn, actions: dict[str, list[dict[str, Any]]],
           official_name2code: dict[str, str]) -> None:
    print("=== 迁移审计 ===")
    print(f"官方名单院校数: {len(official_name2code)}")
    num_keep = len(actions["numeric_off"]) + len(actions["numeric_variant"])
    num_off = sum(1 for x in actions["numeric_off"] if x["official"])
    print(f"numeric（广东地方码）: {num_keep}  其中回填官方码: {num_off}  "
          f"变体(主校码+后缀): {len(actions['numeric_variant'])}")
    all_cu = (len(actions["cu_dup"]) + len(actions["cu_off"]) + len(actions["cu_variant"])
              + len(actions["conflict"]))
    print(f"CU 同名删除: {len(actions['cu_dup'])}")
    print(f"CU -> 官方码: {len(actions['cu_off'])}")
    print(f"CU 变体(主校码+后缀): {len(actions['cu_variant'])}")
    print(f"CU 冲突(保留): {len(actions['conflict'])}")
    print(f"CU 合计: {all_cu}")

    if actions["cu_variant"]:
        print("\n[示例] CU 变体:")
        for x in actions["cu_variant"][:8]:
            print(f"  {x['id']} {x['name']} -> {x['new_id']}")
    if actions["numeric_variant"]:
        print("\n[示例] numeric 变体:")
        for x in actions["numeric_variant"][:8]:
            print(f"  {x['id']} {x['name']} -> {x['new_id']}")
    if actions["cu_dup"]:
        print("\n[示例] CU 同名删除:")
        for x in actions["cu_dup"][:8]:
            print(f"  {x['id']} {x['name']} -> 并入 {x['merge_to']}")
    if actions["conflict"]:
        print(f"\n[警告] CU 冲突 {len(actions['conflict'])}（保留待人工）:")
        for x in actions["conflict"][:20]:
            print(f"  {x['id']} {x['name']}")

    old_ids = set()
    for lst_key, id_key in (("numeric_off", "id"), ("numeric_variant", "id"),
                            ("cu_dup", "id"), ("cu_off", "id"), ("cu_variant", "id")):
        for x in actions[lst_key]:
            old_ids.add(x[id_key])
    refs_cm = refs_ar = 0
    if old_ids:
        ph = ",".join("?" * len(old_ids))
        refs_cm = conn.execute(f"SELECT COUNT(*) FROM college_majors WHERE college_id IN ({ph})",
                               list(old_ids)).fetchone()[0]
        refs_ar = conn.execute(f"SELECT COUNT(*) FROM admission_ranks WHERE college_id IN ({ph})",
                               list(old_ids)).fetchone()[0]
    print(f"\n将被迁移的旧 id 数: {len(old_ids)} | 引用面 college_majors={refs_cm}, admission_ranks={refs_ar}")
    n_conflict_cu = conn.execute("SELECT COUNT(*) FROM colleges WHERE id LIKE 'CU%' AND "
                                 "id NOT IN ({})".format(",".join(["?"]*len(old_ids))),
                                 list(old_ids)).fetchone()[0] if old_ids else conn.execute(
        "SELECT COUNT(*) FROM colleges WHERE id LIKE 'CU%'").fetchone()[0]
    print(f"迁移后剩余 CU 行（冲突保留）: {n_conflict_cu}")


_AR_COLS = ("college_id", "major_id", "province", "year", "batch", "min_rank",
            "min_score", "enrollment_count", "exam_category", "group_code")
_CM_COLS = ("college_id", "major_id", "batch", "years", "degree", "tuition",
            "min_rank_2024", "min_rank_2023", "min_rank_2022", "subject_requirement",
            "metadata", "created_at", "updated_at")


def _remap_table(conn, table: str, cols: list[str], old: str, new: str) -> None:
    """把表中 college_id=old 的行整体改到 new；与既有 new 行 PK 冲突时 REPLACE。"""
    if old == new:
        return
    sel = ", ".join(cols)
    conn.execute(f"INSERT OR REPLACE INTO {table} ({sel}) SELECT ?, " + ", ".join(cols[1:]) +
                 f" FROM {table} WHERE college_id=?",
                 (new, old))
    conn.execute(f"DELETE FROM {table} WHERE college_id=?", (old,))


def _run_migration(conn, actions, official_name2code) -> None:
    old2new = _build_old2new(actions, official_name2code)
    print(f"\n>>> 真跑迁移: 共 {len(old2new)} 个旧 id 变更")

    # id 是 admissions/college_majors 的外键主键，改名期间必须关掉 FK 校验
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        with conn:  # 事务
            # 1) numeric_off：id -> 官方码（主键全面官方码化）+ 回填 official_code
            for x in actions["numeric_off"]:
                if x["official"]:
                    conn.execute("UPDATE colleges SET id=?, official_code=? WHERE id=?",
                                 (x["official"], x["official"], x["id"]))
            # 2) numeric_variant / cu_variant：换 id = 主校码+后缀
            for x in actions["numeric_variant"] + actions["cu_variant"]:
                conn.execute("UPDATE colleges SET id=?, official_code=? WHERE id=?",
                             (x["new_id"], x["official"], x["id"]))
            # 3) cu_off：CU id -> 官方码
            for x in actions["cu_off"]:
                conn.execute("UPDATE colleges SET id=?, official_code=? WHERE id=?",
                             (x["official"], x["official"], x["id"]))
            # 4) cu_dup：删除同名 CU（引用已并入，见引用迁移）
            for x in actions["cu_dup"]:
                conn.execute("DELETE FROM colleges WHERE id=?", (x["id"],))

        with conn:
            # 引用迁移（INSERT OR REPLACE + DELETE，处理同校对同一官方码的 PK 合并）
            for old, new in old2new.items():
                _remap_table(conn, "admission_ranks", list(_AR_COLS), old, new)
                _remap_table(conn, "college_majors", list(_CM_COLS), old, new)
        with conn:
            # volunteer_plans.slots JSON
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
            # doc_meta_v2.metadata 里的 college_id（RAG 知识库种子时写入的旧 id）
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
        with conn:
            # college_code_map 填充（官方码 <-> 广东地方码）
            for x in actions["numeric_off"]:
                if x["official"]:
                    conn.execute(
                        "INSERT OR REPLACE INTO college_code_map (official_code, province_code, province, school_name, source) VALUES (?,?,?,?,?)",
                        (x["official"], x["id"], "广东", x["name"], "gd_local"))
            for x in actions["numeric_variant"]:
                conn.execute(
                    "INSERT OR REPLACE INTO college_code_map (official_code, province_code, province, school_name, source) VALUES (?,?,?,?,?)",
                    (x["official"], x["id"], "广东", x["name"], "gd_variant"))
            # 清除旧备份表
            conn.execute("DROP TABLE IF EXISTS admission_ranks_old")
    finally:
        conn.execute("PRAGMA foreign_keys=ON")

    # 完整性校验
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

    print("Done (real run): 编码归一迁移完成。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="仅审计，不写库")
    args = ap.parse_args()

    official_name2code = _load_official_codes()
    code2name = {code: name for name, code in official_name2code.items()}
    conn = get_connection()

    # 预检查：官方码唯一性 & 地方码是否普遍 = 官方码后5位
    dup = [c for c, n in code2name.items() if list(code2name.values()).count(n) > 1]
    if dup:
        print(f"[警告] 官方名单出现重复名称 {len(dup)}: {dup[:5]}")

    actions = plan_actions(conn, official_name2code, code2name)
    _audit(conn, actions, official_name2code)

    if args.dry_run:
        conn.close()
        print("\n（dry-run 未写库）")
        return
    _run_migration(conn, actions, official_name2code)
    conn.close()


if __name__ == "__main__":
    main()