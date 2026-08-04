from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response

from app.api.briefs import router as briefs_router
from app.api.calendar import router as calendar_router
from app.api.users import router as users_router
from app.gateways.supabase_gateway import SupabaseGateway

app = FastAPI(title="AI Calendar Study Assistant API")

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
        "docs": "/docs",
    }


app.include_router(users_router)
app.include_router(calendar_router)
app.include_router(briefs_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


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


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")
