#!/usr/bin/env python3
"""
Run the 50 test questions through the Gradio UI, screenshot each Q&A,
and write the chatbot answers back into KRS_Chatbot_QA_Dynamic_50Q.xlsx.

  python qa_runner.py ask --phase base      # 50 questions on the original 9 invoices
  python qa_runner.py register              # register invoices 1010-1012 via chat
  python qa_runner.py ask --phase live      # 50 questions after the 3 new invoices
  python qa_runner.py write                 # judge + write answers into the Excel
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from config import BASE_DIR

QA_XLSX = BASE_DIR / "KRS_Chatbot_QA_Dynamic_50Q.xlsx"
OUT_DIR = BASE_DIR / "qa_results"
SHOTS = OUT_DIR / "screenshots"
UI_URL = "http://127.0.0.1:7860"
PENDING = "⏳"

REGISTER_MESSAGES = [
    "یک فاکتور جدید ثبت کن: شناسه 1010، شماره KRS-1405-810، تاریخ صدور 2026-11-08، سررسید 2026-11-08، "
    "مشتری 305 (پارت شرق)، شعبه 1 (دفتر مرکزی)، نماینده فروش 104 (سید کاظم جلالی)، تخفیف 50، "
    "وضعیت PAID، روش پرداخت «نقدی - حواله بانکی». قلم: ردیف 20، محصول 201، تعداد 60، قیمت واحد 25.",
    "یک فاکتور جدید ثبت کن: شناسه 1011، شماره KRS-1405-811، تاریخ صدور 2026-11-09، سررسید 2026-12-09، "
    "مشتری 308 (سینا طب)، شعبه 3 (پاساژ نظام)، نماینده فروش 106 (بهرام شفیعی)، تخفیف 100، "
    "وضعیت CHEQUE_PENDING، روش پرداخت «چک صیادی ۳۰ روزه». قلم: ردیف 21، محصول 210، تعداد 22، قیمت واحد 150.",
    "یک فاکتور جدید ثبت کن: شناسه 1012، شماره KRS-1405-812، تاریخ صدور 2026-11-10، سررسید 2027-01-10، "
    "مشتری 301 (ایپکو)، شعبه 2 (بازار سیف)، نماینده فروش 105 (امیرحسین رضایی)، تخفیف 0، "
    "وضعیت CHEQUE_PENDING، روش پرداخت «چک صیادی ۶۰ روزه». قلم: ردیف 22، محصول 203، تعداد 280، قیمت واحد 20.",
]


# Cells holding a broken formula instead of question text (shown as #NAME? in Excel).
Q_FALLBACK = {1: "شرکت گروه صنعتی کران‌سا در چه سالی تأسیس و ثبت شده است؟"}


def load_questions() -> list[dict]:
    ws = openpyxl.load_workbook(QA_XLSX).worksheets[0]
    out = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None or not row[1]:
            continue
        q = row[1] if isinstance(row[1], str) else Q_FALLBACK.get(int(row[0]), str(row[1]))
        out.append({"n": int(row[0]), "q": q, "base": row[2], "live": row[3], "kind": row[4]})
    return out


def _results_path(phase: str) -> Path:
    return OUT_DIR / f"answers_{phase}.json"


def _load(phase: str) -> dict:
    p = _results_path(phase)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save(phase: str, data: dict) -> None:
    _results_path(phase).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _bot_messages(page) -> list[str]:
    return page.eval_on_selector_all(
        "#chatbot .bot, #chatbot [data-testid='bot']",
        "els => els.map(e => e.innerText)",
    )


def ask_ui(page, text: str, shot: Path, timeout: float = 240) -> str:
    page.click("#clear")
    page.wait_for_timeout(700)
    box = page.locator("#msg textarea")
    box.fill(text)
    box.press("Enter")
    start = time.time()
    answer = ""
    while time.time() - start < timeout:
        page.wait_for_timeout(1000)
        msgs = [m for m in _bot_messages(page) if m.strip()]
        if msgs and PENDING not in msgs[-1]:
            answer = msgs[-1].strip()
            break
    page.wait_for_timeout(800)
    box = page.locator("#chatbot").bounding_box()
    bottom = page.evaluate(
        """() => {
            const els = document.querySelectorAll('#chatbot .bot, #chatbot [data-testid="bot"]');
            if (!els.length) return null;
            const r = els[els.length - 1].getBoundingClientRect();
            return r.bottom + window.scrollY;
        }"""
    )
    height = box["height"] if bottom is None else min(box["height"], bottom - box["y"] + 50)
    page.screenshot(
        path=str(shot),
        clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": max(height, 200)},
    )
    return answer or "(پاسخی در زمان مقرر دریافت نشد)"


def _browser():
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(channel="msedge")
    except Exception:  # noqa: BLE001
        browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 1900}, device_scale_factor=1)
    page.goto(UI_URL)
    page.wait_for_selector("#msg textarea", timeout=60000)
    return pw, browser, page


def cmd_ask(phase: str, only: list[int] | None) -> None:
    (SHOTS / phase).mkdir(parents=True, exist_ok=True)
    data = _load(phase)
    pw, browser, page = _browser()
    try:
        for item in load_questions():
            key = str(item["n"])
            if only and item["n"] not in only:
                continue
            if not only and key in data:
                continue
            shot = SHOTS / phase / f"Q{item['n']:02d}.png"
            ans = ask_ui(page, item["q"], shot)
            data[key] = {"q": item["q"], "answer": ans, "screenshot": str(shot.relative_to(BASE_DIR))}
            _save(phase, data)
            print(f"[{phase}] Q{item['n']:02d} done ({len(ans)} chars)", flush=True)
    finally:
        browser.close()
        pw.stop()


def cmd_register() -> None:
    (SHOTS / "register").mkdir(parents=True, exist_ok=True)
    data = {}
    pw, browser, page = _browser()
    try:
        for i, msg in enumerate(REGISTER_MESSAGES, start=1):
            shot = SHOTS / "register" / f"invoice_{1009 + i}.png"
            data[str(1009 + i)] = {"message": msg, "answer": ask_ui(page, msg, shot)}
            print(f"[register] invoice {1009 + i} done", flush=True)
    finally:
        browser.close()
        pw.stop()
    _save("register", data)


JUDGE_PROMPT = """You grade a chatbot answer against an expected answer for a Persian test question.
Numbers may be written in Persian or Latin digits and with different separators; units are million rials.
Reply with exactly one word: PASS if the chatbot answer contains the expected facts/numbers
(extra detail is fine), PARTIAL if partly correct, FAIL otherwise."""


def judge(question: str, expected: str, answer: str) -> str:
    from llm_client import chat

    raw = chat(
        [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"Question: {question}\nExpected: {expected}\nChatbot answer: {answer}"},
        ]
    ).upper()
    for v in ("PARTIAL", "PASS", "FAIL"):
        if v in raw:
            return v
    return "?"


VERDICT_FA = {"PASS": "درست", "PARTIAL": "نسبتاً درست", "FAIL": "نادرست", "?": "نامشخص"}
VERDICT_FILL = {"PASS": "C6EFCE", "PARTIAL": "FFEB9C", "FAIL": "FFC7CE", "?": "DDDDDD"}


def cmd_write() -> None:
    base, live = _load("base"), _load("live")
    wb = openpyxl.load_workbook(QA_XLSX)
    ws = wb.worksheets[0]
    headers = [
        "جواب چت‌بات (پایه)",
        "ارزیابی (پایه)",
        "جواب چت‌بات (لایو)",
        "ارزیابی (لایو)",
        "اسکرین‌شات پایه",
        "اسکرین‌شات لایو",
    ]
    first = 6
    for j, h in enumerate(headers):
        c = ws.cell(row=1, column=first + j, value=h)
        c.font = Font(bold=True)
    for r in range(2, ws.max_row + 1):
        n = ws.cell(row=r, column=1).value
        if n is None:
            continue
        key = str(int(n))
        q = str(ws.cell(row=r, column=2).value)
        exp_base = str(ws.cell(row=r, column=3).value or "")
        exp_live = str(ws.cell(row=r, column=4).value or "")
        if exp_live.strip().startswith("همان جواب پایه"):
            exp_live = exp_base + " " + exp_live
        for phase, src, exp, col in (("base", base, exp_base, first), ("live", live, exp_live, first + 2)):
            if key not in src:
                continue
            ans = src[key]["answer"]
            verdict = src[key].get("verdict") or judge(q, exp, ans)
            src[key]["verdict"] = verdict
            ws.cell(row=r, column=col, value=ans).alignment = Alignment(wrap_text=True, vertical="top")
            vc = ws.cell(row=r, column=col + 1, value=VERDICT_FA[verdict])
            vc.fill = PatternFill("solid", fgColor=VERDICT_FILL[verdict])
            shot_col = first + 4 if phase == "base" else first + 5
            sc = ws.cell(row=r, column=shot_col, value=src[key]["screenshot"])
            sc.hyperlink = src[key]["screenshot"]
            sc.font = Font(color="0563C1", underline="single")
    for col, width in zip("FGHIJK", (60, 14, 60, 14, 32, 32)):
        ws.column_dimensions[col].width = width
    _save("base", base)
    _save("live", live)
    wb.save(QA_XLSX)
    for phase, src in (("base", base), ("live", live)):
        counts: dict[str, int] = {}
        for v in src.values():
            counts[v.get("verdict", "?")] = counts.get(v.get("verdict", "?"), 0) + 1
        print(phase, counts)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("--phase", choices=["base", "live"], required=True)
    a.add_argument("--only", type=int, nargs="*")
    sub.add_parser("register")
    sub.add_parser("write")
    args = p.parse_args()
    OUT_DIR.mkdir(exist_ok=True)
    if args.cmd == "ask":
        cmd_ask(args.phase, args.only)
    elif args.cmd == "register":
        cmd_register()
    else:
        cmd_write()


if __name__ == "__main__":
    main()
