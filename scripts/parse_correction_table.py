#!/usr/bin/env python3
"""Parse the Guangdong 2026 correction table (更正表) into structured JSON.

The correction table lists, per college, the "原刊登内容" (as printed in PDF)
vs "更正" (corrected). The corrected column is authoritative.

Output: {college_code: {"name":..., "groups": {group_code: [major_records]}}}
"""
import json
import re
import sys

import openpyxl

MAJOR_RE = re.compile(r"^(\d{3})\s+(.+?)\s*(\d+)?$")
GROUP_RE = re.compile(r"专业组(\d+)\s+(\d+)")


def parse_block(text):
    """Parse a corrected text block into groups -> majors list."""
    lines = [l.strip() for l in text.split("\n")]
    groups = {}
    cur_group = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        gm = re.match(r"^专业组(\d+)\s*(\d*)\s*$", line)
        if gm:
            cur_group = gm.group(1)
            plan_total = int(gm.group(2)) if gm.group(2) else None
            groups[cur_group] = {"plan_total": plan_total, "majors": []}
            i += 1
            continue
        if cur_group is not None:
            mm = re.match(r"^(\d{3})\s+(.+?)\s*(\d+)\s*$", line)
            if mm:
                groups[cur_group]["majors"].append({
                    "major_id": mm.group(1),
                    "name": mm.group(2).strip(),
                    "plan": int(mm.group(3)) if mm.group(3) else None,
                })
        i += 1
    return groups


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/sunnyxuan2/桌面/data for agent/2026广东专业目录更正表.xlsx"
    wb = openpyxl.load_workbook(src)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    result = {}
    cur_code = None
    for row in rows:
        code = row[0]
        if code is not None and str(code).strip().isdigit() and len(str(code).strip()) == 5:
            code = str(code).strip()
            name = str(row[1]).replace("\n", "").strip() if row[1] else ""
            if code not in result:
                result[code] = {"name": name, "blocks": []}
            cur_code = code
            corrected = str(row[5]) if len(row) > 5 and row[5] else ""
            if corrected.strip():
                result[cur_code]["blocks"].append(corrected)
            continue
        # non-code row: append c5 to current college
        if cur_code and len(row) > 5 and row[5]:
            corrected = str(row[5])
            if corrected.strip():
                result[cur_code]["blocks"].append(corrected)
    # merge blocks into groups
    out = {}
    for code, v in result.items():
        groups = {}
        for blk in v["blocks"]:
            g = parse_block(blk)
            for gcode, gv in g.items():
                if gcode not in groups:
                    groups[gcode] = gv
                else:
                    groups[gcode]["majors"].extend(gv["majors"])
        out[code] = {"name": v["name"], "groups": groups}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()