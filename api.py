#!/usr/bin/env python3
"""
KRS invoice chatbot backend API (no UI).

Run:
  .venv\\Scripts\\uvicorn api:app --host 0.0.0.0 --port 8000

Docs:
  http://HOST:8000/docs
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db import invoices_frame, items_frame
from pipeline import run_pipeline

Intent = Literal["view_data", "modify_data", "document_question", "hybrid", "greeting"]

app = FastAPI(
    title="KRS Invoice Chat API",
    description="Invoice chatbot pipeline (SQLite + Qdrant + OpenRouter LLM).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="متن پیام کاربر")
    include_debug: bool = Field(False, description="اگر true باشد sql/tool_output/context هم برمی‌گردد")


class ChatResponse(BaseModel):
    answer: str
    intent: Intent
    table_md: str | None = None
    data_changed: bool = False
    sql: str | None = None
    tool_output: str | None = None
    context: str | None = None


class HealthResponse(BaseModel):
    status: str
    service: str = "krs-invoice-chat"


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/invoices", tags=["data"])
def list_invoices() -> dict[str, Any]:
    return {
        "invoices": invoices_frame().to_dict(orient="records"),
        "items": items_frame().to_dict(orient="records"),
    }


@app.post("/api/chat", response_model=ChatResponse, tags=["chat"])
def chat_endpoint(body: ChatRequest) -> ChatResponse:
    text = body.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail="message خالی است")
    try:
        result = run_pipeline(text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    payload: dict[str, Any] = {
        "answer": result.answer,
        "intent": result.intent,
        "table_md": result.table_md,
        "data_changed": result.data_changed,
    }
    if body.include_debug:
        payload["sql"] = result.sql
        payload["tool_output"] = result.tool_output
        payload["context"] = result.context
    return ChatResponse(**payload)


@app.on_event("startup")
def _warmup() -> None:
    try:
        from qdrant_rag import warmup

        warmup()
    except Exception as exc:  # noqa: BLE001
        print(f"warmup skipped: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
