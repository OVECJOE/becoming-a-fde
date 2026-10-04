import aiosqlite
import openai
from chromadb import Collection
from dotenv import load_dotenv

from core.db.repository import insert_page_chunk

load_dotenv()
embedding_client = openai.AsyncOpenAI()


async def embed_text(text: str) -> list[float]:
    response = await embedding_client.embeddings.create(
        model="text-embedding-3-small", input=text
    )
    return response.data[0].embedding


async def embed_and_store_chunk(
    db: aiosqlite.Connection,
    collection: Collection,
    page_id: int,
    chunk_index: int,
    text: str,
) -> None:
    chunk_id = await insert_page_chunk(db, page_id, chunk_index, text)
    vector = await embed_text(text)
    collection.add(
        ids=[str(chunk_id)],
        embeddings=[vector],
        documents=[text],
        metadatas=[{"page_id": page_id, "chunk_index": chunk_index}],
    )


async def retrieve_relevant_chunks(
    collection: Collection, query: str, n_results: int = 5
) -> list[dict]:
    query_vec = await embed_text(query)
    results = collection.query(query_embeddings=[query_vec], n_results=n_results)
    assert results["documents"] and results["metadatas"]
    return [
        {"text": doc, "page_id": meta["page_id"]}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]
