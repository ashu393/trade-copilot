"""FastAPI service exposing the copilot.

    uvicorn copilot.api:app --reload
    POST /ask {"question": "..."}  ->  answer + sql + citations + trace

The agent is built once at startup (DB load, schema card, retriever, graph
compile) and reused across requests.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .agent import build_agent, run_agent

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    _state["agent"], _ = build_agent()
    yield
    _state.clear()


app = FastAPI(title="Trade Intelligence Copilot", version="0.1.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str
    max_retries: int = 1


class AskResponse(BaseModel):
    question: str
    status: str | None
    route: str | None
    answer: str | None
    sql: str | None = None
    citations: list[str] = []
    trace: list[str] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    result = run_agent(req.question, _state["agent"], max_retries=req.max_retries)
    return AskResponse(**{k: result.get(k) for k in AskResponse.model_fields})
