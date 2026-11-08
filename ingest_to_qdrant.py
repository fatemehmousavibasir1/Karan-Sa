#!/usr/bin/env python3
"""
Build krs.db from Dataset.txt, export invoices.xlsx, and load everything into Qdrant.

  .venv\\Scripts\\python.exe ingest_to_qdrant.py            # first run / refresh Qdrant
  .venv\\Scripts\\python.exe ingest_to_qdrant.py --reset-db # rebuild krs.db from Dataset.txt
"""

from __future__ import annotations

import argparse

from config import DB_PATH, INVOICES_EXCEL, QDRANT_COLLECTION, QDRANT_URL
from db import build_from_dataset, export_invoices_excel
from qdrant_rag import sync_invoices, upsert_company_chunks


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--reset-db", action="store_true", help="krs.db را از Dataset.txt از نو بساز")
    args = p.parse_args()

    build_from_dataset(force=args.reset_db)
    print(f"SQLite: {DB_PATH}")
    export_invoices_excel()
    print(f"Excel: {INVOICES_EXCEL}")

    print(f"Qdrant: {QDRANT_URL} / collection={QDRANT_COLLECTION}")
    print(f"  company chunks: {upsert_company_chunks()}")
    print(f"  invoices:       {sync_invoices()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
