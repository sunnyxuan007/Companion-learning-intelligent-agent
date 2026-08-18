"""2026 广东官方专业目录（PDF） vs 库 admission_ranks 全量比对。

维度：
1. 校级差异：
   - missing_schools 缺校（PDF 有、库 colleges 无）— 真缺，需人工核实
   - no_data_schools 有校无 2026 数据（colleges 存在但 admission_ranks 无 2026 广东行）
   - extra_schools 多校（库有、PDF 无）— 可能已撤销 / 解析漏
   - noise 解析噪声（PDF 里非 10 位官方码 / 名字非校名）
2. 组级差异（仅对"双方都有数据"的校）：
   - pdf_only_groups：PDF 有组、库无 → 值得人工核对（可能真缺）
   - db_only_groups：库有组、PDF 无 → 多为解析跨页/跨列丢失（标记疑似解析缺陷）

数据源说明：
- 库 admission_ranks 源于专家版 Excel（普通批投档为主，未含部分提前批/军校）
- PDF 为 2026 官方招生目录（含全部招生院校，含提前批）
- 更正表（gd_2026_correction.json）优先于 PDF，已在修正方向指引

用法：python scripts/compare_db_pdf.py [--out data/user/custom/pdf_parse/diff_report.json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data/user/custom/deeptutor_custom.db"
PDF_DIR = ROOT / "data/user/custom/pdf_parse"
CORRECTION = PDF_DIR / "gd_2026_correction.json"


def load_db(conn: sqlite3.Connection, cat: str) -> dict[str, dict]:
    """college_id -> {"name", "groups": {gcode: {"GEN", "majors": set(ids)}}}
    只取 2026 本科普通批（batch='本科批'），提前批不参与比对（PDF 为普通批目录）。"""
    out: dict[str, dict] = {}
    rows = conn.execute(
        """SELECT ar.college_id, ar.group_code, ar.major_id, c.name
           FROM admission_ranks ar
           JOIN colleges c ON c.id = ar.college_id
           WHERE ar.province='广东' AND ar.exam_category=? AND ar.year=2026
             AND ar.batch='本科批'""",
        (cat,),
    ).fetchall()
    for college_id, gcode, major_id, name in rows:
        col = out.setdefault(college_id, {"name": name, "groups": {}})
        grp = col["groups"].setdefault(gcode, {"majors": set()})
        if major_id == "GEN":
            grp["GEN"] = True
        else:
            grp["majors"].add(major_id)
    return out


def load_pdf(cat: str) -> dict[str, dict]:
    path = PDF_DIR / f"gd_2026_{'physics' if cat == '物理' else 'history'}.json"
    records = json.load(open(path))["records"]
    out: dict[str, dict] = {}
    for r in records:
        out[r["college_id"]] = {
            "name": r["name"],
            "college_code": r.get("college_code"),
            "groups": {g["group_code"]: {m["major_id"] for m in g["majors"] if m.get("major_id")}
                       for g in r["groups"]},
        }
    return out


def is_noise(cid: str, name: str) -> bool:
    """解析噪声判定：非 10 位官方数字码，或名字明显非校名。"""
    if len(cid) != 10 or not cid.isdigit():
        return True
    if not name or len(name) < 2:
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(PDF_DIR / "diff_report.json"))
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    correction = json.load(open(CORRECTION)) if CORRECTION.exists() else {"records": []}
    corr_schools = {r["college_code"] for r in correction.get("records", []) if r.get("college_code")}

    report = {"correction_schools": sorted(corr_schools)}
    for cat in ("物理", "历史"):
        db = load_db(conn, cat)
        pdf = load_pdf(cat)

        # 过滤解析噪声
        noise = [{"college_id": cid, "name": pdf[cid]["name"]}
                 for cid in sorted(pdf) if is_noise(cid, pdf[cid]["name"])]
        clean_pdf = {cid: v for cid, v in pdf.items() if not is_noise(cid, v["name"])}

        pdf_codes = set(clean_pdf)
        db_codes = set(db)

        # 缺校：PDF 有、库 colleges 无
        college_ids = {r[0] for r in conn.execute("SELECT id FROM colleges").fetchall()}
        missing = sorted(pdf_codes - db_codes, key=lambda x: clean_pdf[x]["name"])
        missing_schools = []   # 真缺（colleges 无）
        no_data_schools = []   # 有校无 2026 数据
        for cid in missing:
            item = {"college_id": cid, "name": clean_pdf[cid]["name"]}
            (missing_schools if cid not in college_ids else no_data_schools).append(item)

        # 多校：库有、PDF 无
        extra_schools = [{"college_id": cid, "name": db[cid]["name"]}
                         for cid in sorted(db_codes - pdf_codes, key=lambda x: db[x]["name"])]

        # 组级差异（双方都有 2026 数据的校）
        group_diff = []
        for cid in sorted(db_codes & pdf_codes, key=lambda x: db[x]["name"]):
            pdf_g = set(clean_pdf[cid]["groups"])
            db_g = set(db[cid]["groups"])
            if pdf_g == db_g:
                continue
            group_diff.append({
                "college_id": cid,
                "name": db[cid]["name"],
                "pdf_only_groups": sorted(pdf_g - db_g),
                "db_only_groups": sorted(db_g - pdf_g),
            })

        report[cat] = {
            "pdf_schools": len(clean_pdf),
            "db_schools": len(db_codes),
            "noise_records": len(noise),
            "missing_schools": len(missing_schools),
            "no_data_schools": len(no_data_schools),
            "extra_schools": len(extra_schools),
            "group_diff_schools": len(group_diff),
            "pdf_only_group_total": sum(len(d["pdf_only_groups"]) for d in group_diff),
            "db_only_group_total": sum(len(d["db_only_groups"]) for d in group_diff),
            "noise_list": noise,
            "missing_school_list": missing_schools,
            "no_data_school_list": no_data_schools,
            "extra_school_list": extra_schools,
            "group_diff_list": group_diff,
        }

    conn.close()
    out_path = Path(args.out)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入 {out_path}")

    for cat in ("物理", "历史"):
        s = report[cat]
        print(f"\n=== {cat} ===")
        print(f"  PDF {s['pdf_schools']} 校 / DB {s['db_schools']} 校 / 噪声 {s['noise_records']} 条")
        print(f"  真缺校: {s['missing_schools']}   有校无2026数据: {s['no_data_schools']}   多校: {s['extra_schools']}")
        print(f"  组级差异院校: {s['group_diff_schools']} (PDF独有组 {s['pdf_only_group_total']} / 库独有组 {s['db_only_group_total']})")


if __name__ == "__main__":
    main()