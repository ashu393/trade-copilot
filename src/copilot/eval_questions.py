"""Load the Part A evaluation questions from the dataset."""

from __future__ import annotations

import re
from pathlib import Path

from .config import DATA_DIR

_Q_RE = re.compile(r"^\s*\d+\.\s+(.*\S)\s*$")


def load_eval_questions(path: Path | None = None) -> list[str]:
    path = path or (DATA_DIR / "eval_questions_partA.md")
    questions: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _Q_RE.match(line)
        if m:
            # Strip emphasis markers like *approved*.
            questions.append(m.group(1).replace("*", ""))
    return questions
