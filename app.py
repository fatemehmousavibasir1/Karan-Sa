#!/usr/bin/env python3
"""Gradio chatbot UI for KRS invoices."""

from __future__ import annotations

import os
from collections.abc import Generator

import gradio as gr
import pandas as pd

from db import (
    TABLE_TITLES_FA,
    TABLES,
    invoices_frame,
    items_frame,
    table_frame,
)
from pipeline import run_pipeline

PENDING = "⏳ در حال آماده‌سازی پاسخ…"


def _tables() -> tuple[pd.DataFrame, ...]:
    """Invoice view, items view, then every raw table in TABLES order."""
    return (invoices_frame(), items_frame(), *(table_frame(t) for t in TABLES))


def respond(
    message: str, history: list[dict[str, str]]
) -> Generator[tuple, None, None]:
    tables = _tables()
    if not message or not message.strip():
        yield (history or [], "", "", *tables)
        return

    history = list(history or [])
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": PENDING})
    yield (history, "", "در حال پاسخ…", *tables)

    try:
        result = run_pipeline(message.strip())
        answer = result.answer
        if result.table_md:
            answer += "\n\n" + result.table_md
    except Exception as exc:  # noqa: BLE001
        answer = f"خطا در پردازش درخواست: {exc}"

    history[-1] = {"role": "assistant", "content": answer}
    yield (history, "", "", *_tables())


def respond_example(
    history: list[dict[str, str]], evt: gr.SelectData
) -> Generator[tuple, None, None]:
    yield from respond(evt.value["text"], history)


CSS = """
body, .gradio-container, .gradio-container *:not(code):not(pre) {
    font-family: "B Nazanin", "BNazanin", Tahoma, sans-serif !important;
}
.gradio-container { font-size: 17px; }
#chatbot .placeholder-content { flex-direction: column; justify-content: flex-end; }
#chatbot .examples { margin: auto 0 8px 0 !important; }
"""

SUGGESTIONS = [
    "فاکتورهای معوق را نشان بده",
    "وضعیت فاکتور KRS-1405-802 را تسویه‌شده کن",
]


def build_ui() -> gr.Blocks:
    inv, items, *raw = _tables()
    chat_height = os.getenv("CHAT_HEIGHT")
    with gr.Blocks(title="KRS Invoice Chatbot") as demo:
        gr.Markdown("# کران‌سا | دستیار فاکتورها")
        with gr.Tab("گفتگو"):
            chatbot = gr.Chatbot(
                elem_id="chatbot",
                height=int(chat_height) if chat_height else 380,
                min_height=200,
                max_height=int(chat_height) if chat_height else 380,
                buttons=["copy", "copy_all"],
                rtl=True,
                examples=[{"text": s} for s in SUGGESTIONS],
            )
            status = gr.Markdown("")
            with gr.Row():
                msg = gr.Textbox(
                    elem_id="msg",
                    placeholder="سؤال یا دستور ویرایش فاکتور را بنویسید…",
                    show_label=False,
                    scale=5,
                    rtl=True,
                )
                send = gr.Button("ارسال", variant="primary", scale=1)
            clear = gr.Button("پاک کردن گفتگو", elem_id="clear")
        with gr.Tab("فاکتورها"):
            refresh = gr.Button("به‌روزرسانی جدول")
            inv_table = gr.Dataframe(value=inv, interactive=False, wrap=True, label="فاکتورها")
            items_table = gr.Dataframe(value=items, interactive=False, wrap=True, label="اقلام فاکتور")
        with gr.Tab("همه جداول"):
            refresh_all = gr.Button("به‌روزرسانی جداول")
            raw_tables = [
                gr.Dataframe(
                    value=df,
                    interactive=False,
                    wrap=True,
                    label=f"{TABLE_TITLES_FA[name]} ({name})",
                )
                for name, df in zip(TABLES, raw)
            ]

        table_outputs = [inv_table, items_table, *raw_tables]
        outputs = [chatbot, msg, status, *table_outputs]
        send.click(respond, inputs=[msg, chatbot], outputs=outputs, show_progress="hidden")
        msg.submit(respond, inputs=[msg, chatbot], outputs=outputs, show_progress="hidden")
        chatbot.example_select(
            respond_example, inputs=[chatbot], outputs=outputs, show_progress="hidden"
        )
        clear.click(lambda: ([], "", ""), outputs=[chatbot, msg, status], show_progress="hidden")
        refresh.click(_tables, outputs=table_outputs)
        refresh_all.click(_tables, outputs=table_outputs)
    return demo


if __name__ == "__main__":
    os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
    try:
        from qdrant_rag import warmup

        warmup()
    except Exception as exc:  # noqa: BLE001
        print(f"Qdrant warmup skipped: {exc}")

    ui = build_ui()
    ui.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        share=False,
        css=CSS,
    )
