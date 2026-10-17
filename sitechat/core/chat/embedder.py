import aiosqlite
import openai
from chromadb import Collection
from dotenv import load_dotenv

from core.config import settings
from core.db.repository import insert_page_chunk
from schemas import Page

load_dotenv()
embedding_client = openai.AsyncOpenAI(
    timeout=settings.openai_timeout_seconds,
    max_retries=settings.openai_max_retries,
)


async def embed_text(text: str) -> list[float]:
    response = await embedding_client.embeddings.create(
        model="text-embedding-3-small", input=text
    )
    return response.data[0].embedding


async def embed_and_store_chunk(
    db: aiosqlite.Connection,
    collection: Collection,
    page: Page,
    chunk_index: int,
    text: str,
) -> None:
    chunk_id = await insert_page_chunk(db, page.id, chunk_index, text)
    vector = await embed_text(text)
    collection.add(
        ids=[str(chunk_id)],
        embeddings=[vector],
        documents=[text],
        metadatas=[
            {
                "page_id": page.id,
                "chunk_index": chunk_index,
                "page_url": page.url.encoded_string(),
            }
        ],
    )


async def retrieve_relevant_chunks(
    collection: Collection, query: str, n_results: int = 10
) -> list[dict]:
    query_vec = await embed_text(query)
    results = collection.query(query_embeddings=[query_vec], n_results=n_results)
    assert (
        results["documents"]
        and results["metadatas"]
        and results["distances"]
        and results["ids"]
    )
    return [
        {
            "chunk_id": chunk_id,
            "text": doc,
            "page_id": meta["page_id"],
            "page_url": meta["page_url"],
            "distance": distance,
        }
        for chunk_id, doc, meta, distance in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]
