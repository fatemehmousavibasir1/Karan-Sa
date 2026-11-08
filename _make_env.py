from pathlib import Path

keys = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "QDRANT_COLLECTION", "QDRANT_TOP_K")
lines = [l for l in Path("settings.env").read_text(encoding="utf-8").splitlines()
         if l.split("=", 1)[0].strip() in keys]
Path(".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote .env with", [l.split("=", 1)[0] for l in lines])
