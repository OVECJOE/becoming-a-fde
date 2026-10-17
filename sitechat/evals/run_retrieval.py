import asyncio
import json
from pathlib import Path

import chromadb
from yarl import URL

from core.chat import retrieve_relevant_chunks
from core.config import settings

QUESTIONS_FILE = Path(__file__).parent / "questions.jsonl"
K = 30


def normalize_url(url: str) -> str:
    parsed = URL(url)
    url_obj = parsed.with_fragment(None)

    path = url_obj.path.rstrip("/")
    url_obj = url_obj.with_path(path or "/")

    url_obj = url_obj.with_query(sorted(url_obj.query.items()))
    url_obj = url_obj.with_port(None)
    return str(url_obj)


def load_questions() -> list[dict]:
    questions = []
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    return questions


def first_hit_rank(retrieved_urls: list[str], gold_urls: list[str]) -> int | None:
    for idx, url in enumerate(retrieved_urls, 1):
        if url in gold_urls:
            return idx


def hit_at(ranks: list[int | None], k: int) -> float:
    at_k = 0
    for rank in ranks:
        if rank is None:
            continue
        if rank <= k:
            at_k += 1
    return at_k / len(ranks)


def mrr(ranks: list[int | None]) -> float:
    final = 0
    for rank in ranks:
        if rank is None:
            continue
        final += 1/rank
    return final / len(ranks)


async def main():
    client = chromadb.PersistentClient(path=settings.chroma_path)
    collection = client.get_collection("sitechat_chunks")
    print("chunks in index:", collection.count())

    questions = [q for q in load_questions() if q["gold_urls"]]
    ranks: list[int | None] = []

    for q in questions:
        print(f"For the question '{q['question']}':")
        chunks = await retrieve_relevant_chunks(collection, q["question"], K)
        page_urls = [normalize_url(chunk["page_url"]) for chunk in chunks]
        print(f"\tHere are the page URLs for the chunks returned: {', '.join(page_urls)}")
        gold = [normalize_url(u) for u in q["gold_urls"]]
        print(f"\tAnd here are the gold URLs: {', '.join(gold)}")
        hit = first_hit_rank(page_urls, gold)
        print(f"\n\tWas there a hit? {'yes (' + str(hit) + ')' if hit else 'no'}", end="\n\n\n")
        ranks.append(hit)

    print(f"hit@1  {hit_at(ranks, 1):.2f}")
    print(f"hit@3  {hit_at(ranks, 3):.2f}")
    print(f"hit@10 {hit_at(ranks, 10):.2f}")
    print(f"MRR    {mrr(ranks):.2f}")


if __name__ == "__main__":
    asyncio.run(main())
