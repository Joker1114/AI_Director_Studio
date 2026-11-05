"""Cloud ASGI entry point. React/Electron are deployed independently."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
from starlette.middleware.cors import CORSMiddleware

from app.adapters.qwen import LLMFailure
from app.api.v1.business import router as business_router
from app.api.v1.generation import router as generation_router
from app.config import get_settings

app = FastAPI(title="AI Director Studio Cloud API", version="1.1.0")
settings = get_settings()
if settings.cors_origins.strip():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[s.strip() for s in settings.cors_origins.split(",") if s.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["X-API-Token", "Content-Type"],
    )

app.include_router(business_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
# Temporary aliases for the previous V1 client/tests; remove in a major API release.
app.include_router(business_router, prefix="/api", include_in_schema=False)


@app.exception_handler(LLMFailure)
async def llm_failure_handler(_, exc: LLMFailure):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "version": "1.1.0"}


@app.get("/", include_in_schema=False)
def previous_web_console():
    """Backward-compatible V1 web UI; desktop React uses versioned API."""
    return FileResponse(Path(__file__).parent / "legacy_web" / "index.html")


@app.get("/app.js", include_in_schema=False)
def previous_js():
    return FileResponse(Path(__file__).parent / "legacy_web" / "app.js")


@app.get("/style.css", include_in_schema=False)
def previous_css():
    return FileResponse(Path(__file__).parent / "legacy_web" / "style.css")
