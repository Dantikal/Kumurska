from fastapi import FastAPI

from app.api import api_router
from app.core.errors import register_error_handlers

app = FastAPI(title="Kumurska API", version="0.1.0")
register_error_handlers(app)
app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
