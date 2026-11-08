"""Runtime configuration (reads settings.env)."""

from __future__ import annotations

import os
from pathlib import Path

import env_loader  # noqa: F401  — loads settings.env into os.environ

BASE_DIR = Path(__file__).resolve().parent


def _path(env_key: str, default: str) -> Path:
    p = Path(os.getenv(env_key, default))
    return p if p.is_absolute() else BASE_DIR / p


API_KEY = os.getenv("LLM_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
MODEL = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")

DB_PATH = _path("DB_PATH", "krs.db")
DATASET_FILE = _path("DATASET_FILE", "Dataset.txt")
INVOICES_EXCEL = _path("INVOICES_EXCEL", "invoices.xlsx")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "krs")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
QDRANT_TOP_K = int(os.getenv("QDRANT_TOP_K", "8"))
CHUNKS_FILE = _path("CHUNKS_FILE", "krs_chunks.txt")
EMBED_MODEL = os.getenv(
    "EMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
