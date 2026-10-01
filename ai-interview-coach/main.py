import asyncio
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
import instructor
import openai
import typer
from dotenv import load_dotenv

from core.coach import generate_questions, run_interview
from core.schemas import RecognizedRemoteSourceFormat
from exceptions import SourceUnreachableError, UnsupportedFormat
from report_display import (
    confirm_ready,
    print_answer_saved,
    print_evaluating,
    print_generating_questions,
    print_question,
    print_report,
    prompt_answer,
)

load_dotenv()

app = typer.Typer(
    name="AI Interview Coach",
    add_completion=True,
    add_help_option=True,
    rich_markup_mode="markdown",
)


def classify_source(source: str) -> Literal["file", "url", "text"]:
    parsed = urlparse(source)
    if parsed.scheme and parsed.netloc:
        return "url"
    elif Path(source).exists():
        return "file"
    typer.secho(
        message=f"The source ({source[:30]}) provided is not recognized as a file or URL. Defaulting to text...",
        color=True,
        fg=typer.colors.YELLOW
    )
    return "text"


async def pull_from_url(source: str) -> str:
    async with httpx.AsyncClient() as client:
        try:
            # first determine resource format and see if it is supported
            response = await client.head(source, follow_redirects=True, timeout=10.0)
            mime = response.headers.get("Content-Type", "").split(";")[0].strip()
            supported_format = [member.value for member in RecognizedRemoteSourceFormat]
            if not supported_format.count(mime):
                raise UnsupportedFormat()

            # Make the actual request to pull the content
            if (
                mime == RecognizedRemoteSourceFormat.MARKDOWN
                or mime == RecognizedRemoteSourceFormat.X_MARKDOWN
                or mime == RecognizedRemoteSourceFormat.PLAINTEXT
            ):
                response = await client.get(source)
                response.raise_for_status()
                return response.text
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            raise SourceUnreachableError(f"Unable to reach URL: {source}") from e
        raise NotImplementedError()


async def fetch_content(source: str) -> str:
    format = classify_source(source)
    if format == "text":
        return source
    elif format == "url":
        return await pull_from_url(source)
    return await asyncio.to_thread(lambda: Path(source).read_text(encoding="utf-8"))


async def _run_interview(job_description: str, resume: str, num_questions: int):
    jd_text, resume_text = await asyncio.gather(
        fetch_content(job_description), fetch_content(resume)
    )

    client = instructor.from_openai(openai.AsyncOpenAI())
    print_generating_questions(num_questions)
    question_set = await generate_questions(client, jd_text, resume_text, num_questions)
    answers: dict[int, str] = {}

    if not confirm_ready(question_set):
        raise typer.Abort()

    # Display each question
    total = len(question_set.questions)
    for q_no, question in enumerate(question_set.questions):
        print_question(question, q_no, total)
        answer = prompt_answer()
        answers[q_no] = answer
        print_answer_saved(answer)

    print_evaluating(len(answers))
    report = await run_interview(client, question_set, answers)
    print_report(question_set, report)


@app.command(name="interview")
def interview(job_description: str, resume: str, num_questions: int = 5):
    """Start a mock interview"""
    asyncio.run(_run_interview(job_description, resume, num_questions))


if __name__ == "__main__":
    app()
