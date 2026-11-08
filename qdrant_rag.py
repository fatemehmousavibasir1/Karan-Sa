"""Qdrant storage/retrieval for KRS company chunks and invoice documents."""

from __future__ import annotations

import re
import uuid
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from config import (
    CHUNKS_FILE,
    EMBED_MODEL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_TOP_K,
    QDRANT_URL,
)

POINT_DOC = "company_doc"
POINT_INVOICE = "invoice"


@lru_cache(maxsize=1)
def _model():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=EMBED_MODEL)


@lru_cache(maxsize=1)
def client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60)


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().embed(texts)]


def ensure_collection() -> None:
    c = client()
    if c.collection_exists(QDRANT_COLLECTION):
        return
    dim = len(embed(["probe"])[0])
    c.create_collection(
        QDRANT_COLLECTION,
        vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
    )
    c.create_payload_index(QDRANT_COLLECTION, "point_type", qm.PayloadSchemaType.KEYWORD)


def _point_id(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"krs:{key}"))


def parse_chunks_file(path=CHUNKS_FILE) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"\*{4}\s*</chunk_end>", raw) if b.strip()]
    chunks = []
    for i, block in enumerate(blocks):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        title = lines[0] if lines else f"چانک {i + 1}"
        kw = next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("کلیدواژه")), "")
        body_idx = next((j for j, ln in enumerate(lines) if ln.startswith("متن:")), None)
        if body_idx is None:
            text = "\n".join(lines[1:])
        else:
            text = "\n".join([lines[body_idx][len("متن:"):].strip(), *lines[body_idx + 1 :]])
        chunks.append({"chunk_index": i, "title": title, "keywords": kw, "text": text})
    return chunks


def upsert_company_chunks() -> int:
    ensure_collection()
    chunks = parse_chunks_file()
    vectors = embed([f"{c['keywords']}\n{c['text']}" for c in chunks])
    points = [
        qm.PointStruct(
            id=_point_id(f"doc:{c['chunk_index']}"),
            vector=v,
            payload={"point_type": POINT_DOC, "source": CHUNKS_FILE.name, **c},
        )
        for c, v in zip(chunks, vectors)
    ]
    client().upsert(QDRANT_COLLECTION, points=points, wait=True)
    return len(points)


def sync_invoices() -> int:
    """Replace all invoice points with the current state of the SQLite DB."""
    from db import invoice_documents

    ensure_collection()
    docs = invoice_documents()
    client().delete(
        QDRANT_COLLECTION,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="point_type", match=qm.MatchValue(value=POINT_INVOICE))]
            )
        ),
        wait=True,
    )
    if not docs:
        return 0
    vectors = embed([d["text"] for d in docs])
    points = [
        qm.PointStruct(
            id=_point_id(f"invoice:{d['invoice_id']}"),
            vector=v,
            payload={"point_type": POINT_INVOICE, "source": "invoices", **d},
        )
        for d, v in zip(docs, vectors)
    ]
    client().upsert(QDRANT_COLLECTION, points=points, wait=True)
    return len(points)


def search_chunks(
    query: str,
    *,
    limit: int | None = None,
    point_type: str | None = None,
) -> list[dict[str, Any]]:
    flt = None
    if point_type:
        flt = qm.Filter(
            must=[qm.FieldCondition(key="point_type", match=qm.MatchValue(value=point_type))]
        )
    res = client().query_points(
        QDRANT_COLLECTION,
        query=embed([query])[0],
        query_filter=flt,
        limit=limit or QDRANT_TOP_K,
        with_payload=True,
    )
    out = []
    for p in res.points:
        payload = p.payload or {}
        out.append(
            {
                "score": p.score,
                "text": payload.get("text", ""),
                "title": payload.get("title") or payload.get("invoice_number") or "",
                "point_type": payload.get("point_type"),
            }
        )
    return out


def format_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(هیچ چانکی بازیابی نشد)"
    parts = []
    for i, ch in enumerate(chunks, start=1):
        kind = "فاکتور" if ch.get("point_type") == POINT_INVOICE else "اطلاعات شرکت"
        parts.append(f"[Chunk {i} | {kind} | {ch.get('title', '')}]\n{ch['text'].strip()}")
    return "\n\n---\n\n".join(parts)


def warmup() -> None:
    ensure_collection()
    search_chunks("کران‌سا", limit=1)
