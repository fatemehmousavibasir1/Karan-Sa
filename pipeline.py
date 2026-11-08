"""KRS invoice chat pipeline: classify → SQL (SQLite) / Qdrant → answer LLM."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from config import QDRANT_TOP_K
from db import (
    catalog_text,
    df_to_markdown,
    gregorian_to_jalali,
    invoices_frame,
    run_select,
    run_write,
)
from llm_client import chat, extract_sql
from prompts import (
    CLASSIFIER_PROMPT,
    DOCUMENT_PROMPT,
    GREETING_PROMPT,
    HYBRID_ANSWER_PROMPT,
    MODIFY_ANSWER_PROMPT,
    MODIFY_SQL_PROMPT,
    VIEW_ANSWER_PROMPT,
    VIEW_SQL_PROMPT,
)
from qdrant_rag import POINT_DOC, format_context, search_chunks, sync_invoices

Intent = Literal["view_data", "modify_data", "document_question", "hybrid", "greeting"]
INTENTS: tuple[Intent, ...] = ("hybrid", "view_data", "modify_data", "document_question", "greeting")


@dataclass
class PipelineResult:
    intent: Intent
    answer: str
    sql: str | None = None
    tool_output: str | None = None
    context: str | None = None
    table_md: str | None = None
    data_changed: bool = False


_NO_INFO = re.compile(r"اطلاعاتی\s*(در\s*این\s*(مورد|باره)\s*)?ندارم|(در\s*متن‌?ها|اطلاعاتی).{0,40}(موجود|وجود)\s*نیست")

_GREETINGS = {"سلام", "درود", "صبح بخیر", "عصر بخیر", "وقت بخیر", "خسته نباشید", "ممنون", "مرسی", "سلام وقت بخیر"}


def _today() -> str:
    d = dt.date.today()
    return f"{d.isoformat()} ({gregorian_to_jalali(d.isoformat())})"


def classify_intent(user_query: str) -> Intent:
    q = user_query.strip().rstrip("!.؟?")
    if q in _GREETINGS:
        return "greeting"
    raw = chat(
        [
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": user_query},
        ]
    ).lower()
    for intent in INTENTS:
        if intent in raw:
            return intent
    return "document_question"


def _generate_select(question: str, extra: str = "") -> str:
    raw = chat(
        [
            {"role": "system", "content": VIEW_SQL_PROMPT.format(today=_today(), catalog=catalog_text())},
            {"role": "user", "content": question + (f"\n\n{extra}" if extra else "")},
        ]
    )
    return extract_sql(raw)


def _format_numbers(df):
    """Thousands separators on amount columns so the answer model copies numbers verbatim."""
    out = df.copy()
    for col in out.columns:
        if "id" in str(col).lower() or not pd.api.types.is_numeric_dtype(out[col]):
            continue
        out[col] = out[col].map(
            lambda v: v if pd.isna(v) else (f"{int(v):,}" if float(v).is_integer() else f"{v:,.2f}")
        )
    return out


def _is_empty_result(df) -> bool:
    return df.empty or bool(df.isna().all().all())


def _select_with_retry(question: str) -> tuple[str, str, str | None]:
    """Return (sql, result_text, markdown_table). Retries on SQL errors and empty/NULL results."""
    sql = _generate_select(question)
    last: tuple[str, str, str | None] = (sql, "", None)
    for attempt in range(3):
        try:
            df = run_select(sql)
        except Exception as exc:  # noqa: BLE001
            last = (sql, f"(خطای اجرای SQL: {exc})", None)
            feedback = f"Your previous SQL failed.\nSQL:\n{sql}\nError: {exc}\nFix it."
        else:
            df = df.round(2)
            last = (sql, _format_numbers(df).to_string(index=False, max_rows=200), df_to_markdown(df))
            if not _is_empty_result(df):
                return last
            feedback = (
                f"Your previous SQL returned no rows (or only NULLs):\n{sql}\n"
                "The data most likely exists — your filter is probably wrong. Re-check REFERENCE DATA "
                "and filter by the exact ids (product_id, customer_id, user_id, branch_id) or exact "
                "enum values, then write a corrected query."
            )
        if attempt < 2:
            sql = _generate_select(question, feedback)
    return last


def handle_view_data(user_query: str) -> PipelineResult:
    sql, result, table = _select_with_retry(user_query)
    answer = chat(
        [
            {"role": "system", "content": VIEW_ANSWER_PROMPT.format(question=user_query, result=result)},
            {"role": "user", "content": user_query},
        ]
    )
    return PipelineResult("view_data", answer, sql=sql, tool_output=result, table_md=table)


def _snapshot() -> str:
    from db import items_frame

    inv = invoices_frame(persian=False)
    items = items_frame(persian=False)
    return (
        "invoices:\n"
        + inv[["invoice_id", "invoice_number", "company_name", "branch_name",
               "net_amount_m_rial", "discount_m_rial", "payment_status"]].to_string(index=False)
        + "\n\ninvoice_items:\n"
        + items[["item_id", "invoice_id", "sku_code", "product_name", "quantity",
                 "unit_price_m_rial"]].to_string(index=False)
    )


def _touched_invoices(sql: str) -> list[int]:
    ids = {int(x) for x in re.findall(r"\b(1\d{3})\b", sql)}
    nums = re.findall(r"KRS-\d{4}-\d+", sql)
    if nums:
        inv = invoices_frame(persian=False)
        ids |= set(inv.loc[inv["invoice_number"].isin(nums), "invoice_id"].astype(int))
    return sorted(ids)


def handle_modify_data(user_query: str) -> PipelineResult:
    raw = chat(
        [
            {
                "role": "system",
                "content": MODIFY_SQL_PROMPT.format(
                    today=_today(), snapshot=_snapshot(), catalog=catalog_text()
                ),
            },
            {"role": "user", "content": user_query},
        ]
    )
    cleaned = raw.strip()
    if cleaned.upper().startswith("CANNOT"):
        reason = cleaned.split(":", 1)[-1].strip() or "درخواست مبهم است."
        return PipelineResult("modify_data", f"تغییری انجام نشد: {reason}", tool_output=cleaned)

    sql = extract_sql(raw)
    ids = _touched_invoices(sql)
    before = invoices_frame()
    before_df = before[before["شناسه"].isin(ids)] if ids else before.head(0)
    try:
        results = run_write(sql)
    except Exception as exc:  # noqa: BLE001
        return PipelineResult(
            "modify_data",
            f"ویرایش انجام نشد (هیچ تغییری ذخیره نشد). خطا: {exc}",
            sql=sql,
            tool_output=str(exc),
        )

    changed = sum(max(n, 0) for _, n in results) > 0
    sync_note = ""
    if changed:
        try:
            sync_invoices()
        except Exception as exc:  # noqa: BLE001
            sync_note = f"\n\n⚠️ تغییر در پایگاه داده ذخیره شد ولی همگام‌سازی با Qdrant ناموفق بود: {exc}"

    inv = invoices_frame()
    after_df = inv[inv["شناسه"].isin(ids)] if ids else inv.head(0)
    after_md = df_to_markdown(after_df) if not after_df.empty else None
    result_text = "\n".join(f"{s}\n→ ردیف‌های تغییرکرده: {n}" for s, n in results)

    answer = chat(
        [
            {
                "role": "system",
                "content": MODIFY_ANSWER_PROMPT.format(
                    question=user_query,
                    result=result_text,
                    before=before_df.to_string(index=False) if not before_df.empty else "(نامشخص)",
                    after=after_df.to_string(index=False) if not after_df.empty else "(نامشخص)",
                ),
            },
            {"role": "user", "content": user_query},
        ]
    )
    return PipelineResult(
        "modify_data",
        answer + sync_note,
        sql=sql,
        tool_output=result_text,
        table_md=after_md,
        data_changed=changed,
    )


def handle_document_question(user_query: str) -> PipelineResult:
    try:
        context = format_context(search_chunks(user_query, limit=QDRANT_TOP_K, point_type=POINT_DOC))
    except Exception as exc:  # noqa: BLE001
        context = f"(خطا در بازیابی از Qdrant: {exc})"
    answer = chat(
        [
            {"role": "system", "content": DOCUMENT_PROMPT.format(question=user_query, context=context)},
            {"role": "user", "content": user_query},
        ]
    )
    if _NO_INFO.search(answer):
        return handle_hybrid(user_query)
    return PipelineResult("document_question", answer, context=context)


def handle_hybrid(user_query: str) -> PipelineResult:
    try:
        context = format_context(search_chunks(user_query, limit=QDRANT_TOP_K))
    except Exception as exc:  # noqa: BLE001
        context = f"(خطا در بازیابی از Qdrant: {exc})"
    sql, result, table = _select_with_retry(user_query)
    answer = chat(
        [
            {
                "role": "system",
                "content": HYBRID_ANSWER_PROMPT.format(
                    question=user_query, sql=sql, result=result, context=context
                ),
            },
            {"role": "user", "content": user_query},
        ]
    )
    if table == df_to_markdown(invoices_frame().head(0)):
        table = None
    return PipelineResult("hybrid", answer, sql=sql, tool_output=result, context=context, table_md=table)


def handle_greeting(user_query: str) -> PipelineResult:
    answer = chat(
        [
            {"role": "system", "content": GREETING_PROMPT},
            {"role": "user", "content": user_query},
        ],
        temperature=0.3,
    )
    return PipelineResult("greeting", answer)


HANDLERS = {
    "view_data": handle_view_data,
    "modify_data": handle_modify_data,
    "document_question": handle_document_question,
    "hybrid": handle_hybrid,
    "greeting": handle_greeting,
}


def run_pipeline(user_query: str) -> PipelineResult:
    query = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", user_query).strip() or user_query
    return HANDLERS[classify_intent(query)](query)
