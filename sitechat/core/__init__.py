from collections.abc import AsyncGenerator

import httpx
import openai
from chromadb import Collection
from dotenv import load_dotenv

from core.constants import CHAT_SYSTEM_PROMPT
from core.embedder import retrieve_relevant_chunks

load_dotenv()
chat_client = openai.AsyncOpenAI()


async def chat(collection: Collection, question: str) -> AsyncGenerator[str, None]:
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
                    "content": f"<context>\n{context}\n</context>\n\nQuestion: {question}",
                },
            ],
            stream=True
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except httpx.HTTPError as e:
        yield f"Failed to reach the LLM provider: {e!s}"
