import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from app.api.briefs import router as briefs_router
from app.api.calendar import router as calendar_router
from app.api.rag import router as rag_router
from app.api.users import router as users_router
from app.config import settings
from app.gateways.ollama_gateway import OllamaError, OllamaGateway
from app.gateways.supabase_gateway import SupabaseGateway

logger = logging.getLogger(__name__)


def _warm_ollama_background() -> None:
    """Lightweight readiness probe only — do not invoke the model at startup.

    Skipped when AI polish is disabled (stable demo). Never blocks plan generation.
    """
    if not settings.polish_enabled:
        logger.info(
            "ollama_warmup skipped reason=ai_polish_disabled "
            "ai_polish_enabled=%s",
            settings.ai_polish_enabled,
        )
        return
    try:
        gateway = OllamaGateway()
        if not gateway.is_available():
            logger.info("ollama_warmup skipped reason=unavailable")
            return
        models = gateway.list_models()
        logger.info("ollama_warmup ok models_count=%s", len(set(models)))
    except Exception as exc:
        logger.info("ollama_warmup failed err=%s", type(exc).__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_ollama_background, daemon=True).start()
    yield


app = FastAPI(
    title="AI Calendar Study Assistant API",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "users", "description": "Demo student profile"},
        {"name": "calendar", "description": "Google Calendar OAuth and sync"},
        {"name": "briefs", "description": "Study plan generation and Telegram"},
        {
            "name": "rag",
            "description": (
                "Study material upload and retrieval. "
                "Uploaded PDFs enrich Create Study Plan topics."
            ),
        },
    ],
)

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#2563eb"/>
  <text x="16" y="21" text-anchor="middle" font-family="sans-serif" font-size="11" font-weight="bold" fill="white">AI</text>
</svg>"""


@app.get("/")
def root():
    return {
        "name": "AI Calendar Study Assistant API",
        "health": "/health",
        "health_supabase": "/health/supabase",
        "health_ollama": "/health/ollama",
        "rag_upload": "/rag/upload",
        "rag_ask": "/rag/ask",
        "rag_status": "/rag/status",
        "docs": "/docs",
    }


app.include_router(users_router)
app.include_router(calendar_router)
app.include_router(briefs_router)
app.include_router(rag_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "ai_polish_enabled": bool(settings.ai_polish_enabled),
        "polish_enabled": bool(settings.polish_enabled),
        "ollama_timeout_sec": float(settings.ollama_timeout_sec),
        # Deprecated alias — prefer ai_polish_enabled / polish_enabled.
        "skip_ollama_polish": bool(settings.skip_ollama_polish),
    }


@app.get("/health/supabase")
def supabase_health_check():
    result = SupabaseGateway().health_check()
    if result.get("ok"):
        return {"status": "ok", "service": "supabase"}
    return JSONResponse(
        status_code=503,
        content={
            "status": "error",
            "service": "supabase",
            "detail": result.get("error", "Supabase connection failed"),
        },
    )


@app.get("/health/ollama")
def ollama_health_check():
    """Report whether Docker Ollama is reachable and the configured model is present."""
    gateway = OllamaGateway()
    base_url = gateway.base_url
    model = gateway.model
    try:
        models = gateway.list_models()
    except OllamaError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "service": "ollama",
                "reachable": False,
                "base_url": base_url,
                "model_configured": model,
                "model_available": False,
                "ai_polish_enabled": bool(settings.ai_polish_enabled),
                "detail": str(exc),
            },
        )

    model_available = bool(model) and (
        model in models or f"{model}:latest" in models
    )
    payload = {
        "status": "ok" if model_available else "degraded",
        "service": "ollama",
        "reachable": True,
        "base_url": base_url,
        "model_configured": model,
        "model_available": model_available,
        "ai_polish_enabled": bool(settings.ai_polish_enabled),
        "models_count": len(set(models)),
    }
    if not model_available:
        payload["detail"] = (
            f"Ollama is reachable but model '{model}' is not pulled. "
            f"Run: docker exec -it ai-study-planner-ollama ollama pull {model or 'llama3.2'}"
        )
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")
