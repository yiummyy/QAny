from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title="Enterprise QA MVP", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    settings = get_settings()
    return {"status": "ok", "deps": {}, "env": settings.environment}
