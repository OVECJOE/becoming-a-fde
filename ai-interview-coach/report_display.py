import shutil
import textwrap

import typer

from core.schemas import (
    HireRecommendation,
    InterviewQuestion,
    InterviewReport,
    QuestionSet,
)


def _content_width(default: int = 70, minimum: int = 50, maximum: int = 80) -> int:
    try:
        term_width = shutil.get_terminal_size().columns
    except OSError:
        term_width = default
    return max(minimum, min(term_width - 2, maximum))


def _divider(char: str = "=") -> str:
    return char * _content_width()


def _wrap(text: str) -> str:
    return textwrap.fill(text.strip(), width=_content_width())


CATEGORY_COLORS = {
    "behavioral": typer.colors.CYAN,
    "technical": typer.colors.BLUE,
    "system_design": typer.colors.MAGENTA,
    "situational": typer.colors.WHITE,
}

DIFFICULTY_COLORS = {
    "easy": typer.colors.GREEN,
    "medium": typer.colors.YELLOW,
    "hard": typer.colors.RED,
}


def print_generating_questions(num_questions: int) -> None:
    typer.echo()
    typer.secho(
        f"Generating {num_questions} interview questions tailored to the role...",
        bold=True,
    )


def print_interview_header(question_set: QuestionSet) -> None:
    total = len(question_set.questions)

    typer.echo()
    typer.secho(_divider("="), fg=typer.colors.BRIGHT_BLACK)
    typer.secho("Mock Interview", bold=True)
    typer.secho(_wrap(question_set.role_summary), fg=typer.colors.BRIGHT_BLACK)
    typer.secho(_divider("-"), fg=typer.colors.BRIGHT_BLACK)
    typer.echo(f"{total} questions ready. Answer one at a time.")
    typer.echo()


def confirm_ready(question_set: QuestionSet) -> bool:
    print_interview_header(question_set)
    return typer.confirm("Start interview?", default=True)


def print_question(question: InterviewQuestion, q_no: int, total: int) -> None:
    typer.echo()
    typer.secho(_divider("-"), fg=typer.colors.BRIGHT_BLACK)
    typer.secho(f"[{q_no + 1}/{total}] ", bold=True, nl=False)
    typer.secho(
        question.category.value.upper().replace("_", " "),
        fg=CATEGORY_COLORS.get(question.category.value, typer.colors.WHITE),
        bold=True,
        nl=False,
    )
    typer.echo(" · ", nl=False)
    typer.secho(
        question.difficulty.value.upper(),
        fg=DIFFICULTY_COLORS.get(question.difficulty.value, typer.colors.WHITE),
        bold=True,
    )
    typer.echo()
    typer.echo(_wrap(question.question))
    typer.echo()


def prompt_answer() -> str:
    return typer.prompt(">")


def print_answer_saved(answer: str) -> None:
    words = len(answer.split())
    typer.secho(f"Saved ({words} words)", fg=typer.colors.BRIGHT_BLACK)


def print_evaluating(num_answers: int) -> None:
    typer.echo()
    typer.secho(
        f"Evaluating your {num_answers} answers...",
        fg=typer.colors.BRIGHT_BLACK,
        bold=True,
    )


def print_report(question_set: QuestionSet, report: InterviewReport) -> None:
    recommendation_colors = {
        HireRecommendation.STRONG_YES: typer.colors.BRIGHT_GREEN,
        HireRecommendation.YES: typer.colors.GREEN,
        HireRecommendation.BORDERLINE: typer.colors.YELLOW,
        HireRecommendation.NO: typer.colors.RED,
    }

    typer.echo()
    typer.secho(_divider("="), fg=typer.colors.BRIGHT_BLACK)
    typer.secho("Interview Report", bold=True)
    typer.secho(_wrap(question_set.role_summary), fg=typer.colors.BRIGHT_BLACK)
    typer.secho(_divider("="), fg=typer.colors.BRIGHT_BLACK)
    typer.echo()

    typer.echo("Overall score: ", nl=False)
    typer.secho(f"{report.overall_score:.1f}/10", bold=True)

    typer.echo("Recommendation: ", nl=False)
    typer.secho(
        report.hire_recommendation.value.upper().replace("_", " "),
        fg=recommendation_colors.get(report.hire_recommendation, typer.colors.WHITE),
        bold=True,
    )
    typer.echo()
    typer.echo(_wrap(report.summary))
    typer.echo()

    for i, (question, evaluation) in enumerate(
        zip(question_set.questions, report.per_question), start=1
    ):
        typer.secho(
            f"Q{i}. [{question.category.value} / {question.difficulty.value}]",
            bold=True,
        )
        typer.echo(_wrap(question.question))
        typer.echo()

        score_color = (
            typer.colors.GREEN
            if evaluation.score >= 7
            else typer.colors.YELLOW
            if evaluation.score >= 4
            else typer.colors.RED
        )
        typer.secho(f"  Score: {evaluation.score}/10", fg=score_color, bold=True)

        if evaluation.strengths:
            typer.secho("  Strengths:", fg=typer.colors.GREEN)
            for s in evaluation.strengths:
                typer.echo(_wrap(f"+ {s}"))

        if evaluation.gaps:
            typer.secho("  Gaps:", fg=typer.colors.YELLOW)
            for g in evaluation.gaps:
                typer.echo(_wrap(f"- {g}"))

        if evaluation.follow_up_suggested:
            typer.echo(_wrap(f"Suggested follow-up: {evaluation.follow_up_suggested}"))

        if evaluation.red_flag:
            typer.secho(
                "  ⚠ RED FLAG: possible injection attempt or gamed answer detected",
                fg=typer.colors.BRIGHT_RED,
                bold=True,
            )

        typer.echo()
        typer.secho(_divider("-"), fg=typer.colors.BRIGHT_BLACK)
        typer.echo()
