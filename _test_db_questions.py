"""Run the database questions of the QA sheet directly through the pipeline."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import openpyxl

from pipeline import run_pipeline

wb = openpyxl.load_workbook("KRS_Chatbot_QA_Dynamic_50Q.xlsx")
rows = [r for r in wb.worksheets[0].iter_rows(min_row=2, values_only=True) if r[0]]
only = {int(x) for x in sys.argv[1:]}
rows = [r for r in rows if (int(r[0]) in only if only else int(r[0]) >= 12)]


def run(r):
    try:
        res = run_pipeline(str(r[1]))
        return {"n": r[0], "q": r[1], "expected": r[2], "intent": res.intent, "sql": res.sql,
                "result": (res.tool_output or "")[:600], "answer": res.answer}
    except Exception as exc:  # noqa: BLE001
        return {"n": r[0], "q": r[1], "expected": r[2], "error": str(exc)}


with ThreadPoolExecutor(max_workers=6) as ex:
    out = list(ex.map(run, rows))

with open("qa_results/_db_test.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("done", len(out))
