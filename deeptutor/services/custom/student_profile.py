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
    "103": "不能准确识别红、黄、绿、蓝、紫各种颜色中任何一种颜色的导线、按键、信号灯、几何图形",
    "104": "不能准确在显示器上识别红、黄、绿、蓝、紫各颜色中任何一种颜色的数码、字母",
    "201": "裸眼视力任何一眼低于5.0",
    "202": "裸眼视力任何一眼低于4.8",
    "203": "屈光不正（近视眼或远视眼）任何一眼矫正到4.8，镜片度数大于400度",
    "204": "任何一眼矫正到4.8，镜片度数大于800度",
    "205": "一眼失明，另一眼矫正到4.8，镜片度数大于400度",
    "301": "两耳听力均在3米以内，或一耳听力在5米，另一耳全聋",
    "302": "嗅觉迟钝、口吃、步态异常、驼背、面部疤痕、血管瘤、黑色素痣、白癜风",
    "306": "斜视、嗅觉迟钝、口吃",
    "401": "严重心脏病（先天性心脏病经手术治愈或房室间隔缺损分流量少等除外）、心肌病、高血压病",
    "402": "重症支气管扩张、哮喘、恶性肿瘤、慢性肾炎、尿毒症",
    "403": "严重的血液、内分泌及代谢系统疾病、风湿性疾病",
    "404": "重症或难治性癫痫或其他神经系统疾病、严重精神病未治愈、精神活性物质滥用和依赖",
    "405": "慢性肝炎病人且肝功能不正常者（肝炎病原携带者但肝功能正常者除外）",
    "406": "结核病（除已治愈且稳定者外）",
}


_ALL_EN = [f"EN{i:03d}" for i in range(1, 15)]
_ALL_MD = ["MD001", "MD002", "MD003", "MD004"]
_CS = ["EN001", "EN002", "EN003", "EN004"]
_COLOR_WEAK = ["SC003", "SC004", "MD001", "MD002", "MD003", "MD004", "SC006", "EN014", "BS009"]


RESTRICTION_AFFECTED_MAJORS: dict[str, list[str]] = {
    "101": _COLOR_WEAK,
    "102": _COLOR_WEAK + ["AR001"],
    "103": _COLOR_WEAK + ["AR001", "BS001", "BS002", "BS003", "BS004"],
    "104": _CS,
    "201": [],
    "202": [],
    "203": [],
    "204": ["EN009", "EN012", "EN013", "EN005", "EN014"] + _ALL_MD + ["SC006"],
    "205": _ALL_EN + _ALL_MD + ["BS005", "SC006", "SC004", "SC003"],
    "301": ["BS005", "BS007", "BS006", "BS009", "EN009"] + _ALL_MD,
    "302": ["BS009", "BS005", "BS006", "AR002"],
    "306": _ALL_MD,
    "401": [],
    "402": [],
    "403": [],
    "404": [],
    "405": [],
    "406": [],
}


def get_affected_major_ids(restriction_codes: list[str]) -> set[str]:
    affected: set[str] = set()
    for code in restriction_codes:
        majors = RESTRICTION_AFFECTED_MAJORS.get(code, [])
        affected.update(majors)
    return affected
