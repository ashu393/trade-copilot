"""KB retriever: TF-IDF + cosine similarity over the KB chunks.

Why TF-IDF rather than dense embeddings? The KB is 7 short, curated policy docs
with precise domain vocabulary ("director sign-off", "Display Incentive",
"approved_amount"). Lexical TF-IDF gives exact, deterministic grounding with zero
model download and no API dependency — the right tool at this scale. The
`Embedder` seam keeps it swappable: drop in a dense/embedding backend unchanged
if the KB grows large enough to need semantic recall.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .loader import KBChunk, load_kb_chunks


@dataclass
class RetrievedChunk:
    chunk: KBChunk
    score: float


class KBRetriever:
    """In-memory TF-IDF retriever over the knowledge base."""

    def __init__(self, chunks: list[KBChunk] | None = None):
        self.chunks: list[KBChunk] = chunks if chunks is not None else load_kb_chunks()
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),   # unigrams + bigrams catch phrases like "director sign-off"
            stop_words="english",
        )
        corpus = [f"{c.doc_title}\n{c.text}" for c in self.chunks]
        self._matrix = self._vectorizer.fit_transform(corpus)

    def search(self, query: str, k: int = 3, min_score: float = 0.0) -> list[RetrievedChunk]:
        """Return the top-k chunks above min_score, most similar first."""
        q_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self._matrix)[0]
        ranked = sorted(enumerate(sims), key=lambda x: x[1], reverse=True)
        out: list[RetrievedChunk] = []
        for idx, score in ranked[:k]:
            if score <= min_score:
                continue
            out.append(RetrievedChunk(chunk=self.chunks[idx], score=float(score)))
        return out
