"""普通 CU（合成码）全面国标码迁移脚本（Phase 19）。

处理 Phase 17/18 之后剩余的 219 所普通 CU（非军警校）：
- 已确认转设/更名/升格的 CU -> 迁移到教育部官方码
- 撤销/停办/并入的 CU -> 删除（并入的 remap 引用到目标行）
- 无官方码的普通高校（保持原名）-> 保留 CU 码不动

处置规则（用户逐条确认）：
- MIG（183 所）：目标码在库中存在 -> 并入；目标码缺失 -> 改 id + 更名
- DELETE（7 所）：撤销/停办直接删；并入的两所 remap 引用后删
- KEEP（29 所）：无官方码确认，保留不动

用法：python scripts/migrate_remaining_cu.py --dry-run   # 仅审计
       python scripts/migrate_remaining_cu.py             # 真跑迁移
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from deeptutor.services.custom.db import get_connection

# 保留（无官方码/中外合作/维持原样）29 所
KEEP_CU: set[str] = {
    "CU00212", "CU00276", "CU00322", "CU00342", "CU00344", "CU00349", "CU00350",
    "CU00386", "CU00390", "CU00398", "CU00586", "CU00587", "CU00628", "CU01066",
    "CU01575", "CU01933", "CU02231", "CU02289", "CU02341", "CU02350", "CU02403",
    "CU02440", "CU02475", "CU02487", "CU02530", "CU02670", "CU02747", "CU02752",
    "CU02758",
}

# 删除（撤销/停办/并入）7 所：CU id -> 并入目标（None=直接删）
DELETE_CU: dict[str, str | None] = {
    "CU01479": None,  # 山东杏林科技职业学院（撤销）
    "CU01765": None,  # 湖北青年职业学院（撤销）
    "CU01766": None,  # 鄂东职业技术学院（停招）
    "CU02080": "4145010608",  # 广西大学行健文理学院 -> 广西民族大学
    "CU02395": "4152016206",  # 贵州师范大学求是学院 -> 贵阳康养职业大学
    "CU02653": None,  # 西北师范大学知行学院（停办）
    "CU02657": None,  # 兰州财经大学长青学院（停办）
}

# 迁移（183 所）：CU id -> (新校名, 官方码)
MIG_CU: dict[str, tuple[str, str]] = {
    # 北京
    "CU00052": ("北京金融科技学院", "4111013630"),
    "CU00062": ("北京科技职业大学", "4111010858"),
    "CU00090": ("民政职业大学", "4111014139"),
    # 天津
    "CU00115": ("天津职业大学", "4112011032"),
    # 河北
    "CU00160": ("应急管理大学", "4113011104"),
    "CU00177": ("应急管理大学", "4113011104"),
    "CU00204": ("河北中医药大学", "4113014432"),
    "CU00238": ("唐山工业职业技术大学", "4113012787"),
    "CU00240": ("邢台医学院", "4113012884"),
    "CU00258": ("河北正定师范高等专科学校", "4113014185"),
    "CU00266": ("沧州幼儿师范高等专科学校", "4113014259"),
    # 山西
    "CU00294": ("山西医药学院", "4114014898"),
    "CU00310": ("山西电子科技学院", "4114013537"),
    "CU00317": ("山西科技学院", "4114013597"),
    "CU00319": ("晋中健康学院", "4114013598"),
    # 内蒙古
    "CU00376": ("赤峰大学", "4115010138"),
    "CU00378": ("包头师范学院", "4115018127"),
    # 辽宁
    "CU00449": ("大连工程学院", "4121013198"),
    "CU00487": ("朝阳师范学院", "4121010171"),
    # 吉林
    "CU00550": ("吉林化工大学", "4122010192"),
    "CU00568": ("吉林铁道职业技术大学", "4122014052"),
    "CU00569": ("长春汽车职业技术大学", "4122011436"),
    "CU00579": ("长春职业技术大学", "4122013161"),
    # 黑龙江
    "CU00621": ("牡丹江医科大学", "4123010229"),
    "CU00633": ("哈尔滨职业技术大学", "4123012911"),
    "CU00635": ("黑龙江农业工程职业大学", "4123012726"),
    "CU00646": ("黑龙江农业工程职业大学", "4123012726"),
    "CU00649": ("黑龙江农业工程职业大学", "4123012726"),
    # 上海
    "CU00708": ("上海体育大学", "4131010277"),
    # 江苏
    "CU00791": ("淮安大学", "4132011049"),
    "CU00792": ("苏州工学院", "4132010333"),
    "CU00796": ("苏州职业技术大学", "4132011054"),
    "CU00802": ("无锡职业技术大学", "4132010848"),
    "CU00811": ("江苏建筑职业技术大学", "4132010849"),
    "CU00814": ("常州信息职业技术大学", "4132012317"),
    "CU00829": ("连云港师范高等专科学校", "4132014189"),
    "CU00834": ("扬州职业技术大学", "4132011462"),
    "CU00870": ("苏州高博职业学院", "4132014163"),
    # 浙江
    "CU00927": ("嘉兴大学", "4133010354"),
    "CU00928": ("浙江科技大学", "4133011057"),
    "CU00932": ("湖州师范大学", "4133010347"),
    "CU00935": ("绍兴大学", "4133010349"),
    "CU00958": ("金华职业技术大学", "4133012061"),
    "CU00959": ("绍兴理工学院", "4133013288"),
    "CU00966": ("浙江药科职业大学", "4133016207"),
    "CU00971": ("宁波职业技术大学", "4133010863"),
    "CU00975": ("浙江药科职业大学", "4133016207"),
    "CU00977": ("温州职业技术大学", "4133010864"),
    "CU00978": ("杭州职业技术大学", "4133012872"),
    "CU00987": ("浙江机电职业技术大学", "4133012861"),
    # 安徽
    "CU01030": ("合肥大学", "4134011059"),
    "CU01031": ("安徽科技工程大学", "4134010879"),
    "CU01032": ("皖南医科大学", "4134010368"),
    "CU01033": ("蚌埠医科大学", "4134010367"),
    "CU01045": ("安徽第二医学院", "4134012925"),
    "CU01047": ("安徽应用技术职业大学", "4134012072"),
    "CU01051": ("芜湖职业技术学院", "4134011558"),
    "CU01069": ("安徽应用技术职业大学", "4134012072"),
    "CU01073": ("芜湖学院", "4134013623"),
    "CU01076": ("阜阳理工学院", "4134013619"),
    "CU01086": ("淮北理工学院", "4134013620"),
    "CU01087": ("安徽应用技术职业大学", "4134012072"),
    # 福建
    "CU01146": ("闽江大学", "4135010395"),
    "CU01148": ("福建理工大学", "4135010388"),
    "CU01187": ("福州职业技术大学", "4135011502"),
    # 江西
    "CU01237": ("江西水利电力大学", "4136011319"),
    "CU01243": ("赣南医科大学", "4136010413"),
    "CU01253": ("江西职业技术大学", "4136011785"),
    "CU01266": ("江西中医药大学", "4136010412"),
    "CU01276": ("江西外语外贸职业大学", "4136013422"),
    "CU01290": ("江西飞行学院", "4136014839"),
    "CU01315": ("南昌科技职业大学", "4136014168"),
    "CU01323": ("九江科技职业大学", "4136014403"),
    # 山东
    "CU01362": ("山东第二医科大学", "4137010438"),
    "CU01363": ("日照职业技术学院", "4137011442"),
    "CU01364": ("山东第二医科大学", "4137010438"),
    "CU01372": ("山东航空学院", "4137010449"),
    "CU01378": ("山东商业职业技术学院", "4137010607"),
    "CU01387": ("淄博职业技术大学", "4137013009"),
    "CU01390": ("烟台科技学院", "4137014002"),
    "CU01402": ("滨州职业技术大学", "4137012818"),
    "CU01413": ("山东科技职业大学", "4137012819"),
    "CU01464": ("青岛电影学院", "4137014327"),
    # 河南
    "CU01506": ("信阳师范大学", "4141010477"),
    "CU01509": ("河南医药大学", "4141010472"),
    "CU01525": ("豫北医学院", "4141013505"),
    "CU01534": ("河南职业技术学院", "4141012081"),
    "CU01539": ("郑州铁路职业技术学院", "4141010843"),
    "CU01555": ("黄河水利职业技术大学", "4141012058"),
    "CU01564": ("新乡工程学院", "4141013506"),
    "CU01601": ("漯河食品工程职业大学", "4141014233"),
    # 湖北
    "CU01669": ("武汉职业技术大学", "4142010834"),
    "CU01710": ("荆州学院", "4142013245"),
    "CU01712": ("湖北三峡职业技术学院", "4142010961"),
    "CU01720": ("襄阳职业技术学院", "4142012345"),
    "CU01726": ("黄冈职业技术学院", "4142010964"),
    # 湖南
    "CU01784": ("湖南理工大学", "4143010543"),
    "CU01803": ("湖南工艺美术职业大学", "4143013921"),
    "CU01819": ("湖南化工职业技术学院", "4143012235"),
    "CU01825": ("长沙工业学院", "4143012652"),
    "CU01837": ("张家界学院", "4143012662"),
    "CU01840": ("岳阳学院", "4143012658"),
    "CU01845": ("常德学院", "4143012657"),
    "CU01859": ("湖南汽车工程职业大学", "4143013937"),
    "CU01877": ("湖南软件职业技术大学", "4143013925"),
    # 广东
    "CU01919": ("广东江门南粤学院", "4144013675"),
    "CU01929": ("佛山大学", "4144011847"),
    "CU01940": ("深圳职业技术大学", "4144011113"),
    "CU01959": ("顺德职业技术大学", "4144010831"),
    "CU01963": ("广东轻工职业技术大学", "4144010833"),
    "CU01970": ("广州职业技术大学", "4144012046"),
    "CU01972": ("深圳信息职业技术大学", "4144012957"),
    "CU01976": ("广州华立学院", "4144013656"),
    "CU01978": ("东莞城市学院", "4144013844"),
    "CU01980": ("肇庆医学院", "4144013810"),
    "CU02046": ("广东艺术职业学院", "4144014407"),
    # 广西
    "CU02069": ("桂林医科大学", "4145010601"),
    "CU02083": ("南宁理工学院", "4145013645"),
    "CU02085": ("南宁职业技术大学", "4145011355"),
    "CU02086": ("桂林学院", "4145013641"),
    "CU02087": ("桂林信息科技学院", "4145013644"),
    "CU02094": ("柳州职业技术大学", "4145012104"),
    "CU02095": ("桂林师范高等专科学校", "4145011852"),
    "CU02102": ("广西职业技术学院", "4145012073"),
    "CU02105": ("广西农业职业技术大学", "4145016205"),
    # 海南
    "CU02143": ("海南医科大学", "4146011810"),
    "CU02148": ("海南经贸职业大学", "4146013875"),
    # 重庆
    "CU02171": ("重庆科技大学", "4150011551"),
    "CU02174": ("重庆三峡科技大学", "4150010643"),
    "CU02183": ("重庆工程职业技术学院", "4150012707"),
    "CU02184": ("重庆电子科技职业大学", "4150012609"),
    "CU02197": ("重庆工业职业技术大学", "4150012215"),
    "CU02200": ("重庆城市管理职业大学", "4150012758"),
    # 四川
    "CU02244": ("成都锦城学院", "4151013903"),
    "CU02268": ("四川交通职业技术学院", "4151012711"),
    "CU02269": ("成都航空职业技术学院", "4151012075"),
    "CU02274": ("四川工程职业技术大学", "4151012763"),
    "CU02281": ("成都外国语学院", "4151013673"),
    "CU02282": ("四川建筑职业技术学院", "4151012814"),
    "CU02296": ("绵阳城市学院", "4151014045"),
    # 贵州
    "CU02382": ("贵州黔南科技学院", "4152013649"),
    "CU02386": ("贵阳信息科技学院", "4152013650"),
    "CU02390": ("贵州交通职业大学", "4152012222"),
    "CU02391": ("贵州黔南经济学院", "4152013648"),
    "CU02398": ("重庆人文科技学院", "4150013548"),
    "CU02399": ("贵阳康养职业大学", "4152016206"),
    "CU02400": ("铜仁职业技术学院", "4152012207"),
    "CU02407": ("贵州工业职业技术学院", "4152012205"),
    "CU02412": ("贵州工商职业大学", "4152014412"),
    # 云南
    "CU02453": ("滇池学院", "4153013326"),
    "CU02456": ("昆明城市学院", "4153013330"),
    "CU02464": ("昆明冶金职业大学", "4153011557"),
    "CU02473": ("云南交通职业技术大学", "4153012357"),
    "CU02479": ("昆明传媒学院", "4153013333"),
    "CU02480": ("丽江师范学院", "4153014015"),
    "CU02491": ("德宏师范学院", "4153014016"),
    "CU02516": ("云南交通职业技术大学", "4153012357"),
    # 西藏
    "CU02527": ("拉萨师范学院", "4154012481"),
    # 陕西
    "CU02575": ("榆林大学", "4161011395"),
    "CU02593": ("陕西农林职业技术大学", "4161010966"),
    "CU02599": ("陕西工业职业技术大学", "4161010828"),
    # 甘肃
    "CU02641": ("天水师范大学", "4162010739"),
    "CU02655": ("兰州资源环境职业技术大学", "4162016208"),
    "CU02658": ("兰州石化职业技术大学", "4162016209"),
    "CU02661": ("陇南师范学院", "4162011806"),
    "CU02662": ("甘肃工业职业技术学院", "4162012167"),
    "CU02663": ("酒泉职业技术大学", "4162012539"),
    "CU02664": ("甘肃林业职业技术学院", "4162012168"),
    "CU02666": ("武威职业技术大学", "4162013518"),
    "CU02677": ("兰州石化职业技术大学", "4162016209"),
    # 青海
    "CU02686": ("青海职业技术大学", "4163012973"),
    "CU02690": ("青海农牧科技职业学院", "4163012972"),
    # 宁夏
    "CU02697": ("银川科技学院", "4164013616"),
    "CU02699": ("宁夏师范大学", "4164010753"),
    "CU02704": ("宁夏工商职业技术大学", "4164013087"),
    "CU02705": ("宁夏职业技术大学", "4164013086"),
    # 新疆
    "CU02726": ("新疆工业职业技术大学", "4165012514"),
    "CU02729": ("新疆交通职业技术大学", "4165013926"),
    "CU02730": ("新疆农业职业技术大学", "4165010995"),
    "CU02741": ("新疆能源铁道职业技术大学", "4165014489"),
    "CU02742": ("石河子职业技术大学", "4165013956"),
    "CU02749": ("新疆工业职业技术大学", "4165012514"),
    "CU02759": ("新疆能源铁道职业技术大学", "4165014489"),
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
