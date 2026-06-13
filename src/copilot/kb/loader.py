"""Load and chunk the knowledge-base documents.

The KB is 7 short, curated markdown docs (KB-01..KB-07). They are split into
blank-line-separated blocks so retrieval can return a focused passage, while
each chunk keeps its source doc id and title for citation. Very short blocks are
merged with the previous one so a chunk is a meaningful unit, not a stray line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import KB_DIR

_DOC_ID_RE = re.compile(r"(KB-\d{2})")
_MIN_CHUNK_CHARS = 60


@dataclass
class KBChunk:
    doc_id: str          # e.g. "KB-01"
    doc_title: str       # e.g. "Metric & Term Glossary"
    chunk_id: str        # e.g. "KB-01#2"
    text: str

    @property
    def citation(self) -> str:
        return f"{self.doc_id} — {self.doc_title}"


def _parse_title(first_line: str, doc_id: str) -> str:
    # "# KB-01 — Metric & Term Glossary" -> "Metric & Term Glossary"
    title = first_line.lstrip("#").strip()
    title = title.replace(doc_id, "").lstrip(" —-").strip()
    return title or doc_id


def load_kb_chunks(kb_dir: Path = KB_DIR) -> list[KBChunk]:
    """Return all KB chunks across the 7 documents, in file order."""
    chunks: list[KBChunk] = []
    for path in sorted(kb_dir.glob("KB-*.md")):
        raw = path.read_text(encoding="utf-8").strip()
        m = _DOC_ID_RE.search(path.name) or _DOC_ID_RE.search(raw)
        doc_id = m.group(1) if m else path.stem
        lines = raw.splitlines()
        title = _parse_title(lines[0], doc_id) if lines else doc_id
        body = "\n".join(lines[1:]).strip()

        # Split on blank lines into blocks, then merge tiny fragments forward.
        blocks: list[str] = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
        merged: list[str] = []
        for b in blocks:
            if merged and len(b) < _MIN_CHUNK_CHARS:
                merged[-1] = merged[-1] + "\n" + b
            else:
                merged.append(b)

        for i, block in enumerate(merged):
            chunks.append(
                KBChunk(
                    doc_id=doc_id,
                    doc_title=title,
                    chunk_id=f"{doc_id}#{i}",
                    text=block,
                )
            )
    return chunks
