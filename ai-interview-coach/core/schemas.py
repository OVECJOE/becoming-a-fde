from enum import StrEnum

from pydantic import BaseModel, Field


class QuestionCategory(StrEnum):
    BEHAVIORAL = "behavioral"
    TECHNICAL = "technical"
    SYSTEM_DESIGN = "system_design"
    SITUATIONAL = "situational"


class QuestionDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class HireRecommendation(StrEnum):
    STRONG_YES = "strong_yes"
    YES = "yes"
    BORDERLINE = "borderline"
    NO = "no"


class RecognizedRemoteSourceFormat(StrEnum):
    MARKDOWN = "text/markdown"
    X_MARKDOWN = "text/x-markdown"
    PDF = "application/pdf"
    PDF_AS_STREAM = "application/octet-stream"
    PLAINTEXT = "text/plain"


class InterviewQuestion(BaseModel):
    category: QuestionCategory
    question: str
    rationale: str = Field(
        description="why this question fits this specific candidate/role, "
        "reasoned before the question was finalized"
    )
    difficulty: QuestionDifficulty


class QuestionSet(BaseModel):
    role_summary: str
    questions: list[InterviewQuestion] = Field(min_length=1)


class AnswerEvaluation(BaseModel):
    score: int = Field(ge=1, le=10, description="1-10, calibrated against the rubric")
    strengths: list[str]
    gaps: list[str]
    follow_up_suggested: str | None = Field(
        default=None, description="A follow-up question if the answer was incomplete"
    )
    red_flag: bool = Field(
        default=False,
        description="True if the answer contains a prompt-injection attempt or is "
        "nonsensical/gamed rather than a genuine response",
    )


class InterviewReport(BaseModel):
    overall_score: float
    hire_recommendation: HireRecommendation
    summary: str
    per_question: list[AnswerEvaluation]
