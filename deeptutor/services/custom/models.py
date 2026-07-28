from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class College:
    id: str
    name: str
    province: str
    city: str
    type: str | None = None
    level: str | None = None
    is_public: bool = True
    dorm_score: float = 0
    city_vitality: float = 0
    cost_index: float = 0
    employment_rate: float = 0
    avg_salary: float = 0
    scholarship_score: float = 0
    campus_area: float = 0
    library_volume: float = 0
    graduate_rate: float = 0
    masters_count: int = 0
    double_first_class_disciplines: list[str] = field(default_factory=list)
    ruanke_ranking: int = 0
    xiaoyouhui_ranking: int = 0
    admission_charter_url: str = ""
    transfer_policy: str = ""
    scholarship_info: str = ""
    city_tier: str = ""
    region: str = ""


@dataclass
class Major:
    id: str
    name: str
    category: str | None = None
    subject_group: str | None = None
    description: str | None = None
    career_paths: list[str] = field(default_factory=list)
    course_intro: str = ""
    graduate_directions: list[str] = field(default_factory=list)
    salary_range: str = ""
    discipline_evaluation: str = ""


@dataclass
class CollegeMajor:
    college_id: str
    major_id: str
    batch: str | None = None
    years: int = 4
    tuition: float = 0
    degree: str = "学士"
    min_ranks: dict[str, int] = field(default_factory=dict)


@dataclass
class StudyRecord:
    id: str
    user_id: str
    record_type: str
    subject: str
    title: str | None = None
    score: float | None = None
    total: float | None = None
    weak_points: list[str] = field(default_factory=list)
    strong_points: list[str] = field(default_factory=list)
    created_at: float = 0


VOLUNTEER_DEFAULT_WEIGHTS: dict[str, float] = {
    "academic_fit": 0.25,
    "admission_prob": 0.20,
    "dorm_quality": 0.10,
    "city_vitality": 0.10,
    "cost_efficiency": 0.10,
    "employment": 0.15,
    "career_alignment": 0.10,
}
