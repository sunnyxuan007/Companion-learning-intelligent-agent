"""Custom tool implementations for volunteer/career/study/advisor features."""

from deeptutor.core.tool_protocol import BaseTool
from deeptutor.tools.custom.advisor_tools import AdvisorSearchTool
from deeptutor.tools.custom.exam_tools import (
    GapAnalysisTool,
    StudyDashboardTool,
    UploadExamTool,
)
from deeptutor.tools.custom.volunteer_tools import (
    CollegeSearchTool,
    VolunteerRecommendTool,
    VolunteerScoreTool,
    VolunteerWeightsTool,
)

CUSTOM_TOOL_TYPES: tuple[type[BaseTool], ...] = (
    UploadExamTool,
    StudyDashboardTool,
    GapAnalysisTool,
    CollegeSearchTool,
    VolunteerScoreTool,
    VolunteerRecommendTool,
    AdvisorSearchTool,
    VolunteerWeightsTool,
)

CUSTOM_TOOL_NAMES: tuple[str, ...] = tuple(t().name for t in CUSTOM_TOOL_TYPES)

__all__ = [
    "CUSTOM_TOOL_NAMES",
    "CUSTOM_TOOL_TYPES",
    "UploadExamTool",
    "StudyDashboardTool",
    "GapAnalysisTool",
    "CollegeSearchTool",
    "VolunteerScoreTool",
    "VolunteerRecommendTool",
    "AdvisorSearchTool",
]
