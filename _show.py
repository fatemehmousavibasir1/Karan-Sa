import json

d = json.load(open("qa_results/answers_base.json", encoding="utf-8"))
bad = [k for k, v in d.items() if v["answer"].startswith("خطا")]
print("error answers:", bad or "none", "| total:", len(d))
