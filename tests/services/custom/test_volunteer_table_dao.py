from __future__ import annotations

import time

import pytest

from deeptutor.services.custom import volunteer_table_dao as dao


@pytest.fixture
def clean_user(custom_db):
    user_id = "plan_dao_test"
    for p in dao.list_plans(user_id):
        dao.purge_plan(p["id"])
    for p in dao.list_trash(user_id):
        dao.purge_plan(p["id"])
    return user_id


def _slots(n: int = 3) -> list[dict]:
    return [
        {
            "college_id": f"c{i}",
            "college_name": f"大学{i}",
            "group_code": f"20{i}",
            "group_prob": 0.6,
            "tier": "steady",
            "majors": [{"major_id": "m1", "major_name": "计算机", "admission_prob": 0.6}],
        }
        for i in range(1, n + 1)
    ]


def test_create_and_list(clean_user):
    uid = clean_user
    p = dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, _slots(), batch="本科批")
    assert p["deleted_at"] is None
    assert p["batch"] == "本科批"
    plans = dao.list_plans(uid)
    assert len(plans) == 1
    assert plans[0]["id"] == p["id"]
    assert plans[0]["province_rules"] == {"groups": 45}


def test_find_duplicate_order_sensitive(clean_user):
    uid = clean_user
    slots_a = _slots(2)
    dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, slots_a)
    # 相同顺序 -> 命中
    assert dao.find_duplicate(uid, _slots(2)) is not None
    # 反向顺序 -> 视为不同
    assert dao.find_duplicate(uid, list(reversed(slots_a))) is None


def test_find_duplicate_rank_sensitive(clean_user):
    uid = clean_user
    slots_a = _slots(2)
    p = dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, slots_a)
    # 相同 slots 相同 rank -> 命中
    assert dao.find_duplicate(uid, slots_a, rank=25000, exam_category="物理") is not None
    # 相同 slots 不同 rank -> 视为不同方案（同一份志愿不同位次场景可并存）
    assert dao.find_duplicate(uid, slots_a, rank=15000, exam_category="物理") is None
    # 相同 slots 不同 exam_category -> 视为不同
    assert dao.find_duplicate(uid, slots_a, rank=25000, exam_category="历史") is None
    assert p["score"] is None  # 未传 score 默认 None


def test_create_plan_with_score(clean_user):
    uid = clean_user
    p = dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, _slots(), score=585)
    assert p["score"] == 585
    # clone 继承 score
    c = dao.clone_plan(p["id"], uid)
    assert c["score"] == 585
    # 无 score 的克隆保持 None
    p2 = dao.create_plan(uid, "广东", "物理", 30000, {"groups": 45}, _slots(1))
    assert dao.clone_plan(p2["id"], uid)["score"] is None


def test_soft_delete_restore_purge(clean_user):
    uid = clean_user
    p = dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, _slots())
    # 软删除进回收站
    assert dao.soft_delete_plan(p["id"]) is True
    assert dao.list_plans(uid) == []
    trash = dao.list_trash(uid)
    assert len(trash) == 1
    assert trash[0]["deleted_at"] is not None
    # 重复软删除失败
    assert dao.soft_delete_plan(p["id"]) is False
    # 恢复
    restored = dao.restore_plan(p["id"])
    assert restored is not None
    assert restored["deleted_at"] is None
    assert len(dao.list_plans(uid)) == 1
    # 永久删除
    assert dao.purge_plan(p["id"]) is True
    assert dao.list_plans(uid) == []
    assert dao.list_trash(uid) == []


def test_list_trash_lazy_cleanup_expired(clean_user):
    uid = clean_user
    p = dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, _slots())
    dao.soft_delete_plan(p["id"])
    # 把 deleted_at 改为 8 天前（超过保留期 7 天）
    import sqlite3

    from deeptutor.services.custom.db import get_connection

    conn = get_connection()
    conn.execute(
        "UPDATE volunteer_plans SET deleted_at = ? WHERE id = ?",
        (time.time() - 8 * 24 * 3600, p["id"]),
    )
    conn.commit()
    conn.close()
    # list_trash 时惰性清理
    assert dao.list_trash(uid) == []


def test_find_duplicate_ignores_trash(clean_user):
    uid = clean_user
    p = dao.create_plan(uid, "广东", "物理", 25000, {"groups": 45}, _slots(2))
    dao.soft_delete_plan(p["id"])
    # 回收站里的方案不参与去重
    assert dao.find_duplicate(uid, _slots(2)) is None


def test_plan_label_helper():
    from deeptutor.api.routers.volunteer_table import _plan_label

    # 2026-06-28 16:26 -> 06281626
    ts = time.mktime((2026, 6, 28, 16, 26, 0, 0, 0, 0))
    assert _plan_label({"created_at": ts}) == "06281626"
