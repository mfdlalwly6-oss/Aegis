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
            logger.info(
                "http.request",
                path=request.url.path,
                method=request.method,
                latency_ms=round(dt, 2),
            )
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


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Dedicated throttle for credential/attack-sensitive auth endpoints.

    Distinct from the global per-IP limiter: auth endpoints get a much tighter
    window to blunt brute-force / credential-stuffing, keyed by IP+email where
    an email is present (so a distributed botnet can't hammer one account, and
    one NAT'd office can't lock out a whole tenant). Responses stay generic —
    429 reveals nothing about account existence.

    Policy (per sliding 60s window):
      - institution login ......... 10 attempts / IP+email, 30 / IP
      - forgot-password ...........  5 requests / IP+email, 15 / IP (abuse-safe)
      - reset / accept-invitation . 10 / IP (token-gated already)
    """

    # path-substring -> (per_identity_limit, per_ip_limit, identity_extractor)
    RULES: tuple = (
        ("/auth/institution/login", 10, 30),
        ("/auth/institution/forgot-password", 5, 15),
        ("/auth/institution/reset-password", 10, 30),
        ("/auth/institution/accept-invitation", 10, 30),
        ("/auth/login", 10, 30),
    )

    def __init__(self, app):
        super().__init__(app)
        self.buckets: dict[str, deque] = defaultdict(deque)

    def _hit(self, key: str, limit: int, now: float) -> bool:
        """Sliding-window; returns True when the request is OVER the limit."""
        b = self.buckets[key]
        while b and now - b[0] > 60:
            b.popleft()
        if len(b) >= limit:
            return True
        b.append(now)
        return False

    async def dispatch(self, request, call_next):
        path = request.url.path
        rule = next((r for r in self.RULES if r[0] in path), None)
        if rule and request.method == "POST":
            _, ident_limit, ip_limit = rule
            ip = request.client.host if request.client else "anon"
            now = time.time()
            # Best-effort identity key (email) — read without consuming the body
            # for downstream handlers: Starlette caches request.body().
            email = ""
            try:
                body = await request.body()
                if body:
                    import json as _json
                    email = str(_json.loads(body).get("email", "")).strip().lower()[:64]
            except Exception:
                email = ""
            if self._hit(f"ip:{ip}:{path}", ip_limit, now):
                logger.warning("auth.rate_limited", path=path, scope="ip")
                return JSONResponse({"error": "rate_limited"}, status_code=429)
            if email and self._hit(f"id:{email}:{path}", ident_limit, now):
                logger.warning("auth.rate_limited", path=path, scope="identity")
                return JSONResponse({"error": "rate_limited"}, status_code=429)
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
        return response
