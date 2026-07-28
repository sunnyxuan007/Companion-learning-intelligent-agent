from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_dao():
    """Mock DAO functions at the tool module level."""
    with patch("deeptutor.tools.custom.exam_tools.upload_study_record") as m1:
        with patch("deeptutor.tools.custom.exam_tools.get_study_timeline") as m2:
            with patch("deeptutor.tools.custom.exam_tools.get_gap_analysis") as m3:
                with patch("deeptutor.services.custom.study_dao.get_subject_summary") as m3b:
                    with patch("deeptutor.tools.custom.volunteer_tools.get_user_weights") as m4:
                        with patch("deeptutor.tools.custom.volunteer_tools.search_colleges") as m4b:
                            with patch("deeptutor.tools.custom.volunteer_tools.get_college_detail") as m5:
                                with patch("deeptutor.tools.custom.volunteer_tools.generate_recommendations") as m6:
                                    with patch("deeptutor.tools.custom.volunteer_tools.score_college_major") as m7:
                                        with patch("deeptutor.tools.custom.advisor_tools.search_advisors") as m8:
                                            with patch("deeptutor.tools.custom.advisor_tools.get_advisor_stats") as m9:
                                                yield {
                                                    "upload": m1,
                                                    "timeline": m2,
                                                    "gap": m3,
                                                    "summary": m3b,
                                                    "weights": m4,
                                                    "search": m4b,
                                                    "detail": m5,
                                                    "recommend": m6,
                                                    "score": m7,
                                                    "adv_search": m8,
                                                    "adv_stats": m9,
                                                }
