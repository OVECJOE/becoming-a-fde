import numpy as np
from pydantic.json_schema import math

from schemas import EmoticonCategory, EmoticonProfile

CATEGORY_ORDER = [cat.value for cat in EmoticonCategory]


def multi_hot(categories: tuple[EmoticonCategory, ...]) -> np.ndarray:
    vec = np.zeros(len(EmoticonCategory))
    for cat in categories:
        pos = CATEGORY_ORDER.index(cat.value)
        vec[pos] = 1.0
    return vec


def build_vector(profile: EmoticonProfile) -> np.ndarray:
    categories_vec = multi_hot(profile.categories)
    vec_dimension = math.ceil(categories_vec.shape[0] / 2)
    valence_vec = np.full(vec_dimension, profile.valence)
    intensity_vec = np.full(vec_dimension, profile.intensity)
    return np.concatenate([categories_vec, valence_vec, intensity_vec])


def build_catalog_vectors(catalog: list[EmoticonProfile]) -> dict[str, np.ndarray]:
    return {profile.symbol: build_vector(profile) for profile in catalog}


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def find_nearest(
    symbol: str, vectors: dict[str, np.ndarray], top_n: int = 3
) -> list[tuple[str, float]]:
    profile_vector = vectors[symbol]
    cosine_sim_results: list[tuple[str, float]] = []

    for sym, vector in vectors.items():
        if symbol == sym:
            continue
        cosine_sim = cosine_similarity(profile_vector, vector)
        cosine_sim_results.append((sym, cosine_sim))

    cosine_sim_results.sort(key=lambda r: r[1], reverse=True)
    return cosine_sim_results[:top_n]


def main():
    from catalog import EMOTICONS_CATALOG
    vectors = build_catalog_vectors(EMOTICONS_CATALOG)

    for symbol in [':)', ':(', 'XD', '-_-', ';)', '<3', 'o_O']:
        nearest = find_nearest(symbol, vectors, top_n=3)
        nearest_str = ', '.join(f'{s} ({score:.2f})' for s, score in nearest)
        print(f'{symbol:5} -> {nearest_str}')


if __name__ == "__main__":
    main()
