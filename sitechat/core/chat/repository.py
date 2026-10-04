from collections.abc import AsyncGenerator, Sequence

import openai
from chromadb import Collection
from dotenv import load_dotenv

from core.chat.embedder import retrieve_relevant_chunks
from core.chat.prompts import CHAT_SYSTEM_PROMPT

load_dotenv()
chat_client = openai.AsyncOpenAI()


def _build_question(
    question: str,
    summary: str | None,
    recent: Sequence[tuple[str, str]],
) -> str:
    parts = []
    if summary:
        parts.append(f"<history>\n{summary}\n</history>")
    for user_msg, ai_msg in recent:
        parts.append(f"Earlier user: {user_msg}\nEarlier assistant: {ai_msg}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


async def chat(
    collection: Collection,
    question: str,
    summary: str | None = None,
    recent: Sequence[tuple[str, str]] = (),
) -> AsyncGenerator[str, None]:
    chunks = await retrieve_relevant_chunks(collection, question)
    if not chunks:
        yield "I couldn't find anything relevant on this site to answer that."
        return

    context = "\n\n".join(c["text"] for c in chunks)
    try:
        stream = await chat_client.chat.completions.create(
            model="gpt-5-mini-2025-08-07",
            max_completion_tokens=1000,
            reasoning_effort="low",
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"<context>\n{context}\n</context>\n\n{_build_question(question, summary, recent)}",
                },
            ],
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except openai.APIError as e:
        yield f"Failed to reach the LLM provider: {e!s}"
