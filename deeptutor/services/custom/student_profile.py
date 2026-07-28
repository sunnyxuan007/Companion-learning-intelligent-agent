from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StudentProfile:
    province: str
    year: int
    exam_category: str
    elective_subjects: list[str] = field(default_factory=list)
    score: int | None = None
    rank: int | None = None
    bonus_points: int = 0
    special_qualifications: list[str] = field(default_factory=list)
    medical_restrictions: list[str] = field(default_factory=list)
    gender: str | None = None
    preferences: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "province": self.province,
            "year": self.year,
            "exam_category": self.exam_category,
            "elective_subjects": self.elective_subjects,
            "bonus_points": self.bonus_points,
            "special_qualifications": self.special_qualifications,
            "medical_restrictions": self.medical_restrictions,
        }
        if self.score is not None:
            d["score"] = self.score
        if self.rank is not None:
            d["rank"] = self.rank
        if self.gender is not None:
            d["gender"] = self.gender
        if self.preferences is not None:
            d["preferences"] = self.preferences
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StudentProfile:
        return cls(
            province=str(data.get("province", "")),
            year=int(data.get("year", 2026)),
            exam_category=str(data.get("exam_category", "")),
            elective_subjects=list(data.get("elective_subjects", [])),
            score=int(data["score"]) if data.get("score") is not None else None,
            rank=int(data["rank"]) if data.get("rank") is not None else None,
            bonus_points=int(data.get("bonus_points", 0)),
            special_qualifications=list(data.get("special_qualifications", [])),
            medical_restrictions=list(data.get("medical_restrictions", [])),
            gender=str(data["gender"]) if data.get("gender") else None,
            preferences=data.get("preferences"),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.province:
            errors.append("省份不能为空")
        if self.year < 2020 or self.year > 2030:
            errors.append("年份无效")
        if self.exam_category not in ("物理", "历史"):
            errors.append("首选科目必须是物理或历史")
        if self.score is None and self.rank is None:
            errors.append("分数和位次不能同时为空")
        if self.score is not None and self.score < 0:
            errors.append("分数不能为负数")
        if self.rank is not None and self.rank < 1:
            errors.append("位次不能小于1")
        return errors


MEDICAL_RESTRICTION_MAP: dict[str, str] = {
    "101": "轻度色觉异常（俗称色弱）",
    "102": "色觉异常II度（俗称色盲）",
    "103": "不能准确识别红、黄、绿、兰、紫各种颜色中任何一种颜色的导线、按键、信号灯、几何图形",
    "201": "裸眼视力任何一眼低于5.0",
    "202": "裸眼视力任何一眼低于4.8",
    "203": "矫正视力任何一眼低于4.8或矫正度数超过600度",
    "301": "听力障碍（两耳听力均在3米以内或一耳听力在5米另一耳全聋）",
    "302": "嗅觉迟钝、口吃、步态异常、驼背、面部疤痕、血管瘤、黑色素痣、白癜风",
    "401": "严重心脏病（先天性心脏病经手术治愈或房室间隔缺损分流量少除外）",
    "402": "重症支气管扩张、哮喘、恶性肿瘤、慢性肾炎、尿毒症",
    "403": "严重的血液、内分泌及代谢系统疾病、风湿性疾病",
    "404": "重症或难治性癫痫或其他神经系统疾病、严重精神病未治愈、精神活性物质滥用和依赖",
    "405": "慢性肝炎病人且肝功能不正常者（肝炎病原携带者但肝功能正常者除外）",
    "406": "结核病（除已治愈且稳定者外）",
    "501": "身高限制（男性低于160cm，女性低于150cm）",
    "502": "体重限制（过于肥胖或消瘦）",
}


RESTRICTION_AFFECTED_MAJORS: dict[str, list[str]] = {
    "101": ["EN001", "EN002", "EN003", "EN004", "EN007", "EN008", "EN009", "SC002", "SC003", "MD001", "MD002", "MD003", "MD004", "AR001", "AR002"],
    "102": ["EN001", "EN002", "EN003", "EN004", "EN007", "EN008", "EN009", "SC002", "SC003", "MD001", "MD002", "MD003", "MD004", "AR001", "AR002"],
    "103": ["EN001", "EN002", "EN003", "EN004", "EN007", "EN008", "EN009", "SC002", "SC003", "MD001", "MD002", "MD003", "MD004", "AR001", "AR002"],
    "201": ["SC002", "MD001", "MD002", "MD003", "MD004"],
    "202": ["SC002", "MD001", "MD002", "MD003", "MD004"],
    "203": ["EN001", "EN002", "EN004", "EN005", "SC002"],
    "301": ["BS005", "BS006", "BS007", "BS008", "BS009", "BS010"],
    "302": ["BS005", "BS006", "BS007", "BS008", "BS009", "BS010", "AR001", "AR002"],
    "401": [],
    "402": [],
    "403": [],
    "404": [],
    "405": [],
    "406": [],
    "501": ["MD001", "MD002", "MD003", "MD004"],
    "502": ["MD001", "MD002", "MD003", "MD004"],
}


def get_affected_major_ids(restriction_codes: list[str]) -> set[str]:
    affected: set[str] = set()
    for code in restriction_codes:
        majors = RESTRICTION_AFFECTED_MAJORS.get(code, [])
        affected.update(majors)
    return affected
