"""AEGIS — Fraud Detection Platform · Entry point
Serves: FastAPI backend + 3 static portals (admin, merchant, investigator)
"""
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.api.deps import get_registry, require_investigator, require_owner
from app.api.v1 import router as v1_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, RateLimitMiddleware
from app.core.telemetry import setup_telemetry
from app.services.registry import ServiceRegistry

configure_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("aegis.startup", version=settings.VERSION, env=settings.ENV)
    registry = ServiceRegistry()
    await registry.initialize()
    app.state.registry = registry
    setup_telemetry(app)
    logger.info("aegis.ready")
    yield
    await registry.shutdown()
    logger.info("aegis.shutdown")


app = FastAPI(
    title="AEGIS Fraud Detection Platform",
    description="Multi-tenant financial fraud detection engine",
    version=settings.VERSION,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")
app.mount("/metrics", make_asgi_app())

def _find_portals_dir():
    base = Path(__file__).resolve()
    for level in (2, 1):
        cand = base.parents[level] / "portals"
        if cand.exists():
            return cand
    return None


PORTALS_DIR = _find_portals_dir()
if PORTALS_DIR.exists():
    for portal in ("admin", "merchant", "investigator"):
        p = PORTALS_DIR / portal
        if p.exists():
            app.mount(f"/{portal}", StaticFiles(directory=str(p), html=True), name=portal)


_FONTS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
if _FONTS_DIR.exists():
    app.mount("/fonts", StaticFiles(directory=str(_FONTS_DIR)), name="fonts")


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><title>🛡️ AEGIS Platform</title>
<style>
body{font-family:system-ui,sans-serif;background:#0F172A;color:#F1F5F9;min-height:100vh;
display:flex;align-items:center;justify-content:center;margin:0}
.hero{max-width:680px;padding:40px;text-align:center}
h1{font-size:2.4rem;background:linear-gradient(90deg,#3B82F6,#06B6D4);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:28px}
a{background:#1E293B;border:1px solid #334155;padding:20px;border-radius:12px;
text-decoration:none;color:#F1F5F9;display:block;transition:.15s}
a:hover{border-color:#06B6D4;transform:translateY(-2px)}
.icon{font-size:2.2rem;margin-bottom:8px}
.label{font-weight:700;color:#06B6D4}
.sub{font-size:12px;color:#94A3B8;margin-top:4px}
</style></head><body>
<div class="hero">
<h1>🛡️ AEGIS Platform</h1>
<p style="color:#94A3B8;font-size:15px">منصة كشف الاحتيال المالي متعددة المؤسسات</p>
<div class="grid">
  <a href="/admin/"><div class="icon">👑</div><div class="label">بوابة مالك المنصة</div><div class="sub">إدارة المؤسسات والمفاتيح والحدود</div></a>
  <a href="/merchant/"><div class="icon">🏦</div><div class="label">بوابة المؤسسة</div><div class="sub">للبنوك/المحافظ — لوحة، محققون، تقارير</div></a>
  <a href="/investigator/"><div class="icon">🛡️</div><div class="label">لوحة المحقق</div><div class="sub">مراجعة التنبيهات والحالات الحيّة</div></a>
  <a href="/docs"><div class="icon">📘</div><div class="label">API Docs</div><div class="sub">Swagger UI</div></a>
</div>
</div>
</body></html>
"""


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION, "env": settings.ENV}


@app.get("/ready")
async def ready(request: Request):
    checks = await request.app.state.registry.readiness()
    ok = checks["database"] and checks["rules"] > 0
    return {"status": "ready" if ok else "degraded", **checks}


def _sse_gen(request: Request, registry):
    queue = registry.events.subscribe()

    async def event_gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: {item['event_type']}\ndata: {json.dumps(item['payload'], ensure_ascii=False, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            registry.events.unsubscribe(queue)

    return event_gen()


@app.get("/api/v1/admin/stream")
async def stream(request: Request, owner: str = Depends(require_owner)):
    """SSE stream of live decisions — owner only."""
    registry = request.app.state.registry
    return StreamingResponse(_sse_gen(request, registry),
                             media_type="text/event-stream")


@app.get("/api/v1/investigator/stream")
async def investigator_stream(request: Request,
                              inv: dict = Depends(require_investigator)):
    """SSE stream of live risk events — authenticated, tenant-scoped investigators only."""
    registry = request.app.state.registry
    return StreamingResponse(_sse_gen(request, registry),
                             media_type="text/event-stream")
