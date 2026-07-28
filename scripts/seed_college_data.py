"""Import university data from Excel into the custom database."""

from __future__ import annotations

import time
from pathlib import Path

import openpyxl

from deeptutor.services.custom.college_dao import import_college
from deeptutor.services.custom.db import init_db
from deeptutor.services.custom.models import College

SRC = Path("/home/sunnyxuan2/桌面/data for agent/university_info.xlsx")


def _to_level(has_985, has_211, is_shuangyiliu):
    tags = []
    if has_985 == 1:
        tags.append("985")
    if has_211 == 1:
        tags.append("211")
    if is_shuangyiliu:
        tags.append("双一流")
    return "+".join(tags) if tags else "普通"


def run():
    init_db()
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    ws = wb["university_info"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    total = len(rows)
    ok = 0

    for i, r in enumerate(rows):
        try:
            province, name, typ, pub_private, level_tag, has_985, has_211, syl, city, affiliation, address = (
                (r + (None,) * 11)[:11]
            )
            if not name or not province:
                continue

            college = College(
                id=f"CU{str(i+1).zfill(5)}",
                name=str(name).strip(),
                province=str(province).strip(),
                city=str(city).strip() if city else "",
                type=str(typ).strip() if typ else None,
                level=_to_level(has_985, has_211, syl),
                is_public=pub_private == "公办" if pub_private else True,
            )
            import_college(college)
            ok += 1
        except Exception as e:
            print(f"  [{i+1}] SKIP: {name if 'name' in dir() else '?'} — {e}")

        if (i + 1) % 500 == 0:
            print(f"  Progress: {i+1}/{total} ({ok} imported)")

    wb.close()
    print(f"\nDone: {ok}/{total} universities imported.")


if __name__ == "__main__":
    run()
