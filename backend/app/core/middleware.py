"""Request middleware — correlation IDs, rate limiting, security headers.

Rate limiting is layered:
- RateLimitMiddleware: a global per-IP sliding-window cap on ALL requests.
- AuthRateLimitMiddleware: a TIGHTER, endpoint-scoped cap on authentication /
  account-recovery endpoints to resist brute-force and credential-stuffing.
"""

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
            logger.info(
                "http.request",
                path=request.url.path,
                method=request.method,
                latency_ms=round(dt, 2),
            )
        response.headers["x-request-id"] = req_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket-lite: per-IP sliding-window (global, all endpoints)."""

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


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Stricter sliding-window limiter for auth / account-recovery endpoints.

    Brute-force resistance without DoS-ing legitimate users:
    - Per-IP aggregate cap across the whole auth surface (spray resistance).
    - Per-IP+endpoint cap on each login surface.
    Account-level (per-email) throttling lives in the login handlers via
    app.security.login_throttle, so this middleware never has to read and
    re-inject the request body (fragile under BaseHTTPMiddleware).
    """

    # endpoint path-prefix -> (limit, window_seconds)
    RULES: tuple[tuple[str, int, int], ...] = (
        ("/api/v1/auth/login", 10, 60),
        ("/api/v1/auth/institution/login", 10, 60),
        ("/api/v1/auth/institution/forgot-password", 5, 300),
        ("/api/v1/auth/institution/reset-password", 5, 300),
        ("/api/v1/auth/institution/invitation", 10, 60),
        ("/api/v1/auth/institution/accept-invitation", 10, 60),
        ("/api/v1/investigator/login", 10, 60),
        ("/api/v1/admin/merchant/login", 10, 60),
    )
    IP_AGGREGATE_LIMIT = 40
    IP_AGGREGATE_WINDOW = 60

    def __init__(self, app):
        super().__init__(app)
        self._by_ip: dict[str, deque] = defaultdict(deque)
        self._by_ip_ep: dict[tuple[str, str], deque] = defaultdict(deque)

    @staticmethod
    def _prune(bucket: deque, window: float, now: float) -> None:
        while bucket and now - bucket[0] > window:
            bucket.popleft()

    def _match(self, path: str):
        for prefix, limit, window in self.RULES:
            if path.startswith(prefix):
                return prefix, limit, window
        return None

    async def dispatch(self, request, call_next):
        rule = self._match(request.url.path)
        if rule is None or request.method.upper() != "POST":
            return await call_next(request)
        ip = request.client.host if request.client else "anon"
        now = time.time()

        agg = self._by_ip[ip]
        self._prune(agg, self.IP_AGGREGATE_WINDOW, now)
        if len(agg) >= self.IP_AGGREGATE_LIMIT:
            return JSONResponse({"error": "auth_rate_limited", "scope": "ip"}, status_code=429)
        agg.append(now)

        prefix, limit, window = rule
        bucket = self._by_ip_ep[(ip, prefix)]
        self._prune(bucket, window, now)
        if len(bucket) >= limit:
            return JSONResponse(
                {"error": "auth_rate_limited", "scope": "endpoint"}, status_code=429
            )
        bucket.append(now)

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers on every response."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-XSS-Protection", "0")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        # HSTS only when the request arrived over HTTPS (behind a TLS-terminating
        # reverse proxy). Never sent on plain-HTTP dev traffic.
        if request.headers.get("x-forwarded-proto", "").lower() == "https" or (
            request.url.scheme == "https"
        ):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response
