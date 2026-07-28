from __future__ import annotations

from typing import Any

from deeptutor.services.custom.student_profile import StudentProfile, get_affected_major_ids


def validate_all(
    profile: StudentProfile,
    college: dict[str, Any],
    major: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    violations.extend(_check_medical(profile, major))
    violations.extend(_check_subject(profile, major))
    if profile.gender:
        violations.extend(_check_gender(profile, college, major))
    violations.extend(_check_score(profile, college, major))
    return violations


def _check_medical(profile: StudentProfile, major: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not profile.medical_restrictions or not major:
        return []
    major_id = major.get("id") or major.get("major_id")
    if not major_id:
        return []
    affected = get_affected_major_ids(profile.medical_restrictions)
    if major_id in affected:
        from deeptutor.services.custom.student_profile import MEDICAL_RESTRICTION_MAP
        details = [f"{code}({MEDICAL_RESTRICTION_MAP.get(code, '')})" for code in profile.medical_restrictions]
        return [{
            "type": "medical",
            "major_id": major_id,
            "message": f"体检受限({'; '.join(details)})，不建议报考该专业",
            "severity": "error",
        }]
    return []


def _check_subject(profile: StudentProfile, major: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not major:
        return []
    required = major.get("subject_group") or major.get("subject_requirement", "")
    if not required:
        return []
    if required == profile.exam_category:
        return []
    if profile.exam_category not in required:
        return [{
            "type": "subject",
            "major_id": major.get("id") or major.get("major_id", ""),
            "message": f"选科不匹配：要求{required}，考生选考{profile.exam_category}",
            "severity": "error",
        }]
    return []


def _check_gender(profile: StudentProfile, college: dict[str, Any], major: dict[str, Any] | None) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    restriction = college.get("gender_restriction", "")
    if restriction == "male_only" and profile.gender == "女":
        violations.append({
            "type": "gender",
            "college_id": college.get("id", ""),
            "message": "院校仅招男生",
            "severity": "error",
        })
    elif restriction == "female_only" and profile.gender == "男":
        violations.append({
            "type": "gender",
            "college_id": college.get("id", ""),
            "message": "院校仅招女生",
            "severity": "error",
        })
    if major:
        major_restriction = major.get("gender_restriction", "")
        if major_restriction == "male_only" and profile.gender == "女":
            violations.append({
                "type": "gender",
                "major_id": major.get("id") or major.get("major_id", ""),
                "message": "该专业仅招男生",
                "severity": "error",
            })
        elif major_restriction == "female_only" and profile.gender == "男":
            violations.append({
                "type": "gender",
                "major_id": major.get("id") or major.get("major_id", ""),
                "message": "该专业仅招女生",
                "severity": "error",
            })
    return violations


def _check_score(profile: StudentProfile, college: dict[str, Any], major: dict[str, Any] | None) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    min_score = college.get("min_admission_score")
    if min_score is not None and profile.score is not None:
        if profile.score < int(min_score):
            violations.append({
                "type": "score",
                "college_id": college.get("id", ""),
                "message": f"分数{profile.score}低于该校最低录取分{int(min_score)}",
                "severity": "warning",
            })
    if major:
        major_min_score = major.get("min_score")
        if major_min_score is not None and profile.score is not None:
            if profile.score < int(major_min_score):
                violations.append({
                    "type": "score",
                    "major_id": major.get("id") or major.get("major_id", ""),
                    "message": f"分数{profile.score}低于该专业最低录取分{int(major_min_score)}",
                    "severity": "warning",
                })
    return violations
