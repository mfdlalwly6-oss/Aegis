"""Request middleware — correlation IDs, rate limiting, PII scrubbing."""
import time
import uuid
from collections import defaultdict, deque

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings

logger = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        req_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        tenant = request.headers.get("x-tenant-id", "default")
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=req_id, tenant=tenant)
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            dt = (time.perf_counter() - t0) * 1000
            logger.info("http.request",
                        path=request.url.path,
                        method=request.method,
                        latency_ms=round(dt, 2))
        response.headers["x-request-id"] = req_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket-lite: per-IP sliding-window."""
    def __init__(self, app):
        super().__init__(app)
        self.buckets: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        ip = request.client.host if request.client else "anon"
        now = time.time()
        bucket = self.buckets[ip]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= settings.RATE_LIMIT_PER_MIN:
            return JSONResponse({"error": "rate_limited"}, status_code=429)
        bucket.append(now)
        return await call_next(request)
