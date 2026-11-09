#!/usr/bin/env python3
"""
KRS invoice chatbot backend API + web frontend (served at /).

Run:
  .venv\\Scripts\\uvicorn api:app --host 0.0.0.0 --port 8000

Docs:
  http://HOST:8000/docs
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import web_data
from db import invoices_frame, items_frame
from pipeline import run_pipeline

WEB_DIR = Path(__file__).resolve().parent / "web"

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


@app.get("/api/meta", tags=["web"])
def meta() -> dict[str, Any]:
    return {"columns": web_data.COLUMN_TITLES_FA, "status_labels": web_data.STATUS_FA}


@app.get("/api/dashboard", tags=["web"])
def dashboard() -> dict[str, Any]:
    return web_data.dashboard()


@app.get("/api/web/invoices", tags=["web"])
def web_invoices() -> dict[str, Any]:
    return web_data.invoices()


@app.get("/api/web/invoices/{invoice_id}", tags=["web"])
def web_invoice_detail(invoice_id: int) -> dict[str, Any]:
    detail = web_data.invoice_detail(invoice_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="فاکتور پیدا نشد")
    return detail


@app.get("/api/tables", tags=["web"])
def tables() -> list[dict[str, Any]]:
    return web_data.tables_meta()


@app.get("/api/tables/{name}", tags=["web"])
def table(name: str) -> dict[str, Any]:
    try:
        return web_data.table_data(name)
    except ValueError:
        raise HTTPException(status_code=404, detail="جدول نامعتبر") from None


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


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
