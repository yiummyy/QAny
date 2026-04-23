from fastapi import FastAPI

app = FastAPI(title="Enterprise QA MVP", version="0.1.0")

@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {"status": "ok", "deps": {}}
