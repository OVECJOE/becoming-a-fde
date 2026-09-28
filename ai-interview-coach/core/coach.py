import asyncio

from instructor import AsyncInstructor

from core.prompts import (
    ANSWER_EVALUATION_SYSTEM_PROMPT,
    ANSWER_EVALUATION_USER_TEMPLATE,
    EVALUATION_REFLECTION_SYSTEM_PROMPT,
    EVALUATION_REFLECTION_USER_TEMPLATE,
    QUESTION_GENERATION_SYSTEM_PROMPT,
    QUESTION_GENERATION_USER_TEMPLATE,
)
from core.schemas import (
    AnswerEvaluation,
    HireRecommendation,
    InterviewReport,
    QuestionSet,
)


async def generate_questions(
    client: AsyncInstructor, job_description: str, resume: str, num_questions: int = 5
) -> QuestionSet:
    system_prompt = QUESTION_GENERATION_SYSTEM_PROMPT.format(
        num_questions=num_questions
    )
    user_prompt = QUESTION_GENERATION_USER_TEMPLATE.format(
        job_description=job_description, resume=resume
    )

    return await client.create(
        response_model=QuestionSet,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        model="gpt-5-nano-2025-08-07",
        max_completion_tokens=4000,
        reasoning_effort="minimal"
    )


async def evaluate_answer(
    client: AsyncInstructor, question: str, rationale: str, answer: str
) -> AnswerEvaluation:
    draft = await client.create(
        response_model=AnswerEvaluation,
        messages=[
            {"role": "system", "content": ANSWER_EVALUATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ANSWER_EVALUATION_USER_TEMPLATE.format(
                    question=question, rationale=rationale, answer=answer
                ),
            },
        ],
        model="gpt-5-mini-2025-08-07",
        max_completion_tokens=4000,
        reasoning_effort="minimal"
    )

    final = await client.create(
        response_model=AnswerEvaluation,
        messages=[
            {"role": "system", "content": EVALUATION_REFLECTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": EVALUATION_REFLECTION_USER_TEMPLATE.format(
                    question=question, draft_evaluation_json=draft.model_dump_json()
                ),
            },
        ],
        model="gpt-5-mini-2025-08-07",
        max_completion_tokens=4000,
        reasoning_effort="minimal"
    )

    return final


async def run_interview(
    client: AsyncInstructor, questions: QuestionSet, answers: dict[int, str]
) -> InterviewReport:
    evaluations = await asyncio.gather(
        *[
            evaluate_answer(
                client, question.question, question.rationale, answers[q_no]
            )
            for q_no, question in enumerate(questions.questions)
        ]
    )

    overall_score = sum([evaluation.score for evaluation in evaluations]) / len(
        evaluations
    )

    if overall_score >= 8.5:
        recommendation = HireRecommendation.STRONG_YES
    elif overall_score >= 6.5:
        recommendation = HireRecommendation.YES
    elif overall_score >= 4.5:
        recommendation = HireRecommendation.BORDERLINE
    else:
        recommendation = HireRecommendation.NO

    any_red_flags = any(e.red_flag for e in evaluations)
    summary = (
        f"Candidate for role: {questions.role_summary}. "
        f"Average score {overall_score:.1f}/10 across {len(evaluations)} questions."
    )
    if any_red_flags:
        summary += " NOTE: one or more answers contained a prompt injection attempt, flagged and scored on technical merit only."

    return InterviewReport(
        overall_score=overall_score,
        hire_recommendation=recommendation,
        per_question=evaluations,
        summary=summary,
    )
