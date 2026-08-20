import pytest

from deeptutor.services.custom.art_sports import (
    ART_CATEGORIES,
    ART_SPORTS_RULES,
    calc_composite_score,
    art_batch_for,
    art_directions,
    art_keywords,
    default_art_direction,
    is_art_sports,
)


class TestIsArtSports:
    def test_art(self):
        assert is_art_sports("艺体类") is True

    def test_normal(self):
        assert is_art_sports("物理") is False
        assert is_art_sports("历史") is False
        assert is_art_sports(None) is False
        assert is_art_sports("") is False


class TestArtCategories:
    def test_eight_categories(self):
        assert len(ART_CATEGORIES) == 8
        codes = [c["code"] for c in ART_CATEGORIES]
        assert codes == ["音乐", "舞蹈", "表（导）演", "播音与主持", "美术与设计", "书法", "戏曲", "体育"]

    def test_keywords(self):
        assert "音乐" in art_keywords("音乐")
        assert "设计" in art_keywords("美术与设计")
        assert "书法" in art_keywords("书法")
        assert art_keywords("不存在") == []


class TestCompositeScore:
    def test_art_formula(self):
        # 美术与设计：文化×50% + 术科×2.5×50%
        r = calc_composite_score("美术与设计", 400, 250)
        assert r["errors"] == []
        assert r["score"] == 400 * 0.5 + 250 * 2.5 * 0.5  # 512.5

    def test_music_dance_directing_calligraphy_same_formula(self):
        for cat in ["音乐", "舞蹈", "表（导）演", "书法", "戏曲"]:
            r = calc_composite_score(cat, 400, 250)
            assert r["score"] == 400 * 0.5 + 250 * 2.5 * 0.5

    def test_broadcast_formula(self):
        # 播音与主持：文化×60% + 术科×2.5×40%
        r = calc_composite_score("播音与主持", 400, 250)
        assert r["score"] == 400 * 0.6 + 250 * 2.5 * 0.4  # 490

    def test_sports_formula(self):
        # 体育：文化×40% + 术科×2.5×60%
        r = calc_composite_score("体育", 400, 250)
        assert r["score"] == 400 * 0.4 + 250 * 2.5 * 0.6  # 535

    def test_bonus_points(self):
        r = calc_composite_score("美术与设计", 400, 250, bonus_points=20)
        assert r["culture"] == 420
        assert r["score"] == 420 * 0.5 + 250 * 2.5 * 0.5

    def test_major_score_out_of_range(self):
        r = calc_composite_score("美术与设计", 400, 301)
        assert "专业统考分应在 0-300 之间" in r["errors"]
        r2 = calc_composite_score("美术与设计", 400, -1)
        assert r2["errors"]

    def test_culture_score_out_of_range(self):
        r = calc_composite_score("美术与设计", 751, 200)
        assert "文化分应在 0-750 之间" in r["errors"]

    def test_missing_scores(self):
        r = calc_composite_score("美术与设计", None, None)
        assert "文化与专业统考分数均需填写" in r["errors"]
        assert r["score"] is None

    def test_unknown_category_defaults_to_art(self):
        r = calc_composite_score("未知", 400, 250)
        assert r["score"] == 400 * 0.5 + 250 * 2.5 * 0.5


class TestArtRules:
    def test_undergrad_rules(self):
        rules = ART_SPORTS_RULES["本科批"]
        assert rules["groups"] == 20
        assert rules["majors_per_group"] == 6
        assert rules["mode"] == "院校专业组"
        assert rules["ratio"] == [3, 4, 3]

    def test_art_batch(self):
        assert art_batch_for("艺体类") == "艺体类本科批"
        assert art_batch_for("物理") is None
        assert art_batch_for(None) is None


class TestArtDirections:
    def test_music_has_five_directions(self):
        assert art_directions("音乐") == ["音乐教育类", "音乐教育(声乐主项)", "音乐教育(器乐主项)",
                                          "音乐表演(声乐)", "音乐表演(器乐)"]

    def test_directing_has_three_directions(self):
        assert art_directions("表（导）演") == [
            "表(导)演(戏剧影视表演)", "表(导)演(服装表演)", "表(导)演(戏剧影视导演)",
        ]

    def test_broadcast_has_two_directions(self):
        assert art_directions("播音与主持") == ["播音与主持(普通话)", "播音与主持(粤语)"]

    def test_single_direction_category(self):
        for cat in ("美术与设计", "书法", "舞蹈", "体育", "戏曲"):
            assert art_directions(cat) == [cat]

    def test_default_direction_is_first(self):
        assert default_art_direction("音乐") == "音乐教育类"
        assert default_art_direction("美术与设计") == "美术与设计"

    def test_unknown_category(self):
        assert art_directions("未知") == ["未知"]
        assert default_art_direction("未知") == "未知"


class TestScorerArtBranch:
    def test_art_no_data_returns_no_data_status(self, custom_db: None) -> None:
        from deeptutor.services.custom.db import get_connection
        from deeptutor.services.custom.volunteer_scorer import generate_group_recommendations

        conn = get_connection()
        ids = [
            r["college_id"]
            for r in conn.execute(
                "SELECT DISTINCT college_id FROM admission_ranks WHERE province=? AND exam_category=?",
                ("广东", "艺体类"),
            ).fetchall()
        ]
        conn.close()
        colleges_map = {cid: {"id": cid, "name": cid, "province": "广东"} for cid in ids}

        result = generate_group_recommendations(
            colleges_map,
            province="广东",
            exam_category="艺体类",
            user_profile={"rank": 100, "exam_category": "艺体类"},
            top_n=100,
            batch="艺体类本科批",
            art_category="美术与设计",
        )
        assert result["total"] == 0
        assert result["data_status"] == "no_data"
        assert "待补充" in result.get("message", "")

    def test_art_with_data_uses_20_group_caps(self, custom_db: None) -> None:
        from deeptutor.services.custom.db import get_connection
        from deeptutor.services.custom.volunteer_scorer import generate_group_recommendations

        conn = get_connection()
        now = 2026
        # 30 art groups: 10 reach (low rank), 10 steady, 10 safe (high rank)
        rank_bands = ([20] * 10) + ([100] * 10) + ([5000] * 10)
        for i, group_rank in enumerate(rank_bands):
            cid = f"ART{i:03d}"
            conn.execute(
                """INSERT INTO colleges (id, name, province, city, type, level, is_public, tags,
                   dorm_score, city_vitality, cost_index, employment_rate, avg_salary, region, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, strftime('%s','now'), strftime('%s','now'))""",
                (cid, f"艺校{i}", "广东", "广州", "艺术", "普通", 1, None, 6.0, 6.0, 5.0, 0.85, 12000, "华南"),
            )
            conn.execute(
                """INSERT INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code, rank_source, art_category)
                   VALUES (?, 'GEN', '广东', ?, '艺体类本科批', ?, 300, 5, '艺体类', 'g201', 'official', '美术与设计')""",
                (cid, now, group_rank),
            )
            conn.execute(
                """INSERT INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code, rank_source, art_category)
                   VALUES (?, 'A001', '广东', ?, '艺体类本科批', ?, 300, 5, '艺体类', 'g201', 'official', '美术与设计')""",
                (cid, now, 0),
            )
        conn.commit()

        ids = [
            r["college_id"]
            for r in conn.execute(
                "SELECT DISTINCT college_id FROM admission_ranks WHERE province=? AND exam_category=?",
                ("广东", "艺体类"),
            ).fetchall()
        ]
        conn.close()
        colleges_map = {cid: {"id": cid, "name": cid, "province": "广东", "city": "广州"} for cid in ids}

        result = generate_group_recommendations(
            colleges_map,
            province="广东",
            exam_category="艺体类",
            user_profile={"rank": 100, "exam_category": "艺体类"},
            top_n=9999,
            batch="艺体类本科批",
            art_category="美术与设计",
        )
        assert result["data_status"] == "ok"
        total = sum(len(v) for v in result["tiers"].values())
        assert total == 20  # 6 冲 / 8 稳 / 6 保
        assert len(result["tiers"]["reach"]) == 6
        assert len(result["tiers"]["steady"]) == 8
        assert len(result["tiers"]["safe"]) == 6
        conn = get_connection()
        for cid in ids:
            conn.execute("DELETE FROM admission_ranks WHERE college_id=?", (cid,))
            conn.execute("DELETE FROM college_majors WHERE college_id=?", (cid,))
            conn.execute("DELETE FROM college_major_name WHERE college_id=?", (cid,))
            conn.execute("DELETE FROM colleges WHERE id=?", (cid,))
        conn.commit()
        conn.close()

    def test_art_category_column_filters_groups(self, custom_db: None) -> None:
        """同校同组号跨类别共存时，按 art_category 列精确过滤互不干扰。"""
        from deeptutor.services.custom.db import get_connection
        from deeptutor.services.custom.volunteer_scorer import generate_group_recommendations

        conn = get_connection()
        now = 2026
        conn.execute(
            """INSERT INTO colleges (id, name, province, city, type, level, is_public, tags,
               dorm_score, city_vitality, cost_index, employment_rate, avg_salary, region, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, strftime('%s','now'), strftime('%s','now'))""",
            ("ART_MIX", "混类别艺校", "广东", "广州", "艺术", "普通", 1, None, 6.0, 6.0, 5.0, 0.85, 12000, "华南"),
        )
        # 同一组号 g201 在音乐/美术两个类别都有投档
        for cat, rank in (("音乐", 50), ("美术与设计", 1500)):
            conn.execute(
                """INSERT INTO admission_ranks
                   (college_id, major_id, province, year, batch, min_rank, min_score, enrollment_count, exam_category, group_code, rank_source, art_category)
                   VALUES (?, 'GEN', '广东', ?, '艺体类本科批', ?, 300, 5, '艺体类', 'g201', 'official', ?)""",
                ("ART_MIX", now, rank, cat),
            )
        conn.commit()

        ids = [r["college_id"] for r in conn.execute("SELECT DISTINCT college_id FROM admission_ranks WHERE province=? AND exam_category=?", ("广东", "艺体类")).fetchall()]
        conn.close()
        colleges_map = {cid: {"id": cid, "name": cid, "province": "广东", "city": "广州"} for cid in ids}

        # 美术与设计 rank=800：用户位次优于组位次 → 该类别下应为 safe（prob 高）
        res_art = generate_group_recommendations(
            colleges_map, province="广东", exam_category="艺体类",
            user_profile={"rank": 800, "exam_category": "艺体类"}, top_n=100,
            batch="艺体类本科批", art_category="美术与设计",
        )
        assert res_art["data_status"] == "ok"
        assert res_art["total"] == 1
        safe = res_art["tiers"]["safe"]
        assert len(safe) == 1
        assert safe[0]["college"]["id"] == "ART_MIX"
        assert safe[0]["group_prob"] > 0.5

        # 音乐 rank=200：用户位次低于组位次 → 应为 reach
        res_music = generate_group_recommendations(
            colleges_map, province="广东", exam_category="艺体类",
            user_profile={"rank": 200, "exam_category": "艺体类"}, top_n=100,
            batch="艺体类本科批", art_category="音乐",
        )
        assert res_music["data_status"] == "ok"
        assert res_music["total"] == 1
        assert len(res_music["tiers"]["reach"]) == 1

        conn = get_connection()
        conn.execute("DELETE FROM admission_ranks WHERE college_id='ART_MIX'")
        conn.execute("DELETE FROM colleges WHERE id='ART_MIX'")
        conn.commit()
        conn.close()
