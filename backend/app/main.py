from fastapi import Depends, FastAPI

from app.config import Settings, get_settings

app = FastAPI(title="Enterprise QA MVP", version="0.1.0")


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> dict[str, object]:  # noqa: B008
    return {"status": "ok", "deps": {}, "env": settings.environment}
