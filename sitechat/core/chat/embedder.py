import asyncio

import aiosqlite
import openai
from chromadb import Collection
from dotenv import load_dotenv

from core.config import settings

load_dotenv()
embedding_client = openai.AsyncOpenAI(
    timeout=settings.openai_timeout_seconds,
    max_retries=settings.openai_max_retries,
)
EMBEDDING_MODEL = "text-embedding-3-small"
EMBED_BATCH_SIZE = 64


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        response = await embedding_client.embeddings.create(
            model=EMBEDDING_MODEL, input=batch
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors.extend(item.embedding for item in ordered)
    return vectors


async def add_page_chunks(
    collection: Collection,
    page_id: int,
    page_url: str,
    site_id: int,
    site_domain: str,
    chunk_ids: list[int],
    texts: list[str],
) -> None:
    embeddings = await embed_texts(texts)
    collection.add(
        ids=[str(chunk_id) for chunk_id in chunk_ids],
        embeddings=embeddings,
        documents=texts,
        metadatas=[
            {
                "page_id": page_id,
                "chunk_index": index,
                "page_url": page_url,
                "site_id": site_id,
                "site": site_domain,
            }
            for index in range(len(texts))
        ],
    )


async def retrieve_relevant_chunks(
    collection: Collection,
    query: str,
    n_results: int = 10,
    site_id: int | None = None,
) -> list[dict]:
    vectors = await embed_texts([query])
    if not vectors:
        return []
    results = collection.query(
        query_embeddings=vectors,
        n_results=n_results,
        where={"site_id": {"$eq": site_id}} if site_id is not None else None,
    )
    documents = results["documents"][0] if results["documents"] else []
    metadatas = results["metadatas"][0] if results["metadatas"] else []
    distances = results["distances"][0] if results["distances"] else []
    ids = results["ids"][0] if results["ids"] else []
    return [
        {
            "chunk_id": chunk_id,
            "text": doc,
            "page_id": meta["page_id"],
            "page_url": meta["page_url"],
            "site": meta.get("site"),
            "distance": distance,
        }
        for chunk_id, doc, meta, distance in zip(ids, documents, metadatas, distances)
    ]


async def backfill_chunk_sites(db: aiosqlite.Connection, collection: Collection) -> int:
    snapshot = collection.get(include=["metadatas"])
    missing = [
        (chunk_id, meta)
        for chunk_id, meta in zip(snapshot["ids"], snapshot["metadatas"])
        if meta and "site_id" not in meta
    ]
    if not missing:
        return 0

    page_ids = {meta["page_id"] for _, meta in missing}
    placeholders = ",".join("?" * len(page_ids))
    async with db.execute(
        f"SELECT id, site_id FROM pages WHERE id IN ({placeholders})",
        tuple(page_ids),
    ) as cursor:
        site_by_page = {row[0]: row[1] for row in await cursor.fetchall()}

    async with db.execute("SELECT id, domain FROM sites") as cursor:
        domain_by_site = {row[0]: row[1] for row in await cursor.fetchall()}

    ids: list[str] = []
    metadatas: list[dict] = []
    for chunk_id, meta in missing:
        site_id = site_by_page.get(meta["page_id"])
        if site_id is None:
            continue
        ids.append(chunk_id)
        metadatas.append(
            {**meta, "site_id": site_id, "site": domain_by_site.get(site_id, "")}
        )
    if ids:
        collection.update(ids=ids, metadatas=metadatas)
    return len(ids)
